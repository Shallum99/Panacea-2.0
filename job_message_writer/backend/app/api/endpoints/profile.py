"""
Profile endpoints — get/update user profile, CRUD writing samples.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
import logging

from app.db.database import get_db
from app.db import models
from app.schemas.profile import (
    ProfileUpdate,
    ProfileResponse,
    WritingSampleCreate,
    WritingSampleResponse,
)
from app.core.supabase_auth import get_current_user

router = APIRouter()
logger = logging.getLogger(__name__)


def _csv_to_list(val):
    if not val:
        return []
    return [s.strip() for s in val.split(",") if s.strip()]


def _list_to_csv(lst):
    if not lst:
        return None
    return ",".join(lst)


def _build_profile_response(user: models.User) -> ProfileResponse:
    return ProfileResponse(
        full_name=user.full_name,
        email=user.email,
        phone=user.phone,
        linkedin_url=user.linkedin_url,
        portfolio_url=user.portfolio_url,
        professional_summary=user.professional_summary,
        master_skills=_csv_to_list(user.master_skills),
        target_roles=_csv_to_list(user.target_roles),
        target_industries=_csv_to_list(user.target_industries),
        target_locations=_csv_to_list(user.target_locations),
        work_arrangement=user.work_arrangement,
        salary_range_min=user.salary_range_min,
        salary_range_max=user.salary_range_max,
        tone_formality=user.tone_formality or "balanced",
        tone_confidence=user.tone_confidence or "confident",
        tone_verbosity=user.tone_verbosity or "concise",
    )


@router.get("/", response_model=ProfileResponse)
async def get_profile(
    current_user: models.User = Depends(get_current_user),
):
    return _build_profile_response(current_user)


@router.patch("/", response_model=ProfileResponse)
async def update_profile(
    update: ProfileUpdate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if update.full_name is not None:
        current_user.full_name = update.full_name
    if update.phone is not None:
        current_user.phone = update.phone
    if update.linkedin_url is not None:
        current_user.linkedin_url = update.linkedin_url
    if update.portfolio_url is not None:
        current_user.portfolio_url = update.portfolio_url
    if update.professional_summary is not None:
        current_user.professional_summary = update.professional_summary
    if update.master_skills is not None:
        current_user.master_skills = _list_to_csv(update.master_skills)
    if update.target_roles is not None:
        current_user.target_roles = _list_to_csv(update.target_roles)
    if update.target_industries is not None:
        current_user.target_industries = _list_to_csv(update.target_industries)
    if update.target_locations is not None:
        current_user.target_locations = _list_to_csv(update.target_locations)
    if update.work_arrangement is not None:
        current_user.work_arrangement = update.work_arrangement
    if update.salary_range_min is not None:
        current_user.salary_range_min = update.salary_range_min
    if update.salary_range_max is not None:
        current_user.salary_range_max = update.salary_range_max
    if update.tone_formality is not None:
        current_user.tone_formality = update.tone_formality
    if update.tone_confidence is not None:
        current_user.tone_confidence = update.tone_confidence
    if update.tone_verbosity is not None:
        current_user.tone_verbosity = update.tone_verbosity

    db.commit()
    db.refresh(current_user)
    return _build_profile_response(current_user)


# --- Writing Samples ---

@router.get("/writing-samples", response_model=List[WritingSampleResponse])
async def list_writing_samples(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return (
        db.query(models.WritingSample)
        .filter(models.WritingSample.user_id == current_user.id)
        .order_by(models.WritingSample.created_at.desc())
        .all()
    )


@router.post("/writing-samples", response_model=WritingSampleResponse)
async def create_writing_sample(
    body: WritingSampleCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    sample = models.WritingSample(
        user_id=current_user.id,
        title=body.title,
        content=body.content,
        sample_type=body.sample_type,
    )
    db.add(sample)
    db.commit()
    db.refresh(sample)
    return sample


@router.delete("/writing-samples/{sample_id}")
async def delete_writing_sample(
    sample_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    sample = (
        db.query(models.WritingSample)
        .filter(
            models.WritingSample.id == sample_id,
            models.WritingSample.user_id == current_user.id,
        )
        .first()
    )
    if not sample:
        raise HTTPException(status_code=404, detail="Writing sample not found")
    db.delete(sample)
    db.commit()
    return {"detail": "Writing sample deleted"}
