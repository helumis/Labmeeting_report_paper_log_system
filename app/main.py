# app/main.py - 完整修復版

from fastapi import FastAPI, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from sqlmodel import select, Session, delete, func
from typing import List, Optional, Dict, Any
from pathlib import Path
from datetime import datetime
import uvicorn

from .config import settings
from .db import create_db_and_tables, get_session
from .models import (
    User, LabMeeting, Paper, Report, Tag, Comment,
    Author, Affiliation, AuthorAffiliationLink,
    PaperAuthorLink, PaperTag, TagCountSnapshot
)
from .security import get_password_hash, verify_password

# ============ 應用初始化 ============
app = FastAPI()
BASE_DIR = Path(__file__).resolve().parent

app.mount("/css", StaticFiles(directory="app/css"), name="css")
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)
templates = Jinja2Templates(directory="templates")

@app.on_event("startup")
def on_startup():
    create_db_and_tables()

# ============ 輔助函數 ============

# -------- 認證相關 --------

def get_current_user(request: Request, session: Session) -> Optional[User]:
    """取得當前登入使用者"""
    user_id = request.session.get("user_id")
    return session.get(User, user_id) if user_id else None

def require_auth(request: Request, session: Session) -> User:
    """確保使用者已登入，否則重定向到登入頁"""
    user = get_current_user(request, session)
    if not user:
        raise HTTPException(status_code=401, detail="請先登入")
    return user

# -------- 計數查詢 --------

def get_count(session: Session, statement) -> int:
    """統一的計數查詢函數"""
    result = session.exec(statement).first()
    if result is None:
        return 0
    # 如果結果是元組，取第一個元素；否則直接返回
    return result[0] if isinstance(result, tuple) else result

def get_tag_count(session: Session, tag_id: int) -> int:
    """從快照獲取標籤計數"""
    stmt = select(TagCountSnapshot.count).where(TagCountSnapshot.tag_id == tag_id)
    return get_count(session, stmt)

def get_author_count(session: Session, author_id: int) -> int:
    """獲取作者關聯的 Paper 總數（不限於已報告）"""
    stmt = (
        select(func.count(func.distinct(Paper.id)))
        .join(PaperAuthorLink, Paper.id == PaperAuthorLink.paper_id)
        .where(PaperAuthorLink.author_id == author_id)
    )
    return get_count(session, stmt)

def get_affiliation_count(session: Session, aff_id: int) -> int:
    """獲取組織關聯的 Paper 總數（不限於已報告）"""
    stmt = (
        select(func.count(func.distinct(Paper.id)))
        .join(PaperAuthorLink, Paper.id == PaperAuthorLink.paper_id)
        .join(Author, PaperAuthorLink.author_id == Author.id)
        .join(AuthorAffiliationLink, Author.id == AuthorAffiliationLink.author_id)
        .where(AuthorAffiliationLink.affiliation_id == aff_id)
    )
    return get_count(session, stmt)

def get_year_count(session: Session, year: int) -> int:
    """獲取某年份的 Paper 總數（不限於已報告）"""
    stmt = (
        select(func.count(Paper.id))
        .where(Paper.published_year == year)
    )
    return get_count(session, stmt)

def get_venue_count(session: Session, venue: str) -> int:
    """獲取某期刊/會議的 Paper 總數（不限於已報告）"""
    stmt = (
        select(func.count(Paper.id))
        .where(Paper.journal_or_conference == venue)
    )
    return get_count(session, stmt)

# -------- 資料豐富化 --------

def enrich_paper_with_counts(session: Session, paper: Paper) -> Optional[Dict[str, Any]]:
    """為 Paper 添加計數資訊"""
    if not paper:
        return None

    # 豐富作者資訊
    enriched_authors = []
    for author in paper.authors:
        enriched_affs = [
            {"aff": aff, "count": get_affiliation_count(session, aff.id)}
            for aff in author.affiliations
        ]
        enriched_authors.append({
            "auth": author,
            "affiliations": enriched_affs,
            "count": get_author_count(session, author.id)
        })

    # 豐富標籤資訊
    enriched_tags = [
        {"tag": tag, "count": get_tag_count(session, tag.id)}
        for tag in paper.tags
    ]

    return {
        "paper": paper,
        "authors": enriched_authors,
        "tags": enriched_tags,
        "year_count": get_year_count(session, paper.published_year),
        "venue_count": get_venue_count(session, paper.journal_or_conference)
    }

