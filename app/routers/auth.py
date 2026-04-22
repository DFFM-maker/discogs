from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.database import get_db
from app.deps import template_ctx
from app.services.auth_service import authenticate_user, record_login, record_logout

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    if request.session.get("user_id"):
        return RedirectResponse("/", status_code=302)
    ctx = template_ctx(request)
    ctx["error"] = None
    return templates.TemplateResponse("login.html", ctx)


@router.post("/login", response_class=HTMLResponse)
def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = authenticate_user(db, username, password)
    if not user:
        ctx = template_ctx(request)
        ctx["error"] = "Credenziali non valide."
        return templates.TemplateResponse("login.html", ctx, status_code=401)

    request.session["user_id"] = str(user.id)
    request.session["username"] = user.username
    request.session["is_admin"] = user.is_admin

    ip = request.client.host if request.client else ""
    record_login(db, user, ip)

    return RedirectResponse("/", status_code=302)


@router.post("/logout")
def logout(request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    request.session.clear()
    if user_id:
        record_logout(db, user_id)
    return RedirectResponse("/login", status_code=302)
