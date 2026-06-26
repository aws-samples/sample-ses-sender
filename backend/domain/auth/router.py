from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from core.database import get_db
from core.deps import get_current_user, require_admin
from domain.auth.models import User
from domain.auth.schemas import LoginRequest, UserCreate, UserUpdate, UserOut
from domain.auth import service

router = APIRouter()


# ========== 验证码 ==========
@router.get("/auth/captcha")
def get_captcha():
    """生成图形验证码（SVG），答案存 Redis（TTL 120s）。"""
    from core import captcha
    return captcha.generate()


# ========== 登录 ==========
@router.post("/auth/login")
def login(req: LoginRequest, db: Session = Depends(get_db)):
    from core import captcha
    if not captcha.verify(req.captcha_id or "", req.captcha_code or ""):
        raise HTTPException(status_code=400, detail="验证码错误或已过期")
    user = service.authenticate_user(db, req.username, req.password)
    if not user:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="账户已被禁用")
    token = service.create_access_token({"sub": user.username})
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "username": user.username,
            "display_name": user.display_name,
            "email": user.email,
            "is_admin": user.is_admin,
            "daily_send_limit": user.daily_send_limit or 1000,
        },
    }


@router.get("/auth/me", response_model=UserOut)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user


# ========== 管理员：用户管理 ==========
@router.get("/admin/users", response_model=List[UserOut])
def list_users(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return db.query(User).all()


@router.post("/admin/users", response_model=UserOut)
def create_user(data: UserCreate, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.username == data.username).first()
    if existing:
        raise HTTPException(status_code=400, detail="用户名已存在")
    return service.create_user(db, data)


@router.put("/admin/users/{user_id}", response_model=UserOut)
def update_user(user_id: int, data: UserUpdate, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    return service.update_user(db, user, data)


# ========== 用户：退订页面自定义 ==========
@router.get("/user/unsub-config")
def get_unsub_config(current_user: User = Depends(get_current_user)):
    import json
    if current_user.unsub_config:
        try:
            return json.loads(current_user.unsub_config)
        except Exception:
            pass
    return {}


@router.put("/user/unsub-config")
def save_unsub_config(data: dict, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    import json
    from core import redis_cache
    current_user.unsub_config = json.dumps(data, ensure_ascii=False)
    db.commit()
    # 失效该发送邮箱的退订页缓存
    if current_user.email:
        redis_cache.delete("settings:unsub_page:" + current_user.email)
    return {"message": "退订页面配置已保存"}


@router.get("/user/unsub-defaults")
def get_unsub_defaults(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """获取管理员设置的退订页面默认值"""
    from domain.settings.service import get_unsub_page_config
    return get_unsub_page_config(db)


@router.put("/user/contact-email")
def update_contact_email(data: dict, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """用户自己修改收件邮箱"""
    contact_email = data.get("contact_email", "").strip()
    if not contact_email:
        raise HTTPException(status_code=400, detail="收件邮箱不能为空")
    current_user.contact_email = contact_email
    db.commit()
    return {"message": "收件邮箱已更新"}
