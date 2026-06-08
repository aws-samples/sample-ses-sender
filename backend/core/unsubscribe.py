"""退订 token 的生成和验证（HMAC 签名）"""
import hmac
import hashlib
import base64
from core.config import SECRET_KEY


def generate_unsubscribe_token(email: str, source_email: str) -> str:
    """生成退订 token: base64url(email|source_email|hmac_sig)"""
    payload = f"{email}|{source_email}"
    sig = hmac.new(SECRET_KEY.encode(), payload.encode(), hashlib.sha256).hexdigest()[:16]
    raw = f"{payload}|{sig}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def verify_unsubscribe_token(token: str) -> tuple[str, str] | None:
    """验证退订 token，成功返回 (email, source_email)，失败返回 None"""
    try:
        raw = base64.urlsafe_b64decode(token.encode()).decode()
        parts = raw.split("|")
        if len(parts) != 3:
            return None
        email, source_email, sig = parts
        expected_sig = hmac.new(SECRET_KEY.encode(), f"{email}|{source_email}".encode(), hashlib.sha256).hexdigest()[:16]
        if not hmac.compare_digest(sig, expected_sig):
            return None
        return (email, source_email)
    except Exception:
        return None
