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


# ============================================================
# 模块级共享函数（内存队列引擎 与 SQS 消费者 共用）
# ============================================================

def replace_vars(template: str, task: SendTask) -> str:
    """替换模板变量：{{name}} {{email}} {{unsubscribe_url}} + 自定义属性。"""
    if not template:
        return ""
    result = template.replace("{{name}}", task.name).replace("{{email}}", task.recipient)
    result = result.replace("{{unsubscribe_url}}", task.unsub_url or "#")
    for k, v in task.attributes.items():
        result = result.replace("{{" + k + "}}", str(v))
    return result


def extract_error(err_str: str) -> str:
    """精简 SES 错误信息为 [Code] Message。"""
    m = re.match(r'An error occurred \(([^)]+)\) when calling the \w+ operation: (.+)', err_str)
    if m:
        return f"[{m.group(1)}] {m.group(2)}"
    return err_str[:200]


def update_detail_status(task: SendTask, status: str, error: str = "", message_id: str = ""):
    """更新 sending_job_details 状态（优先按 detail_id 精确更新，回退按邮箱）。"""
    try:
        from core.database import SessionLocal
        from domain.sending.models import SendingJobDetail, SendingJob
        db = SessionLocal()
        try:
            if task.detail_id:
                details = db.query(SendingJobDetail).filter(
                    SendingJobDetail.id == task.detail_id,
                    SendingJobDetail.send_status.in_(("Pending", "Queued")),
                ).all()
            else:
                details = db.query(SendingJobDetail).filter(
                    SendingJobDetail.batch_id == task.batch_id,
                    SendingJobDetail.recipient == task.recipient,
                    SendingJobDetail.send_status.in_(("Pending", "Queued")),
                ).all()
            updated_count = 0
            for detail in details:
                detail.send_status = status
                if error:
                    detail.send_error = error
                if message_id:
                    detail.message_id = message_id
                updated_count += 1
            if updated_count:
                job = db.query(SendingJob).filter(SendingJob.batch_id == task.batch_id).first()
                if job:
                    job.sent_count = (job.sent_count or 0) + updated_count
            db.commit()
            return updated_count
        finally:
            db.close()
    except Exception as e:
        logger.error(f"[Engine] 更新状态失败: {e}")
        return 0


def send_task(task: SendTask, rate_limiter=None, log_prefix: str = "Sender") -> str:
    """发送单封邮件的共享主体。返回 'success' / 'skipped' / 'failed'。

    rate_limiter: 可选，发送前 acquire 一个全局令牌（多实例限流）。
    """
    from core.ses import sesv2_client
    from core import blacklist as _bl
    from core.database import SessionLocal
    from domain.sending.models import SendingJobDetail

    # 黑名单检查
    if _bl.is_blacklisted(task.recipient):
        logger.info(f"[{log_prefix}] 跳过黑名单邮箱: {task.recipient}")
        update_detail_status(task, "Failed", "[Blacklisted] 邮箱在黑名单中")
        return "failed"

    # 幂等检查：detail 已非待发送状态则跳过
    _cdb = SessionLocal()
    try:
        if task.detail_id:
            _d = _cdb.query(SendingJobDetail).filter(SendingJobDetail.id == task.detail_id).first()
        else:
            _d = _cdb.query(SendingJobDetail).filter(
                SendingJobDetail.batch_id == task.batch_id,
                SendingJobDetail.recipient == task.recipient,
            ).order_by(SendingJobDetail.id.asc()).first()
        if _d and _d.send_status not in ("Pending", "Queued"):
            logger.debug(f"[{log_prefix}] 跳过已处理: {task.recipient} status={_d.send_status}")
            return "skipped"
    finally:
        _cdb.close()

    # 全局令牌桶限流
    if rate_limiter is not None:
        rate_limiter.acquire(1)

    try:
        subject = replace_vars(task.subject_tpl, task)
        html_body = replace_vars(task.html_tpl, task)

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
        update_detail_status(task, "Success", "", message_id)
        return "success"

    except Exception as e:
        err_str = str(e)
        short_err = extract_error(err_str)
        logger.warning(f"[{log_prefix}] 发送失败 {task.recipient}: {short_err}")
        update_detail_status(task, "Failed", short_err)
        if "Throttling" in err_str or "Rate exceeded" in err_str:
            time.sleep(2)  # nosemgrep: arbitrary-sleep
        return "failed"


