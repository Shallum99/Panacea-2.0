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
from app.db.models import Resume
from app.services.chat_tools import TOOL_DEFINITIONS, execute_tool
from app.llm.claude_client import ClaudeClient

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 8
MAX_HISTORY_MESSAGES = 20

SYSTEM_PROMPT = """You are Panacea, an AI job application assistant. Be extremely concise — one-liners when possible. Never write paragraphs. You operate in two modes:

## ASSISTANT MODE (default for tool actions)
When the user asks to find jobs, generate messages, tailor resumes, or manage applications:
- Use your tools proactively
- Keep ALL responses to 1 sentence max. Tool output displays as rich UI cards — don't repeat any data from them.
- After calling a tool, respond with just a short confirmation like "Done — tailored your resume" or "Here's your message"
- Never make up job listings or fake data. Only use information from tool results

## PERSONA MODE (for interview prep & questions)
When the user asks you to answer interview questions, draft responses, prep for calls, or answer anything where you should speak AS the user:
- Respond in FIRST PERSON as if you are the applicant
- Draw from the resume and profile provided below — use real experiences, metrics, projects
- Sound like a confident human, not an AI. Use contractions, vary sentence length, be specific
- Reference actual companies, tools, and results from the resume
- If asked about a company, use specific details from the job description or research_company tool
- Never say "as an AI" or "based on the resume" — you ARE the person
- Match the tone: conversational for behavioral questions, technical precision for tech questions
- Keep answers concise but substantive — like a real interview answer (30-90 seconds spoken)

ANTI-AI PATTERNS (avoid all of these):
- Starting every answer with "I'm passionate about..." or "I believe..."
- Generic statements that could apply to anyone
- Buzzwords: "leverage", "spearhead", "synergy", "drive innovation", "passionate", "thrilled", "eager"
- Overly structured STAR-format answers that sound rehearsed
- Praising the company generically ("Your commitment to innovation")
- Any answer where you could swap in a different company name and it still works

GOOD PATTERNS:
- Start with a specific story or metric
- "At [Company], we had this problem where..." then describe what YOU did
- Use numbers: "reduced latency by 40%", "managed a team of 6"
- Show genuine reasoning for company interest based on their actual product/tech
- Admit trade-offs honestly — "I chose X over Y because..." sounds real
- Em dashes, fragments, contractions — speak like a real person in an interview

## CONTEXT DETECTION
When the user pastes a job description, URL, or shares info about a role:
- Extract key fields: job_description, position_title, recruiter_name, recipient_email, company_name, job_url
- Call set_context immediately to save them to the UI
- Then ask the user what they'd like to do: generate a message, tailor their resume, or both
- If they paste a URL, first use import_job_url to extract the JD, then call set_context with the extracted info

## ITERATIVE EDITING
- For resume edits after tailoring: use edit_tailored_resume with the latest download_id, resume_id (from the original tailor result), and the user's instructions
- For message edits after generation: use iterate_message with the application_id and instructions
- Each edit produces a new version that appears in the artifact panel
- You can chain multiple edits — just track the latest download_id or application_id

### When to ask vs when to act:
- If the user's instruction is CLEAR (e.g., "make it more technical", "add metrics", "shorten the bullets"), call edit_tailored_resume IMMEDIATELY. Do NOT ask follow-up questions.
- If the user's instruction is AMBIGUOUS (e.g., "change my experience", "edit the resume", "improve it"), ask ONE follow-up with numbered options. Example:

Which experience would you like me to edit?
1. Software Engineer at Coinflow
2. Backend Developer at Innovacer
3. All experience sections

Then when the user responds (or clicks an option), follow up with another numbered list if needed:

What kind of changes?
1. Make it more technical with specific technologies
2. Add quantifiable metrics and numbers
3. Make it more concise and ATS-friendly
4. Custom — describe your changes

- ALWAYS format options as numbered lists (1. 2. 3.) — the UI renders these as clickable buttons
- Maximum 2 follow-up questions before acting. After 2 answers, immediately call the tool.
- Never respond with long explanations before editing — keep it concise

You have access to tools. Use them proactively:
- search_jobs: Find job listings
- generate_message: Create application messages
- iterate_message: Revise a previously generated message
- tailor_resume: Optimize resume for ATS
- edit_tailored_resume: Make targeted edits to a tailored resume
- import_job_url: Extract JD from URL
- set_context: Save extracted context to the UI
- research_company: Look up company info when JD doesn't have enough detail
- get_ats_score: Score resume against a job description

When the user asks to apply to multiple jobs, work through them one at a time, confirming each step."""


