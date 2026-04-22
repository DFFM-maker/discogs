import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import desc
from app.database import get_db
from app.deps import get_current_user, template_ctx
from app.models.user import User
from app.models.wishlist import WishlistItem, CONDITION_CHOICES, FORMAT_CHOICES
from app.models.listing import Listing
from app.services.claude_adapter import parse_query
from app.models.audit import AuditLog, CLAUDE_CALL, CLAUDE_ERROR

router = APIRouter(prefix="/wishlist")
templates = Jinja2Templates(directory="app/templates")


def _get_item_or_404(db: Session, item_id: str, user: User) -> WishlistItem:
    item = db.query(WishlistItem).filter(
        WishlistItem.id == item_id,
        WishlistItem.user_id == user.id,
    ).first()
    if not item:
        raise HTTPException(404, "Item not found")
    return item


@router.get("", response_class=HTMLResponse)
def wishlist_list(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    items = (
        db.query(WishlistItem)
        .filter(WishlistItem.user_id == user.id)
        .order_by(desc(WishlistItem.priority), WishlistItem.artist)
        .all()
    )
    ctx = template_ctx(request)
    ctx.update({"user": user, "items": items, "page": "wishlist"})
    return templates.TemplateResponse("wishlist/list.html", ctx)


@router.get("/new", response_class=HTMLResponse)
def wishlist_new(
    request: Request,
    user: User = Depends(get_current_user),
):
    ctx = template_ctx(request)
    ctx.update({
        "user": user,
        "item": None,
        "conditions": CONDITION_CHOICES,
        "formats": FORMAT_CHOICES,
        "page": "wishlist",
        "error": None,
    })
    return templates.TemplateResponse("wishlist/form.html", ctx)


@router.post("/new", response_class=HTMLResponse)
def wishlist_create(
    request: Request,
    artist: str = Form(...),
    title: str = Form(...),
    discogs_release_id: str = Form(""),
    notes: str = Form(""),
    priority: int = Form(3),
    max_price: str = Form(""),
    currency: str = Form("EUR"),
    country: str = Form(""),
    format: str = Form(""),
    min_condition: str = Form(""),
    active: bool = Form(True),
    tags: str = Form(""),
    ai_query: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Parse AI query if provided
    ai_filters = None
    if ai_query.strip():
        try:
            ai_filters = parse_query(ai_query.strip()) or None
            db.add(AuditLog(event=CLAUDE_CALL, user_id=user.id, meta={"query": ai_query}))
        except Exception as exc:
            db.add(AuditLog(event=CLAUDE_ERROR, user_id=user.id, meta={"error": str(exc)}))

    item = WishlistItem(
        id=uuid.uuid4(),
        user_id=user.id,
        artist=artist.strip(),
        title=title.strip(),
        discogs_release_id=int(discogs_release_id) if discogs_release_id.strip() else None,
        notes=notes.strip() or None,
        priority=max(1, min(5, priority)),
        max_price=float(max_price) if max_price.strip() else None,
        currency=currency or "EUR",
        country=country.strip() or None,
        format=format.strip() or None,
        min_condition=min_condition.strip() or None,
        active=active,
        tags=[t.strip() for t in tags.split(",") if t.strip()],
        ai_query=ai_query.strip() or None,
        ai_filters=ai_filters,
    )
    db.add(item)
    db.commit()
    return RedirectResponse("/wishlist", status_code=302)


@router.get("/{item_id}", response_class=HTMLResponse)
def wishlist_detail(
    item_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    item = _get_item_or_404(db, item_id, user)
    listings = (
        db.query(Listing)
        .filter(Listing.wishlist_item_id == item.id, Listing.dismissed == False)
        .order_by(desc(Listing.found_at))
        .limit(50)
        .all()
    )
    ctx = template_ctx(request)
    ctx.update({"user": user, "item": item, "listings": listings, "page": "wishlist"})
    return templates.TemplateResponse("wishlist/detail.html", ctx)


@router.get("/{item_id}/edit", response_class=HTMLResponse)
def wishlist_edit(
    item_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    item = _get_item_or_404(db, item_id, user)
    ctx = template_ctx(request)
    ctx.update({
        "user": user,
        "item": item,
        "conditions": CONDITION_CHOICES,
        "formats": FORMAT_CHOICES,
        "page": "wishlist",
        "error": None,
    })
    return templates.TemplateResponse("wishlist/form.html", ctx)


@router.post("/{item_id}/edit", response_class=HTMLResponse)
def wishlist_update(
    item_id: str,
    request: Request,
    artist: str = Form(...),
    title: str = Form(...),
    discogs_release_id: str = Form(""),
    notes: str = Form(""),
    priority: int = Form(3),
    max_price: str = Form(""),
    currency: str = Form("EUR"),
    country: str = Form(""),
    format: str = Form(""),
    min_condition: str = Form(""),
    active: bool = Form(True),
    tags: str = Form(""),
    ai_query: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    item = _get_item_or_404(db, item_id, user)

    ai_filters = item.ai_filters
    if ai_query.strip() and ai_query.strip() != (item.ai_query or ""):
        try:
            ai_filters = parse_query(ai_query.strip()) or None
            db.add(AuditLog(event=CLAUDE_CALL, user_id=user.id, meta={"query": ai_query}))
        except Exception as exc:
            db.add(AuditLog(event=CLAUDE_ERROR, user_id=user.id, meta={"error": str(exc)}))

    item.artist = artist.strip()
    item.title = title.strip()
    item.discogs_release_id = int(discogs_release_id) if discogs_release_id.strip() else None
    item.notes = notes.strip() or None
    item.priority = max(1, min(5, priority))
    item.max_price = float(max_price) if max_price.strip() else None
    item.currency = currency or "EUR"
    item.country = country.strip() or None
    item.format = format.strip() or None
    item.min_condition = min_condition.strip() or None
    item.active = active
    item.tags = [t.strip() for t in tags.split(",") if t.strip()]
    item.ai_query = ai_query.strip() or None
    item.ai_filters = ai_filters
    item.updated_at = datetime.now(timezone.utc)
    db.commit()
    return RedirectResponse(f"/wishlist/{item_id}", status_code=302)


@router.post("/{item_id}/toggle")
def wishlist_toggle(
    item_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    item = _get_item_or_404(db, item_id, user)
    item.active = not item.active
    item.updated_at = datetime.now(timezone.utc)
    db.commit()
    # HTMX: return updated row partial
    ctx = template_ctx(request)
    ctx.update({"user": user, "item": item})
    return templates.TemplateResponse("_partials/wishlist_row.html", ctx)


@router.post("/{item_id}/delete")
def wishlist_delete(
    item_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    item = _get_item_or_404(db, item_id, user)
    db.delete(item)
    db.commit()
    return RedirectResponse("/wishlist", status_code=302)
