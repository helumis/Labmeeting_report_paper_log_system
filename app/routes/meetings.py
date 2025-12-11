#meetings.py
"""
會議路由
"""
from datetime import datetime
from fastapi import APIRouter, Request, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session

from ..db import get_session
from ..services.meeting_service import MeetingService
from ..services.query_service import QueryService
from ..dependencies.auth import require_auth, get_optional_user
from ..utils.validators import safe_str

router = APIRouter()
templates = Jinja2Templates(directory="templates")

@router.get("/meetings", response_class=HTMLResponse)
def list_meetings(
    request: Request,
    session: Session = Depends(get_session),
    current_user = Depends(get_optional_user)
):
    """會議列表頁"""
    meeting_service = MeetingService(session)
    meetings = meeting_service.get_all_meetings()
    
    # 為每個會議添加報告數量
    enriched_meetings = []
    for meeting in meetings:
        reports = meeting_service.get_meeting_reports(meeting.id)
        enriched_meetings.append({
            "meeting": meeting,
            "report_count": len(reports),
            "reports": reports[:3]  # 只顯示前 3 個報告
        })
    
    return templates.TemplateResponse("meetings/list.html", {
        "request": request,
        "meetings": enriched_meetings,
        "current_user": current_user
    })

@router.get("/meetings/{meeting_id}", response_class=HTMLResponse)
def meeting_detail(
    request: Request,
    meeting_id: int,
    session: Session = Depends(get_session),
    current_user = Depends(get_optional_user)
):
    """會議詳情頁"""
    meeting_service = MeetingService(session)
    query_service = QueryService(session)
    
    meeting = meeting_service.get_meeting_by_id(meeting_id)
    reports = meeting_service.get_meeting_reports(meeting_id)
    stats = meeting_service.get_meeting_stats(meeting_id)
    
    return templates.TemplateResponse("meetings/detail.html", {
        "request": request,
        "meeting": meeting,
        "reports": query_service.enrich_reports(reports),
        "stats": stats,
        "current_user": current_user
    })

@router.get("/meetings/create", response_class=HTMLResponse)
def create_meeting_form(
    request: Request,
    current_user = Depends(require_auth)
):
    """創建會議表單"""
    return templates.TemplateResponse("meetings/create.html", {
        "request": request,
        "current_user": current_user
    })

@router.post("/meetings/create")
def create_meeting(
    request: Request,
    meeting_title: str = Form(...),
    meeting_date: str = Form(...),
    meeting_location: str = Form(""),
    session: Session = Depends(get_session),
    current_user = Depends(require_auth)
):
    """創建新會議"""
    try:
        # 解析日期
        parsed_date = datetime.strptime(meeting_date, "%Y-%m-%d").date()
        
        meeting_service = MeetingService(session)
        meeting = meeting_service.create_meeting(
            meeting_title=meeting_title,
            meeting_date=parsed_date,
            meeting_location=meeting_location
        )
        
        return RedirectResponse(
            url=f"/meetings/{meeting.id}",
            status_code=303
        )
    
    except ValueError as e:
        return templates.TemplateResponse("meetings/create.html", {
            "request": request,
            "current_user": current_user,
            "error": str(e)
        })

@router.get("/meetings/{meeting_id}/edit", response_class=HTMLResponse)
def edit_meeting_form(
    request: Request,
    meeting_id: int,
    session: Session = Depends(get_session),
    current_user = Depends(require_auth)
):
    """編輯會議表單"""
    meeting_service = MeetingService(session)
    meeting = meeting_service.get_meeting_by_id(meeting_id)
    
    return templates.TemplateResponse("meetings/edit.html", {
        "request": request,
        "meeting": meeting,
        "current_user": current_user
    })

@router.post("/meetings/{meeting_id}/edit")
def update_meeting(
    request: Request,
    meeting_id: int,
    meeting_title: str = Form(...),
    meeting_date: str = Form(...),
    meeting_location: str = Form(""),
    session: Session = Depends(get_session),
    current_user = Depends(require_auth)
):
    """更新會議"""
    try:
        parsed_date = datetime.strptime(meeting_date, "%Y-%m-%d").date()
        
        meeting_service = MeetingService(session)
        meeting = meeting_service.update_meeting(
            meeting_id=meeting_id,
            meeting_title=meeting_title,
            meeting_date=parsed_date,
            meeting_location=meeting_location
        )
        
        return RedirectResponse(
            url=f"/meetings/{meeting.id}",
            status_code=303
        )
    
    except ValueError as e:
        meeting_service = MeetingService(session)
        meeting = meeting_service.get_meeting_by_id(meeting_id)
        
        return templates.TemplateResponse("meetings/edit.html", {
            "request": request,
            "meeting": meeting,
            "current_user": current_user,
            "error": str(e)
        })

@router.post("/meetings/{meeting_id}/delete")
def delete_meeting(
    request: Request,
    meeting_id: int,
    force: bool = Form(False),
    session: Session = Depends(get_session),
    current_user = Depends(require_auth)
):
    """刪除會議"""
    try:
        meeting_service = MeetingService(session)
        meeting_service.delete_meeting(meeting_id, force=force)
        
        return RedirectResponse(url="/meetings", status_code=303)
    
    except HTTPException as e:
        # 如果有關聯報告，顯示確認頁面
        meeting = meeting_service.get_meeting_by_id(meeting_id)
        reports = meeting_service.get_meeting_reports(meeting_id)
        
        return templates.TemplateResponse("meetings/delete_confirm.html", {
            "request": request,
            "meeting": meeting,
            "reports": reports,
            "current_user": current_user,
            "error": e.detail
        })