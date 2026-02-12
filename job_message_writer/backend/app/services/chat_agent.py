"""
Agentic chat service — runs the Claude tool_use loop.

Architecture:
  1. Load conversation history (last 20 messages)
  2. Send to Claude with tool definitions
  3. If Claude returns tool_use → execute tool → append result → loop
  4. If Claude returns end_turn text → yield SSE chunks → done
  5. Max 8 iterations to prevent runaway loops
"""

import json
import logging
from typing import AsyncGenerator, Optional, Dict, Any
import httpx

from sqlalchemy.orm import Session

from app.db import models
from app.services.chat_tools import TOOL_DEFINITIONS, execute_tool
from app.llm.claude_client import ClaudeClient

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 8
MAX_HISTORY_MESSAGES = 20

SYSTEM_PROMPT = """You are Panacea, an AI job application assistant. You help users find jobs, generate cover letters, tailor resumes, and manage applications — all through conversation.

You have access to real tools that take real actions. Use them proactively:
- When the user asks to find jobs, use search_jobs
- When they want a cover letter, use generate_message
- When they want to tailor their resume, use tailor_resume
- When they paste a URL, use import_job_url

Keep responses concise. After using a tool, summarize the result in 1-2 sentences — the tool output will be displayed as rich UI cards, so don't repeat all the data.

When the user asks to apply to multiple jobs, work through them one at a time, confirming each step.

Never make up job listings or fake data. Only use information from tool results."""


async def run_agent(
    conversation_id: int,
    user_message: str,
    user: models.User,
    db: Session,
) -> AsyncGenerator[str, None]:
    """
    Run the agent loop and yield SSE-formatted lines.
    """
    # 1. Load conversation history
    messages = _load_history(conversation_id, db)

    # 2. Save user message to DB
    user_msg = models.ChatMessage(
        conversation_id=conversation_id,
        role="user",
        content=user_message,
    )
    db.add(user_msg)
    db.commit()

    # 3. Add user message to Claude messages
    messages.append({"role": "user", "content": user_message})

    # 4. Agent loop
    claude = ClaudeClient()
    iteration = 0

    while iteration < MAX_ITERATIONS:
        iteration += 1

        # Call Claude (non-streaming) with tools
        response = await _call_claude(claude, messages)

        if not response:
            yield _sse({"type": "text", "content": "I encountered an error. Please try again."})
            yield _sse({"type": "done"})
            return

        stop_reason = response.get("stop_reason")
        content_blocks = response.get("content", [])

        # Check if Claude wants to use tools
        tool_uses = [b for b in content_blocks if b.get("type") == "tool_use"]
        text_blocks = [b for b in content_blocks if b.get("type") == "text"]

        if tool_uses:
            # Build the assistant message with all content blocks
            assistant_content = []
            for block in content_blocks:
                if block["type"] == "text":
                    assistant_content.append({"type": "text", "text": block["text"]})
                elif block["type"] == "tool_use":
                    assistant_content.append({
                        "type": "tool_use",
                        "id": block["id"],
                        "name": block["name"],
                        "input": block["input"],
                    })

            messages.append({"role": "assistant", "content": assistant_content})

            # Save assistant tool_use messages to DB
            for tu in tool_uses:
                db.add(models.ChatMessage(
                    conversation_id=conversation_id,
                    role="tool_use",
                    content=json.dumps(tu["input"]),
                    tool_name=tu["name"],
                    tool_call_id=tu["id"],
                ))
            db.commit()

            # Execute each tool and collect results
            tool_results = []
            for tu in tool_uses:
                tool_name = tu["name"]
                tool_input = tu["input"]
                tool_id = tu["id"]

                # Notify frontend that tool is running
                yield _sse({
                    "type": "tool_start",
                    "tool": tool_name,
                    "args": tool_input,
                })

                # Execute
                result, rich_type = await execute_tool(tool_name, tool_input, user, db)

                # Save tool result to DB
                db.add(models.ChatMessage(
                    conversation_id=conversation_id,
                    role="tool_result",
                    content=json.dumps(result),
                    tool_name=tool_name,
                    tool_call_id=tool_id,
                ))
                db.commit()

                # Notify frontend of result
                yield _sse({
                    "type": "tool_result",
                    "tool": tool_name,
                    "result": result,
                    "rich_type": rich_type,
                })

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "content": json.dumps(result),
                })

            # Add tool results to messages and continue loop
            messages.append({"role": "user", "content": tool_results})
            continue

        # No tool use — Claude is done, extract final text
        final_text = " ".join(b.get("text", "") for b in text_blocks).strip()
        if not final_text:
            final_text = "Done."

        # Save assistant response to DB
        db.add(models.ChatMessage(
            conversation_id=conversation_id,
            role="assistant",
            content=final_text,
        ))
        db.commit()

        # Update conversation title from first exchange
        _maybe_update_title(conversation_id, user_message, final_text, db)

        # Stream the text in chunks (simulated streaming)
        chunk_size = 20
        for i in range(0, len(final_text), chunk_size):
            chunk = final_text[i:i + chunk_size]
            yield _sse({"type": "text", "content": chunk})

        yield _sse({"type": "done"})
        return

    # Hit max iterations
    yield _sse({"type": "text", "content": "I've reached the maximum number of steps for this request. Please try a simpler request or break it into parts."})
    yield _sse({"type": "done"})