def enrich_reports(session: Session, reports: List[Report]) -> List[Dict]:
    """豐富報告列表資訊"""
    enriched = []
    for r in reports:
        user = session.get(User, r.user_id) if r.user_id else None
        meeting = session.get(LabMeeting, r.meeting_id) if r.meeting_id else None
        paper = session.get(Paper, r.paper_id) if r.paper_id else None
        tags = paper.tags if paper else []
        enriched.append({
            "r": r, "user": user, "meeting": meeting, 
            "paper": paper, "tags": tags
        })
    return enriched

# -------- 標籤計數更新 --------

def update_tag_count_snapshot(session: Session, tag_id: int, increment: int):
    """更新標籤計數快照"""
    snapshot = session.get(TagCountSnapshot, tag_id)
    
    if snapshot:
        snapshot.count += increment
        snapshot.last_updated = datetime.utcnow()
        session.add(snapshot)
    elif increment > 0:
        snapshot = TagCountSnapshot(
            tag_id=tag_id,
            count=increment,
            last_updated=datetime.utcnow()
        )
        session.add(snapshot)
    
    session.commit()

# -------- Paper 關聯處理 --------

def clear_paper_relations(session: Session, paper_id: int):
    """清除 Paper 的所有關聯"""
    # 獲取舊標籤並更新計數
    old_tags = session.exec(
        select(PaperTag.tag_id)
        .where(PaperTag.paper_id == paper_id)
    ).all()

    # 刪除關聯
    session.exec(delete(PaperTag).where(PaperTag.paper_id == paper_id))
    session.exec(delete(PaperAuthorLink).where(PaperAuthorLink.paper_id == paper_id))
    session.commit()

    # 更新標籤計數
    for tag_id in old_tags:
        update_tag_count_snapshot(session, tag_id, -1)

def get_or_create_author(session: Session, name: str) -> Author:
    """獲取或創建作者"""
    author = session.exec(select(Author).where(Author.name == name)).first()
    if not author:
        author = Author(name=name)
        session.add(author)
        session.commit()
        session.refresh(author)
    return author

def get_or_create_affiliation(session: Session, name: str) -> Affiliation:
    """獲取或創建組織"""
    aff = session.exec(select(Affiliation).where(Affiliation.name == name)).first()
    if not aff:
        aff = Affiliation(name=name)
        session.add(aff)
        session.commit()
        session.refresh(aff)
    return aff

def get_or_create_tag(session: Session, name: str) -> Tag:
    """獲取或創建標籤"""
    tag = session.exec(select(Tag).where(Tag.name == name)).first()
    if not tag:
        tag = Tag(name=name)
        session.add(tag)
        session.commit()
        session.refresh(tag)
    return tag

def link_author_affiliation(session: Session, author_id: int, aff_id: int):
    """連結作者與組織"""
    link_exists = session.exec(
        select(AuthorAffiliationLink).where(
            AuthorAffiliationLink.author_id == author_id,
            AuthorAffiliationLink.affiliation_id == aff_id
        )
    ).first()
    
    if not link_exists:
        session.add(AuthorAffiliationLink(author_id=author_id, affiliation_id=aff_id))
        session.commit()

def process_paper_authors(session: Session, form, paper_id: int):
    """處理 Paper 的作者資訊"""
    idx = 0
    while True:
        author_name = form.get(f"author_name_{idx}")
        if not author_name:
            break
            
        author = get_or_create_author(session, author_name)
        session.add(PaperAuthorLink(paper_id=paper_id, author_id=author.id))
        
        # 處理組織
        affiliations_str = form.get(f"author_affiliations_{idx}", "")
        for aff_name in [x.strip() for x in affiliations_str.split(",") if x.strip()]:
            aff = get_or_create_affiliation(session, aff_name)
            link_author_affiliation(session, author.id, aff.id)
        
        session.commit()
        idx += 1

def process_paper_tags(session: Session, tags_str: str, paper_id: int):
    """處理 Paper 的標籤"""
    if not tags_str:
        return
        
    for tag_name in [x.strip() for x in tags_str.split(",") if x.strip()]:
        tag = get_or_create_tag(session, tag_name)
        
        # 檢查是否已存在連結
        link_exists = session.exec(
            select(PaperTag).where(
                PaperTag.paper_id == paper_id,
                PaperTag.tag_id == tag.id
            )
        ).first()
        
        if not link_exists:
            session.add(PaperTag(paper_id=paper_id, tag_id=tag.id))
            session.commit()
            update_tag_count_snapshot(session, tag.id, 1)

