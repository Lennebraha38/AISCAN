"""users.token_version — şifre değişiminde eski JWT'leri geçersiz kılar

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-16
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "users" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("users")}
    if "token_version" not in cols:
        op.add_column(
            "users",
            sa.Column("token_version", sa.Integer(), nullable=False,
                      server_default="0"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "users" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("users")}
    if "token_version" in cols:
        op.drop_column("users", "token_version")