def _load_history(conversation_id: int, db: Session) -> list:
    """Load last N messages and convert to Claude messages format."""
    db_messages = (
        db.query(models.ChatMessage)
        .filter(models.ChatMessage.conversation_id == conversation_id)
        .order_by(models.ChatMessage.id.desc())
        .limit(MAX_HISTORY_MESSAGES)
        .all()
    )
    db_messages.reverse()

    messages = []
    i = 0
    while i < len(db_messages):
        msg = db_messages[i]

        if msg.role == "user":
            messages.append({"role": "user", "content": msg.content})

        elif msg.role == "assistant":
            messages.append({"role": "assistant", "content": msg.content})

        elif msg.role == "tool_use":
            # Collect consecutive tool_use messages as one assistant turn
            assistant_content = []
            tool_ids = []
            while i < len(db_messages) and db_messages[i].role == "tool_use":
                tu_msg = db_messages[i]
                try:
                    tool_input = json.loads(tu_msg.content)
                except Exception:
                    tool_input = {}
                assistant_content.append({
                    "type": "tool_use",
                    "id": tu_msg.tool_call_id,
                    "name": tu_msg.tool_name,
                    "input": tool_input,
                })
                tool_ids.append(tu_msg.tool_call_id)
                i += 1

            messages.append({"role": "assistant", "content": assistant_content})

            # Now collect corresponding tool_result messages
            tool_results = []
            while i < len(db_messages) and db_messages[i].role == "tool_result":
                tr_msg = db_messages[i]
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tr_msg.tool_call_id,
                    "content": tr_msg.content[:2000],  # Truncate large results
                })
                i += 1

            if tool_results:
                messages.append({"role": "user", "content": tool_results})
            continue  # Skip the i += 1 at the bottom

        elif msg.role == "tool_result":
            # Orphaned tool_result (shouldn't happen but handle gracefully)
            pass

        i += 1

    return messages


async def _call_claude(claude: ClaudeClient, messages: list) -> Optional[dict]:
    """Call Claude API with tool definitions (non-streaming)."""
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                claude.base_url,
                headers=claude.headers,
                json={
                    "model": claude.model,
                    "system": SYSTEM_PROMPT,
                    "messages": messages,
                    "tools": TOOL_DEFINITIONS,
                    "max_tokens": 4096,
                },
            )

            if response.status_code != 200:
                logger.error(f"Claude API error: {response.status_code}: {response.text[:500]}")
                return None

            return response.json()
    except Exception as e:
        logger.error(f"Claude API call failed: {e}")
        return None


def _maybe_update_title(conversation_id: int, user_message: str, assistant_response: str, db: Session):
    """Set conversation title from first user message if still 'New Chat'."""
    conv = db.query(models.ChatConversation).filter(
        models.ChatConversation.id == conversation_id
    ).first()
    if conv and conv.title == "New Chat":
        # Use first 50 chars of user message as title
        title = user_message[:50].strip()
        if len(user_message) > 50:
            title += "..."
        conv.title = title
        db.commit()


def _sse(data: dict) -> str:
    """Format a dict as an SSE data line."""
    return f"data: {json.dumps(data)}\n\n"
