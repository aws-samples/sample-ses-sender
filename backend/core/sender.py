"""
Sender Engine — 参考 Listmonk 的 Worker Pool + Rate Limiting 设计

架构:
  DB(queued jobs) → Scanner Thread → Message Queue → Worker Pool → SES

限速:
  - Concurrency: Worker 数量（并发发送协程数）
  - MessageRate: 每个 Worker 每秒最大发送数
  - 全局速率 = Concurrency × MessageRate
  - 滑动窗口: 可选的全局总量限制（N 秒内最多 M 封）

单 Writer:
  - 通过 ENABLE_SENDER=true 控制，只有一个实例启动 Engine
  - 其他实例只负责 API，发送任务写入 DB 由 sender 实例处理
"""

import threading
import queue
import time
import logging
import json
import re
import os
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("ses-sender.engine")


@dataclass
class SendTask:
    """单封邮件发送任务"""
    job_id: int
    batch_id: str
    recipient: str
    name: str
    source_email: str
    reply_to: str = ""
    subject_tpl: str = ""
    html_tpl: str = ""
    text_tpl: str = ""
    attributes: dict = field(default_factory=dict)
    config_set: str = ""
    tags: dict = field(default_factory=dict)
    unsub_url: str = ""
    attachments: list = field(default_factory=list)
    detail_id: int = 0


