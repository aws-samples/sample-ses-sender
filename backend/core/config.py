import os
from dotenv import load_dotenv

load_dotenv()

# JWT
SECRET_KEY = os.getenv("SECRET_KEY", "ses-sender-secret-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24

# Database
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