def safe_int(value, default=0) -> int:
    """安全地將值轉換為整數"""
    if not value or value == '':
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default

def safe_str(value, default="") -> str:
    """安全地將值轉換為字串"""
    if value is None:
        return default
    return str(value).strip()

def is_valid_id(value) -> bool:
    """檢查是否為有效的 ID"""
    if not value:
        return False
    try:
        return str(value).strip().isdigit() and int(value) > 0
    except:
        return False

def create_or_update_paper(session: Session, form, paper_id: Optional[int] = None) -> int:
    """創建或更新 Paper"""
    if paper_id:
        paper = session.get(Paper, paper_id)
    else:
        paper = Paper()
    
    paper.paper_title = form.get("paper_title")
    paper.published_year = safe_int(form.get("published_year"))
    paper.published_month = safe_int(form.get("published_month"))
    paper.journal_or_conference = form.get("journal_or_conference", "")
    
    session.add(paper)
    session.commit()
    session.refresh(paper)
    
    # 如果是更新，先清除舊關聯
    if paper_id:
        clear_paper_relations(session, paper.id)
    
    # 處理作者和標籤
    process_paper_authors(session, form, paper.id)
    process_paper_tags(session, form.get("tags", ""), paper.id)
    
    return paper.id

# ============ 路由 ============

# -------- 首頁和篩選 --------

@app.get("/", response_class=HTMLResponse)
def index(request: Request, session: Session = Depends(get_session)):
    """首頁 - 顯示所有報告"""
    reports = session.exec(select(Report).order_by(Report.created_at.desc())).all()
    return templates.TemplateResponse("index.html", {
        "request": request,
        "reports": enrich_reports(session, reports),
        "current_user": get_current_user(request, session),
        "filter_msg": "All Reports"
    })

def render_filtered_reports(
    request: Request,
    session: Session,
    statement,
    filter_msg: str
):
    """通用的報告篩選渲染函數"""
    reports = session.exec(statement).all()
    return templates.TemplateResponse("index.html", {
        "request": request,
        "reports": enrich_reports(session, reports),
        "current_user": get_current_user(request, session),
        "filter_msg": filter_msg
    })

@app.get("/tags/{tag_id}", response_class=HTMLResponse)
def filter_by_tag(request: Request, tag_id: int, session: Session = Depends(get_session)):
    """按標籤篩選"""
    tag = session.get(Tag, tag_id)
    if not tag:
        raise HTTPException(status_code=404, detail="Tag not found")
    
    stmt = (
        select(Report)
        .join(Paper, Report.paper_id == Paper.id)
        .join(PaperTag, Paper.id == PaperTag.paper_id)
        .where(PaperTag.tag_id == tag_id)
        .order_by(Report.created_at.desc())
    )
    return render_filtered_reports(request, session, stmt, f"Reports with Tag: {tag.name}")

@app.get("/authors/{author_id}", response_class=HTMLResponse)
def filter_by_author(request: Request, author_id: int, session: Session = Depends(get_session)):
    """按作者篩選"""
    author = session.get(Author, author_id)
    if not author:
        raise HTTPException(status_code=404, detail="Author not found")
    
    stmt = (
        select(Report)
        .join(Paper, Report.paper_id == Paper.id)
        .join(PaperAuthorLink, Paper.id == PaperAuthorLink.paper_id)
        .where(PaperAuthorLink.author_id == author_id)
        .order_by(Report.created_at.desc())
    )
    return render_filtered_reports(request, session, stmt, f"Reports by Author: {author.name}")

@app.get("/affiliations/{aff_id}", response_class=HTMLResponse)
def filter_by_affiliation(request: Request, aff_id: int, session: Session = Depends(get_session)):
    """按組織篩選"""
    aff = session.get(Affiliation, aff_id)
    if not aff:
        raise HTTPException(status_code=404, detail="Affiliation not found")
    
    stmt = (
        select(Report)
        .join(Paper, Report.paper_id == Paper.id)
        .join(PaperAuthorLink, Paper.id == PaperAuthorLink.paper_id)
        .join(Author, PaperAuthorLink.author_id == Author.id)
        .join(AuthorAffiliationLink, Author.id == AuthorAffiliationLink.author_id)
        .where(AuthorAffiliationLink.affiliation_id == aff_id)
        .distinct()
        .order_by(Report.created_at.desc())
    )
    return render_filtered_reports(request, session, stmt, f"Reports from Affiliation: {aff.name}")

