from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from passlib.context import CryptContext
from jose import jwt

from core.config import SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_HOURS
from domain.auth.models import User
from domain.auth.schemas import UserCreate, UserUpdate

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    to_encode["exp"] = datetime.utcnow() + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def authenticate_user(db: Session, username: str, password: str) -> User | None:
    user = db.query(User).filter(User.username == username).first()
    if not user or not verify_password(password, user.hashed_password):
        return None
    return user


def create_user(db: Session, data: UserCreate) -> User:
    user = User(
        username=data.username,
        display_name=data.display_name,
        hashed_password=hash_password(data.password),
        email=data.email,
        contact_email=data.contact_email or data.email,
        is_admin=data.is_admin,
        is_active=True,
        daily_send_limit=data.daily_send_limit,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def update_user(db: Session, user: User, data: UserUpdate) -> User:
    if data.display_name is not None:
        user.display_name = data.display_name
    if data.email is not None:
        user.email = data.email
    if data.contact_email is not None:
        user.contact_email = data.contact_email
    if data.password is not None:
        user.hashed_password = hash_password(data.password)
    if data.is_active is not None:
        user.is_active = data.is_active
    if data.daily_send_limit is not None:
        user.daily_send_limit = data.daily_send_limit
    db.commit()
    db.refresh(user)
    return user


def init_default_admin(db: Session):
    """创建默认管理员账号"""
    admin = db.query(User).filter(User.username == "admin").first()
    if not admin:
        admin = User(
            username="admin",
            display_name="管理员",
            hashed_password=hash_password("admin123"),
            email="",
            is_admin=True,
            is_active=True,
        )
        db.add(admin)
        db.commit()
        print("Default admin created: admin / admin123")
