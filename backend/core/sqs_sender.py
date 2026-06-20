"""
SQS 发送队列引擎（方案 B：SQS 队列 + Redis 全局令牌桶）。

- Producer（单实例）：分页认领 detail（Pending→Queued），批量投递 detail_id 到 SQS 发送队列；
  并负责批次完成判定（Pending=0 且 Queued=0 → 结算 job 状态）。
- Consumer（多实例）：长轮询 SQS，按 detail_id 回查并通过 send_task 发送，受 Redis 令牌桶全局限流。

消息体只放 {detail_id, batch_id}，保持轻量（远低于 SQS 256KB 限制）；模板/附件/联系人在消费端按需回查。
"""

import json
import time
import threading
import logging

import boto3

from core.config import (
    AWS_REGION, SEND_QUEUE_URL, GLOBAL_SEND_RATE, REDIS_URL,
    SEND_CONSUMER_THREADS,
)
from core.database import SessionLocal
from core import sender as _sender
from core.rate_limiter import GlobalRateLimiter

logger = logging.getLogger("ses-sender.sqs-sender")

PAGE = 500           # Producer 每轮认领的 detail 页大小
BATCH = 10           # SQS SendMessageBatch / ReceiveMessage 上限


class SqsSendEngine:
    def __init__(self, enable_producer: bool, enable_consumer: bool,
                 consumer_threads: int = SEND_CONSUMER_THREADS):
        self.enable_producer = enable_producer
        self.enable_consumer = enable_consumer
        self.consumer_threads = max(consumer_threads, 1)
        self.running = False
        self.sqs = boto3.client("sqs", region_name=AWS_REGION)

        from core.ses import SES_MAX_SEND_RATE
        rate = GLOBAL_SEND_RATE or int(SES_MAX_SEND_RATE or 1)
        self.rate_limiter = GlobalRateLimiter(rate=rate, redis_url=REDIS_URL)

        self._threads: list[threading.Thread] = []

    def start(self):
        if self.running:
            return
        self.running = True
        if self.enable_producer:
            t = threading.Thread(target=self._producer_loop, daemon=True, name="sqs-producer")
            t.start()
            self._threads.append(t)
            logger.info("[SQS Producer] 已启动")
        if self.enable_consumer:
            for i in range(self.consumer_threads):
                t = threading.Thread(target=self._consumer_loop, args=(i,), daemon=True, name=f"sqs-consumer-{i}")
                t.start()
                self._threads.append(t)
            logger.info(f"[SQS Consumer] 已启动 {self.consumer_threads} 个消费线程")

    def stop(self):
        self.running = False

    # ---------------- Producer ----------------

    def _producer_loop(self):
        logger.info("[SQS Producer] 循环启动，每 5 秒扫描一次")
        while self.running:
            try:
                self._produce_once()
            except Exception as e:
                logger.error(f"[SQS Producer] 异常: {e}")
            time.sleep(5)  # nosemgrep: arbitrary-sleep

    def _produce_once(self):
        from domain.sending.models import SendingJob, SendingJobDetail
        from datetime import datetime

        db = SessionLocal()
        try:
            # 1) sending 中的任务：继续投递剩余 Pending；完成判定
            for job in db.query(SendingJob).filter(SendingJob.status == "sending").all():
                # delivery_status 已有值但仍 Pending/Queued 的，修正为 Success
                stale = db.query(SendingJobDetail).filter(
                    SendingJobDetail.batch_id == job.batch_id,
                    SendingJobDetail.send_status.in_(("Pending", "Queued")),
                    SendingJobDetail.delivery_status != None,
                ).all()
                for d in stale:
                    d.send_status = "Success"
                if stale:
                    db.commit()

                pending = db.query(SendingJobDetail).filter(
                    SendingJobDetail.batch_id == job.batch_id,
                    SendingJobDetail.send_status == "Pending",
                ).count()
                queued = db.query(SendingJobDetail).filter(
                    SendingJobDetail.batch_id == job.batch_id,
                    SendingJobDetail.send_status == "Queued",
                ).count()

                if pending > 0:
                    n = self._claim_and_publish(db, job)
                    if n:
                        logger.info(f"[SQS Producer] batch={job.batch_id} 投递 {n} 条到 SQS")
                elif queued == 0:
                    self._finalize(db, job)

            # 2) queued 新任务：原子抢占 → sending → 投递首页
            for job in db.query(SendingJob).filter(SendingJob.status == "queued").limit(5).all():
                claimed = db.query(SendingJob).filter(
                    SendingJob.id == job.id, SendingJob.status == "queued",
                ).update({"status": "sending"}, synchronize_session=False)
                db.commit()
                if claimed == 0:
                    continue
                db.refresh(job)
                pending = db.query(SendingJobDetail).filter(
                    SendingJobDetail.batch_id == job.batch_id,
                    SendingJobDetail.send_status == "Pending",
                ).count()
                if pending == 0:
                    job.status = "success"
                    job.finished_at = datetime.utcnow()
                    db.commit()
                    continue
                n = self._claim_and_publish(db, job)
                logger.info(f"[SQS Producer] batch={job.batch_id} 开始：{pending} 待发，本轮投递 {n}")
        finally:
            db.close()

    def _claim_and_publish(self, db, job) -> int:
        """认领一页 Pending（→Queued）并投递 detail_id 到 SQS。返回投递数。"""
        from domain.sending.models import SendingJobDetail

        page = (
            db.query(SendingJobDetail.id)
            .filter(SendingJobDetail.batch_id == job.batch_id,
                    SendingJobDetail.send_status == "Pending")
            .order_by(SendingJobDetail.id.asc())
            .limit(PAGE)
            .all()
        )
        ids = [r[0] for r in page]
        if not ids:
            return 0
        db.query(SendingJobDetail).filter(
            SendingJobDetail.id.in_(ids),
            SendingJobDetail.send_status == "Pending",
        ).update({"send_status": "Queued"}, synchronize_session=False)
        db.commit()

        # 分批投递到 SQS（每批 10）
        published = 0
        for i in range(0, len(ids), BATCH):
            chunk = ids[i:i + BATCH]
            entries = [
                {"Id": str(did), "MessageBody": json.dumps({"detail_id": did, "batch_id": job.batch_id})}
                for did in chunk
            ]
            try:
                self.sqs.send_message_batch(QueueUrl=SEND_QUEUE_URL, Entries=entries)
                published += len(chunk)
            except Exception as e:
                logger.error(f"[SQS Producer] 投递失败 batch={job.batch_id}: {e}")
                # 投递失败的回滚为 Pending，下轮重试
                db.query(SendingJobDetail).filter(
                    SendingJobDetail.id.in_(chunk),
                    SendingJobDetail.send_status == "Queued",
                ).update({"send_status": "Pending"}, synchronize_session=False)
                db.commit()
        return published

    def _finalize(self, db, job):
        from domain.sending.models import SendingJobDetail
        from datetime import datetime
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
        logger.info(f"[SQS Producer] 任务完成 {job.batch_id} → {job.status}")

    # ---------------- Consumer ----------------

    def _consumer_loop(self, worker_id: int):
        from domain.sending.models import SendingJob, SendingJobDetail

        while self.running:
            try:
                resp = self.sqs.receive_message(
                    QueueUrl=SEND_QUEUE_URL,
                    MaxNumberOfMessages=BATCH,
                    WaitTimeSeconds=20,
                )
                messages = resp.get("Messages", [])
                if not messages:
                    continue

                # 批量回查本批 detail_id 的 job 上下文（按 batch 缓存）
                db = SessionLocal()
                try:
                    job_ctx_cache: dict = {}
                    for msg in messages:
                        try:
                            body = json.loads(msg["Body"])
                            detail_id = body["detail_id"]
                            detail = db.query(SendingJobDetail).filter(SendingJobDetail.id == detail_id).first()
                            if not detail or detail.send_status not in ("Pending", "Queued"):
                                # 已处理或不存在 → 删除消息
                                self.sqs.delete_message(QueueUrl=SEND_QUEUE_URL, ReceiptHandle=msg["ReceiptHandle"])
                                continue

                            bid = detail.batch_id
                            if bid not in job_ctx_cache:
                                job = db.query(SendingJob).filter(SendingJob.batch_id == bid).first()
                                if not job:
                                    self.sqs.delete_message(QueueUrl=SEND_QUEUE_URL, ReceiptHandle=msg["ReceiptHandle"])
                                    continue
                                tpl, atts, reply_to, gid = _sender.load_job_send_context(db, job)
                                job_ctx_cache[bid] = (job, tpl, atts, reply_to, gid)
                            job, tpl, atts, reply_to, gid = job_ctx_cache[bid]

                            cmap = _sender.load_contact_map(db, [detail.recipient], gid)
                            task = _sender.build_send_task(
                                detail, job, tpl, atts, reply_to, cmap.get(detail.recipient)
                            )
                            # 受全局令牌桶限流的发送
                            _sender.send_task(task, rate_limiter=self.rate_limiter, log_prefix=f"SQS-Consumer-{worker_id}")
                            self.sqs.delete_message(QueueUrl=SEND_QUEUE_URL, ReceiptHandle=msg["ReceiptHandle"])
                        except Exception as e:
                            logger.error(f"[SQS Consumer-{worker_id}] 处理消息失败: {e}")
                            # 不删除 → 可见性超时后重投，超 maxReceiveCount 进 DLQ
                finally:
                    db.close()
            except Exception as e:
                logger.error(f"[SQS Consumer-{worker_id}] 轮询异常: {e}")
                time.sleep(3)  # nosemgrep: arbitrary-sleep


_sqs_engine = None


def start_sqs_engine(enable_producer: bool, enable_consumer: bool, consumer_threads: int = SEND_CONSUMER_THREADS):
    global _sqs_engine
    if _sqs_engine and _sqs_engine.running:
        return _sqs_engine
    _sqs_engine = SqsSendEngine(enable_producer, enable_consumer, consumer_threads)
    _sqs_engine.start()
    return _sqs_engine
