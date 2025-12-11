#filters.py
"""
篩選路由
"""
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select

from ..db import get_session
from ..models import (
    Report, Paper, Tag, Author, Affiliation,
    PaperTag, PaperAuthorLink, AuthorAffiliationLink
)
from ..services.query_service import QueryService
from ..dependencies.auth import get_optional_user

router = APIRouter()
templates = Jinja2Templates(directory="templates")

def render_filtered_reports(
    request: Request,
    session: Session,
    statement,
    filter_msg: str,
    current_user
):
    """通用的報告篩選渲染函數"""
    reports = session.exec(statement).all()
    query_service = QueryService(session)
    
    return templates.TemplateResponse("index.html", {
        "request": request,
        "reports": query_service.enrich_reports(reports),
        "current_user": current_user,
        "filter_msg": filter_msg
    })

@router.get("/tags/{tag_id}", response_class=HTMLResponse)
def filter_by_tag(
    request: Request,
    tag_id: int,
    session: Session = Depends(get_session),
    current_user = Depends(get_optional_user)
):
    """按標籤篩選"""
    tag = session.get(Tag, tag_id)
    if not tag:
        raise HTTPException(status_code=404, detail="標籤不存在")
    
    stmt = (
        select(Report)
        .join(Paper, Report.paper_id == Paper.id)
        .join(PaperTag, Paper.id == PaperTag.paper_id)
        .where(PaperTag.tag_id == tag_id)
        .order_by(Report.created_at.desc())
    )
    
    return render_filtered_reports(
        request, session, stmt, 
        f"Reports with Tag: {tag.name}",
        current_user
    )

@router.get("/authors/{author_id}", response_class=HTMLResponse)
def filter_by_author(
    request: Request,
    author_id: int,
    session: Session = Depends(get_session),
    current_user = Depends(get_optional_user)
):
    """按作者篩選"""
    author = session.get(Author, author_id)
    if not author:
        raise HTTPException(status_code=404, detail="作者不存在")
    
    stmt = (
        select(Report)
        .join(Paper, Report.paper_id == Paper.id)
        .join(PaperAuthorLink, Paper.id == PaperAuthorLink.paper_id)
        .where(PaperAuthorLink.author_id == author_id)
        .order_by(Report.created_at.desc())
    )
    
    return render_filtered_reports(
        request, session, stmt,
        f"Reports by Author: {author.name}",
        current_user
    )

@router.get("/affiliations/{aff_id}", response_class=HTMLResponse)
def filter_by_affiliation(
    request: Request,
    aff_id: int,
    session: Session = Depends(get_session),
    current_user = Depends(get_optional_user)
):
    """按機構篩選"""
    aff = session.get(Affiliation, aff_id)
    if not aff:
        raise HTTPException(status_code=404, detail="機構不存在")
    
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
    
    return render_filtered_reports(
        request, session, stmt,
        f"Reports from Affiliation: {aff.name}",
        current_user
    )

@router.get("/years/{year}", response_class=HTMLResponse)
def filter_by_year(
    request: Request,
    year: int,
    session: Session = Depends(get_session),
    current_user = Depends(get_optional_user)
):
    """按年份篩選"""
    stmt = (
        select(Report)
        .join(Paper, Report.paper_id == Paper.id)
        .where(Paper.published_year == year)
        .order_by(Report.created_at.desc())
    )
    
    return render_filtered_reports(
        request, session, stmt,
        f"Reports Published in: {year}",
        current_user
    )

@router.get("/venues/{venue_name:path}", response_class=HTMLResponse)
def filter_by_venue(
    request: Request,
    venue_name: str,
    session: Session = Depends(get_session),
    current_user = Depends(get_optional_user)
):
    """按期刊/會議篩選"""
    stmt = (
        select(Report)
        .join(Paper, Report.paper_id == Paper.id)
        .where(Paper.journal_or_conference == venue_name)
        .order_by(Report.created_at.desc())
    )
    
    return render_filtered_reports(
        request, session, stmt,
        f"Reports in Venue: {venue_name}",
        current_user
    )

@router.get("/search", response_class=HTMLResponse)
def search(
    request: Request,
    q: str,
    session: Session = Depends(get_session),
    current_user = Depends(get_optional_user)
):
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
            "current_user": current_user,
            "filter_msg": f"搜尋結果: '{q}' (找不到相關資料)"
        })
    
    stmt = (
        select(Report)
        .where(Report.paper_id.in_(paper_ids))
        .order_by(Report.created_at.desc())
    )
    
    reports = session.exec(stmt).all()
    query_service = QueryService(session)
    
    return templates.TemplateResponse("index.html", {
        "request": request,
        "reports": query_service.enrich_reports(reports),
        "current_user": current_user,
        "filter_msg": f"搜尋結果: '{q}' (共找到 {len(reports)} 篇)"
    })