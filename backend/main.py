"""
SES Sender API - 应用入口

业务域划分:
  - auth      认证域: 用户登录、用户管理
  - identity  发送实体域: SES 邮箱/域名验证
  - template  邮件模版域: SES 模版 CRUD
  - audience  客群域: 客群管理、联系人管理、Excel 导入导出
  - sending   邮件发送域: 测试邮件、批量发送
"""

import sys
import os
import logging
import uuid
from fastapi import FastAPI, UploadFile, File, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from alembic.config import Config as AlembicConfig
from alembic import command as alembic_command
from alembic.script import ScriptDirectory
from alembic.runtime.migration import MigrationContext

from core.database import engine, SessionLocal
from domain.auth.service import init_default_admin

# 导入所有 models，确保 Alembic 能发现它们
from domain.auth import models as _auth_models        # noqa: F401
from domain.audience import models as _audience_models  # noqa: F401
from domain.template import models as _template_models  # noqa: F401
from domain.sending import models as _sending_models    # noqa: F401

# 导入各域路由
from domain.auth.router import router as auth_router
from domain.identity.router import router as identity_router
from domain.template.router import router as template_router
from domain.audience.router import router as audience_router
from domain.sending.router import router as sending_router
from domain.settings.router import router as settings_router
from domain.auth.sso import router as sso_router


# --- Alembic 迁移检查 & 自动升级 ---
def check_and_run_migrations():
    """启动时检查数据库迁移版本，若不是最新则自动执行 upgrade head"""
    alembic_cfg = AlembicConfig("alembic.ini")

    # 获取脚本目录中的最新版本
    script = ScriptDirectory.from_config(alembic_cfg)
    head_revision = script.get_current_head()

    # 获取数据库当前版本
    with engine.connect() as conn:
        migration_ctx = MigrationContext.configure(conn)
        current_revision = migration_ctx.get_current_revision()

    if current_revision == head_revision:
        print(f"[Alembic] 数据库版本已是最新: {current_revision}")
    else:
        print(f"[Alembic] 数据库版本: {current_revision} -> 目标版本: {head_revision}")
        print("[Alembic] 正在执行数据库迁移 (upgrade head)...")
        alembic_command.upgrade(alembic_cfg, "head")
        print("[Alembic] 迁移完成!")


try:
    check_and_run_migrations()
except Exception as e:
    print(f"[Alembic] 迁移检查失败: {e}")
    print("[Alembic] 请手动执行: alembic upgrade head")
    # 迁移失败不阻止服务启动，允许手动修复后继续运行

# --- 初始化默认管理员 ---
db = SessionLocal()
try:
    init_default_admin(db)
finally:
    db.close()

# --- FastAPI App ---
# --- 配置日志 ---
LOG_DIR = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "app.log")

from logging.handlers import RotatingFileHandler

_log_format = "%(asctime)s [%(name)s] %(levelname)s: %(message)s"
_file_handler = RotatingFileHandler(LOG_FILE, maxBytes=10*1024*1024, backupCount=5, encoding="utf-8")
_file_handler.setLevel(logging.DEBUG)
_file_handler.setFormatter(logging.Formatter(_log_format))

logging.basicConfig(
    level=logging.DEBUG,
    format=_log_format,
    handlers=[logging.StreamHandler(sys.stdout), _file_handler],
)
# 降低第三方库的日志级别，避免过多噪音
logging.getLogger("botocore").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("boto3").setLevel(logging.WARNING)

app = FastAPI(
    title="SES Sender API",
    description="前后端分离的 AWS SES 邮件发送管理平台",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 图片上传目录 & 静态文件服务 ---
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads", "images")
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "uploads")), name="uploads")

# --- 图片上传 API ---
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp", "image/svg+xml"}
MAX_IMAGE_SIZE = 5 * 1024 * 1024  # 5MB

from core.deps import get_current_user

