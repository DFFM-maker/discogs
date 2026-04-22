"""
Scanner service: orchestrates Discogs polling for all active wishlist items.

Called by the APScheduler job and by the manual trigger endpoint.
"""
import logging
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.wishlist import WishlistItem
from app.models.listing import Listing
from app.models.audit import AuditLog, SCAN_START, SCAN_DONE, SCAN_ERROR, EMAIL_SENT, EMAIL_ERROR
from app.services import discogs_adapter, email_service

log = logging.getLogger(__name__)

# Shared state for status polling
_scan_state: dict = {
    "running": False,
    "last_run_at": None,
    "last_run_found": 0,
    "last_error": None,
}


def get_scan_state() -> dict:
    return dict(_scan_state)


def scan_all(db: Session | None = None) -> dict:
    """
    Scan all active wishlist items. Returns summary dict.
    Opens its own DB session if none provided (for scheduler calls).
    """
    own_session = db is None
    if own_session:
        db = SessionLocal()

    _scan_state["running"] = True
    _scan_state["last_error"] = None

    total_new = 0
    errors = 0

    try:
        items = db.query(WishlistItem).filter(WishlistItem.active == True).all()
        log.info("Scan started: %d active items", len(items))
        db.add(AuditLog(event=SCAN_START, meta={"item_count": len(items)}))
        db.commit()

        for item in items:
            try:
                new_count = scan_item(item, db)
                total_new += new_count
            except Exception as exc:
                errors += 1
                log.error("Scan error for item %s: %s", item.id, exc)
                db.add(AuditLog(
                    event=SCAN_ERROR,
                    meta={"item_id": str(item.id), "error": str(exc)},
                ))
                db.commit()

        _scan_state["last_run_at"] = datetime.now(timezone.utc).isoformat()
        _scan_state["last_run_found"] = total_new
        db.add(AuditLog(event=SCAN_DONE, meta={"new_listings": total_new, "errors": errors}))
        db.commit()
        log.info("Scan done: new=%d errors=%d", total_new, errors)

    except Exception as exc:
        _scan_state["last_error"] = str(exc)
        log.exception("Scan failed: %s", exc)
    finally:
        _scan_state["running"] = False
        if own_session:
            db.close()

    return {"new_listings": total_new, "errors": errors}


def scan_item(item: WishlistItem, db: Session) -> int:
    """Scan a single wishlist item. Returns count of new listings found."""
    # Build effective filters (AI filters override manual if present)
    ai = item.ai_filters or {}
    artist = ai.get("artist") or item.artist
    title = ai.get("title") or item.title
    max_price = ai.get("max_price") or (float(item.max_price) if item.max_price else None)
    currency = ai.get("currency") or item.currency
    min_condition = ai.get("min_condition") or item.min_condition
    country = ai.get("country") or item.country
    fmt = ai.get("format") or item.format

    listings = discogs_adapter.get_listings_for_item(
        artist=artist,
        title=title,
        discogs_release_id=item.discogs_release_id,
        max_price=max_price,
        currency=currency,
        min_condition=min_condition,
        country=country,
        fmt=fmt,
    )

    # Deduplicate against already seen listing IDs for this item
    existing_ids = {
        row.discogs_listing_id
        for row in db.query(Listing.discogs_listing_id)
        .filter(Listing.wishlist_item_id == item.id)
        .all()
    }

    new_listings: list[Listing] = []
    for raw in listings:
        if raw["listing_id"] in existing_ids:
            continue
        listing = Listing(
            wishlist_item_id=item.id,
            discogs_listing_id=raw["listing_id"],
            discogs_release_id=raw.get("release_id"),
            seller_username=raw.get("seller"),
            seller_feedback=raw.get("seller_feedback"),
            price=raw["price"],
            currency=raw["currency"],
            condition=raw.get("condition"),
            sleeve_condition=raw.get("sleeve_condition"),
            ships_from=raw.get("ships_from"),
            url=raw["url"],
            ai_score=raw.get("ai_score"),
            ai_explanation=raw.get("ai_explanation"),
        )
        new_listings.append(listing)
        db.add(listing)

    # Update last_scanned_at
    item.last_scanned_at = datetime.now(timezone.utc)
    db.commit()

    # Send email for new listings
    if new_listings:
        # Refresh to get IDs assigned
        db.refresh(item)
        ok = email_service.send_new_listings(item, new_listings)
        now = datetime.now(timezone.utc)
        event = EMAIL_SENT if ok else EMAIL_ERROR
        for l in new_listings:
            if ok:
                l.notified_at = now
        db.add(AuditLog(
            event=event,
            meta={"item_id": str(item.id), "count": len(new_listings)},
        ))
        db.commit()
        log.info("New listings for %s/%s: %d", artist, title, len(new_listings))

    return len(new_listings)
