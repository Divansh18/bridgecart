"""Record session delegation and request correlation on gateway audits.

Revision ID: 20261012_01
Revises: 20261011_01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261012_01"
down_revision: str | None = "20261011_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("tool_audit", "api_key_id", existing_type=sa.Integer(), nullable=True)
    op.add_column("tool_audit", sa.Column("session_id", sa.Integer()))
    op.add_column("tool_audit", sa.Column("credential_type", sa.String(24), nullable=False, server_default="api_key"))
    op.add_column("tool_audit", sa.Column("correlation_id", sa.String(36)))


def downgrade() -> None:
    # Delegated rows have no API key ID. A downgrade must never invent attribution.
    connection = op.get_bind()
    count = connection.scalar(sa.text("SELECT count(*) FROM tool_audit WHERE api_key_id IS NULL"))
    if count:
        raise RuntimeError("Cannot downgrade while delegated tool audit rows exist")
    op.drop_column("tool_audit", "correlation_id")
    op.drop_column("tool_audit", "credential_type")
    op.drop_column("tool_audit", "session_id")
    op.alter_column("tool_audit", "api_key_id", existing_type=sa.Integer(), nullable=False)