def build_send_task(detail, job, tpl, tpl_attachments, reply_to, contact_info) -> SendTask:
    """根据 detail + job + 模板 + 联系人信息构建 SendTask（内存引擎与 SQS 消费者共用）。

    contact_info: (name, attributes_json) 或 None。
    """
    from core.config import SES_CONFIGURATION_SET, UNSUBSCRIBE_BASE_URL
    from core.unsubscribe import generate_unsubscribe_token

    unsub_url = ""
    if UNSUBSCRIBE_BASE_URL:
        token = generate_unsubscribe_token(detail.recipient, job.source_email)
        unsub_url = f"{UNSUBSCRIBE_BASE_URL}/unsubscribe?token={token}"

    attrs = {}
    cname = "Customer"
    if contact_info:
        cname = contact_info[0] or "Customer"
        if contact_info[1]:
            try:
                attrs = json.loads(contact_info[1])
            except Exception:
                pass

    return SendTask(
        job_id=job.id,
        batch_id=job.batch_id,
        recipient=detail.recipient,
        name=cname,
        source_email=job.source_email,
        reply_to=reply_to,
        subject_tpl=(tpl.subject if tpl else job.template_name),
        html_tpl=(tpl.html_body if tpl else ""),
        text_tpl="",
        attributes=attrs,
        config_set=SES_CONFIGURATION_SET or "",
        tags={"batch_id": job.batch_id, "user_id": str(job.user_id)},
        unsub_url=unsub_url,
        attachments=tpl_attachments or [],
        detail_id=detail.id,
    )


def load_job_send_context(db, job):
    """加载 job 的发送上下文：模板、附件、reply_to、group_id。每批只查一次。"""
    from domain.template.models import EmailTemplate, TemplateAttachment
    from domain.audience.models import ContactGroup
    from domain.auth.models import User as UserModel

    tpl = None
    if job.template_id:
        tpl = db.query(EmailTemplate).filter(EmailTemplate.id == job.template_id).first()
    if not tpl:
        tpl = db.query(EmailTemplate).filter(
            EmailTemplate.user_id == job.user_id,
            EmailTemplate.name == job.template_name,
        ).first()

    tpl_attachments = []
    if tpl:
        for a in db.query(TemplateAttachment).filter(TemplateAttachment.template_id == tpl.id).all():
            tpl_attachments.append({"file_name": a.file_name, "file_path": a.file_path, "content_type": a.content_type})

    job_user = db.query(UserModel).filter(UserModel.id == job.user_id).first()
    reply_to = (job_user.contact_email if job_user and job_user.contact_email else job.source_email) or job.source_email

    job_group_id = job.group_id
    if not job_group_id:
        jg = db.query(ContactGroup).filter(
            ContactGroup.user_id == job.user_id,
            ContactGroup.name == job.group_name,
        ).first()
        job_group_id = jg.id if jg else None

    return tpl, tpl_attachments, reply_to, job_group_id


