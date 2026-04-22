import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.database import Base

# Event types
LOGIN = "LOGIN"
LOGOUT = "LOGOUT"
SCAN_START = "SCAN_START"
SCAN_DONE = "SCAN_DONE"
SCAN_ERROR = "SCAN_ERROR"
EMAIL_SENT = "EMAIL_SENT"
EMAIL_ERROR = "EMAIL_ERROR"
CLAUDE_CALL = "CLAUDE_CALL"
CLAUDE_ERROR = "CLAUDE_ERROR"
DISCOGS_ERROR = "DISCOGS_ERROR"


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    meta: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False, index=True
    )

    user = relationship("User", back_populates="audit_logs")
