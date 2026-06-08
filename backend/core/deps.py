"""公共依赖：认证、权限检查"""

from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from jose import JWTError, jwt

from core.config import SECRET_KEY, ALGORITHM
from core.database import get_db
from domain.auth.models import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")


def _decode_token(token: str) -> str:
    """解码 JWT token，返回 username"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if not username:
            raise HTTPException(status_code=401, detail="无效的认证信息")
        return username
    except JWTError:
        raise HTTPException(status_code=401, detail="无效的认证信息")


def _get_active_user(username: str, db: Session) -> User:
    """根据 username 查询活跃用户"""
    user = db.query(User).filter(User.username == username).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="用户不存在或已禁用")
    return user


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    """从 Authorization header 获取当前用户"""
    username = _decode_token(token)
    return _get_active_user(username, db)


def get_user_from_query_token(token: str, db: Session) -> User:
    """从 query parameter 获取当前用户（用于文件下载等场景）"""
    username = _decode_token(token)
    return _get_active_user(username, db)


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """要求管理员权限"""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return current_user