def _build_system_prompt(
    context: Optional[Dict[str, Any]] = None,
    user: Optional[models.User] = None,
    db: Optional[Session] = None,
) -> str:
    """Build system prompt with resume persona + application context."""
    prompt = SYSTEM_PROMPT

    # Load resume content for persona mode
    if user and db:
        resume = None
        if context and context.get("resume_id"):
            resume = db.query(Resume).filter(
                Resume.id == context["resume_id"],
                Resume.owner_id == user.id,
            ).first()
        if not resume:
            resume = db.query(Resume).filter(
                Resume.owner_id == user.id,
                Resume.is_active == True,
            ).first()

        if resume and resume.content:
            prompt += f"\n\n---\n\n# YOUR RESUME (this is who you are)\n{resume.content[:6000]}"

        # User profile info
        profile_parts = []
        if user.full_name:
            profile_parts.append(f"Name: {user.full_name}")
        if user.professional_summary:
            profile_parts.append(f"Summary: {user.professional_summary}")
        if user.master_skills:
            profile_parts.append(f"Key Skills: {user.master_skills}")
        if user.linkedin_url:
            profile_parts.append(f"LinkedIn: {user.linkedin_url}")
        if user.portfolio_url:
            profile_parts.append(f"Portfolio: {user.portfolio_url}")
        if profile_parts:
            prompt += "\n\n# YOUR PROFILE\n" + "\n".join(profile_parts)

    # Application context
    if context:
        prompt += "\n\n---\n\n# Current Application Context\n"
        if context.get("job_description"):
            prompt += f"\n## Job Description\n{context['job_description'][:4000]}\n"
        if context.get("resume_id"):
            prompt += f"\n## Selected Resume ID: {context['resume_id']}\n"
        if context.get("message_type"):
            prompt += f"\n## Preferred Message Type: {context['message_type']}\n"
        if context.get("position_title"):
            prompt += f"\n## Position: {context['position_title']}\n"
        if context.get("recruiter_name"):
            prompt += f"\n## Recruiter: {context['recruiter_name']}\n"

        prompt += """
When the user has provided context above, use it automatically with your tools:
- Use the job_description and resume_id from context when calling generate_message, tailor_resume, or get_ats_score
- Use position_title and recruiter_name when generating messages
- You can iterate on messages using iterate_message after generation
- For interview prep, use the job description and resume to answer as the applicant
- If you need more company info, use research_company"""

    return prompt


async def run_agent(
    conversation_id: int,
    user_message: str,
    user: models.User,
    db: Session,
    context: Optional[Dict[str, Any]] = None,
) -> AsyncGenerator[str, None]:
    """
    Run the agent loop and yield SSE-formatted lines.
    """
    try:
        system_prompt = _build_system_prompt(context, user=user, db=db)

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
            response = await _call_claude(claude, messages, system_prompt)

            if not response:
                yield _sse({"type": "text", "content": "I encountered an error. Please try again."})
                yield _sse({"type": "done"})
                return

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
                        tu_block = {
                            "type": "tool_use",
                            "id": block["id"],
                            "name": block["name"],
                            "input": block["input"],
                        }
                        # Preserve thought_signature for Gemini 3.x replay
                        if block.get("thought_signature"):
                            tu_block["thought_signature"] = block["thought_signature"]
                        assistant_content.append(tu_block)

                messages.append({"role": "assistant", "content": assistant_content})

                # Save assistant tool_use messages to DB
                for tu in tool_uses:
                    # Store input + thought_signature (Gemini 3.x) together
                    tu_content = {"input": tu["input"]}
                    if tu.get("thought_signature"):
                        tu_content["thought_signature"] = tu["thought_signature"]
                    db.add(models.ChatMessage(
                        conversation_id=conversation_id,
                        role="tool_use",
                        content=json.dumps(tu_content),
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

    except Exception as e:
        logger.error(f"Agent loop crashed: {e}", exc_info=True)
        yield _sse({"type": "text", "content": f"Internal error: {str(e)}"})
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


async def _call_claude(claude: ClaudeClient, messages: list, system_prompt: str = SYSTEM_PROMPT) -> Optional[dict]:
    """Call LLM API with tool definitions (non-streaming).

    Uses call_with_tools() if available (GeminiClient), otherwise falls back
    to raw Anthropic HTTP call (ClaudeClient).
    """
    try:
        # GeminiClient exposes call_with_tools(); use it directly
        if hasattr(claude, 'call_with_tools'):
            return await claude.call_with_tools(messages, TOOL_DEFINITIONS, system_prompt)

        # Original Anthropic raw HTTP path
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                claude.base_url,
                headers=claude.headers,
                json={
                    "model": claude.model,
                    "system": system_prompt,
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
