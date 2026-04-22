from fastapi import APIRouter, Depends, Request, Query
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import desc
from app.database import get_db
from app.deps import get_current_user, template_ctx
from app.models.user import User
from app.models.wishlist import WishlistItem
from app.models.listing import Listing

router = APIRouter(prefix="/results")
templates = Jinja2Templates(directory="app/templates")


@router.get("", response_class=HTMLResponse)
def results_list(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    item_id: str = Query(None),
    condition: str = Query(None),
    show_dismissed: bool = Query(False),
    page: int = Query(1, ge=1),
):
    per_page = 50
    q = (
        db.query(Listing)
        .join(WishlistItem)
        .filter(WishlistItem.user_id == user.id)
    )
    if not show_dismissed:
        q = q.filter(Listing.dismissed == False)
    if item_id:
        q = q.filter(Listing.wishlist_item_id == item_id)
    if condition:
        q = q.filter(Listing.condition == condition)

    total = q.count()
    listings = q.order_by(desc(Listing.found_at)).offset((page - 1) * per_page).limit(per_page).all()

    wishlist_items = (
        db.query(WishlistItem)
        .filter(WishlistItem.user_id == user.id)
        .order_by(WishlistItem.artist)
        .all()
    )

    ctx = template_ctx(request)
    ctx.update({
        "user": user,
        "listings": listings,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": max(1, (total + per_page - 1) // per_page),
        "wishlist_items": wishlist_items,
        "filter_item_id": item_id or "",
        "filter_condition": condition or "",
        "show_dismissed": show_dismissed,
        "nav_page": "results",
    })
    return templates.TemplateResponse("results/list.html", ctx)


@router.post("/{listing_id}/dismiss")
def dismiss_listing(
    listing_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    listing = (
        db.query(Listing)
        .join(WishlistItem)
        .filter(Listing.id == listing_id, WishlistItem.user_id == user.id)
        .first()
    )
    if listing:
        listing.dismissed = True
        db.commit()
    # HTMX: return empty string to remove row
    return HTMLResponse("")
