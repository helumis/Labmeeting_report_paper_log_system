# app/main.py

from fastapi import FastAPI, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from sqlmodel import select, Session, delete
from typing import List, Optional
import uvicorn
from datetime import datetime

# 假設這些模組存在於您的專案結構中
from .config import settings
from .db import create_db_and_tables, get_session
from .models import (
    User, LabMeeting, Paper, Report, Tag, Comment,
    Author, Affiliation, AuthorAffiliationLink,
    PaperAuthorLink, PaperTag
)

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)
templates = Jinja2Templates(directory="templates")

# ---------------- startup ----------------
@app.on_event("startup")
def on_startup():
    create_db_and_tables()

# ---------------- helpers ----------------
def get_current_user(request: Request, session: Session = Depends(get_session)) -> Optional[User]:
    """取得當前登入的使用者"""
    username = request.session.get("username")
    if not username:
        return None
    user = session.exec(select(User).where(User.username == username)).first()
    return user

def get_report_tags(session: Session, report: Report) -> List[Tag]:
    """取得 report 對應 paper 的 tags"""
    if not report.paper_id:
        return []
    paper = session.get(Paper, report.paper_id)
    if not paper:
        return []
    return paper.tags if hasattr(paper, "tags") else []

def clear_paper_relations(session: Session, paper_id: int):
    """清除指定 Paper 所有 AuthorLink 和 TagLink (用於編輯時重建)"""
    
    # *** 修正: 使用 sqlmodel.delete 語句進行批量刪除 ***
    
    # 清除 PaperAuthorLink
    author_link_statement = delete(PaperAuthorLink).where(PaperAuthorLink.paper_id == paper_id)
    session.exec(author_link_statement)
    
    # 清除 PaperTag
    tag_link_statement = delete(PaperTag).where(PaperTag.paper_id == paper_id)
    session.exec(tag_link_statement)
    
    session.commit()
def enrich_reports(session: Session, reports: List[Report]):
    """將 report 列表打包成前端需要的格式 (包含 user, meeting, paper, tags)"""
    enriched = []
    for r in reports:
        user = session.get(User, r.user_id) if r.user_id else None
        meeting = session.get(LabMeeting, r.meeting_id) if r.meeting_id else None
        paper = session.get(Paper, r.paper_id) if r.paper_id else None
        tags = get_report_tags(session, r)
        enriched.append({"r": r, "user": user, "meeting": meeting, "paper": paper, "tags": tags})
    return enriched
# ---------------- 首頁 (Index) ----------------
@app.get("/", response_class=HTMLResponse)
def index(request: Request, session: Session = Depends(get_session)):
    reports = session.exec(select(Report).order_by(Report.created_at.desc())).all()
    enriched = enrich_reports(session, reports) # 使用 helper
    
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request, 
            "reports": enriched, 
            "current_user": get_current_user(request, session),
            "filter_msg": "All Reports" # 給前端顯示標題用
        }
    )
# 1. 篩選 Tag
@app.get("/tags/{tag_id}", response_class=HTMLResponse)
def filter_by_tag(request: Request, tag_id: int, session: Session = Depends(get_session)):
    tag = session.get(Tag, tag_id)
    if not tag:
        raise HTTPException(status_code=404, detail="Tag not found")
    
    # 邏輯: Tag -> PaperTag -> Paper -> Report
    # 這邊使用 Join 查詢
    statement = (
        select(Report)
        .join(Paper, Report.paper_id == Paper.id)
        .join(PaperTag, Paper.id == PaperTag.paper_id)
        .where(PaperTag.tag_id == tag_id)
        .order_by(Report.created_at.desc())
    )
    reports = session.exec(statement).all()
    
    return templates.TemplateResponse(
        "index.html", # 重用 index 模板
        {
            "request": request, 
            "reports": enrich_reports(session, reports), 
            "current_user": get_current_user(request, session),
            "filter_msg": f"Reports with Tag: {tag.name}"
        }
    )

