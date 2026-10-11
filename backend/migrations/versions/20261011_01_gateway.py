"""Add upstream registry and immutable-attribution tool audit.

Revision ID: 20261011_01
Revises: 20261010_01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261011_01"
down_revision: str | None = "20261010_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "upstream_servers",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("url", sa.String(500), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("auth_type", sa.String(16), nullable=False),
        sa.Column("header_name", sa.String(80)),
        sa.Column("credential_encrypted", sa.LargeBinary()),
        sa.Column("removed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("auth_type IN ('none', 'bearer', 'header')", name="ck_upstream_auth_type"),
    )
    op.create_table(
        "tool_audit",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("user_email", sa.String(320), nullable=False),
        sa.Column("api_key_id", sa.Integer(), nullable=False),
        sa.Column("server_id", sa.String(36)),
        sa.Column("server_name", sa.String(100)),
        sa.Column("original_tool_name", sa.String(200)),
        sa.Column("exposed_tool_name", sa.String(200), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_ms", sa.Integer()),
        sa.Column("outcome", sa.String(24), nullable=False),
        sa.Column("error_category", sa.String(40)),
    )
    op.create_index("ix_tool_audit_user_started", "tool_audit", ["user_id", "started_at"])


def downgrade() -> None:
    op.drop_index("ix_tool_audit_user_started", table_name="tool_audit")
    op.drop_table("tool_audit")
    op.drop_table("upstream_servers")