@app.get("/years/{year}", response_class=HTMLResponse)
def filter_by_year(request: Request, year: int, session: Session = Depends(get_session)):
    """按年份篩選"""
    stmt = (
        select(Report)
        .join(Paper, Report.paper_id == Paper.id)
        .where(Paper.published_year == year)
        .order_by(Report.created_at.desc())
    )
    return render_filtered_reports(request, session, stmt, f"Reports Published in: {year}")

@app.get("/venues/{venue_name:path}", response_class=HTMLResponse)
def filter_by_venue(request: Request, venue_name: str, session: Session = Depends(get_session)):
    """按期刊/會議篩選"""
    stmt = (
        select(Report)
        .join(Paper, Report.paper_id == Paper.id)
        .where(Paper.journal_or_conference == venue_name)
        .order_by(Report.created_at.desc())
    )
    return render_filtered_reports(request, session, stmt, f"Reports in Venue: {venue_name}")

@app.get("/search", response_class=HTMLResponse)
def search(request: Request, q: str, session: Session = Depends(get_session)):
    """搜尋功能"""
    if not q:
        return RedirectResponse(url="/")
    
    # 搜尋論文、作者、標籤
    paper_ids = set()
    
    # 搜論文標題
    paper_ids.update(session.exec(
        select(Paper.id).where(Paper.paper_title.ilike(f"%{q}%"))
    ).all())
    
    # 搜作者
    paper_ids.update(session.exec(
        select(Paper.id)
        .join(PaperAuthorLink)
        .join(Author)
        .where(Author.name.ilike(f"%{q}%"))
    ).all())
    
    # 搜標籤
    paper_ids.update(session.exec(
        select(Paper.id)
        .join(PaperTag)
        .join(Tag)
        .where(Tag.name.ilike(f"%{q}%"))
    ).all())
    
    if not paper_ids:
        return templates.TemplateResponse("index.html", {
            "request": request,
            "reports": [],
            "current_user": get_current_user(request, session),
            "filter_msg": f"搜尋結果: '{q}' (找不到相關資料)"
        })
    
    stmt = (
        select(Report)
        .where(Report.paper_id.in_(paper_ids))
        .order_by(Report.created_at.desc())
    )
    reports = session.exec(stmt).all()
    
    return templates.TemplateResponse("index.html", {
        "request": request,
        "reports": enrich_reports(session, reports),
        "current_user": get_current_user(request, session),
        "filter_msg": f"搜尋結果: '{q}' (共找到 {len(reports)} 篇)"
    })

# -------- 報告詳情 --------