def load_contact_map(db, recipients, group_id):
    """一次性查出一批 recipient 的 contact 映射 email->(name, attributes)，消除 N+1。"""
    from domain.audience.models import Contact
    contact_map = {}
    if not recipients:
        return contact_map
    cq = db.query(Contact.email, Contact.name, Contact.attributes).filter(Contact.email.in_(recipients))
    if group_id:
        cq = cq.filter(Contact.group_id == group_id)
    for email, name, attributes in cq:
        if email not in contact_map:
            contact_map[email] = (name, attributes)
    return contact_map


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
        # 队列容量：至少能容纳一页(500)入队量，并随并发/速率放大，避免 Scanner 频繁阻塞。
        qsize = max(concurrency * self.message_rate * 4, 1000)
        self.queue: queue.Queue[Optional[SendTask]] = queue.Queue(maxsize=qsize)
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
        # 阻塞入队：队列满则等待 worker 消费，形成天然背压，不丢任务。
        # 在 running 期间循环等待，避免无限阻塞导致 stop 卡住。
        while True:
            try:
                self.queue.put(task, timeout=5)
                return
            except queue.Full:
                if not self.running:
                    return

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
        return extract_error(err_str)

    def _send_one(self, task: SendTask, worker_id: int):
        """发送单封邮件（委托模块级 send_task，复用同一发送主体）。"""
        result = send_task(task, rate_limiter=None, log_prefix=f"Worker-{worker_id}")
        with self._stats_lock:
            if result == "success":
                self._total_sent += 1
            elif result == "failed":
                self._total_errors += 1

    def _replace_vars(self, template: str, task: SendTask) -> str:
        return replace_vars(template, task)

    def _update_detail_status(self, task: SendTask, status: str, error: str = "", message_id: str = ""):
        return update_detail_status(task, status, error, message_id)

    def _scan_loop(self):
        """扫描数据库中 queued 状态的任务并加载到队列"""
        logger.info("[Scanner] 启动，每 5 秒扫描一次")
        while self.running:
            try:
                self._process_queued_jobs()
            except Exception as e:
                logger.error(f"[Scanner] 异常: {e}")
            time.sleep(5)  # nosemgrep: arbitrary-sleep

    def _enqueue_pending_details(self, db, job, limit: int = 500) -> tuple[bool, int]:
        """将 job 中 Pending 状态的 detail 分批构建为 SendTask 并入队。

        每次最多处理 limit 条（分页，避免一次性 load 百万行进内存）。
        返回 (是否还有更多待处理, 本次入队数量)。
        队列满时通过阻塞 enqueue 自然背压。
        """
        from domain.sending.models import SendingJobDetail
        from domain.audience.models import Contact, ContactGroup
        from domain.template.models import EmailTemplate, TemplateAttachment
        from core.config import SES_CONFIGURATION_SET, UNSUBSCRIBE_BASE_URL
        from core.unsubscribe import generate_unsubscribe_token

        # 分页拾取本轮要处理的 Pending detail（按 id 升序，稳定）
        page = (
            db.query(SendingJobDetail.id)
            .filter(
                SendingJobDetail.batch_id == job.batch_id,
                SendingJobDetail.send_status == "Pending",
            )
            .order_by(SendingJobDetail.id.asc())
            .limit(limit)
            .all()
        )
        page_ids = [r[0] for r in page]
        if not page_ids:
            return (False, 0)

        # 原子认领：把这批 Pending 标记为 Queued，避免下一轮 Scanner 重复入队
        db.query(SendingJobDetail).filter(
            SendingJobDetail.id.in_(page_ids),
            SendingJobDetail.send_status == "Pending",
        ).update({"send_status": "Queued"}, synchronize_session=False)
        db.commit()

        details = (
            db.query(SendingJobDetail)
            .filter(SendingJobDetail.id.in_(page_ids))
            .all()
        )
        if not details:
            return (False, 0)

        # 模板（每批只查一次）
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

        # 模板附件（每批只查一次）
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

        # 消除 N+1：本批所有 recipient 一次性查出 contact 映射
        recipients = [d.recipient for d in details]
        contact_map: dict = {}
        if recipients:
            cq = db.query(Contact.email, Contact.name, Contact.attributes).filter(
                Contact.email.in_(recipients)
            )
            if job_group_id:
                cq = cq.filter(Contact.group_id == job_group_id)
            for email, name, attributes in cq:
                if email not in contact_map:
                    contact_map[email] = (name, attributes)

        enqueued = 0
        for detail in details:
            unsub_url = ""
            if UNSUBSCRIBE_BASE_URL:
                token = generate_unsubscribe_token(detail.recipient, job.source_email)
                unsub_url = f"{UNSUBSCRIBE_BASE_URL}/unsubscribe?token={token}"

            attrs = {}
            cname = "Customer"
            cinfo = contact_map.get(detail.recipient)
            if cinfo:
                cname = cinfo[0] or "Customer"
                if cinfo[1]:
                    try:
                        attrs = json.loads(cinfo[1])
                    except Exception:
                        pass

            task = SendTask(
                job_id=job.id,
                batch_id=job.batch_id,
                recipient=detail.recipient,
                name=cname,
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
            # 阻塞入队（队列满则等待，形成天然背压；不丢任务）
            self.enqueue(task)
            enqueued += 1

        # 本批已满 limit，可能还有更多
        return (len(page_ids) >= limit, enqueued)

    def _process_queued_jobs(self):
        from core.database import SessionLocal
        from domain.sending.models import SendingJob, SendingJobDetail
        from core.config import SES_CONFIGURATION_SET
        from datetime import datetime

        db = SessionLocal()
        try:
            # ---- 处理 sending 中的任务：修复 + 继续分页入队 + 完成判定 ----
            stuck = db.query(SendingJob).filter(SendingJob.status == "sending").all()
            for job in stuck:
                # send_status 仍为 Pending/Queued 但 delivery_status 已有值的，说明实际已发出
                stale = db.query(SendingJobDetail).filter(
                    SendingJobDetail.batch_id == job.batch_id,
                    SendingJobDetail.send_status.in_(("Pending", "Queued")),
                    SendingJobDetail.delivery_status != None,
                ).all()
                for d in stale:
                    d.send_status = "Success"
                if stale:
                    db.commit()

                # 还未入队的 Pending 数量
                pending = db.query(SendingJobDetail).filter(
                    SendingJobDetail.batch_id == job.batch_id,
                    SendingJobDetail.send_status == "Pending",
                ).count()
                # 已入队但 worker 尚未处理完的 Queued 数量
                queued = db.query(SendingJobDetail).filter(
                    SendingJobDetail.batch_id == job.batch_id,
                    SendingJobDetail.send_status == "Queued",
                ).count()

                if pending > 0:
                    # 继续把下一页 Pending 入队（队列满会阻塞，自然背压）
                    has_more, n = self._enqueue_pending_details(db, job)
                    if n:
                        logger.info(f"[Scanner] batch={job.batch_id} 本轮入队 {n} 封（剩余待入队约 {pending - n}）")
                elif queued == 0:
                    # 既无待入队也无在途，批次完成，结算状态
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
                    if total > 0 and failed == total:
                        job.status = "failed"
                    elif failed > 0:
                        job.status = "partial"
                        job.error_message = f"{failed} 封发送失败"
                    else:
                        job.status = "success"
                    db.commit()
                    logger.info(f"[Scanner] 任务完成 {job.batch_id} → {job.status}")
                # else: queued>0，等 worker 处理完，下一轮再判定

            # ---- 拾取 queued 的新任务 ----
            jobs = db.query(SendingJob).filter(SendingJob.status == "queued").limit(5).all()
            for job in jobs:
                # 原子抢占：只有把 status 从 queued 改为 sending 成功（影响行数=1）的实例才处理该 job
                claimed = db.query(SendingJob).filter(
                    SendingJob.id == job.id,
                    SendingJob.status == "queued",
                ).update({"status": "sending"}, synchronize_session=False)
                db.commit()
                if claimed == 0:
                    continue
                db.refresh(job)

                pending_count = db.query(SendingJobDetail).filter(
                    SendingJobDetail.batch_id == job.batch_id,
                    SendingJobDetail.send_status == "Pending",
                ).count()
                if pending_count == 0:
                    job.status = "success"
                    job.finished_at = datetime.utcnow()
                    db.commit()
                    continue

                # 入队首页（后续页由上面的 sending 分支逐轮继续入队）
                has_more, n = self._enqueue_pending_details(db, job)
                logger.info(f"[Scanner] batch={job.batch_id} 开始处理：共 {pending_count} 待发，本轮入队 {n}, template={job.template_name}, config_set={SES_CONFIGURATION_SET or '(无)'}")
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