# 2. 篩選 Author
@app.get("/authors/{author_id}", response_class=HTMLResponse)
def filter_by_author(request: Request, author_id: int, session: Session = Depends(get_session)):
    author = session.get(Author, author_id)
    if not author:
        raise HTTPException(status_code=404, detail="Author not found")

    statement = (
        select(Report)
        .join(Paper, Report.paper_id == Paper.id)
        .join(PaperAuthorLink, Paper.id == PaperAuthorLink.paper_id)
        .where(PaperAuthorLink.author_id == author_id)
        .order_by(Report.created_at.desc())
    )
    reports = session.exec(statement).all()

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request, 
            "reports": enrich_reports(session, reports), 
            "current_user": get_current_user(request, session),
            "filter_msg": f"Reports by Author: {author.name}"
        }
    )

# 3. 篩選 Affiliation
@app.get("/affiliations/{aff_id}", response_class=HTMLResponse)
def filter_by_affiliation(request: Request, aff_id: int, session: Session = Depends(get_session)):
    aff = session.get(Affiliation, aff_id)
    if not aff:
        raise HTTPException(status_code=404, detail="Affiliation not found")

    # 路徑較長: Report -> Paper -> AuthorLink -> Author -> AffiliationLink
    statement = (
        select(Report)
        .join(Paper, Report.paper_id == Paper.id)
        .join(PaperAuthorLink, Paper.id == PaperAuthorLink.paper_id)
        .join(Author, PaperAuthorLink.author_id == Author.id)
        .join(AuthorAffiliationLink, Author.id == AuthorAffiliationLink.author_id)
        .where(AuthorAffiliationLink.affiliation_id == aff_id)
        .distinct() # 避免同一篇 Paper 多位作者同單位造成重複
        .order_by(Report.created_at.desc())
    )
    reports = session.exec(statement).all()

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request, 
            "reports": enrich_reports(session, reports), 
            "current_user": get_current_user(request, session),
            "filter_msg": f"Reports from Affiliation: {aff.name}"
        }
    )

# 4. 篩選 Year
@app.get("/years/{year}", response_class=HTMLResponse)
def filter_by_year(request: Request, year: int, session: Session = Depends(get_session)):
    statement = (
        select(Report)
        .join(Paper, Report.paper_id == Paper.id)
        .where(Paper.published_year == year)
        .order_by(Report.created_at.desc())
    )
    reports = session.exec(statement).all()

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request, 
            "reports": enrich_reports(session, reports), 
            "current_user": get_current_user(request, session),
            "filter_msg": f"Reports Published in: {year}"
        }
    )

# app/main.py (修正 filter_by_venue 路由)

# 5. 篩選 Venue (Journal/Conference)
# *** 修正: 將 {venue_name} 改為 {venue_name:path} 以允許斜線 (/) 存在於參數中 ***
@app.get("/venues/{venue_name:path}", response_class=HTMLResponse)
def filter_by_venue(request: Request, venue_name: str, session: Session = Depends(get_session)):
    
    # 由於 venue_name 現在可能包含編碼的斜線，FastAPI 會自動處理 URL 解碼。
    
    statement = (
        select(Report)
        .join(Paper, Report.paper_id == Paper.id)
        .where(Paper.journal_or_conference == venue_name)
        .order_by(Report.created_at.desc())
    )
    reports = session.exec(statement).all()

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request, 
            "reports": enrich_reports(session, reports), 
            "current_user": get_current_user(request, session),
            "filter_msg": f"Reports in Venue: {venue_name}"
        }
    )
# ---------------- 報告詳情 (Report Detail) ----------------
@app.get("/reports/{report_id}", response_class=HTMLResponse)
def report_detail(request: Request, report_id: int, session: Session = Depends(get_session)):
    r = session.get(Report, report_id)
    if not r:
        raise HTTPException(status_code=404, detail="Report not found")
    
    user = session.get(User, r.user_id)
    meeting = session.get(LabMeeting, r.meeting_id) if r.meeting_id else None
    paper = session.get(Paper, r.paper_id) if r.paper_id else None
    tags = get_report_tags(session, r)
    comments = session.exec(select(Comment).where(Comment.report_id == r.id).order_by(Comment.created_at)).all()
    
    # 為每個評論載入使用者資訊
    enriched_comments = []
    for c in comments:
        c_user = session.get(User, c.user_id)
        enriched_comments.append({"c": c, "user": c_user})

    return templates.TemplateResponse(
        "report_detail.html",
        {
            "request": request,
            "report": r,
            "user": user,
            "meeting": meeting,
            "paper": paper,
            "tags": tags,
            "comments": enriched_comments,
            "current_user": get_current_user(request, session)
        }
    )