@app.get("/reports/{report_id}", response_class=HTMLResponse)
def report_detail(request: Request, report_id: int, session: Session = Depends(get_session)):
    """報告詳情頁"""
    report = session.get(Report, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    
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
    
    return templates.TemplateResponse("report_detail.html", {
        "request": request,
        "report": report,
        "user": user,
        "meeting": meeting,
        "enriched_paper_data": enrich_paper_with_counts(session, paper),
        "comments": enriched_comments,
        "current_user": get_current_user(request, session)
    })

# -------- 新增報告 --------

@app.get("/upload", response_class=HTMLResponse)
def upload_form(request: Request, session: Session = Depends(get_session)):
    """新增報告表單"""
    current_user = get_current_user(request, session)
    if not current_user:
        return RedirectResponse(url="/login")
    
    meetings = session.exec(select(LabMeeting).order_by(LabMeeting.meeting_date.desc())).all()
    papers = session.exec(select(Paper)).all()
    
    return templates.TemplateResponse("upload.html", {
        "request": request,
        "meetings": meetings,
        "papers": papers,
        "current_user": current_user
    })

@app.post("/upload")
async def create_report(request: Request, session: Session = Depends(get_session)):
    """創建新報告"""
    current_user = get_current_user(request, session)
    if not current_user:
        return RedirectResponse(url="/login")
    
    form = await request.form()
    
    # 驗證必填欄位
    report_title = safe_str(form.get("report_title"))
    if not report_title:
        raise HTTPException(status_code=400, detail="報告標題不能為空")
    
    # 處理 Meeting
    meeting_id = None
    existing_meeting_id = form.get("existing_meeting_id")
    if is_valid_id(existing_meeting_id):
        meeting_id = int(existing_meeting_id)
    else:
        meeting_title = safe_str(form.get("meeting_title"))
        if meeting_title:
            meeting = LabMeeting(
                meeting_title=meeting_title,
                meeting_location=safe_str(form.get("meeting_location")),
                meeting_date=datetime.now().date()
            )
            meeting_date_str = form.get("meeting_date")
            if meeting_date_str:
                try:
                    meeting.meeting_date = datetime.fromisoformat(str(meeting_date_str)).date()
                except:
                    pass
            session.add(meeting)
            session.commit()
            session.refresh(meeting)
            meeting_id = meeting.id
    
    # 處理 Paper
    paper_id = None
    existing_paper_id = form.get("existing_paper_id") or form.get("paper_id")
    if is_valid_id(existing_paper_id):
        paper_id = int(existing_paper_id)
    elif safe_str(form.get("paper_title")):
        paper_id = create_or_update_paper(session, form)
    
    # 創建 Report (確保有 meeting_id)
    if not meeting_id:
        raise HTTPException(status_code=400, detail="必須選擇或創建會議")
    
    report = Report(
        report_title=report_title,
        report_summary=safe_str(form.get("report_summary")),
        slides_link=safe_str(form.get("slides_link")),
        user_id=current_user.id,
        meeting_id=meeting_id,
        paper_id=paper_id
    )
    session.add(report)
    session.commit()
    session.refresh(report)
    
    return RedirectResponse(url=f"/reports/{report.id}", status_code=303)

# -------- 編輯報告 --------

@app.get("/reports/{report_id}/edit", response_class=HTMLResponse)
def edit_report_form(request: Request, report_id: int, session: Session = Depends(get_session)):
    """編輯報告表單"""
    current_user = get_current_user(request, session)
    if not current_user:
        return RedirectResponse(url="/login")
    
    report = session.get(Report, report_id)
    if not report or report.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="權限不足或報告不存在")
    
    # 載入報告作者資訊
    user = session.get(User, report.user_id)
    
    # 載入會議和論文列表
    meetings = session.exec(select(LabMeeting).order_by(LabMeeting.meeting_date.desc())).all()
    papers = session.exec(select(Paper)).all()
    
    # 載入當前論文資訊和關聯數據
    current_paper = session.get(Paper, report.paper_id) if report.paper_id else None
    paper_tags = ",".join([t.name for t in current_paper.tags]) if current_paper else ""
    
    # 正確載入作者和組織資訊
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

@app.post("/reports/{report_id}/edit")
async def update_report(request: Request, report_id: int, session: Session = Depends(get_session)):
    """更新報告"""
    current_user = get_current_user(request, session)
    if not current_user:
        return RedirectResponse(url="/login")
    
    report = session.get(Report, report_id)
    if not report or report.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="權限不足")
    
    form = await request.form()
    
    # 驗證必填欄位
    report_title = safe_str(form.get("report_title"))
    if not report_title:
        raise HTTPException(status_code=400, detail="報告標題不能為空")
    
    # 更新基本資訊
    report.report_title = report_title
    report.report_summary = safe_str(form.get("report_summary"))
    report.slides_link = safe_str(form.get("slides_link"))
    
    # 更新 Meeting
    meeting_id = form.get("existing_meeting_id")
    if is_valid_id(meeting_id):
        report.meeting_id = int(meeting_id)
    
    # 更新 Paper
    existing_paper_id = form.get("existing_paper_id")
    if is_valid_id(existing_paper_id):
        report.paper_id = int(existing_paper_id)
    elif safe_str(form.get("paper_title")):
        report.paper_id = create_or_update_paper(session, form, report.paper_id)
    else:
        report.paper_id = None
    
    session.add(report)
    session.commit()
    
    return RedirectResponse(url=f"/reports/{report.id}", status_code=303)

# -------- 刪除報告 --------

@app.post("/reports/{report_id}/delete")
def delete_report(request: Request, report_id: int, session: Session = Depends(get_session)):
    """刪除報告"""
    current_user = get_current_user(request, session)
    if not current_user:
        return RedirectResponse(url="/login")
    
    report = session.get(Report, report_id)
    if not report or report.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="權限不足")
    
    # 刪除關聯的評論
    comments = session.exec(select(Comment).where(Comment.report_id == report_id)).all()
    for comment in comments:
        session.delete(comment)
    
    session.delete(report)
    session.commit()
    
    return RedirectResponse(url=f"/profile/{current_user.username}", status_code=303)

