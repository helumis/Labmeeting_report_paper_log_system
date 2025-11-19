# main.py

from fastapi import FastAPI, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from sqlmodel import select, Session, SQLModel
from .config import settings
from .db import engine, create_db_and_tables, get_session
from .models import (
    User,
    LabMeeting,
    Paper,
    Report,
    Tag,
    Comment,
    Author,
    Affiliation,
    AuthorAffiliationLink,   # <-- 新增
    PaperAuthorLink,
    PaperTag
)

from typing import List, Optional
import uvicorn

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)
templates = Jinja2Templates(directory="templates")

# ---------------- startup ----------------
@app.on_event("startup")
def on_startup():
    create_db_and_tables()

# ---------------- helpers ----------------
def get_current_user(request: Request, session=Depends(get_session)):
    username = request.session.get("username")
    if not username:
        return None
    user = session.exec(select(User).where(User.username == username)).first()
    return user

def get_report_tags(session: Session, report: Report) -> List[Tag]:
    """
    取得 report 對應 paper 的 tags，若 report 沒有 paper 回傳空 list
    """
    if not report.paper_id:
        return []
    paper = session.get(Paper, report.paper_id)
    if not paper:
        return []
    # 使用 selectinload 或直接 access
    return paper.tags if hasattr(paper, "tags") else []

# ---------------- index ----------------
@app.get("/", response_class=HTMLResponse)
def index(request: Request, session = Depends(get_session)):
    reports = session.exec(select(Report).order_by(Report.created_at.desc())).all()
    enriched = []
    for r in reports:
        user = session.get(User, r.user_id) if r.user_id else None
        meeting = session.get(LabMeeting, r.meeting_id) if r.meeting_id else None
        tags = get_report_tags(session, r)
        enriched.append({"r": r, "user": user, "meeting": meeting, "tags": tags})
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "reports": enriched, "current_user": get_current_user(request, session)}
    )

# ---------------- report detail ----------------
@app.get("/reports/{report_id}", response_class=HTMLResponse)
def report_detail(request: Request, report_id: int, session = Depends(get_session)):
    r = session.get(Report, report_id)
    if not r:
        raise HTTPException(status_code=404, detail="Report not found")
    user = session.get(User, r.user_id) if r.user_id else None
    meeting = session.get(LabMeeting, r.meeting_id) if r.meeting_id else None
    tags = get_report_tags(session, r)
    comments = session.exec(select(Comment).where(Comment.report_id == r.id).order_by(Comment.created_at)).all()
    return templates.TemplateResponse(
        "report_detail.html",
        {"request": request, "report": r, "user": user, "meeting": meeting, "tags": tags, "comments": comments, "current_user": get_current_user(request, session)}
    )

# ---------------- upload ----------------
@app.get("/upload", response_class=HTMLResponse)
def upload_form(request: Request, session = Depends(get_session)):
    current_user = get_current_user(request, session)
    if not current_user:
        return RedirectResponse(url="/login")
    meetings = session.exec(select(LabMeeting).order_by(LabMeeting.meeting_date.desc())).all()
    papers = session.exec(select(Paper)).all()
    return templates.TemplateResponse(
        "upload.html", {"request": request, "meetings": meetings, "papers": papers, "current_user": current_user}
    )