# ---------------- 新增報告 (Upload) ----------------
@app.get("/upload", response_class=HTMLResponse)
def upload_form(request: Request, session: Session = Depends(get_session)):
    current_user = get_current_user(request, session)
    if not current_user:
        return RedirectResponse(url="/login")
    
    meetings = session.exec(select(LabMeeting).order_by(LabMeeting.meeting_date.desc())).all()
    papers = session.exec(select(Paper)).all()
    return templates.TemplateResponse(
        "upload.html", 
        {"request": request, "meetings": meetings, "papers": papers, "current_user": current_user}
    )

@app.post("/upload")
async def create_report(request: Request, session: Session = Depends(get_session)):
    form = await request.form()
    current_user = get_current_user(request, session)
    if not current_user:
        return RedirectResponse(url="/login")

    # 1. 處理 Meeting
    meeting_id = None
    existing_meeting_id = form.get("existing_meeting_id")
    if existing_meeting_id and existing_meeting_id.isdigit():
        meeting_id = int(existing_meeting_id)
    else:
        # 創建新 Meeting
        m_title = form.get("meeting_title")
        if m_title:
            meeting = LabMeeting(
                meeting_title=m_title,
                meeting_location=form.get("meeting_location", ""),
                meeting_date=datetime.now().date() # 簡化處理，若有日期欄位請自行轉換
            )
            # 嘗試轉換日期
            if form.get("meeting_date"):
                try:
                    meeting.meeting_date = datetime.fromisoformat(form.get("meeting_date")).date()
                except: pass
            session.add(meeting)
            session.commit()
            session.refresh(meeting)
            meeting_id = meeting.id

    # 2. 處理 Paper
    paper_id = None
    existing_paper_id = form.get("existing_paper_id") or form.get("paper_id")
    if existing_paper_id and existing_paper_id.isdigit():
        paper_id = int(existing_paper_id)
    else:
        # 創建新 Paper
        p_title = form.get("paper_title")
        if p_title:
            paper = Paper(
                paper_title=p_title,
                published_year=int(form.get("published_year", 0)),
                published_month=int(form.get("published_month", 0)),
                journal_or_conference=form.get("journal_or_conference", "")
            )
            session.add(paper)
            session.commit()
            session.refresh(paper)
            paper_id = paper.id

            # 處理 Authors & Affiliations
            idx = 0
            while True:
                a_name = form.get(f"author_name_{idx}")
                a_affils = form.get(f"author_affiliations_{idx}")
                if not a_name: break
                
                author = session.exec(select(Author).where(Author.name == a_name)).first()
                if not author:
                    author = Author(name=a_name)
                    session.add(author)
                    session.commit()
                    session.refresh(author)
                
                # Link Author <-> Paper
                session.add(PaperAuthorLink(paper_id=paper.id, author_id=author.id))

                # Link Author <-> Affiliation
                if a_affils:
                    for aff_name in [x.strip() for x in a_affils.split(",") if x.strip()]:
                        aff = session.exec(select(Affiliation).where(Affiliation.name == aff_name)).first()
                        if not aff:
                            aff = Affiliation(name=aff_name)
                            session.add(aff)
                            session.commit()
                            session.refresh(aff)
                        
                        link_exists = session.exec(select(AuthorAffiliationLink).where(
                            AuthorAffiliationLink.author_id == author.id,
                            AuthorAffiliationLink.affiliation_id == aff.id
                        )).first()
                        if not link_exists:
                            session.add(AuthorAffiliationLink(author_id=author.id, affiliation_id=aff.id))
                session.commit()
                idx += 1

            # 處理 Tags
            tags_str = form.get("tags", "")
            if tags_str:
                for t_name in [x.strip() for x in tags_str.split(",") if x.strip()]:
                    tag = session.exec(select(Tag).where(Tag.name == t_name)).first()
                    if not tag:
                        tag = Tag(name=t_name)
                        session.add(tag)
                        session.commit()
                        session.refresh(tag)
                    session.add(PaperTag(paper_id=paper.id, tag_id=tag.id))
                session.commit()

    # 3. 創建 Report
    report = Report(
        report_title=form.get("report_title"),
        report_summary=form.get("report_summary", ""),
        slides_link=form.get("slides_link", ""),
        user_id=current_user.id,
        meeting_id=meeting_id if meeting_id else 1, # 若沒選會議，可能需要預設值或報錯
        paper_id=paper_id
    )
    session.add(report)
    session.commit()
    session.refresh(report)
    return RedirectResponse(url=f"/reports/{report.id}", status_code=303)

