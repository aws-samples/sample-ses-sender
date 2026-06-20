import os
from dotenv import load_dotenv

load_dotenv()

# JWT
SECRET_KEY = os.getenv("SECRET_KEY", "ses-sender-secret-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24

# Database
# 优先使用拆分的 DB_* 变量（云原生部署：密码经 Secrets Manager 注入，避免明文 DATABASE_URL）。
# 未设置 DB_HOST 时回退到完整的 DATABASE_URL（本地 docker-compose 兼容）。
_DB_HOST = os.getenv("DB_HOST")
if _DB_HOST:
    _DB_USER = os.getenv("DB_USER", "ses_sender")
    _DB_PASSWORD = os.getenv("DB_PASSWORD", "")
    _DB_PORT = os.getenv("DB_PORT", "3306")
    _DB_NAME = os.getenv("DB_NAME", "ses_sender")
    DATABASE_URL = f"mysql+pymysql://{_DB_USER}:{_DB_PASSWORD}@{_DB_HOST}:{_DB_PORT}/{_DB_NAME}"
else:
    DATABASE_URL = os.getenv("DATABASE_URL", "mysql+pymysql://ses_sender:ses_sender_123@localhost:3306/ses_sender")

# AWS
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

# SES Configuration Set (用于 VDM 追踪送达率/打开率)
# 需要在 AWS SES 控制台创建 Configuration Set 并启用 VDM
SES_CONFIGURATION_SET = os.getenv("SES_CONFIGURATION_SET", "")

# SQS Queue URL（用于接收 SES 事件通知，替代 Webhook）
# 架构：SES → SNS → SQS → 后端轮询
SQS_QUEUE_URL = os.getenv("SQS_QUEUE_URL", "")

# 退订链接的基础 URL（公网可访问的后端地址）
UNSUBSCRIBE_BASE_URL = os.getenv("UNSUBSCRIBE_BASE_URL", "")

# AWS Bedrock（AI 邮件优化）
BEDROCK_MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "global.anthropic.claude-opus-4-6-v1")
BEDROCK_REGION = os.getenv("BEDROCK_REGION", os.getenv("AWS_REGION", "us-east-1"))

# Sender Engine（单 Writer 模式）
ENABLE_SENDER = os.getenv("ENABLE_SENDER", "true").lower() in ("true", "1", "yes")
SENDER_CONCURRENCY = int(os.getenv("SENDER_CONCURRENCY", "2"))
SENDER_MESSAGE_RATE = int(os.getenv("SENDER_MESSAGE_RATE", "0"))  # 0=auto from SES MaxSendRate
SENDER_SLIDING_WINDOW_SECONDS = int(os.getenv("SENDER_SLIDING_WINDOW_SECONDS", "0"))
SENDER_SLIDING_WINDOW_RATE = int(os.getenv("SENDER_SLIDING_WINDOW_RATE", "0"))

# ===== SQS 发送队列 + Redis 令牌桶模式（大批量 / 多实例水平扩展）=====
# 设置 SEND_QUEUE_URL 即启用 SQS 发送模式（替代内存队列引擎）。
SEND_QUEUE_URL = os.getenv("SEND_QUEUE_URL", "")
# Producer：分页认领 detail 并投递到 SQS（仅单实例开启，避免重复投递）
ENABLE_PRODUCER = os.getenv("ENABLE_PRODUCER", "true").lower() in ("true", "1", "yes")
# Consumer：消费 SQS 发送（所有实例都可开启，水平扩展吞吐）
ENABLE_CONSUMER = os.getenv("ENABLE_CONSUMER", "true").lower() in ("true", "1", "yes")
# 每实例 Consumer 线程数
SEND_CONSUMER_THREADS = int(os.getenv("SEND_CONSUMER_THREADS", "4"))

# Redis 全局令牌桶（限流）。设置 REDIS_URL 即启用全局精确限流，否则降级为本地限流。
REDIS_URL = os.getenv("REDIS_URL", "")
# 全局每秒发送令牌数（0=auto，取 SES MaxSendRate）
GLOBAL_SEND_RATE = int(os.getenv("GLOBAL_SEND_RATE", "0"))
