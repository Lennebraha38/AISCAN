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
        data_hash=data_hash or _hash(action, entity_type, entity_id, user_id, ip),
        ip=ip,
    )
    db.add(entry)


def _hash(action: str, entity_type: str | None, entity_id: str | None,
          user_id: str | None, ip: str | None) -> str:
    # Yalnız action+id değil; kaydın tüm bağlamı hash'e girer → kurcalama
    # tespiti (tamper-evidence) daha anlamlı olur.
    raw = "|".join(str(x or "") for x in (action, entity_type, entity_id, user_id, ip))
    return hashlib.sha256(raw.encode()).hexdigest()
