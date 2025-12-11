#reports.py
"""
報告路由
"""
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select

from ..db import get_session
from ..models import Report, Paper, LabMeeting, Comment, User
from ..services.report_service import ReportService
from ..services.query_service import QueryService
from ..dependencies.auth import require_auth, get_optional_user

router = APIRouter()
templates = Jinja2Templates(directory="templates")

@router.get("/", response_class=HTMLResponse)
def index(
    request: Request,
    session: Session = Depends(get_session),
    current_user = Depends(get_optional_user)
):
    """首頁 - 顯示所有報告"""
    reports = session.exec(
        select(Report).order_by(Report.created_at.desc())
    ).all()
    
    query_service = QueryService(session)
    
    return templates.TemplateResponse("index.html", {
        "request": request,
        "reports": query_service.enrich_reports(reports),
        "current_user": current_user,
        "filter_msg": "All Reports"
    })

@router.get("/reports/{report_id}", response_class=HTMLResponse)
def report_detail(
    request: Request,
    report_id: int,
    session: Session = Depends(get_session),
    current_user = Depends(get_optional_user)
):
    """報告詳情頁"""
    report = session.get(Report, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="報告不存在")
    
    user = session.get(User, report.user_id)
    meeting = session.get(LabMeeting, report.meeting_id) if report.meeting_id else None
    paper = session.get(Paper, report.paper_id) if report.paper_id else None
    
    # 載入評論
    comments = session.exec(
        select(Comment)
        .where(Comment.report_id == report_id)
        .order_by(Comment.created_at)
    ).all()
    
    enriched_comments = [
        {"c": c, "user": session.get(User, c.user_id)}
        for c in comments
    ]
    
    query_service = QueryService(session)
    
    return templates.TemplateResponse("report_detail.html", {
        "request": request,
        "report": report,
        "user": user,
        "meeting": meeting,
        "enriched_paper_data": query_service.enrich_paper_with_counts(paper),
        "comments": enriched_comments,
        "current_user": current_user
    })

@router.get("/upload", response_class=HTMLResponse)
def upload_form(
    request: Request,
    session: Session = Depends(get_session),
    current_user = Depends(require_auth)
):
    """新增報告表單"""
    meetings = session.exec(
        select(LabMeeting).order_by(LabMeeting.meeting_date.desc())
    ).all()
    papers = session.exec(select(Paper)).all()
    
    return templates.TemplateResponse("upload.html", {
        "request": request,
        "meetings": meetings,
        "papers": papers,
        "current_user": current_user
    })

@router.post("/upload")
async def create_report(
    request: Request,
    session: Session = Depends(get_session),
    current_user = Depends(require_auth)
):
    """創建新報告"""
    form = await request.form()
    
    report_service = ReportService(session)
    report = report_service.create_report(form, current_user.id)
    
    return RedirectResponse(url=f"/reports/{report.id}", status_code=303)

@router.get("/reports/{report_id}/edit", response_class=HTMLResponse)
def edit_report_form(
    request: Request,
    report_id: int,
    session: Session = Depends(get_session),
    current_user = Depends(require_auth)
):
    """編輯報告表單"""
    report = session.get(Report, report_id)
    if not report or report.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="權限不足或報告不存在")
    
    user = session.get(User, report.user_id)
    meetings = session.exec(
        select(LabMeeting).order_by(LabMeeting.meeting_date.desc())
    ).all()
    papers = session.exec(select(Paper)).all()
    
    current_paper = session.get(Paper, report.paper_id) if report.paper_id else None
    paper_tags = ",".join([t.name for t in current_paper.tags]) if current_paper else ""
    
    paper_authors = []
    if current_paper:
        for author in current_paper.authors:
            author_affiliations = ",".join([aff.name for aff in author.affiliations])
            paper_authors.append({
                "name": author.name,
                "affiliations": author_affiliations
            })
    
    return templates.TemplateResponse("edit_report.html", {
        "request": request,
        "report": report,
        "user": user,
        "meetings": meetings,
        "papers": papers,
        "current_meeting_id": report.meeting_id,
        "current_paper_id": report.paper_id,
        "current_paper": current_paper,
        "paper_tags": paper_tags,
        "paper_authors": paper_authors,
        "current_user": current_user
    })

@router.post("/reports/{report_id}/edit")
async def update_report(
    request: Request,
    report_id: int,
    session: Session = Depends(get_session),
    current_user = Depends(require_auth)
):
    """更新報告"""
    report = session.get(Report, report_id)
    if not report or report.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="權限不足")
    
    form = await request.form()
    
    report_service = ReportService(session)
    report_service.update_report(report, form)
    
    return RedirectResponse(url=f"/reports/{report.id}", status_code=303)

@router.post("/reports/{report_id}/delete")
def delete_report(
    request: Request,
    report_id: int,
    session: Session = Depends(get_session),
    current_user = Depends(require_auth)
):
    """刪除報告"""
    report = session.get(Report, report_id)
    if not report or report.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="權限不足")
    
    report_service = ReportService(session)
    report_service.delete_report(report_id)
    
    return RedirectResponse(
        url=f"/profile/{current_user.username}", 
        status_code=303
    )