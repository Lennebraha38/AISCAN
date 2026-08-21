"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-08-21
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

IMMUTABLE_TRIGGER_SQL = """
CREATE OR REPLACE FUNCTION prevent_audit_mutation() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'audit_logs tablosu append-onlydir: % yasak', TG_OP;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER audit_logs_immutable
BEFORE UPDATE OR DELETE ON audit_logs
FOR EACH ROW EXECUTE FUNCTION prevent_audit_mutation();
"""


def upgrade() -> None:
    bind = op.get_bind()
    # Modellerle birebir senkron şema; sonraki değişiklikler için
    # `alembic revision --autogenerate` kullanılmalıdır.
    from app.models import Base

    Base.metadata.create_all(bind=bind)
    if bind.dialect.name == "postgresql":
        bind.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS vector")
        bind.exec_driver_sql(IMMUTABLE_TRIGGER_SQL)


def downgrade() -> None:
    from app.models import Base

    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS audit_logs_immutable ON audit_logs")
    Base.metadata.drop_all(bind=op.get_bind())
