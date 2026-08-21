"""Audit log servisi — append-only işlem kaydı (KVKK md.12)."""
from __future__ import annotations

import hashlib

from sqlalchemy.orm import Session

from ..models import AuditLog


def write_audit(db: Session, *, user_id: str | None, action: str,
                entity_type: str, entity_id: str | None = None,
                data_hash: str | None = None, ip: str | None = None) -> None:
    entry = AuditLog(
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        data_hash=data_hash or _hash(action, entity_id),
        ip=ip,
    )
    db.add(entry)


def _hash(action: str, entity_id: str | None) -> str | None:
    if not entity_id:
        return None
    return hashlib.sha256(f"{action}:{entity_id}".encode()).hexdigest()
