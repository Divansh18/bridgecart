from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, Integer, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column

from bridgecart.auth.models import utc_now
from bridgecart.db.base import Base


class UpstreamServer(Base):
    __tablename__ = "upstream_servers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    auth_type: Mapped[str] = mapped_column(String(16), nullable=False, default="none")
    header_name: Mapped[str | None] = mapped_column(String(80))
    credential_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary)
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class ToolAudit(Base):
    __tablename__ = "tool_audit"
    __table_args__ = (Index("ix_tool_audit_user_started", "user_id", "started_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    user_email: Mapped[str] = mapped_column(String(320), nullable=False)
    api_key_id: Mapped[int | None] = mapped_column(Integer)
    session_id: Mapped[int | None] = mapped_column(Integer)
    credential_type: Mapped[str] = mapped_column(String(24), nullable=False, default="api_key")
    correlation_id: Mapped[str | None] = mapped_column(String(36))
    server_id: Mapped[str | None] = mapped_column(String(36))
    server_name: Mapped[str | None] = mapped_column(String(100))
    original_tool_name: Mapped[str | None] = mapped_column(String(200))
    exposed_tool_name: Mapped[str] = mapped_column(String(200), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    outcome: Mapped[str] = mapped_column(String(24), nullable=False, default="started")
    error_category: Mapped[str | None] = mapped_column(String(40))
