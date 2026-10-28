"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-10-28

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "weekly_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("model", sa.String(100), nullable=True),
        sa.Column("prompt_version", sa.String(50), nullable=True),
        sa.Column("signals_count", sa.Integer(), nullable=False),
        sa.Column("source_counts", sa.JSON(), nullable=False),
        sa.Column("raw_response", sa.Text(), nullable=True),
        sa.Column("summary", sa.JSON(), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivery_status", sa.String(30), nullable=False),
    )

    op.create_table(
        "signals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source", sa.String(30), nullable=False),
        sa.Column("category", sa.String(50), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False, unique=True),
        sa.Column("content_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("relevance", sa.Float(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "sent_in_run_id",
            sa.Integer(),
            sa.ForeignKey("weekly_runs.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_signals_source", "signals", ["source"])
    op.create_index("ix_signals_category", "signals", ["category"])
    op.create_index("ix_signals_published_at", "signals", ["published_at"])
    op.create_index("ix_signals_created_at", "signals", ["created_at"])


def downgrade() -> None:
    op.drop_table("signals")
    op.drop_table("weekly_runs")
