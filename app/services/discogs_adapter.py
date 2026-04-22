"""
Discogs API adapter.

Rate limit: 60 req/min authenticated (personal token).
We stay at 45 req/min to be safe.

Search strategy per wishlist item:
  1. If discogs_release_id set: directly query marketplace for that release.
  2. Otherwise: search /database/search by artist+title, get top release IDs,
     then query marketplace for each (up to 3 releases).

Note: /marketplace/search is an undocumented but working endpoint used widely.
If it changes, update _marketplace_search() in this file only.
"""
import logging
import threading
import time
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlencode

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from app.config import get_settings

log = logging.getLogger(__name__)
settings = get_settings()

BASE_URL = "https://api.discogs.com"
MARKETPLACE_URL = "https://www.discogs.com/marketplace/listings"


class RateLimiter:
    """Simple token bucket: 45 req/min."""

    def __init__(self, rate: float = 45, per: float = 60.0):
        self.rate = rate
        self.per = per
        self._tokens = rate
        self._last = time.monotonic()
        self._lock = threading.Lock()

    def acquire(self) -> None:
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last
            self._last = now
            self._tokens = min(self.rate, self._tokens + elapsed * (self.rate / self.per))
            if self._tokens < 1:
                sleep_for = (1 - self._tokens) * (self.per / self.rate)
                time.sleep(sleep_for)
                self._tokens = 0
            else:
                self._tokens -= 1


_rate_limiter = RateLimiter()

_client: Optional[httpx.Client] = None


def _get_client() -> httpx.Client:
    global _client
    if _client is None or _client.is_closed:
        headers = {"User-Agent": settings.discogs_user_agent}
        if settings.discogs_token:
            headers["Authorization"] = f"Discogs token={settings.discogs_token}"
        _client = httpx.Client(
            base_url=BASE_URL,
            headers=headers,
            timeout=15.0,
        )
    return _client


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=2, max=30),
    retry=retry_if_exception_type((httpx.TimeoutException, httpx.ConnectError)),
)
def _get(path: str, params: dict | None = None) -> dict:
    _rate_limiter.acquire()
    client = _get_client()
    resp = client.get(path, params=params)
    if resp.status_code == 429:
        retry_after = int(resp.headers.get("Retry-After", "60"))
        log.warning("Discogs rate limited, sleeping %ds", retry_after)
        time.sleep(retry_after)
        resp = client.get(path, params=params)
    resp.raise_for_status()
    return resp.json()


def search_releases(artist: str, title: str, per_page: int = 5) -> list[dict]:
    """Search releases in Discogs database, return list of {id, title, year}."""
    try:
        data = _get("/database/search", {
            "artist": artist,
            "release_title": title,
            "type": "release",
            "per_page": per_page,
            "page": 1,
        })
        results = data.get("results", [])
        return [
            {
                "id": r.get("id"),
                "title": r.get("title", ""),
                "year": r.get("year", ""),
                "country": r.get("country", ""),
                "format": r.get("format", []),
                "label": r.get("label", []),
            }
            for r in results
            if r.get("id")
        ]
    except Exception as exc:
        log.error("Discogs database search failed: artist=%s title=%s err=%s", artist, title, exc)
        return []


def _marketplace_search(release_id: int, filters: dict) -> list[dict]:
    """
    Search marketplace listings for a given release_id.
    Uses /marketplace/search (widely used, not officially documented).
    Falls back to empty list on 404/403.
    """
    params = {"release_id": release_id, "per_page": 50, "page": 1}
    if filters.get("currency"):
        params["currency"] = filters["currency"]
    if filters.get("condition"):
        params["media_condition"] = filters["condition"]
    if filters.get("ships_from"):
        params["ships_from"] = filters["ships_from"]

    try:
        data = _get("/marketplace/search", params)
        return data.get("listings", [])
    except httpx.HTTPStatusError as e:
        if e.response.status_code in (404, 403):
            log.debug("Marketplace search 404/403 for release %d, skipping", release_id)
            return []
        raise


def get_listings_for_item(
    artist: str,
    title: str,
    discogs_release_id: Optional[int],
    max_price: Optional[float],
    currency: str,
    min_condition: Optional[str],
    country: Optional[str],
    fmt: Optional[str],
) -> list[dict]:
    """
    Main entry point: return filtered marketplace listings for a wishlist item.
    Each listing dict has keys: listing_id, release_id, seller, seller_feedback,
    price, currency, condition, sleeve_condition, ships_from, url.
    """
    filters = {"currency": currency}
    if country:
        filters["ships_from"] = country

    release_ids: list[int] = []
    if discogs_release_id:
        release_ids = [discogs_release_id]
    else:
        releases = search_releases(artist, title, per_page=5)
        release_ids = [r["id"] for r in releases[:3]]

    if not release_ids:
        log.debug("No release IDs found for %s - %s", artist, title)
        return []

    CONDITION_RANK = {"M": 7, "NM": 6, "VG+": 5, "VG": 4, "G+": 3, "G": 2, "F": 1, "P": 0}
    min_rank = CONDITION_RANK.get(min_condition, 0) if min_condition else 0

    all_listings: list[dict] = []

    for rid in release_ids:
        raw = _marketplace_search(rid, filters)
        for item in raw:
            try:
                listing = _normalize_listing(item, rid)
                if not listing:
                    continue
                # Filter by condition
                item_rank = CONDITION_RANK.get(listing["condition"], -1)
                if item_rank < min_rank:
                    continue
                # Filter by price
                if max_price and listing["price"] > max_price:
                    continue
                # Filter by format
                if fmt and listing.get("format") and fmt.lower() not in listing["format"].lower():
                    continue
                all_listings.append(listing)
            except Exception as exc:
                log.debug("Error normalizing listing: %s", exc)
                continue

    return all_listings


def _normalize_listing(raw: dict, release_id: int) -> dict | None:
    """Normalize a raw Discogs marketplace listing to our schema."""
    listing_id = raw.get("id")
    if not listing_id:
        return None

    price_data = raw.get("price", {})
    price_value = price_data.get("value", 0) if isinstance(price_data, dict) else price_data

    seller = raw.get("seller", {})
    seller_name = seller.get("username", "") if isinstance(seller, dict) else ""
    seller_stats = seller.get("stats", {}) if isinstance(seller, dict) else {}
    feedback_pct = None
    if seller_stats and isinstance(seller_stats, dict):
        total = seller_stats.get("total", 0)
        positive = seller_stats.get("rating", 0)
        if total:
            feedback_pct = round(float(positive), 1)

    release_info = raw.get("release", {}) or {}
    description = raw.get("description", "")
    ships_from = raw.get("ships_from", "")

    return {
        "listing_id": int(listing_id),
        "release_id": release_id,
        "seller": seller_name,
        "seller_feedback": feedback_pct,
        "price": float(price_value),
        "currency": price_data.get("currency", "USD") if isinstance(price_data, dict) else "USD",
        "condition": raw.get("condition", ""),
        "sleeve_condition": raw.get("sleeve_condition", ""),
        "ships_from": ships_from,
        "format": description,
        "url": f"https://www.discogs.com/sell/item/{listing_id}",
    }
