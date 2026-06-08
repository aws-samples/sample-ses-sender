import boto3
from typing import List
from datetime import datetime, timedelta
from core.ses import ses_client
from core.config import AWS_REGION
from domain.identity.schemas import IdentityOut


def list_identities() -> List[IdentityOut]:
    response = ses_client.list_identities()
    identities = response.get("Identities", [])
    if not identities:
        return []

    status_response = ses_client.get_identity_verification_attributes(Identities=identities)
    sesv2 = boto3.client("sesv2", region_name=AWS_REGION)

    result = []
    for identity in identities:
        status = status_response["VerificationAttributes"].get(identity, {}).get("VerificationStatus", "Unknown")
        type_str = "Domain" if "." in identity and "@" not in identity else "EmailAddress"

        # 获取 DKIM 等详细信息
        dkim_status = "N/A"
        dkim_signing = False
        try:
            detail = sesv2.get_email_identity(EmailIdentity=identity)
            dkim_status = detail.get("DkimAttributes", {}).get("Status", "N/A")
            dkim_signing = detail.get("DkimAttributes", {}).get("SigningEnabled", False)
        except Exception:
            pass

        result.append(IdentityOut(
            identity=identity,
            type=type_str,
            verification_status=status,
            dkim_status=dkim_status,
            dkim_signing=dkim_signing,
        ))
    return result


def get_account_reputation() -> dict:
    """获取账户信誉和发送配额"""
    sesv2 = boto3.client("sesv2", region_name=AWS_REGION)
    cw = boto3.client("cloudwatch", region_name=AWS_REGION)

    # 账户信息
    account = sesv2.get_account()
    quota = account.get("SendQuota", {})

    # 信誉指标
    now = datetime.utcnow()
    start = now - timedelta(days=7)

    def get_metric(name):
        try:
            r = cw.get_metric_statistics(
                Namespace="AWS/SES", MetricName=name,
                StartTime=start, EndTime=now,
                Period=86400 * 7, Statistics=["Average"],
            )
            dps = r.get("Datapoints", [])
            return round(dps[0]["Average"] * 100, 2) if dps else 0
        except Exception:
            return 0

    return {
        "sending_enabled": account.get("SendingEnabled", False),
        "production_access": account.get("ProductionAccessEnabled", False),
        "enforcement_status": account.get("EnforcementStatus", "UNKNOWN"),
        "max_24h_send": quota.get("Max24HourSend", 0),
        "max_send_rate": quota.get("MaxSendRate", 0),
        "sent_last_24h": quota.get("SentLast24Hours", 0),
        "bounce_rate": get_metric("Reputation.BounceRate"),
        "complaint_rate": get_metric("Reputation.ComplaintRate"),
    }


def verify_email(email: str) -> dict:
    ses_client.verify_email_identity(EmailAddress=email)
    return {"message": f"验证邮件已发送到 {email}"}


def verify_domain(domain: str) -> dict:
    response = ses_client.verify_domain_identity(Domain=domain)
    return {"message": "请添加 TXT 记录", "token": response.get("VerificationToken")}