@app.post("/upload")
async def create_report(request: Request, session=Depends(get_session)):
    from datetime import datetime

    form = await request.form()  # <--- async 取得表單
    username = request.session.get("username")
    user = session.exec(select(User).where(User.username == username)).first() if username else None

    # --------------------
    # 取得基本 Report 欄位
    # --------------------
    report_title = form.get("report_title")
    report_summary = form.get("report_summary", "")
    slides_link = form.get("slides_link", "")

    # --------------------
    # LabMeeting
    # --------------------
    meeting_id = None
    existing_meeting_id_raw = form.get("existing_meeting_id")
    existing_meeting_id = int(existing_meeting_id_raw) if existing_meeting_id_raw and existing_meeting_id_raw.isdigit() else None
    if existing_meeting_id:
        meeting_id = existing_meeting_id
    else:
        meeting_title = form.get("meeting_title")
        meeting_date = form.get("meeting_date")
        meeting_location = form.get("meeting_location")
        if meeting_title:
            meeting = LabMeeting(meeting_title=meeting_title, meeting_location=meeting_location)
            if meeting_date:
                try:
                    meeting.meeting_date = datetime.fromisoformat(meeting_date).date()
                except:
                    pass
            session.add(meeting)
            session.commit()
            session.refresh(meeting)
            meeting_id = meeting.id

    # --------------------
    # Paper
    # --------------------
    paper_id_raw = form.get("existing_paper_id") or form.get("paper_id")
    paper_id = int(paper_id_raw) if paper_id_raw and paper_id_raw.isdigit() else None

    # 新 Paper 欄位
    paper_title = form.get("paper_title")
    published_year = form.get("published_year")
    published_month = form.get("published_month")
    journal_or_conference = form.get("journal_or_conference")
    tags_raw = form.get("tags", "")

    if not paper_id and paper_title:
        paper = Paper(
            paper_title=paper_title,
            published_year=int(published_year) if published_year and published_year.isdigit() else 0,
            published_month=int(published_month) if published_month and published_month.isdigit() else 0,
            journal_or_conference=journal_or_conference or ""
        )
        session.add(paper)
        session.commit()
        session.refresh(paper)
        paper_id = paper.id

        # --------------------
        # Authors & Affiliations
        # --------------------
        author_idx = 0
        while True:
            author_name = form.get(f"author_name_{author_idx}")
            author_affils = form.get(f"author_affiliations_{author_idx}")
            if not author_name:
                break
            # 建立 Author
            author = session.exec(select(Author).where(Author.name == author_name)).first()
            if not author:
                author = Author(name=author_name)
                session.add(author)
                session.commit()
                session.refresh(author)
            # Affiliations
            if author_affils:
                for aff_name in [x.strip() for x in author_affils.split(",") if x.strip()]:
                    aff = session.exec(select(Affiliation).where(Affiliation.name == aff_name)).first()
                    if not aff:
                        aff = Affiliation(name=aff_name)
                        session.add(aff)
                        session.commit()
                        session.refresh(aff)
                    # Link author ↔ affiliation
                    link_exists = session.exec(
                        select(AuthorAffiliationLink).where(
                            AuthorAffiliationLink.author_id == author.id,
                            AuthorAffiliationLink.affiliation_id == aff.id
                        )
                    ).first()
                    if not link_exists:
                        session.add(AuthorAffiliationLink(author_id=author.id, affiliation_id=aff.id))
                        session.commit()
            # Link author ↔ paper
            link_exists = session.exec(
                select(PaperAuthorLink).where(
                    PaperAuthorLink.author_id == author.id,
                    PaperAuthorLink.paper_id == paper.id
                )
            ).first()
            if not link_exists:
                session.add(PaperAuthorLink(author_id=author.id, paper_id=paper.id))
                session.commit()
            author_idx += 1

        # --------------------
        # Tags
        # --------------------
        if tags_raw:
            for t_name in [x.strip() for x in tags_raw.split(",") if x.strip()]:
                tag = session.exec(select(Tag).where(Tag.name == t_name)).first()
                if not tag:
                    tag = Tag(name=t_name)
                    session.add(tag)
                    session.commit()
                    session.refresh(tag)
                # Link paper ↔ tag
                link_exists = session.exec(
                    select(PaperTag).where(
                        PaperTag.paper_id == paper.id,
                        PaperTag.tag_id == tag.id
                    )
                ).first()
                if not link_exists:
                    session.add(PaperTag(paper_id=paper.id, tag_id=tag.id))
                    session.commit()

    # --------------------
    # Create Report
    # --------------------
    r = Report(
        report_title=report_title,
        report_summary=report_summary,
        slides_link=slides_link,
        user_id=user.id if user else None,
        meeting_id=meeting_id,
        paper_id=paper_id
    )
    session.add(r)
    session.commit()
    session.refresh(r)

    return RedirectResponse(url=f"/reports/{r.id}", status_code=303)