class SlidingWindow:
    """滑动窗口限流器"""

    def __init__(self, window_seconds: int, max_count: int):
        self.window = window_seconds
        self.max_count = max_count
        self._count = 0
        self._start = time.monotonic()
        self._lock = threading.Lock()

    def acquire(self) -> bool:
        with self._lock:
            now = time.monotonic()
            if now - self._start >= self.window:
                self._count = 0
                self._start = now
            if self._count < self.max_count:
                self._count += 1
                return True
            return False

    def wait_and_acquire(self, timeout: float = 60.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.acquire():
                return True
            time.sleep(0.05)  # nosemgrep: arbitrary-sleep
        return False


class SenderEngine:
    """
    邮件发送引擎

    参考 Listmonk 的设计:
    - 固定数量的 Worker 线程从共享队列消费
    - 每个 Worker 有独立的 MessageRate 限速
    - 所有任务（不论哪个用户发起）共享同一个 Worker Pool
    - 全局速率 = concurrency × message_rate
    """

    def __init__(self, concurrency: int = 2, message_rate: int = 10,
                 sliding_window_seconds: int = 0, sliding_window_rate: int = 0):
        self.concurrency = max(concurrency, 1)
        self.message_rate = max(message_rate, 1)
        self.queue: queue.Queue[Optional[SendTask]] = queue.Queue(maxsize=concurrency * message_rate * 4)
        self.running = False
        self._workers: list[threading.Thread] = []
        self._scanner: Optional[threading.Thread] = None

        self.sliding_window: Optional[SlidingWindow] = None
        if sliding_window_seconds > 0 and sliding_window_rate > 0:
            self.sliding_window = SlidingWindow(sliding_window_seconds, sliding_window_rate)

        self._stats_lock = threading.Lock()
        self._total_sent = 0
        self._total_errors = 0

    @property
    def effective_rate(self) -> int:
        return self.concurrency * self.message_rate

    def start(self):
        if self.running:
            return
        self.running = True
        logger.info(f"[Sender Engine] 启动: concurrency={self.concurrency}, "
                     f"message_rate={self.message_rate}/worker/s, "
                     f"全局速率≈{self.effective_rate}/s"
                     f"{f', 滑动窗口={self.sliding_window.window}s/{self.sliding_window.max_count}' if self.sliding_window else ''}")

        for i in range(self.concurrency):
            t = threading.Thread(target=self._worker, args=(i,), daemon=True, name=f"sender-worker-{i}")
            t.start()
            self._workers.append(t)

        self._scanner = threading.Thread(target=self._scan_loop, daemon=True, name="sender-scanner")
        self._scanner.start()

    def stop(self):
        self.running = False
        for _ in self._workers:
            self.queue.put(None)
        for t in self._workers:
            t.join(timeout=5)
        self._workers.clear()
        logger.info(f"[Sender Engine] 已停止. 总发送={self._total_sent}, 总错误={self._total_errors}")

    def enqueue(self, task: SendTask):
        self.queue.put(task, timeout=30)

    def _worker(self, worker_id: int):
        """Worker 线程：从队列取任务，限速发送"""
        logger.info(f"[Worker-{worker_id}] 启动")
        num_msg = 0
        last_reset = time.monotonic()

        while self.running:
            try:
                task = self.queue.get(timeout=2)
            except queue.Empty:
                continue

            if task is None:
                break

            if self.sliding_window and not self.sliding_window.wait_and_acquire(timeout=30):
                logger.warning(f"[Worker-{worker_id}] 滑动窗口限流超时，跳过")
                self._update_detail_status(task, "Failed", "Rate limit timeout")
                continue

            now = time.monotonic()
            if now - last_reset >= 1.0:
                num_msg = 0
                last_reset = now
            elif num_msg >= self.message_rate:
                sleep_time = 1.0 - (now - last_reset)
                if sleep_time > 0:
                    time.sleep(sleep_time)  # nosemgrep: arbitrary-sleep
                num_msg = 0
                last_reset = time.monotonic()

            num_msg += 1
            self._send_one(task, worker_id)

        logger.info(f"[Worker-{worker_id}] 已退出")

    @staticmethod
    def _extract_error(err_str: str) -> str:
        m = re.match(r'An error occurred \(([^)]+)\) when calling the \w+ operation: (.+)', err_str)
        if m:
            return f"[{m.group(1)}] {m.group(2)}"
        return err_str[:200]

    def _send_one(self, task: SendTask, worker_id: int):
        """发送单封邮件"""
        from core.ses import sesv2_client
        from core.config import SES_CONFIGURATION_SET, UNSUBSCRIBE_BASE_URL
        from core import blacklist as _bl

        # 黑名单检查（内存 Set 查询，O(1)）
        if _bl.is_blacklisted(task.recipient):
            logger.info(f"[Worker-{worker_id}] 跳过黑名单邮箱: {task.recipient}")
            self._update_detail_status(task, "Failed", "[Blacklisted] 邮箱在黑名单中")
            with self._stats_lock:
                self._total_errors += 1
            return

        try:
            # 发送前检查 detail 是否仍为 Pending，防止重复发送
            from core.database import SessionLocal as _CheckSession
            from domain.sending.models import SendingJobDetail as _CheckDetail
            _cdb = _CheckSession()
            try:
                if task.detail_id:
                    _d = _cdb.query(_CheckDetail).filter(_CheckDetail.id == task.detail_id).first()
                else:
                    _d = _cdb.query(_CheckDetail).filter(
                        _CheckDetail.batch_id == task.batch_id,
                        _CheckDetail.recipient == task.recipient,
                        _CheckDetail.send_status == "Pending",
                    ).first()
                if _d and _d.send_status != "Pending":
                    logger.debug(f"[Worker-{worker_id}] 跳过已处理: {task.recipient} status={_d.send_status}")
                    return
            finally:
                _cdb.close()

            subject = self._replace_vars(task.subject_tpl, task)
            html_body = self._replace_vars(task.html_tpl, task)

            email_params = {
                "FromEmailAddress": task.source_email,
                "Destination": {"ToAddresses": [task.recipient]},
                "ReplyToAddresses": [task.reply_to or task.source_email],
                "Content": {
                    "Simple": {
                        "Subject": {"Data": subject, "Charset": "UTF-8"},
                        "Body": {"Html": {"Data": html_body, "Charset": "UTF-8"}},
                    }
                },
            }

            if task.config_set:
                email_params["ConfigurationSetName"] = task.config_set
            if task.tags:
                email_params["EmailTags"] = [{"Name": k, "Value": v} for k, v in task.tags.items()]

            headers = []
            if task.unsub_url:
                headers.append({"Name": "List-Unsubscribe", "Value": f"<{task.unsub_url}>"})
                headers.append({"Name": "List-Unsubscribe-Post", "Value": "List-Unsubscribe=One-Click"})
            if headers:
                email_params["Content"]["Simple"]["Headers"] = headers

            if task.attachments:
                att_list = []
                for att in task.attachments:
                    file_path = att["file_path"]
                    if os.path.exists(file_path):
                        with open(file_path, "rb") as fp:
                            att_list.append({
                                "RawContent": fp.read(),
                                "FileName": att["file_name"],
                                "ContentType": att["content_type"],
                                "ContentDisposition": "ATTACHMENT",
                                "ContentTransferEncoding": "BASE64",
                            })
                if att_list:
                    email_params["Content"]["Simple"]["Attachments"] = att_list

            response = sesv2_client.send_email(**email_params)
            message_id = response.get("MessageId", "")

            self._update_detail_status(task, "Success", "", message_id)

            with self._stats_lock:
                self._total_sent += 1

        except Exception as e:
            err_str = str(e)
            short_err = self._extract_error(err_str)
            logger.warning(f"[Worker-{worker_id}] 发送失败 {task.recipient}: {short_err}")
            self._update_detail_status(task, "Failed", short_err)

            with self._stats_lock:
                self._total_errors += 1

            if "Throttling" in err_str or "Rate exceeded" in err_str:
                time.sleep(2)  # nosemgrep: arbitrary-sleep

    def _replace_vars(self, template: str, task: SendTask) -> str:
        if not template:
            return ""
        result = template.replace("{{name}}", task.name).replace("{{email}}", task.recipient)
        if task.unsub_url:
            result = result.replace("{{unsubscribe_url}}", task.unsub_url)
        else:
            result = result.replace("{{unsubscribe_url}}", "#")
        for k, v in task.attributes.items():
            result = result.replace("{{" + k + "}}", str(v))
        return result

    def _update_detail_status(self, task: SendTask, status: str, error: str = "", message_id: str = ""):
        """更新 sending_job_details 表（同一 batch 中相同邮箱的所有记录一起更新）"""
        try:
            from core.database import SessionLocal
            from domain.sending.models import SendingJobDetail, SendingJob
            db = SessionLocal()
            try:
                # 更新同一 batch 中该邮箱的所有 detail 记录
                details = db.query(SendingJobDetail).filter(
                    SendingJobDetail.batch_id == task.batch_id,
                    SendingJobDetail.recipient == task.recipient,
                    SendingJobDetail.send_status == "Pending",
                ).all()
                updated_count = 0
                for detail in details:
                    detail.send_status = status
                    if error:
                        detail.send_error = error
                    if message_id:
                        detail.message_id = message_id
                    updated_count += 1

                job = db.query(SendingJob).filter(SendingJob.batch_id == task.batch_id).first()
                if job:
                    job.sent_count = (job.sent_count or 0) + updated_count

                db.commit()
            finally:
                db.close()
        except Exception as e:
            logger.error(f"[Engine] 更新状态失败: {e}")

    def _scan_loop(self):
        """扫描数据库中 queued 状态的任务并加载到队列"""
        logger.info("[Scanner] 启动，每 5 秒扫描一次")
        while self.running:
            try:
                self._process_queued_jobs()
            except Exception as e:
                logger.error(f"[Scanner] 异常: {e}")
            time.sleep(5)  # nosemgrep: arbitrary-sleep

    def _enqueue_pending_details(self, db, job) -> bool:
        """将 job 中 Pending 状态的 detail 构建为 SendTask 并入队。成功返回 True，队列满返回 False。"""
        from domain.sending.models import SendingJobDetail
        from domain.audience.models import Contact, ContactGroup
        from domain.template.models import EmailTemplate, TemplateAttachment
        from core.config import SES_CONFIGURATION_SET, UNSUBSCRIBE_BASE_URL
        from core.unsubscribe import generate_unsubscribe_token

        details = db.query(SendingJobDetail).filter(
            SendingJobDetail.batch_id == job.batch_id,
            SendingJobDetail.send_status == "Pending",
        ).all()

        tpl = None
        if job.template_id:
            tpl = db.query(EmailTemplate).filter(EmailTemplate.id == job.template_id).first()
        if not tpl:
            tpl = db.query(EmailTemplate).filter(
                EmailTemplate.user_id == job.user_id,
                EmailTemplate.name == job.template_name,
            ).first()
        subject_tpl = tpl.subject if tpl else job.template_name
        html_tpl = tpl.html_body if tpl else ""

        # 加载模板附件
        tpl_attachments = []
        if tpl:
            att_rows = db.query(TemplateAttachment).filter(TemplateAttachment.template_id == tpl.id).all()
            for a in att_rows:
                tpl_attachments.append({"file_name": a.file_name, "file_path": a.file_path, "content_type": a.content_type})

        from domain.auth.models import User as UserModel
        job_user = db.query(UserModel).filter(UserModel.id == job.user_id).first()
        reply_to = (job_user.contact_email if job_user and job_user.contact_email else job.source_email) or job.source_email

        job_group_id = job.group_id
        if not job_group_id:
            job_group = db.query(ContactGroup).filter(
                ContactGroup.user_id == job.user_id,
                ContactGroup.name == job.group_name,
            ).first()
            job_group_id = job_group.id if job_group else None

        for detail in details:
            if detail.send_status == "Unsubscribed":
                continue

            unsub_url = ""
            if UNSUBSCRIBE_BASE_URL:
                token = generate_unsubscribe_token(detail.recipient, job.source_email)
                unsub_url = f"{UNSUBSCRIBE_BASE_URL}/unsubscribe?token={token}"

            attrs = {}
            contact = None
            if job_group_id:
                contact = db.query(Contact).filter(Contact.email == detail.recipient, Contact.group_id == job_group_id).first()
            if not contact:
                contact = db.query(Contact).filter(Contact.email == detail.recipient).first()
            if contact and contact.attributes:
                try:
                    attrs = json.loads(contact.attributes)
                except Exception:
                    pass

            task = SendTask(
                job_id=job.id,
                batch_id=job.batch_id,
                recipient=detail.recipient,
                name=contact.name if contact else "Customer",
                source_email=job.source_email,
                reply_to=reply_to,
                subject_tpl=subject_tpl,
                html_tpl=html_tpl,
                text_tpl="",
                attributes=attrs,
                config_set=SES_CONFIGURATION_SET or "",
                tags={
                    "batch_id": job.batch_id,
                    "user_id": str(job.user_id),
                },
                unsub_url=unsub_url,
                attachments=tpl_attachments,
                detail_id=detail.id,
            )
            try:
                self.enqueue(task)
            except Exception:
                logger.warning(f"[Scanner] 队列满，稍后重试 batch={job.batch_id}")
                return False

        return True

    def _process_queued_jobs(self):
        from core.database import SessionLocal
        from domain.sending.models import SendingJob, SendingJobDetail
        from core.config import SES_CONFIGURATION_SET
        from datetime import datetime

        db = SessionLocal()
        try:
            # 修复卡住的 sending 任务（所有 detail 已处理完但状态未更新）
            stuck = db.query(SendingJob).filter(SendingJob.status == "sending").all()
            for job in stuck:
                # send_status 仍为 Pending 但 delivery_status 已有值的，说明实际已发出
                stale_pending = db.query(SendingJobDetail).filter(
                    SendingJobDetail.batch_id == job.batch_id,
                    SendingJobDetail.send_status == "Pending",
                    SendingJobDetail.delivery_status != None,
                ).all()
                for d in stale_pending:
                    d.send_status = "Success"
                if stale_pending:
                    db.commit()

                # 真正未处理的：send_status=Pending 且无 delivery_status
                pending = db.query(SendingJobDetail).filter(
                    SendingJobDetail.batch_id == job.batch_id,
                    SendingJobDetail.send_status == "Pending",
                    SendingJobDetail.delivery_status == None,
                ).count()

                if pending == 0:
                    failed = db.query(SendingJobDetail).filter(
                        SendingJobDetail.batch_id == job.batch_id,
                        SendingJobDetail.send_status == "Failed",
                    ).count()
                    total = db.query(SendingJobDetail).filter(
                        SendingJobDetail.batch_id == job.batch_id,
                        SendingJobDetail.send_status != "Unsubscribed",
                    ).count()
                    job.sent_count = total
                    job.finished_at = datetime.utcnow()
                    if failed == total:
                        job.status = "failed"
                    elif failed > 0:
                        job.status = "partial"
                        job.error_message = f"{failed} 封发送失败"
                    else:
                        job.status = "success"
                    db.commit()
                    logger.info(f"[Scanner] 任务完成 {job.batch_id} → {job.status}")

            jobs = db.query(SendingJob).filter(SendingJob.status == "queued").limit(5).all()
            for job in jobs:
                job.status = "sending"
                db.commit()

                pending_count = db.query(SendingJobDetail).filter(
                    SendingJobDetail.batch_id == job.batch_id,
                    SendingJobDetail.send_status == "Pending",
                ).count()

                if pending_count == 0:
                    job.status = "success"
                    job.finished_at = datetime.utcnow()
                    db.commit()
                    continue

                if not self._enqueue_pending_details(db, job):
                    logger.warning(f"[Scanner] 队列满，batch={job.batch_id} 保持 sending 状态等待下轮处理")
                    return

                logger.info(f"[Scanner] batch={job.batch_id} 已入队 {pending_count} 封, template={job.template_name}, group={job.group_name}, config_set={SES_CONFIGURATION_SET or '(无)'}")
        finally:
            db.close()


# 全局单例
_engine: Optional[SenderEngine] = None


def get_engine() -> Optional[SenderEngine]:
    return _engine


def start_engine(concurrency: int = 2, message_rate: int = 10,
                 sliding_window_seconds: int = 0, sliding_window_rate: int = 0):
    global _engine
    if _engine and _engine.running:
        return _engine

    from core.ses import SES_MAX_SEND_RATE
    if message_rate <= 0:
        message_rate = max(int(SES_MAX_SEND_RATE / max(concurrency, 1)), 1)

    _engine = SenderEngine(
        concurrency=concurrency,
        message_rate=message_rate,
        sliding_window_seconds=sliding_window_seconds,
        sliding_window_rate=sliding_window_rate,
    )
    _engine.start()
    return _engine