# -------- 評論 --------

@app.post("/comments")
def create_comment(
    request: Request,
    report_id: int = Form(...),
    content: str = Form(...),
    session: Session = Depends(get_session)
):
    """新增評論"""
    current_user = get_current_user(request, session)
    if not current_user:
        return RedirectResponse(url="/login")
    
    # 驗證評論內容
    content = safe_str(content)
    if not content:
        raise HTTPException(status_code=400, detail="評論內容不能為空")
    
    # 驗證報告是否存在
    report = session.get(Report, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="報告不存在")
    
    comment = Comment(report_id=report_id, user_id=current_user.id, content=content)
    session.add(comment)
    session.commit()
    
    return RedirectResponse(url=f"/reports/{report_id}", status_code=303)

@app.post("/comments/{comment_id}/delete")
def delete_comment(request: Request, comment_id: int, session: Session = Depends(get_session)):
    """刪除評論"""
    current_user = get_current_user(request, session)
    if not current_user:
        return RedirectResponse(url="/login")
    
    comment = session.get(Comment, comment_id)
    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")
    if comment.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="權限不足")
    
    report_id = comment.report_id
    session.delete(comment)
    session.commit()
    
    return RedirectResponse(url=f"/reports/{report_id}", status_code=303)

# -------- 個人頁面 --------

@app.get("/profile/{username}", response_class=HTMLResponse)
def user_profile(request: Request, username: str, session: Session = Depends(get_session)):
    """使用者個人頁面"""
    target_user = session.exec(select(User).where(User.username == username)).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")
    
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
    
    enriched_reports = []
    for r in user_reports:
        meeting = session.get(LabMeeting, r.meeting_id)
        paper = session.get(Paper, r.paper_id) if r.paper_id else None
        tags = paper.tags if paper else []
        enriched_reports.append({"r": r, "meeting": meeting, "tags": tags})
    
    return templates.TemplateResponse("profile.html", {
        "request": request,
        "target_user": target_user,
        "reports": enriched_reports,
        "comments": user_comments,
        "current_user": get_current_user(request, session)
    })

# -------- 認證 --------

@app.get("/register", response_class=HTMLResponse)
def register_form(request: Request):
    """註冊表單"""
    return templates.TemplateResponse("register.html", {"request": request})

@app.post("/register")
def register(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    display_name: str = Form(None),
    session: Session = Depends(get_session)
):
    """註冊新使用者"""
    # 驗證必填欄位
    username = safe_str(username)
    password = safe_str(password)
    
    if not username or len(username) < 3:
        return templates.TemplateResponse("register.html", {
            "request": request,
            "error": "使用者名稱至少需要 3 個字元"
        })
    
    if not password or len(password) < 6:
        return templates.TemplateResponse("register.html", {
            "request": request,
            "error": "密碼至少需要 6 個字元"
        })
    
    # 檢查帳號是否存在
    exists = session.exec(select(User).where(User.username == username)).first()
    if exists:
        return templates.TemplateResponse("register.html", {
            "request": request,
            "error": "使用者名稱已存在"
        })
    
    # 加密密碼並建立使用者
    hashed_pwd = get_password_hash(password)
    display_name = safe_str(display_name) or username
    
    user = User(
        username=username,
        display_name=display_name,
        hashed_password=hashed_pwd
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    
    # 註冊成功後直接登入
    request.session["user_id"] = user.id
    return RedirectResponse(url="/", status_code=303)

@app.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    """登入表單"""
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    session: Session = Depends(get_session)
):
    """使用者登入"""
    # 驗證必填欄位
    username = safe_str(username)
    password = safe_str(password)
    
    if not username or not password:
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": "請輸入使用者名稱和密碼"
        })
    
    # 尋找使用者
    user = session.exec(select(User).where(User.username == username)).first()
    
    # 驗證帳號與密碼
    if not user or not verify_password(password, user.hashed_password):
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": "使用者名稱或密碼錯誤"
        })
    
    # 登入成功，寫入 Session
    request.session["user_id"] = user.id
    return RedirectResponse(url="/", status_code=303)

@app.get("/logout")
def logout(request: Request):
    """登出"""
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)

# ============ 主程式入口 ============

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)