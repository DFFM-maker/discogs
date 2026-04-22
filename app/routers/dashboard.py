from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from app.database import get_db
from app.deps import get_current_user, template_ctx
from app.models.user import User
from app.models.wishlist import WishlistItem
from app.models.listing import Listing
from app.workers.scheduler import get_next_run, is_running
from app.services.scanner_service import get_scan_state

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
def index(request: Request):
    return HTMLResponse(headers={"Location": "/dashboard"}, status_code=302)


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    now = datetime.now(timezone.utc)
    yesterday = now - timedelta(hours=24)

    active_count = db.query(func.count(WishlistItem.id)).filter(
        WishlistItem.user_id == user.id,
        WishlistItem.active == True,
    ).scalar() or 0

    new_today = db.query(func.count(Listing.id)).join(WishlistItem).filter(
        WishlistItem.user_id == user.id,
        Listing.found_at >= yesterday,
        Listing.dismissed == False,
    ).scalar() or 0

    recent = (
        db.query(Listing)
        .join(WishlistItem)
        .filter(WishlistItem.user_id == user.id, Listing.dismissed == False)
        .order_by(desc(Listing.found_at))
        .limit(10)
        .all()
    )

    scan_state = get_scan_state()
    next_run = get_next_run()

    ctx = template_ctx(request)
    ctx.update({
        "user": user,
        "active_wishlist": active_count,
        "new_today": new_today,
        "recent_listings": recent,
        "scan_running": scan_state["running"],
        "last_scan_at": scan_state.get("last_run_at"),
        "next_run": next_run,
        "worker_ok": is_running(),
        "page": "dashboard",
        "now": now,
    })
    return templates.TemplateResponse("dashboard.html", ctx)
