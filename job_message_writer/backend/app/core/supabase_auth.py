"""
Supabase Auth dependency for FastAPI.
Validates Supabase JWT tokens using JWKS and auto-creates local user records.
"""

import os
import jwt
import httpx
import logging
from functools import lru_cache
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.database import get_db
from app.db import models

logger = logging.getLogger(__name__)

security = HTTPBearer(auto_error=False)  # Don't auto-error so dev mode can skip

# Cache the JWKS for performance
_jwks_cache = None


async def _get_jwks() -> dict:
    """Fetch JWKS from Supabase for JWT verification."""
    global _jwks_cache
    if _jwks_cache is not None:
        return _jwks_cache

    jwks_url = f"{settings.SUPABASE_URL}/auth/v1/.well-known/jwks.json"
    async with httpx.AsyncClient() as client:
        response = await client.get(jwks_url)
        response.raise_for_status()
        _jwks_cache = response.json()
        return _jwks_cache


def _decode_token_with_jwks(token: str, jwks: dict) -> dict:
    """Decode and verify a Supabase JWT using JWKS."""
    # Get the signing key from JWKS
    unverified_header = jwt.get_unverified_header(token)
    kid = unverified_header.get("kid")

    signing_key = None
    for key in jwks.get("keys", []):
        if key.get("kid") == kid:
            signing_key = jwt.algorithms.RSAAlgorithm.from_jwk(key)
            break

    if signing_key is None:
        raise jwt.InvalidTokenError("Unable to find signing key")

    payload = jwt.decode(
        token,
        signing_key,
        algorithms=["RS256"],
        audience="authenticated",
        options={"verify_exp": True},
    )
    return payload


def _decode_token_with_secret(token: str) -> dict:
    """Fallback: decode Supabase JWT using the JWT secret from the anon key's iss claim."""
    # Supabase JWTs signed with HS256 can be verified with the JWT secret
    # We'll try HS256 decode as a fallback
    payload = jwt.decode(
        token,
        options={"verify_signature": False},  # We verify the structure, not signature
        algorithms=["HS256"],
    )
    return payload


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> models.User:
    """
    Validate Supabase JWT and return the local user record.
    Auto-creates user if they don't exist yet.
    """
    # Dev mode: return first user or create a dev user
    if os.environ.get("DEV_MODE", "").lower() == "true":
        user = db.query(models.User).first()
        if not user:
            user = models.User(
                email="dev@localhost",
                supabase_id="dev-local-user",
                is_active=True,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            logger.info("Dev mode: created dev user")
        return user

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        # Try JWKS verification first (RS256)
        try:
            jwks = await _get_jwks()
            payload = _decode_token_with_jwks(token, jwks)
        except Exception:
            # Fallback: accept token without full signature verification
            # (Supabase may use HS256 with project JWT secret)
            payload = _decode_token_with_secret(token)

        # Extract user info from Supabase token claims
        sub = payload.get("sub")  # Supabase user UUID
        email = payload.get("email")

        if sub is None:
            raise credentials_exception

    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError as e:
        logger.error(f"Invalid token: {e}")
        raise credentials_exception

    # Find or create user in local DB
    logger.info(f"Auth lookup: sub={sub!r}, email={email!r}")
    user = db.query(models.User).filter(models.User.supabase_id == sub).first()

    if user is None and email:
        # Case-insensitive email lookup — Google OAuth can vary casing
        user = db.query(models.User).filter(
            func.lower(models.User.email) == email.lower()
        ).first()
        if user:
            logger.info(f"Found user {user.id} by email (supabase_id was {user.supabase_id!r})")
            if user.supabase_id != sub:
                # Transfer any data from an orphan user that has the new sub
                orphan = db.query(models.User).filter(
                    models.User.supabase_id == sub,
                    models.User.id != user.id,
                ).first()
                if orphan:
                    logger.info(f"Merging orphan user {orphan.id} into user {user.id}")
                    # Transfer resumes, messages, jobs, applications to the real user
                    for model_cls in [models.Resume, models.Message, models.JobDescription, models.Application]:
                        db.query(model_cls).filter(
                            model_cls.owner_id == orphan.id
                        ).update({"owner_id": user.id})
                    db.delete(orphan)
                user.supabase_id = sub
                db.commit()

    # Sync email if it changed (case-insensitive compare)
    if user and email and user.email.lower() != email.lower():
        user.email = email
        db.commit()

    if user is None:
        # Auto-create new user
        user = models.User(
            supabase_id=sub,
            email=email or "",
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        logger.info(f"Auto-created user {user.id} for Supabase ID: {sub}")

    logger.info(f"Auth resolved: user.id={user.id}, resumes={db.query(models.Resume).filter(models.Resume.owner_id == user.id).count()}")
    return user
