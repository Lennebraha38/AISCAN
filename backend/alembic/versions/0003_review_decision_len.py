"""review_decisions.decision uzunlugunu genislet (SECOND_OPINION = 14 karakter)

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-16
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "review_decisions" not in insp.get_table_names():
        return
    cols = {c["name"]: c for c in insp.get_columns("review_decisions")}
    col = cols.get("decision")
    if col is None:
        return
    length = getattr(col["type"], "length", None)
    if length is not None and length < 20:
        op.alter_column(
            "review_decisions",
            "decision",
            existing_type=sa.String(length=length),
            type_=sa.String(length=20),
            existing_nullable=col.get("nullable", False),
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "review_decisions" not in insp.get_table_names():
        return
    cols = {c["name"]: c for c in insp.get_columns("review_decisions")}
    col = cols.get("decision")
    if col is None:
        return
    length = getattr(col["type"], "length", None)
    if length is not None and length > 10:
        op.alter_column(
            "review_decisions",
            "decision",
            existing_type=sa.String(length=length),
            type_=sa.String(length=10),
            existing_nullable=col.get("nullable", False),
        )
