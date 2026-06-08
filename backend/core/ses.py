import boto3
from core.config import AWS_REGION
import logging

_logger = logging.getLogger("ses-sender.ses")

ses_client = boto3.client("ses", region_name=AWS_REGION)
sesv2_client = boto3.client("sesv2", region_name=AWS_REGION)

# 获取 SES 账户发送配额
def get_send_quota() -> dict:
    """获取当前 SES 账户的发送配额信息"""
    try:
        quota = ses_client.get_send_quota()
        info = {
            "max_send_rate": quota.get("MaxSendRate", 1),
            "max_24_hour_send": quota.get("Max24HourSend", 200),
            "sent_last_24_hours": quota.get("SentLast24Hours", 0),
        }
        _logger.info(f"[SES Quota] MaxSendRate={info['max_send_rate']}/s, "
                      f"24h Limit={info['max_24_hour_send']}, "
                      f"24h Sent={info['sent_last_24_hours']}")
        return info
    except Exception as e:
        _logger.warning(f"[SES Quota] 获取配额失败: {e}，使用默认值 max_send_rate=1")
        return {"max_send_rate": 1, "max_24_hour_send": 200, "sent_last_24_hours": 0}

# 启动时获取一次
_quota = get_send_quota()
SES_MAX_SEND_RATE = _quota["max_send_rate"]
