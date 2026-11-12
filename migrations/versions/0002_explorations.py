"""Exploration jobs: one row per request, its plan, result and timings.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-12
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

JSON_TYPE = sa.JSON().with_variant(JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "explorations",
        sa.Column("id", sa.String(40), primary_key=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("stage", sa.String(16), nullable=False),
        sa.Column("lens", sa.String(32), nullable=False),
        sa.Column("source", sa.String(1), nullable=False),
        sa.Column("optical_evidence", sa.Boolean, nullable=False),
        sa.Column("cache_key", sa.String(64), nullable=False),
        sa.Column("area_bucket", sa.String(16), nullable=False),
        sa.Column("scenes_total", sa.Integer, nullable=False),
        sa.Column("plan_seconds", sa.Float, nullable=False),
        sa.Column("plan", JSON_TYPE, nullable=True),
        sa.Column("runner_id", sa.String(80), nullable=True),
        sa.Column("result", JSON_TYPE, nullable=True),
        sa.Column("error", JSON_TYPE, nullable=True),
        sa.Column("layer_urls", JSON_TYPE, nullable=False),
        sa.Column("timings", JSON_TYPE, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_explorations_status", "explorations", ["status"])
    op.create_index("ix_explorations_cache_key", "explorations", ["cache_key"])


def downgrade() -> None:
    op.drop_index("ix_explorations_cache_key", table_name="explorations")
    op.drop_index("ix_explorations_status", table_name="explorations")
    op.drop_table("explorations")
