"""
Claude adapter — AI features.

Two functions only:
  1. parse_query(text) → structured filters dict
  2. rank_results(query, listings) → sorted list with score + explanation

Claude never invents data. It only interprets user intent and ranks
existing listings that Discogs returned.

Disable entirely via CLAUDE_ENABLED=false.
"""
import json
import logging
from typing import Optional

from app.config import get_settings

log = logging.getLogger(__name__)
settings = get_settings()

PARSE_SYSTEM = """You are a Discogs marketplace search assistant.
Convert the user's natural language LP search request into structured JSON filters.

Return ONLY valid JSON with these optional keys:
{
  "artist": string,
  "title": string,
  "max_price": number,
  "currency": "EUR"|"USD"|"GBP",
  "min_condition": "M"|"NM"|"VG+"|"VG"|"G+"|"G",
  "country": string (ISO country code or full name),
  "format": "LP"|"12\""|"7\""|"EP"|"Album",
  "notes": string (any extra context to keep)
}

Omit keys that are not mentioned. Do not invent information.
Respond with JSON only, no explanation."""

RANK_SYSTEM = """You are a Discogs marketplace result ranker.
Given a search intent and a list of listings, return a JSON array of objects:
[{"listing_id": number, "score": 0.0-1.0, "explanation": "one short sentence"}]

Score based on relevance to the query (condition match, price, origin, etc.).
Sort by score descending. Include all listings. Be concise."""


def _get_client():
    try:
        import anthropic
        return anthropic.Anthropic(api_key=settings.claude_api_key)
    except ImportError:
        raise RuntimeError("anthropic package not installed")


def _is_available() -> bool:
    return (
        settings.claude_enabled
        and bool(settings.claude_api_key)
    )


def parse_query(text: str) -> dict:
    """
    Parse natural language query into structured filters.
    Returns {} on failure (caller should use manual filters).
    """
    if not _is_available():
        log.debug("Claude disabled or no API key, skipping parse_query")
        return {}

    try:
        client = _get_client()
        resp = client.messages.create(
            model=settings.claude_model,
            max_tokens=settings.claude_max_tokens,
            timeout=settings.claude_timeout_seconds,
            system=PARSE_SYSTEM,
            messages=[{"role": "user", "content": text}],
        )
        raw = resp.content[0].text.strip()
        # Strip markdown code block if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        result = json.loads(raw)
        log.info("Claude parse_query OK: input=%r output=%r", text, result)
        return result
    except Exception as exc:
        log.error("Claude parse_query failed: %s", exc)
        return {}


def rank_results(query: str, listings: list[dict]) -> list[dict]:
    """
    Rank listings by relevance to query.
    Returns listings list with added 'ai_score' and 'ai_explanation' keys.
    On failure returns listings unchanged.
    """
    if not _is_available() or not listings:
        return listings

    # Truncate to 20 listings to keep token usage bounded
    to_rank = listings[:20]

    simplified = [
        {
            "listing_id": l["listing_id"],
            "price": l["price"],
            "currency": l["currency"],
            "condition": l["condition"],
            "ships_from": l.get("ships_from", ""),
            "seller": l.get("seller", ""),
        }
        for l in to_rank
    ]

    prompt = f"Search intent: {query}\n\nListings:\n{json.dumps(simplified, ensure_ascii=False)}"

    try:
        client = _get_client()
        resp = client.messages.create(
            model=settings.claude_model,
            max_tokens=settings.claude_max_tokens,
            timeout=settings.claude_timeout_seconds,
            system=RANK_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = resp.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        rankings = json.loads(raw)
        score_map = {r["listing_id"]: r for r in rankings}

        enriched = []
        for l in listings:
            ranked = score_map.get(l["listing_id"], {})
            enriched.append({
                **l,
                "ai_score": ranked.get("score"),
                "ai_explanation": ranked.get("explanation"),
            })
        # Sort ranked ones first, then unranked
        enriched.sort(key=lambda x: x.get("ai_score") or -1, reverse=True)
        log.info("Claude rank_results OK: %d listings ranked", len(to_rank))
        return enriched
    except Exception as exc:
        log.error("Claude rank_results failed: %s", exc)
        return listings
