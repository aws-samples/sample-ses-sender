from typing import List
from fastapi import APIRouter, Depends, HTTPException

from core.deps import require_admin
from domain.auth.models import User
from domain.identity.schemas import IdentityOut
from domain.identity import service

router = APIRouter(prefix="/admin/identities", tags=["发送实体管理"])


@router.get("/reputation")
def get_reputation(admin: User = Depends(require_admin)):
    try:
        return service.get_account_reputation()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("", response_model=List[IdentityOut])
def list_identities(admin: User = Depends(require_admin)):
    try:
        return service.list_identities()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/verify-email")
def verify_email(email: str, admin: User = Depends(require_admin)):
    try:
        return service.verify_email(email)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/verify-domain")
def verify_domain(domain: str, admin: User = Depends(require_admin)):
    try:
        return service.verify_domain(domain)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
