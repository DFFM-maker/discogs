from typing import Optional
from pydantic import BaseModel, field_validator
from app.models.wishlist import CONDITION_CHOICES, FORMAT_CHOICES


class WishlistItemCreate(BaseModel):
    artist: str
    title: str
    discogs_release_id: Optional[int] = None
    notes: Optional[str] = None
    priority: int = 3
    max_price: Optional[float] = None
    currency: str = "EUR"
    country: Optional[str] = None
    format: Optional[str] = None
    min_condition: Optional[str] = None
    active: bool = True
    tags: list[str] = []
    ai_query: Optional[str] = None

    @field_validator("priority")
    @classmethod
    def priority_range(cls, v: int) -> int:
        if not 1 <= v <= 5:
            raise ValueError("Priority must be 1-5")
        return v

    @field_validator("min_condition")
    @classmethod
    def valid_condition(cls, v: Optional[str]) -> Optional[str]:
        if v and v not in CONDITION_CHOICES:
            raise ValueError(f"Condition must be one of {CONDITION_CHOICES}")
        return v


class AIParseRequest(BaseModel):
    query: str
