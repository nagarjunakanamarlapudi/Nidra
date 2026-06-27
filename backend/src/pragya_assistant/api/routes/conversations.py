"""Conversation history endpoints — list past chats and load one's messages."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from pragya_assistant.api.auth import require_token
from pragya_assistant.api.deps import get_conversations
from pragya_assistant.api.schemas import (
    ConversationDetailOut,
    ConversationSummaryOut,
    MessageOut,
)
from pragya_assistant.memory.conversations import ConversationStore

router = APIRouter(tags=["conversations"], dependencies=[Depends(require_token)])


@router.get("/conversations", response_model=list[ConversationSummaryOut])
async def list_conversations(
    conversations: Annotated[ConversationStore, Depends(get_conversations)],
) -> list[ConversationSummaryOut]:
    summaries = await conversations.list_conversations()
    return [
        ConversationSummaryOut(id=s.id, title=s.title, created_at=s.created_at) for s in summaries
    ]


@router.get("/conversations/{conversation_id}", response_model=ConversationDetailOut)
async def get_conversation(
    conversation_id: int,
    conversations: Annotated[ConversationStore, Depends(get_conversations)],
) -> ConversationDetailOut:
    if not await conversations.exists(conversation_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown conversation")
    history = await conversations.history(conversation_id)
    return ConversationDetailOut(
        id=conversation_id,
        messages=[MessageOut(role=m.role, content=m.content) for m in history],
    )