# ---------------- 編輯報告 (Edit) ----------------
@app.get("/reports/{report_id}/edit", response_class=HTMLResponse)
def edit_report_form(request: Request, report_id: int, session: Session = Depends(get_session)):
    current_user = get_current_user(request, session)
    if not current_user:
        return RedirectResponse(url="/login")

    report = session.get(Report, report_id)
    if not report or report.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="權限不足或報告不存在")

    meetings = session.exec(select(LabMeeting).order_by(LabMeeting.meeting_date.desc())).all()
    papers = session.exec(select(Paper)).all()
    
    current_paper = session.get(Paper, report.paper_id) if report.paper_id else None
    paper_tags = current_paper.tags if current_paper else []
    paper_authors = current_paper.authors if current_paper else []

    return templates.TemplateResponse(
        "edit_report.html",
        {
            "request": request,
            "report": report,
            "meetings": meetings,
            "papers": papers,
            "current_meeting_id": report.meeting_id,
            "current_paper_id": report.paper_id,
            "current_paper": current_paper,
            "paper_tags": ",".join([t.name for t in paper_tags]),
            "paper_authors": paper_authors,
            "current_user": current_user
        }
    )

@app.post("/reports/{report_id}/edit")
async def update_report(request: Request, report_id: int, session: Session = Depends(get_session)):
    current_user = get_current_user(request, session)
    if not current_user:
        return RedirectResponse(url="/login")

    report = session.get(Report, report_id)
    if not report or report.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="權限不足")

    form = await request.form()
    
    # Update Basic Info
    report.report_title = form.get("report_title")
    report.report_summary = form.get("report_summary")
    report.slides_link = form.get("slides_link")
    
    # Update Meeting
    m_id_raw = form.get("existing_meeting_id")
    if m_id_raw and m_id_raw.isdigit():
        report.meeting_id = int(m_id_raw)

    # Update Paper
    existing_paper_id = form.get("existing_paper_id")
    new_paper_title = form.get("paper_title")

    paper_to_update = None

    # 情境 A: 切換到現有的 Paper
    if existing_paper_id and existing_paper_id.isdigit():
        report.paper_id = int(existing_paper_id)
    
    # 情境 B: 編輯當前 Paper 或 創建新 Paper
    elif new_paper_title:
        if report.paper_id:
            paper_to_update = session.get(Paper, report.paper_id)
        
        if not paper_to_update:
            paper_to_update = Paper()
            session.add(paper_to_update)
            session.commit()
            session.refresh(paper_to_update)
            report.paper_id = paper_to_update.id
        
        # 更新 Paper 屬性
        paper_to_update.paper_title = new_paper_title
        paper_to_update.published_year = int(form.get("published_year", 0))
        paper_to_update.published_month = int(form.get("published_month", 0))
        paper_to_update.journal_or_conference = form.get("journal_or_conference", "")
        session.add(paper_to_update)
        session.commit()

        # 重建關聯 (Author & Tags)
        clear_paper_relations(session, paper_to_update.id)

        # 重建 Author
        idx = 0
        while True:
            a_name = form.get(f"author_name_{idx}")
            a_affils = form.get(f"author_affiliations_{idx}")
            if not a_name: break
            
            author = session.exec(select(Author).where(Author.name == a_name)).first()
            if not author:
                author = Author(name=a_name)
                session.add(author)
                session.commit()
                session.refresh(author)
            
            session.add(PaperAuthorLink(paper_id=paper_to_update.id, author_id=author.id))

            if a_affils:
                for aff_name in [x.strip() for x in a_affils.split(",") if x.strip()]:
                    aff = session.exec(select(Affiliation).where(Affiliation.name == aff_name)).first()
                    if not aff:
                        aff = Affiliation(name=aff_name)
                        session.add(aff)
                        session.commit()
                        session.refresh(aff)
                    link_exists = session.exec(select(AuthorAffiliationLink).where(
                        AuthorAffiliationLink.author_id == author.id,
                        AuthorAffiliationLink.affiliation_id == aff.id
                    )).first()
                    if not link_exists:
                        session.add(AuthorAffiliationLink(author_id=author.id, affiliation_id=aff.id))
            session.commit()
            idx += 1

        # 重建 Tags
        tags_str = form.get("tags", "")
        if tags_str:
            for t_name in [x.strip() for x in tags_str.split(",") if x.strip()]:
                tag = session.exec(select(Tag).where(Tag.name == t_name)).first()
                if not tag:
                    tag = Tag(name=t_name)
                    session.add(tag)
                    session.commit()
                    session.refresh(tag)
                session.add(PaperTag(paper_id=paper_to_update.id, tag_id=tag.id))
            session.commit()

    else:
        # 清空 Paper
        report.paper_id = None

    session.add(report)
    session.commit()
    return RedirectResponse(url=f"/reports/{report.id}", status_code=303)

