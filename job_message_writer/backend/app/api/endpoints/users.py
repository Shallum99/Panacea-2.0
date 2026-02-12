# File: backend/app/api/endpoints/users.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Any, List
from pydantic import BaseModel
import logging
import secrets
import time
import urllib.parse

import httpx

from app.db.database import get_db
from app.db import models
from app.schemas.user import UserCreate, UserResponse
from app.core.supabase_auth import get_current_user
from app.core.config import settings

router = APIRouter()
logger = logging.getLogger(__name__)

# In-memory state store for Gmail OAuth (state -> {user_id, redirect_uri, expires})
_gmail_oauth_states: dict = {}


class SaveGmailTokenRequest(BaseModel):
    refresh_token: str


class GmailAuthUrlRequest(BaseModel):
    redirect_uri: str  # e.g. "https://myapp.com/settings"


class ExchangeGmailCodeRequest(BaseModel):
    code: str
    state: str
    redirect_uri: str


@router.post("/", response_model=UserResponse)
def create_user(
    user: UserCreate,
    db: Session = Depends(get_db)
) -> Any:
    """Create a new user."""
    try:
        db_user = db.query(models.User).filter(models.User.email == user.email).first()
        if db_user:
            return {"id": db_user.id, "email": db_user.email}

        db_user = models.User(
            email=user.email,
            hashed_password="dummy_hashed_password",
            is_active=True
        )

        db.add(db_user)
        db.commit()
        db.refresh(db_user)

        return {"id": db_user.id, "email": db_user.email}
    except Exception as e:
        logger.error(f"Error creating user: {str(e)}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/", response_model=List[UserResponse])
def read_users(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
) -> Any:
    """Get all users."""
    try:
        users = db.query(models.User).offset(skip).limit(limit).all()

        result = []
        for user in users:
            result.append({
                "id": user.id,
                "email": user.email
            })

        return result
    except Exception as e:
        logger.error(f"Error reading users: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/current", response_model=UserResponse)
def get_current_user_endpoint(
    db: Session = Depends(get_db)
) -> Any:
    """For development purposes, get or create a default user."""
    try:
        db_user = db.query(models.User).first()

        if not db_user:
            db_user = models.User(
                email="user@example.com",
                hashed_password="dummy_hashed_password",
                is_active=True
            )
            db.add(db_user)
            db.commit()
            db.refresh(db_user)

        return {"id": db_user.id, "email": db_user.email}
    except Exception as e:
        logger.error(f"Error getting current user: {str(e)}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


# --- Gmail OAuth (direct Google flow, no Supabase middleman) ---

@router.post("/gmail-auth-url")
async def gmail_auth_url(
    request: GmailAuthUrlRequest,
    current_user: models.User = Depends(get_current_user),
):
    """Generate a Google OAuth URL for Gmail access. Frontend navigates to this URL."""
    if not settings.GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=500, detail="Google OAuth not configured")

    # Clean expired states
    now = time.time()
    expired = [k for k, v in _gmail_oauth_states.items() if v["expires"] < now]
    for k in expired:
        del _gmail_oauth_states[k]

    # Create state token
    state = secrets.token_urlsafe(32)
    _gmail_oauth_states[state] = {
        "user_id": current_user.id,
        "redirect_uri": request.redirect_uri,
        "expires": now + 600,  # 10 min
    }

    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": request.redirect_uri,
        "response_type": "code",
        "scope": "https://www.googleapis.com/auth/gmail.send",
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    url = f"https://accounts.google.com/o/oauth2/v2/auth?{urllib.parse.urlencode(params)}"
    return {"url": url}


@router.post("/exchange-gmail-code")
async def exchange_gmail_code(
    request: ExchangeGmailCodeRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Exchange Google auth code for tokens and store the refresh token."""
    # Verify state
    state_data = _gmail_oauth_states.pop(request.state, None)
    if not state_data:
        raise HTTPException(status_code=400, detail="Invalid or expired state")
    if state_data["user_id"] != current_user.id:
        raise HTTPException(status_code=403, detail="State mismatch")
    if state_data["expires"] < time.time():
        raise HTTPException(status_code=400, detail="State expired")

    # Exchange code with Google
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": request.code,
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "redirect_uri": request.redirect_uri,
                "grant_type": "authorization_code",
            },
        )

    if resp.status_code != 200:
        logger.error(f"Google token exchange failed: {resp.status_code} {resp.text}")
        raise HTTPException(status_code=400, detail="Failed to exchange code with Google")

    tokens = resp.json()
    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        raise HTTPException(status_code=400, detail="No refresh token returned by Google")

    # Store it
    current_user.gmail_refresh_token = refresh_token
    db.commit()
    logger.info(f"Saved Gmail refresh token for user {current_user.id} via direct OAuth")
    return {"connected": True}


@router.post("/save-gmail-token")
async def save_gmail_token(
    request: SaveGmailTokenRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Store the user's Google refresh token for Gmail sending."""
    current_user.gmail_refresh_token = request.refresh_token
    db.commit()
    logger.info(f"Saved Gmail refresh token for user {current_user.id}")
    return {"status": "ok"}


@router.get("/usage")
async def get_my_usage(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get the current user's tier, limits, and usage counts."""
    from app.core.rate_limit import _get_usage_count, _get_limit

    msg_used = _get_usage_count(db, current_user.id, "message_generation")
    tailor_used = _get_usage_count(db, current_user.id, "resume_tailor")
    msg_limit = _get_limit(current_user, "message_generation")
    tailor_limit = _get_limit(current_user, "resume_tailor")

    return {
        "tier": current_user.tier,
        "message_generation": {"used": msg_used, "limit": msg_limit},
        "resume_tailor": {"used": tailor_used, "limit": tailor_limit},
    }


@router.get("/gmail-status")
async def gmail_status(
    current_user: models.User = Depends(get_current_user),
):
    """Check if the user has a Gmail refresh token stored."""
    return {"connected": bool(current_user.gmail_refresh_token)}
