"""Audit logging helper for Breathe API.

Provides a non-blocking audit log helper that records user actions
to the audit_logs table. All failures are swallowed so audit
logging never breaks the main operation.
"""
import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def log_audit(
    db,
    user_id: int,
    action: str,
    entity_type: str,
    entity_id: Optional[int] = None,
    details: Optional[dict] = None,
    ip_address: Optional[str] = None,
):
    """Create and commit an AuditLog record.

    This function is non-blocking: any exception is caught and logged
    so audit failures never break the main API operation.

    Args:
        db: SQLAlchemy session (SessionLocal instance)
        user_id: ID of the user performing the action
        action: Action name (e.g. 'ceu_create', 'login', 'register')
        entity_type: Type of entity (e.g. 'ceu', 'license', 'credential')
        entity_id: ID of the affected entity, if applicable
        details: Dict of relevant data — will be JSON-dumped
        ip_address: Request IP address, if available
    """
    try:
        from database import AuditLog

        details_str = json.dumps(details) if details else None

        entry = AuditLog(
            user_id=user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            details=details_str,
            ip_address=ip_address,
        )
        db.add(entry)
        db.commit()
    except Exception as e:
        logger.warning("Audit log failed (non-blocking): %s", e)
        try:
            db.rollback()
        except Exception:
            pass