#user_service.py
"""
使用者服務
負責使用者認證和管理
"""
from fastapi import HTTPException
from sqlmodel import Session, select

from ..models import User
from ..security import get_password_hash, verify_password
from ..utils.validators import safe_str

class UserService:
    """使用者服務類"""
    
    def __init__(self, session: Session):
        self.session = session
    
    def register(
        self, 
        username: str, 
        password: str, 
        display_name: str = None
    ) -> User:
        """註冊新使用者"""
        username = safe_str(username)
        password = safe_str(password)
        
        if not username or len(username) < 3:
            raise HTTPException(
                status_code=400, 
                detail="使用者名稱至少需要 3 個字元"
            )
        
        if not password or len(password) < 6:
            raise HTTPException(
                status_code=400, 
                detail="密碼至少需要 6 個字元"
            )
        
        # 檢查帳號是否存在
        exists = self.session.exec(
            select(User).where(User.username == username)
        ).first()
        
        if exists:
            raise HTTPException(status_code=400, detail="使用者名稱已存在")
        
        # 創建使用者
        hashed_pwd = get_password_hash(password)
        display_name = safe_str(display_name) or username
        
        user = User(
            username=username,
            display_name=display_name,
            hashed_password=hashed_pwd
        )
        
        self.session.add(user)
        self.session.commit()
        self.session.refresh(user)
        
        return user
    
    def authenticate(self, username: str, password: str) -> User:
        """驗證使用者"""
        username = safe_str(username)
        password = safe_str(password)
        
        if not username or not password:
            raise HTTPException(
                status_code=400, 
                detail="請輸入使用者名稱和密碼"
            )
        
        user = self.session.exec(
            select(User).where(User.username == username)
        ).first()
        
        if not user or not verify_password(password, user.hashed_password):
            raise HTTPException(
                status_code=401, 
                detail="使用者名稱或密碼錯誤"
            )
        
        return user