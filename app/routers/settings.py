from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.database import get_db
from app.deps import get_current_user, template_ctx
from app.models.user import User
from app.models.audit import AuditLog
from app.config import get_settings
from app.workers import scheduler as sched
from app.services import discogs_adapter, email_service
from app.services.claude_adapter import _is_available as claude_available

router = APIRouter(prefix="/settings")
templates = Jinja2Templates(directory="app/templates")
settings = get_settings()


@router.get("", response_class=HTMLResponse)
def settings_page(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Check integration statuses
    discogs_ok = bool(settings.discogs_token)
    claude_ok = claude_available()
    email_ok = bool(settings.smtp_user and settings.smtp_pass)

    recent_logs = (
        db.query(AuditLog)
        .order_by(AuditLog.created_at.desc())
        .limit(30)
        .all()
    )

    ctx = template_ctx(request)
    ctx.update({
        "user": user,
        "page": "settings",
        "discogs_ok": discogs_ok,
        "claude_ok": claude_ok,
        "email_ok": email_ok,
        "claude_enabled": settings.claude_enabled,
        "email_enabled": settings.email_enabled,
        "scan_interval": settings.scan_interval_minutes,
        "worker_running": sched.is_running(),
        "next_run": sched.get_next_run(),
        "recent_logs": recent_logs,
        "discogs_token_set": bool(settings.discogs_token),
        "smtp_host": settings.smtp_host,
        "smtp_port": settings.smtp_port,
        "smtp_user": settings.smtp_user,
        "mail_to": settings.mail_to,
    })
    return templates.TemplateResponse("settings/index.html", ctx)
