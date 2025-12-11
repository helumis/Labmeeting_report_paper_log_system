#auth.py
"""
認證路由
"""
from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session

from ..db import get_session
from ..services.user_service import UserService
from ..dependencies.auth import get_optional_user

router = APIRouter()
templates = Jinja2Templates(directory="templates")

@router.get("/register", response_class=HTMLResponse)
def register_form(request: Request):
    """註冊表單"""
    return templates.TemplateResponse("register.html", {"request": request})

@router.post("/register")
def register(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    display_name: str = Form(None),
    session: Session = Depends(get_session)
):
    """註冊新使用者"""
    try:
        user_service = UserService(session)
        user = user_service.register(username, password, display_name)
        
        # 註冊成功後直接登入
        request.session["user_id"] = user.id
        return RedirectResponse(url="/", status_code=303)
    
    except Exception as e:
        return templates.TemplateResponse("register.html", {
            "request": request,
            "error": str(e)
        })

@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    """登入表單"""
    return templates.TemplateResponse("login.html", {"request": request})

@router.post("/login")
def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    session: Session = Depends(get_session)
):
    """使用者登入"""
    try:
        user_service = UserService(session)
        user = user_service.authenticate(username, password)
        
        request.session["user_id"] = user.id
        return RedirectResponse(url="/", status_code=303)
    
    except Exception as e:
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": str(e)
        })

@router.get("/logout")
def logout(request: Request):
    """登出"""
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)