@app.post("/upload/image")
async def upload_image(file: UploadFile = File(...), current_user=Depends(get_current_user)):
    """上传图片，支持本地存储和 S3"""
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=f"不支持的图片格式: {file.content_type}，支持 JPEG/PNG/GIF/WebP/SVG")

    contents = await file.read()
    if len(contents) > MAX_IMAGE_SIZE:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=f"图片大小不能超过 5MB，当前 {len(contents)/1024/1024:.1f}MB")

    ext = os.path.splitext(file.filename or "image.png")[1] or ".png"
    filename = f"{uuid.uuid4().hex[:16]}{ext}"

    from core.database import SessionLocal
    from domain.settings.service import get_image_storage_config
    db = SessionLocal()
    try:
        cfg = get_image_storage_config(db)
    finally:
        db.close()

    if cfg["mode"] == "s3" and cfg["s3_bucket"]:
        import boto3
        s3_kwargs = {"region_name": cfg["s3_region"]}
        if cfg["s3_access_key"] and cfg["s3_secret_key"]:
            s3_kwargs["aws_access_key_id"] = cfg["s3_access_key"]
            s3_kwargs["aws_secret_access_key"] = cfg["s3_secret_key"]
        s3 = boto3.client("s3", **s3_kwargs)
        s3_key = f"{cfg['s3_prefix']}{filename}"
        s3.put_object(Bucket=cfg["s3_bucket"], Key=s3_key, Body=contents, ContentType=file.content_type or "image/png")

        if cfg["base_url"]:
            url = f"{cfg['base_url'].rstrip('/')}/{s3_key}"
        else:
            url = f"https://{cfg['s3_bucket']}.s3.{cfg['s3_region']}.amazonaws.com/{s3_key}"
        return {"url": url, "filename": filename, "size": len(contents), "storage": "s3"}
    else:
        filepath = os.path.join(UPLOAD_DIR, filename)
        with open(filepath, "wb") as fp:
            fp.write(contents)
        base_url = cfg.get("base_url", "").rstrip("/")
        if base_url:
            url = f"{base_url}/uploads/images/{filename}"
        else:
            url = f"/uploads/images/{filename}"
        return {"url": url, "filename": filename, "size": len(contents), "storage": "local"}

# --- 注册各业务域路由 ---
app.include_router(auth_router)
app.include_router(identity_router)
app.include_router(template_router)
app.include_router(audience_router)
app.include_router(sending_router)
app.include_router(settings_router)
app.include_router(sso_router)


# --- 启动全局黑名单缓存 ---
from core import blacklist as _blacklist_cache
_blacklist_cache.start()


# --- SQS 后台轮询线程（替代 Webhook，主动拉取 SES 事件） ---
import threading
import json as _json
import time as _time
import boto3

from core.config import SQS_QUEUE_URL, AWS_REGION

_sqs_logger = logging.getLogger("ses-sender.sqs-worker")


def _sqs_polling_worker():
    """后台线程：持续轮询 SQS 队列，处理 SES 事件通知"""
    _sqs_logger.info(f"[SQS Worker] 启动，队列: {SQS_QUEUE_URL}")

    sqs_client = boto3.client("sqs", region_name=AWS_REGION)

    while True:
        try:
            resp = sqs_client.receive_message(
                QueueUrl=SQS_QUEUE_URL,
                MaxNumberOfMessages=10,       # 每次最多拉 10 条
                WaitTimeSeconds=20,            # 长轮询，最多等 20 秒
                MessageAttributeNames=["All"],
            )

            messages = resp.get("Messages", [])
            if not messages:
                continue

            _sqs_logger.info(f"[SQS Worker] 收到 {len(messages)} 条消息")

            for msg in messages:
                try:
                    body = _json.loads(msg["Body"])

                    # SNS 包装的消息：body 里有 "Type" 和 "Message"
                    if body.get("Type") == "Notification":
                        message_content = body.get("Message", "{}")
                        # SNS 确认/测试消息不是 JSON，直接跳过
                        try:
                            event_data = _json.loads(message_content)
                        except (_json.JSONDecodeError, TypeError):
                            _sqs_logger.debug(f"[SQS Worker] 跳过非 SES 事件消息: {str(message_content)[:100]}")
                            # 删除该消息，避免重复处理
                            sqs_client.delete_message(QueueUrl=SQS_QUEUE_URL, ReceiptHandle=msg["ReceiptHandle"])
                            continue
                    elif body.get("Type") == "SubscriptionConfirmation":
                        _sqs_logger.info("[SQS Worker] 跳过 SNS 订阅确认消息")
                        sqs_client.delete_message(QueueUrl=SQS_QUEUE_URL, ReceiptHandle=msg["ReceiptHandle"])
                        continue
                    else:
                        # 也可能是直接的 SES 事件（如果 SQS 是 SES 的直接目标）
                        event_data = body

                    # 用独立的 DB session 处理
                    from core.database import SessionLocal
                    from domain.sending.service import process_ses_event
                    bg_db = SessionLocal()
                    try:
                        process_ses_event(event_data, bg_db)
                    finally:
                        bg_db.close()

                    # 处理成功，删除消息
                    sqs_client.delete_message(
                        QueueUrl=SQS_QUEUE_URL,
                        ReceiptHandle=msg["ReceiptHandle"],
                    )
                except Exception as e:
                    _sqs_logger.error(f"[SQS Worker] 处理消息失败: {e}, body={msg.get('Body', '')[:200]}")

        except Exception as e:
            _sqs_logger.error(f"[SQS Worker] 轮询异常: {e}")
            _time.sleep(5)  # nosemgrep: arbitrary-sleep  出错后等 5 秒再重试


