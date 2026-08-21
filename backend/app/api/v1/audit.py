"""Audit log görüntüleme (yalnız admin)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ...core.deps import get_current_user, get_db, require_role
from ...models import AuditLog, User
from ...schemas import AuditLogOut

router = APIRouter(prefix="/v1/audit", tags=["audit"])


@router.get("/logs")
def logs(user: User = Depends(require_role("admin")),
         db: Session = Depends(get_db)) -> list[dict]:
    rows = db.query(AuditLog).order_by(AuditLog.created_at.desc()).limit(200)
    return [AuditLogOut.model_validate({
        "id": r.id,
        "user_id": r.user_id,
        "action": r.action,
        "entity_type": r.entity_type,
        "entity_id": r.entity_id,
        "data_hash": r.data_hash,
        "ip": r.ip,
        "created_at": r.created_at,
    }).model_dump() for r in rows]