# ---------------- 刪除報告 ----------------
# 修正 app/main.py 中的 delete_report

@app.post("/reports/{report_id}/delete")
def delete_report(request: Request, report_id: int, session: Session = Depends(get_session)):
    current_user = get_current_user(request, session)
    if not current_user:
        return RedirectResponse(url="/login")

    report = session.get(Report, report_id)
    if not report or report.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="權限不足")

    # --- 修正部分開始 ---
    # 先找出所有關聯的評論，然後逐一刪除
    comments = session.exec(select(Comment).where(Comment.report_id == report_id)).all()
    for comment in comments:
        session.delete(comment)
    # --- 修正部分結束 ---

    session.delete(report)
    session.commit()
    return RedirectResponse(url=f"/profile/{current_user.username}", status_code=303)
# ---------------- 評論功能 (Comment) ----------------
@app.post("/comments")
def create_comment(request: Request, report_id: int = Form(...), content: str = Form(...), session: Session = Depends(get_session)):
    current_user = get_current_user(request, session)
    if not current_user:
        return RedirectResponse(url="/login")
    
    c = Comment(report_id=report_id, user_id=current_user.id, content=content)
    session.add(c)
    session.commit()
    return RedirectResponse(url=f"/reports/{report_id}", status_code=303)

@app.post("/comments/{comment_id}/delete")
def delete_comment(request: Request, comment_id: int, session: Session = Depends(get_session)):
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

# ---------------- 個人頁面 (Profile) ----------------
@app.get("/profile/{username}", response_class=HTMLResponse)
def user_profile(request: Request, username: str, session: Session = Depends(get_session)):
    target_user = session.exec(select(User).where(User.username == username)).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    user_reports = session.exec(select(Report).where(Report.user_id == target_user.id).order_by(Report.created_at.desc())).all()
    user_comments = session.exec(select(Comment).where(Comment.user_id == target_user.id).order_by(Comment.created_at.desc())).all()

    enriched_reports = []
    for r in user_reports:
        meeting = session.get(LabMeeting, r.meeting_id)
        tags = get_report_tags(session, r)
        enriched_reports.append({"r": r, "meeting": meeting, "tags": tags})

    return templates.TemplateResponse(
        "profile.html",
        {
            "request": request,
            "target_user": target_user,
            "reports": enriched_reports,
            "comments": user_comments,
            "current_user": get_current_user(request, session)
        }
    )

# ---------------- 認證 (Auth) ----------------
@app.get("/register", response_class=HTMLResponse)
def register_form(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})

@app.post("/register")
def register(request: Request, username: str = Form(...), display_name: str = Form(None), session: Session = Depends(get_session)):
    exists = session.exec(select(User).where(User.username == username)).first()
    if exists:
        return templates.TemplateResponse("register.html", {"request": request, "error": "Username already exists"})
    
    u = User(username=username, display_name=display_name or username)
    session.add(u)
    session.commit()
    request.session["username"] = username
    return RedirectResponse(url="/", status_code=303)

@app.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
def login(request: Request, username: str = Form(...), session: Session = Depends(get_session)):
    user = session.exec(select(User).where(User.username == username)).first()
    if not user:
        # 自動註冊 (Demo 用)
        user = User(username=username, display_name=username)
        session.add(user)
        session.commit()
    
    request.session["username"] = username
    return RedirectResponse(url="/", status_code=303)

@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/")

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)