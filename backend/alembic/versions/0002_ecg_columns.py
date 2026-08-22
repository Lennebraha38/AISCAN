"""ecg kolonlari: studies.ecg_meta, analyses.ecg_result

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-21
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("studies", sa.Column("ecg_meta", sa.JSON(), nullable=True))
    op.add_column("analyses", sa.Column("ecg_result", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("analyses", "ecg_result")
    op.drop_column("studies", "ecg_meta")
