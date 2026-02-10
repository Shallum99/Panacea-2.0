"""
Auth endpoints — now powered by Supabase.
Signup/login handled by Supabase client-side.
This module provides a /me endpoint for the frontend.
"""

from fastapi import APIRouter, Depends
from typing import Any

from app.db import models
from app.core.supabase_auth import get_current_user

router = APIRouter()


@router.get("/me")
async def read_users_me(
    current_user: models.User = Depends(get_current_user),
) -> Any:
    """Get current authenticated user."""
    return {
        "id": current_user.id,
        "supabase_id": current_user.supabase_id,
        "email": current_user.email,
    }
