from fastapi import FastAPI, Request, Depends, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from sqlmodel import select
from .config import settings
from .db import engine, create_db_and_tables, get_session
from .models import User, LabMeeting, Paper, Report, Tag, ReportTag, Comment
from typing import List
import uvicorn

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)

templates = Jinja2Templates(directory="templates")

# create tables at startup
@app.on_event("startup")
def on_startup():
    create_db_and_tables()

# helper
def get_current_user(request: Request, session = Depends(get_session)):
    username = request.session.get("username")
    if not username:
        return None
    user = session.exec(select(User).where(User.username == username)).first()
    return user

# Index - list reports
@app.get("/", response_class=HTMLResponse)
def index(request: Request, session = Depends(get_session)):
    q = select(Report).order_by(Report.created_at.desc())
    reports = session.exec(q).all()
    # fetch related small data
    enriched = []
    for r in reports:
        user = session.exec(select(User).where(User.id == r.user_id)).first()
        meeting = session.exec(select(LabMeeting).where(LabMeeting.id == r.meeting_id)).first()
        # tags
        rt_q = select(ReportTag).where(ReportTag.report_id == r.id)
        rtags = session.exec(rt_q).all()
        tags = []
        for rt in rtags:
            t = session.exec(select(Tag).where(Tag.id == rt.tag_id)).first()
            if t:
                tags.append(t)
        enriched.append({"r": r, "user": user, "meeting": meeting, "tags": tags})
    return templates.TemplateResponse("index.html", {"request": request, "reports": enriched, "current_user": get_current_user(request, session)})

# Report detail
@app.get("/reports/{report_id}", response_class=HTMLResponse)
def report_detail(request: Request, report_id: int, session = Depends(get_session)):
    r = session.get(Report, report_id)
    if not r:
        raise HTTPException(status_code=404, detail="Report not found")
    user = session.get(User, r.user_id) if r.user_id else None
    meeting = session.get(LabMeeting, r.meeting_id) if r.meeting_id else None
    # tags
    rt_q = select(ReportTag).where(ReportTag.report_id == r.id)
    rtags = session.exec(rt_q).all()
    tags = [session.get(Tag, rt.tag_id) for rt in rtags]
    # papers? (not linked in simplified schema but could query)
    comments = session.exec(select(Comment).where(Comment.report_id == r.id).order_by(Comment.created_at)).all()
    return templates.TemplateResponse("report_detail.html", {"request": request, "report": r, "user": user, "meeting": meeting, "tags": tags, "comments": comments, "current_user": get_current_user(request, session)})

# Tag filter
@app.get("/tags/{tag_name}", response_class=HTMLResponse)
def tag_filter(request: Request, tag_name: str, session = Depends(get_session)):
    t = session.exec(select(Tag).where(Tag.name == tag_name)).first()
    if not t:
        return templates.TemplateResponse("tag_list.html", {"request": request, "tag": tag_name, "reports": [], "current_user": get_current_user(request, session)})
    rt_q = select(ReportTag).where(ReportTag.tag_id == t.id)
    rts = session.exec(rt_q).all()
    reports = [session.get(Report, rt.report_id) for rt in rts]
    enriched = []
    for r in reports:
        user = session.get(User, r.user_id) if r.user_id else None
        meeting = session.get(LabMeeting, r.meeting_id) if r.meeting_id else None
        enriched.append({"r": r, "user": user, "meeting": meeting, "tags": [t]})
    return templates.TemplateResponse("tag_list.html", {"request": request, "tag": tag_name, "reports": enriched, "current_user": get_current_user(request, session)})

# Upload form
@app.get("/upload", response_class=HTMLResponse)
def upload_form(request: Request, session = Depends(get_session)):
    current_user = get_current_user(request, session)
    if not current_user:
        return RedirectResponse(url="/login")
    meetings = session.exec(select(LabMeeting).order_by(LabMeeting.meeting_date.desc())).all()
    return templates.TemplateResponse("upload.html", {"request": request, "meetings": meetings, "current_user": current_user})

# Create report (form post)
@app.post("/upload")
def create_report(request: Request,
                  report_title: str = Form(...),
                  report_summary: str = Form(""),
                  slides_link: str = Form(None),
                  meeting_title: str = Form(None),
                  meeting_date: str = Form(None),
                  meeting_location: str = Form(None),
                  tags: str = Form(""),
                  session = Depends(get_session)):
    # user
    username = request.session.get("username")
    user = None
    if username:
        user = session.exec(select(User).where(User.username == username)).first()
    # optionally create meeting
    meeting_id = None
    if meeting_title:
        meeting = LabMeeting(meeting_title=meeting_title, meeting_location=meeting_location)
        if meeting_date:
            try:
                from datetime import datetime
                meeting.meeting_date = datetime.fromisoformat(meeting_date).date()
            except:
                pass
        session.add(meeting)
        session.commit()
        session.refresh(meeting)
        meeting_id = meeting.id
    # create report
    r = Report(report_title=report_title, report_summary=report_summary, slides_link=slides_link, user_id=user.id if user else None, meeting_id=meeting_id)
    session.add(r)
    session.commit()
    session.refresh(r)
    # tags - input as comma separated
    if tags:
        tag_names = [t.strip() for t in tags.split(",") if t.strip()]
        for tn in tag_names:
            t = session.exec(select(Tag).where(Tag.name == tn)).first()
            if not t:
                t = Tag(name=tn)
                session.add(t)
                session.commit()
                session.refresh(t)
            rt = ReportTag(report_id=r.id, tag_id=t.id)
            session.add(rt)
        session.commit()
    return RedirectResponse(url=f"/reports/{r.id}", status_code=303)

# Register (simple)
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

# Login
@app.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
def login(request: Request, username: str = Form(...), session = Depends(get_session)):
    user = session.exec(select(User).where(User.username == username)).first()
    if not user:
        # auto register (convenience)
        user = User(username=username)
        session.add(user)
        session.commit()
    request.session["username"] = username
    return RedirectResponse(url="/", status_code=303)

# Logout
@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/")

# Create comment
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

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
