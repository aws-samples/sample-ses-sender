"""用户 API Key 的签发、查询和撤销。"""

import hashlib
import json
import secrets
from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from core.database import get_db
from core.deps import API_KEY_SCOPES, get_current_jwt_user
from domain.auth.models import ApiKey, User
from domain.auth.schemas import ApiKeyCreate, ApiKeyCreated, ApiKeyOut

router = APIRouter()


def _utc_naive(value: datetime) -> datetime:
    """MySQL DateTime 使用无时区 UTC，兼容带时区的 ISO 输入。"""
    if value.tzinfo is not None:
        return value.astimezone().replace(tzinfo=None)
    return value


def _out(item: ApiKey) -> dict:
    return {
        "id": item.id,
        "name": item.name,
        "key_prefix": item.key_prefix,
        "scopes": json.loads(item.scopes),
        "expires_at": item.expires_at,
        "last_used_at": item.last_used_at,
        "revoked_at": item.revoked_at,
        "created_at": item.created_at,
    }


@router.get("/user/api-keys", response_model=List[ApiKeyOut])
def list_api_keys(
    current_user: User = Depends(get_current_jwt_user),
    db: Session = Depends(get_db),
):
    items = db.query(ApiKey).filter(ApiKey.user_id == current_user.id).order_by(ApiKey.created_at.desc()).all()
    return [_out(item) for item in items]


@router.post("/user/api-keys", response_model=ApiKeyCreated)
def create_api_key(
    data: ApiKeyCreate,
    current_user: User = Depends(get_current_jwt_user),
    db: Session = Depends(get_db),
):
    name = data.name.strip()
    scopes = sorted(set(data.scopes))
    if not name:
        raise HTTPException(status_code=400, detail="API Key 名称不能为空")
    invalid = set(scopes) - API_KEY_SCOPES
    if invalid:
        raise HTTPException(status_code=400, detail=f"未知 scope: {', '.join(sorted(invalid))}")
    if not scopes:
        raise HTTPException(status_code=400, detail="至少选择一个 scope")
    if not current_user.is_admin and any(scope.startswith("admin:") for scope in scopes):
        raise HTTPException(status_code=403, detail="普通用户不能签发管理员 scope")
    expires_at = _utc_naive(data.expires_at) if data.expires_at else None
    if expires_at and expires_at <= datetime.utcnow():
        raise HTTPException(status_code=400, detail="过期时间必须晚于当前时间")

    plaintext = f"ses_live_{secrets.token_urlsafe(32)}"
    item = ApiKey(
        user_id=current_user.id,
        name=name,
        key_prefix=plaintext[:20],
        key_hash=hashlib.sha256(plaintext.encode("utf-8")).hexdigest(),
        scopes=json.dumps(scopes),
        expires_at=expires_at,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return {**_out(item), "api_key": plaintext}


@router.delete("/user/api-keys/{api_key_id}")
def revoke_api_key(
    api_key_id: int,
    current_user: User = Depends(get_current_jwt_user),
    db: Session = Depends(get_db),
):
    item = db.query(ApiKey).filter(ApiKey.id == api_key_id, ApiKey.user_id == current_user.id).first()
    if not item:
        raise HTTPException(status_code=404, detail="API Key 不存在")
    if not item.revoked_at:
        item.revoked_at = datetime.utcnow()
        db.commit()
    return {"message": "API Key 已撤销"}
