#auth.py
"""
認證相關依賴注入
"""
from typing import Optional
from fastapi import Request, Depends, HTTPException
from sqlmodel import Session

from ..db import get_session
from ..models import User

def get_current_user(
    request: Request, 
    session: Session = Depends(get_session)
) -> Optional[User]:
    """取得當前登入使用者（可選）"""
    user_id = request.session.get("user_id")
    return session.get(User, user_id) if user_id else None

def require_auth(
    request: Request,
    session: Session = Depends(get_session)
) -> User:
    """確保使用者已登入（必需）"""
    user = get_current_user(request, session)
    if not user:
        raise HTTPException(status_code=401, detail="請先登入")
    return user

def get_optional_user(
    request: Request,
    session: Session = Depends(get_session)
) -> Optional[User]:
    """獲取可選的當前使用者（不會拋出異常）"""
    return get_current_user(request, session)