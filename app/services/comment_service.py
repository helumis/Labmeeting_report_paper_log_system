#comment_service.py
"""
評論服務
負責評論的 CRUD 操作
"""
from fastapi import HTTPException
from sqlmodel import Session

from ..models import Comment, Report
from ..utils.validators import safe_str

class CommentService:
    """評論服務類"""
    
    def __init__(self, session: Session):
        self.session = session
    
    def create_comment(
        self, 
        report_id: int, 
        content: str, 
        user_id: int
    ) -> Comment:
        """創建評論"""
        content = safe_str(content)
        if not content:
            raise HTTPException(status_code=400, detail="評論內容不能為空")
        
        # 驗證報告是否存在
        report = self.session.get(Report, report_id)
        if not report:
            raise HTTPException(status_code=404, detail="報告不存在")
        
        comment = Comment(
            report_id=report_id,
            user_id=user_id,
            content=content
        )
        
        self.session.add(comment)
        self.session.commit()
        self.session.refresh(comment)
        
        return comment
    
    def delete_comment(self, comment_id: int, user_id: int) -> int:
        """刪除評論"""
        comment = self.session.get(Comment, comment_id)
        
        if not comment:
            raise HTTPException(status_code=404, detail="評論不存在")
        
        if comment.user_id != user_id:
            raise HTTPException(status_code=403, detail="權限不足")
        
        report_id = comment.report_id
        self.session.delete(comment)
        self.session.commit()
        
        return report_id