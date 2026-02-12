"""Admin endpoints for managing user tiers and usage."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func as sqlfunc
from pydantic import BaseModel
from typing import Optional
import logging

from app.db.database import get_db
from app.db import models
from app.core.supabase_auth import get_current_user

router = APIRouter()
logger = logging.getLogger(__name__)

ADMIN_EMAILS = [
    "shallumisrael@gmail.com",
]


def require_admin(
    current_user: models.User = Depends(get_current_user),
) -> models.User:
    if current_user.email not in ADMIN_EMAILS:
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user


class UpdateTierRequest(BaseModel):
    tier: str  # "free", "unlimited", "custom"
    custom_message_limit: Optional[int] = None
    custom_tailor_limit: Optional[int] = None


class UserTierResponse(BaseModel):
    id: int
    email: str
    tier: str
    custom_message_limit: Optional[int] = None
    custom_tailor_limit: Optional[int] = None
    message_usage: int
    tailor_usage: int

    class Config:
        from_attributes = True


def _get_user_tier_response(db: Session, user: models.User) -> UserTierResponse:
    msg_count = db.query(sqlfunc.count(models.UsageLog.id)).filter(
        models.UsageLog.user_id == user.id,
        models.UsageLog.action_type == "message_generation",
    ).scalar() or 0
    tailor_count = db.query(sqlfunc.count(models.UsageLog.id)).filter(
        models.UsageLog.user_id == user.id,
        models.UsageLog.action_type == "resume_tailor",
    ).scalar() or 0
    return UserTierResponse(
        id=user.id,
        email=user.email,
        tier=user.tier,
        custom_message_limit=user.custom_message_limit,
        custom_tailor_limit=user.custom_tailor_limit,
        message_usage=msg_count,
        tailor_usage=tailor_count,
    )


@router.post("/users/{user_id}/tier", response_model=UserTierResponse)
async def update_user_tier(
    user_id: int,
    request: UpdateTierRequest,
    admin: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Set a user's tier and optional custom limits (admin only)."""
    if request.tier not in ("free", "unlimited", "custom"):
        raise HTTPException(status_code=400, detail="Invalid tier. Must be: free, unlimited, custom")

    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.tier = request.tier
    if request.tier == "custom":
        user.custom_message_limit = request.custom_message_limit
        user.custom_tailor_limit = request.custom_tailor_limit
    else:
        user.custom_message_limit = None
        user.custom_tailor_limit = None

    db.commit()
    db.refresh(user)
    logger.info(f"Admin {admin.email} set user {user.id} ({user.email}) tier={request.tier}")

    return _get_user_tier_response(db, user)


@router.get("/users/{user_id}/usage", response_model=UserTierResponse)
async def get_user_usage(
    user_id: int,
    admin: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Get a user's tier and usage counts (admin only)."""
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return _get_user_tier_response(db, user)
