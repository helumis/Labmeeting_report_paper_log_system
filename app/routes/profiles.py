#profiles.py
"""
個人頁面路由
"""
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select

from ..db import get_session
from ..models import User, Report, Comment
from ..utils.helpers import enrich_reports_for_profile
from ..dependencies.auth import get_optional_user

router = APIRouter()
templates = Jinja2Templates(directory="templates")

@router.get("/profile/{username}", response_class=HTMLResponse)
def user_profile(
    request: Request,
    username: str,
    session: Session = Depends(get_session),
    current_user = Depends(get_optional_user)
):
    """使用者個人頁面"""
    target_user = session.exec(
        select(User).where(User.username == username)
    ).first()
    
    if not target_user:
        raise HTTPException(status_code=404, detail="使用者不存在")
    
    user_reports = session.exec(
        select(Report)
        .where(Report.user_id == target_user.id)
        .order_by(Report.created_at.desc())
    ).all()
    
    user_comments = session.exec(
        select(Comment)
        .where(Comment.user_id == target_user.id)
        .order_by(Comment.created_at.desc())
    ).all()
    
    enriched_reports = enrich_reports_for_profile(session, user_reports)
    
    return templates.TemplateResponse("profile.html", {
        "request": request,
        "target_user": target_user,
        "reports": enriched_reports,
        "comments": user_comments,
        "current_user": current_user
    })