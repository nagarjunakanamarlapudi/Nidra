"""Chat endpoint — drives the agent and persists the conversation turn."""

from __future__ import annotations

import time
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, status

from pragya_assistant.agent.engine import AgentEngine
from pragya_assistant.api.auth import require_token
from pragya_assistant.api.deps import get_agent, get_conversations
from pragya_assistant.api.schemas import ChatRequest, ChatResponse
from pragya_assistant.memory.conversations import ConversationStore

router = APIRouter(tags=["chat"], dependencies=[Depends(require_token)])
log = structlog.get_logger(__name__)


@router.post("/chat", response_model=ChatResponse)
async def chat(
    payload: ChatRequest,
    agent: Annotated[AgentEngine, Depends(get_agent)],
    conversations: Annotated[ConversationStore, Depends(get_conversations)],
) -> ChatResponse:
    if payload.conversation_id is None:
        conversation_id = await conversations.create("web")
    else:
        if not await conversations.exists(payload.conversation_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Unknown conversation"
            )
        conversation_id = payload.conversation_id

    history = await conversations.history(conversation_id)
    engine_name = type(agent).__name__
    started = time.perf_counter()
    try:
        reply, _ = await agent.respond(history, payload.message, effort=payload.effort)
    except Exception as exc:
        log.exception("chat_engine_failed", conversation_id=conversation_id, engine=engine_name)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The assistant engine failed to respond. Please try again; see server logs.",
        ) from exc

    duration_ms = round((time.perf_counter() - started) * 1000)
    await conversations.append(conversation_id, "user", payload.message)
    await conversations.append(conversation_id, "assistant", reply)
    log.info(
        "chat_completed",
        conversation_id=conversation_id,
        engine=engine_name,
        duration_ms=duration_ms,
    )
    return ChatResponse(reply=reply, conversation_id=conversation_id)
