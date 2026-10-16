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


def _columns(table: str) -> set[str]:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if table not in insp.get_table_names():
        return set()
    return {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    # 0001, canli modellerden create_all cagirdigi icin bu kolonlar taze
    # kurulumda ZATEN olusmus olabilir. Bu yuzden ekleme idempotenttir;
    # aksi halde taze DB'de "duplicate column" ile patlar.
    if "ecg_meta" not in _columns("studies"):
        op.add_column("studies", sa.Column("ecg_meta", sa.JSON(), nullable=True))
    if "ecg_result" not in _columns("analyses"):
        op.add_column("analyses", sa.Column("ecg_result", sa.JSON(), nullable=True))


def downgrade() -> None:
    if "ecg_result" in _columns("analyses"):
        op.drop_column("analyses", "ecg_result")
    if "ecg_meta" in _columns("studies"):
        op.drop_column("studies", "ecg_meta")
