"""
Rate-limit enforcement via FastAPI dependency injection.
Pure DB approach — no Redis needed.
"""
import os
import logging
from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.db.database import get_db
from app.db import models
from app.core.supabase_auth import get_current_user

logger = logging.getLogger(__name__)

# Default limits for the "free" tier (lifetime)
FREE_MESSAGE_LIMIT = 5
FREE_TAILOR_LIMIT = 5


def _get_usage_count(db: Session, user_id: int, action_type: str) -> int:
    """Count total lifetime usage for a user + action type."""
    return db.query(func.count(models.UsageLog.id)).filter(
        models.UsageLog.user_id == user_id,
        models.UsageLog.action_type == action_type,
    ).scalar() or 0


def _get_limit(user: models.User, action_type: str):
    """Return the limit for this user + action, or None if unlimited."""
    if user.tier == "unlimited":
        return None

    if user.tier == "custom":
        if action_type == "message_generation":
            return user.custom_message_limit  # None = unlimited for this action
        elif action_type == "resume_tailor":
            return user.custom_tailor_limit
        return None

    # Default: "free" tier
    if action_type == "message_generation":
        return FREE_MESSAGE_LIMIT
    elif action_type == "resume_tailor":
        return FREE_TAILOR_LIMIT
    return None


def require_quota(action_type: str):
    """
    Factory that returns a FastAPI dependency checking the user's quota.
    Raises 429 if exceeded. Returns the current_user on success.

    Usage:
        current_user: models.User = Depends(require_quota("message_generation"))
    """
    async def _check(
        current_user: models.User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> models.User:
        # Skip in dev mode
        if os.environ.get("DEV_MODE", "").lower() == "true":
            return current_user

        limit = _get_limit(current_user, action_type)

        if limit is not None:
            used = _get_usage_count(db, current_user.id, action_type)
            if used >= limit:
                label = action_type.replace("_", " ")
                logger.warning(
                    f"Rate limit hit: user {current_user.id} ({current_user.email}) "
                    f"action={action_type} used={used} limit={limit}"
                )
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail={
                        "error": "rate_limit_exceeded",
                        "action": action_type,
                        "used": used,
                        "limit": limit,
                        "message": f"You've used all {limit} free {label}s. Contact us to upgrade your account.",
                    },
                )

        return current_user

    return _check


def log_usage(db: Session, user_id: int, action_type: str):
    """Record a usage event. Call AFTER successful generation/tailoring."""
    entry = models.UsageLog(user_id=user_id, action_type=action_type)
    db.add(entry)
    db.commit()