# 仅在配置了 SQS_QUEUE_URL 时启动轮询线程
if SQS_QUEUE_URL:
    _sqs_thread = threading.Thread(target=_sqs_polling_worker, daemon=True)
    _sqs_thread.start()
    _sqs_logger.info("[SQS Worker] 后台轮询线程已启动")
else:
    _sqs_logger.info("[SQS Worker] 未配置 SQS_QUEUE_URL，SQS 轮询未启动（将使用 Webhook 模式或不启用事件追踪）")


# --- 定时任务调度线程 ---
_scheduler_logger = logging.getLogger("ses-sender.scheduler")


def _scheduler_worker():
    """后台线程：每 30 秒检查一次到期的定时发送任务"""
    _scheduler_logger.info("[Scheduler] 定时任务调度线程已启动")
    while True:
        try:
            _time.sleep(30)  # nosemgrep: arbitrary-sleep
            from datetime import datetime
            from core.database import SessionLocal
            from domain.sending.models import ScheduledJob

            db = SessionLocal()
            try:
                now = datetime.utcnow()
                due_jobs = db.query(ScheduledJob).filter(
                    ScheduledJob.status == "active",
                    ScheduledJob.next_run_at <= now,
                ).all()

                for job in due_jobs:
                    _scheduler_logger.info(f"[Scheduler] 触发任务 #{job.id} ({job.schedule_type})")
                    try:
                        from domain.sending.service import execute_scheduled_job
                        execute_scheduled_job(job.id)
                    except Exception as e:
                        _scheduler_logger.error(f"[Scheduler] 执行任务 #{job.id} 失败: {e}")
            finally:
                db.close()

        except Exception as e:
            _scheduler_logger.error(f"[Scheduler] 调度循环异常: {e}")
            _time.sleep(10)  # nosemgrep: arbitrary-sleep


_scheduler_thread = threading.Thread(target=_scheduler_worker, daemon=True)
_scheduler_thread.start()


# --- 发送引擎 ---
# 模式选择：
#   设置 SEND_QUEUE_URL → SQS 发送队列模式（Producer + 多实例 Consumer + Redis 全局令牌桶，支持水平扩展）
#   否则 → 单实例内存队列引擎（ENABLE_SENDER）
from core.config import (
    ENABLE_SENDER, SENDER_CONCURRENCY, SENDER_MESSAGE_RATE,
    SENDER_SLIDING_WINDOW_SECONDS, SENDER_SLIDING_WINDOW_RATE,
    SEND_QUEUE_URL, ENABLE_PRODUCER, ENABLE_CONSUMER, SEND_CONSUMER_THREADS,
)

_engine_logger = logging.getLogger("ses-sender.engine")

if SEND_QUEUE_URL:
    from core.sqs_sender import start_sqs_engine
    _engine_logger.info(
        f"[Send] SQS 发送队列模式启动: producer={ENABLE_PRODUCER}, "
        f"consumer={ENABLE_CONSUMER}, threads={SEND_CONSUMER_THREADS}"
    )
    _sqs_send_engine = start_sqs_engine(
        enable_producer=ENABLE_PRODUCER,
        enable_consumer=ENABLE_CONSUMER,
        consumer_threads=SEND_CONSUMER_THREADS,
    )
elif ENABLE_SENDER:
    from core.sender import start_engine
    _sender_engine = start_engine(
        concurrency=SENDER_CONCURRENCY,
        message_rate=SENDER_MESSAGE_RATE,
        sliding_window_seconds=SENDER_SLIDING_WINDOW_SECONDS,
        sliding_window_rate=SENDER_SLIDING_WINDOW_RATE,
    )
else:
    _engine_logger.info("[Sender Engine] ENABLE_SENDER=false 且未配置 SEND_QUEUE_URL，当前实例不处理发送任务")


@app.get("/")
def root():
    return {"message": "SES Sender API is running"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
