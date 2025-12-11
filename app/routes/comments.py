#comments.py
"""
評論路由
"""
from fastapi import APIRouter, Request, Form, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlmodel import Session

from ..db import get_session
from ..services.comment_service import CommentService
from ..dependencies.auth import require_auth

router = APIRouter()

@router.post("/comments")
def create_comment(
    request: Request,
    report_id: int = Form(...),
    content: str = Form(...),
    session: Session = Depends(get_session),
    current_user = Depends(require_auth)
):
    """新增評論"""
    comment_service = CommentService(session)
    comment_service.create_comment(report_id, content, current_user.id)
    
    return RedirectResponse(url=f"/reports/{report_id}", status_code=303)

@router.post("/comments/{comment_id}/delete")
def delete_comment(
    request: Request,
    comment_id: int,
    session: Session = Depends(get_session),
    current_user = Depends(require_auth)
):
    """刪除評論"""
    comment_service = CommentService(session)
    report_id = comment_service.delete_comment(comment_id, current_user.id)
    
    return RedirectResponse(url=f"/reports/{report_id}", status_code=303)