# ---------------- register / login / logout ----------------
@app.get("/register", response_class=HTMLResponse)
def register_form(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})

@app.post("/register")
def register(request: Request, username: str = Form(...), display_name: str = Form(None), session = Depends(get_session)):
    exists = session.exec(select(User).where(User.username == username)).first()
    if exists:
        return templates.TemplateResponse("register.html", {"request": request, "error": "username exists"})
    u = User(username=username, display_name=display_name)
    session.add(u)
    session.commit()
    request.session["username"] = username
    return RedirectResponse(url="/", status_code=303)

@app.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
def login(request: Request, username: str = Form(...), session = Depends(get_session)):
    user = session.exec(select(User).where(User.username == username)).first()
    auto_created = False
    if not user:
        user = User(username=username, display_name=username)
        session.add(user)
        session.commit()
        auto_created = True
    request.session["username"] = username
    if auto_created:
        return templates.TemplateResponse("index.html", {"request": request, "current_user": user, "info": "已自動建立帳號"})
    return RedirectResponse(url="/", status_code=303)

@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/")

# ---------------- comment ----------------
@app.post("/comments")
def create_comment(request: Request, report_id: int = Form(...), content: str = Form(...), session = Depends(get_session)):
    username = request.session.get("username")
    user = session.exec(select(User).where(User.username == username)).first() if username else None
    if not user:
        return RedirectResponse(url="/login")
    c = Comment(report_id=report_id, user_id=user.id, content=content)
    session.add(c)
    session.commit()
    return RedirectResponse(url=f"/reports/{report_id}", status_code=303)

# ---------------- query_ui ----------------
@app.get("/query_ui", response_class=HTMLResponse)
def query_ui(request: Request, session=Depends(get_session)):
    return templates.TemplateResponse("query_ui.html", {"request": request, "current_user": get_current_user(request, session)})

# ---------------- dynamic query ----------------
FIELD_MAP = {
    "report_title": Report.report_title,
    "presenter": User.display_name,
    "paper_year": Paper.published_year,
    "paper_tag": Tag.name,
    "author_name": "author",
    "affiliation_name": "affiliation",
}

def apply_filter(query, f, col):
    op = f["op"]
    value = f["value"]
    if op == "contains":
        return query.where(col.ilike(f"%{value}%"))
    if op == "=":
        return query.where(col == value)
    if op == ">":
        return query.where(col > value)
    if op == ">=":
        return query.where(col >= value)
    if op == "<":
        return query.where(col < value)
    if op == "<=":
        return query.where(col <= value)
    return query

@app.post("/query")
def run_query(req: dict, session=Depends(get_session)):
    filters = req.get("filters", [])
    q = select(Report)
    joined = set()

    for f in filters:
        field = f["field"]
        if field in ["paper_tag", "author_name", "affiliation_name", "paper_year"] and "paper" not in joined:
            q = q.join(Paper, Paper.id == Report.paper_id)
            joined.add("paper")
        if field == "paper_tag" and "tag" not in joined:
            q = q.join(Tag, Tag.id == Paper.id)  # 這邏輯可按你的 join table 調整
            joined.add("tag")
        if field == "author_name" and "author" not in joined:
            q = q.join(Paper.authors)
            joined.add("author")
        if field == "affiliation_name" and "affiliation" not in joined:
            q = q.join(Paper.authors).join(Author.affiliations)
            joined.add("affiliation")
        if field == "presenter" and "presenter" not in joined:
            q = q.join(User, User.id == Report.user_id)
            joined.add("presenter")

    for f in filters:
        col_key = FIELD_MAP.get(f["field"])
        if col_key == "author":
            col = Author.name
        elif col_key == "affiliation":
            col = Affiliation.name
        else:
            col = col_key
        q = apply_filter(q, f, col)

    results = session.exec(q).all()
    enriched = []
    for r in results:
        user = session.get(User, r.user_id)
        meeting = session.get(LabMeeting, r.meeting_id)
        tags = get_report_tags(session, r)
        enriched.append({"r": r, "user": user, "meeting": meeting, "tags": tags})
    return enriched

# ---------------- main ----------------
if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
