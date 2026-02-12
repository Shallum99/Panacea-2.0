"""
Chat endpoints — conversation CRUD + SSE message streaming via agent loop.
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import List

from app.db.database import get_db
from app.db import models
from app.schemas.chat import (
    ChatMessageCreate,
    ChatConversationCreate,
    ChatConversationResponse,
    ChatConversationDetail,
)
from app.core.supabase_auth import get_current_user
from app.services.chat_agent import run_agent

router = APIRouter()


@router.post("/conversations", response_model=ChatConversationResponse)
async def create_conversation(
    body: ChatConversationCreate = ChatConversationCreate(),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conv = models.ChatConversation(
        user_id=current_user.id,
        title=body.title or "New Chat",
    )
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return conv


@router.get("/conversations", response_model=List[ChatConversationResponse])
async def list_conversations(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    convs = (
        db.query(models.ChatConversation)
        .filter(models.ChatConversation.user_id == current_user.id)
        .order_by(desc(models.ChatConversation.updated_at))
        .limit(50)
        .all()
    )
    return convs


@router.get("/conversations/{conversation_id}", response_model=ChatConversationDetail)
async def get_conversation(
    conversation_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conv = (
        db.query(models.ChatConversation)
        .filter(
            models.ChatConversation.id == conversation_id,
            models.ChatConversation.user_id == current_user.id,
        )
        .first()
    )
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conv


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conv = (
        db.query(models.ChatConversation)
        .filter(
            models.ChatConversation.id == conversation_id,
            models.ChatConversation.user_id == current_user.id,
        )
        .first()
    )
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    db.delete(conv)
    db.commit()
    return {"detail": "Conversation deleted"}


@router.post("/conversations/{conversation_id}/send")
async def send_message(
    conversation_id: int,
    body: ChatMessageCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Send a message to the chat agent. Returns SSE stream."""
    # Verify conversation belongs to user
    conv = (
        db.query(models.ChatConversation)
        .filter(
            models.ChatConversation.id == conversation_id,
            models.ChatConversation.user_id == current_user.id,
        )
        .first()
    )
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    return StreamingResponse(
        run_agent(conversation_id, body.message, current_user, db),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
