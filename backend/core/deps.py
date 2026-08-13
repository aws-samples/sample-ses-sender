"""公共依赖：JWT / API Key 认证与权限检查。"""

import hashlib
import json
from datetime import datetime
from typing import Optional, Set

from fastapi import Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from core.config import ALGORITHM, SECRET_KEY
from core.database import get_db
from domain.auth.models import ApiKey, User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login", auto_error=False)


API_KEY_SCOPES = {
    "profile:read",
    "profile:write",
    "audience:read",
    "audience:write",
    "templates:read",
    "templates:write",
    "ai:use",
    "sending:read",
    "sending:write",
    "scheduled:read",
    "scheduled:write",
    "unsubscribe:read",
    "unsubscribe:write",
    "admin:read",
    "admin:write",
}


def _decode_token(token: str) -> str:
    """解码 JWT token，返回 username。"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if not username:
            raise HTTPException(status_code=401, detail="无效的认证信息")
        return username
    except JWTError:
        raise HTTPException(status_code=401, detail="无效的认证信息")


def _get_active_user(username: str, db: Session) -> User:
    user = db.query(User).filter(User.username == username).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="用户不存在或已禁用")
    return user


def _required_scope(request: Request) -> str:
    """把现有 API 路由映射到稳定的业务 scope。"""
    path = request.url.path
    write = request.method not in {"GET", "HEAD", "OPTIONS"}

    if path.startswith("/admin/"):
        return f"admin:{'write' if write else 'read'}"
    if path.startswith(("/groups", "/contacts")):
        return f"audience:{'write' if write else 'read'}"
    if path.startswith(("/user/templates", "/admin/templates", "/upload/image")):
        return f"templates:{'write' if write else 'read'}"
    if path.startswith("/ai/") or path == "/ai-models/available":
        return "ai:use"
    if path.startswith("/scheduled-jobs"):
        return f"scheduled:{'write' if write else 'read'}"
    if path.startswith("/unsubscribe-list"):
        return f"unsubscribe:{'write' if write else 'read'}"
    if path.startswith(("/send-bulk", "/admin/test-email")):
        return "sending:write"
    if path.startswith(("/sending-jobs", "/email-details", "/ses-quota", "/user/daily-quota", "/user/dashboard")):
        return "sending:read"
    return f"profile:{'write' if write else 'read'}"


def _authenticate_api_key(token: str, request: Request, db: Session) -> User:
    key_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    api_key = db.query(ApiKey).filter(ApiKey.key_hash == key_hash).first()
    now = datetime.utcnow()
    if not api_key or api_key.revoked_at or (api_key.expires_at and api_key.expires_at <= now):
        raise HTTPException(status_code=401, detail="API Key 无效、已撤销或已过期")
    if not api_key.user or not api_key.user.is_active:
        raise HTTPException(status_code=401, detail="用户不存在或已禁用")

    scopes: Set[str] = set(json.loads(api_key.scopes or "[]"))
    required = _required_scope(request)
    if "*" not in scopes and required not in scopes:
        raise HTTPException(status_code=403, detail=f"API Key 缺少 scope: {required}")

    api_key.last_used_at = now
    db.commit()
    return api_key.user


def get_current_user(
    request: Request,
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Authorization Bearer 同时支持网页 JWT 和 ses_ 前缀的用户 API Key。"""
    if not token:
        raise HTTPException(status_code=401, detail="缺少认证信息", headers={"WWW-Authenticate": "Bearer"})
    if token.startswith("ses_"):
        return _authenticate_api_key(token, request, db)
    return _get_active_user(_decode_token(token), db)


def get_current_jwt_user(
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """仅接受网页登录 JWT，用于 API Key 的签发与撤销。"""
    if not token or token.startswith("ses_"):
        raise HTTPException(status_code=401, detail="该操作需要网页登录")
    return _get_active_user(_decode_token(token), db)


def get_user_from_query_token(token: str, db: Session) -> User:
    """文件下载继续只接受短期 JWT，避免 API Key 出现在 URL 和访问日志中。"""
    if token.startswith("ses_"):
        raise HTTPException(status_code=401, detail="文件下载链接不接受 API Key")
    return _get_active_user(_decode_token(token), db)


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return current_user
