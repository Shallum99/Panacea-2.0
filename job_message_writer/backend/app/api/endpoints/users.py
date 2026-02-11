# File: backend/app/api/endpoints/users.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Any, List
from pydantic import BaseModel
import logging

from app.db.database import get_db
from app.db import models
from app.schemas.user import UserCreate, UserResponse
from app.core.supabase_auth import get_current_user

router = APIRouter()
logger = logging.getLogger(__name__)


class SaveGmailTokenRequest(BaseModel):
    refresh_token: str

@router.post("/", response_model=UserResponse)
def create_user(
    user: UserCreate,
    db: Session = Depends(get_db)
) -> Any:
    """Create a new user."""
    try:
        # Check if user with this email already exists
        db_user = db.query(models.User).filter(models.User.email == user.email).first()
        if db_user:
            return {"id": db_user.id, "email": db_user.email}
        
        # Create new user (in a real app, password would be hashed)
        db_user = models.User(
            email=user.email,
            hashed_password="dummy_hashed_password",  # This is just for development
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
def get_current_user(
    db: Session = Depends(get_db)
) -> Any:
    """
    For development purposes, get or create a default user.
    In a real app, this would use authentication.
    """
    try:
        # Try to get an existing user
        db_user = db.query(models.User).first()
        
        # If no user exists, create one
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


@router.get("/gmail-status")
async def gmail_status(
    current_user: models.User = Depends(get_current_user),
):
    """Check if the user has a Gmail refresh token stored."""
    return {"connected": bool(current_user.gmail_refresh_token)}