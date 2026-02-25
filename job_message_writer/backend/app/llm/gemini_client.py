# File: backend/app/llm/gemini_client.py
"""Drop-in replacement for ClaudeClient using Google Gemini API.

Exposes the same interface: _send_request, _send_request_json, _stream_request,
extract_company_info, extract_jd_fields, generate_message.
"""
import os
import json
import httpx
from typing import Dict, Any, Optional, AsyncIterator
import logging

logger = logging.getLogger(__name__)


def _repair_truncated_json(text: str) -> Optional[Dict]:
    """Try to salvage a truncated JSON response from Gemini.

    When max_tokens is hit, the JSON is typically:
      {"bullets": [{"index":1,"lines":[...]}, {"index":2,"lines":[...]}, {"inde
    We find the last complete array element and close the JSON.
    """
    import re
    # Find the last complete object in a "bullets" array
    # Look for the pattern: }, { ... and try closing after the last complete }
    # Strategy: progressively trim from the end until json.loads works
    for end_marker in ['},', '}']:
        idx = text.rfind(end_marker)
        while idx > 0:
            candidate = text[:idx + 1]
            # Close any open arrays/objects
            open_brackets = candidate.count('[') - candidate.count(']')
            open_braces = candidate.count('{') - candidate.count('}')
            closing = ']' * max(0, open_brackets) + '}' * max(0, open_braces)
            try:
                result = json.loads(candidate + closing)
                if isinstance(result, dict) and "bullets" in result and len(result["bullets"]) > 0:
                    return result
            except json.JSONDecodeError:
                pass
            idx = text.rfind(end_marker, 0, idx)
    return None


class GeminiClient:
    def __init__(self):
        self.api_key = os.environ.get("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY environment variable not set")

        self.model = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
        self.fast_model = os.environ.get("GEMINI_FAST_MODEL", "gemini-2.0-flash")
        self.base_url = "https://generativelanguage.googleapis.com/v1beta"
        logger.info(f"Initialized GeminiClient with model: {self.model}, fast_model: {self.fast_model}")

    def _endpoint(self, model: str, stream: bool = False) -> str:
        action = "streamGenerateContent" if stream else "generateContent"
        url = f"{self.base_url}/models/{model}:{action}?key={self.api_key}"
        if stream:
            url += "&alt=sse"
        return url

    @staticmethod
    def _build_body(
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 8192,
        json_schema: Optional[Dict] = None,
        model: str = "",
    ) -> Dict[str, Any]:
        body: Dict[str, Any] = {
            "contents": [
                {"role": "user", "parts": [{"text": user_prompt}]},
            ],
            "generationConfig": {
                "maxOutputTokens": max_tokens,
                "temperature": 0.7,
            },
        }
        # 3.x models REQUIRE thinking — can't disable it.
        # 2.5 models: disable thinking so tokens aren't wasted on CoT.
        if model.startswith("gemini-3"):
            # 3.x requires thinking; set a generous budget
            body["generationConfig"]["thinkingConfig"] = {"thinkingBudget": 8192}
        else:
            body["generationConfig"]["thinkingConfig"] = {"thinkingBudget": 0}
        if system_prompt:
            body["systemInstruction"] = {"parts": [{"text": system_prompt}]}

        if json_schema:
            body["generationConfig"]["responseMimeType"] = "application/json"
            # Gemini uses a subset of JSON Schema — pass it through.
            # Strip unsupported keys that Gemini rejects.
            clean_schema = _clean_schema_for_gemini(json_schema)
            body["generationConfig"]["responseSchema"] = clean_schema

        return body

    # ── Core methods (same signature as ClaudeClient) ──────────────────────

    async def _send_request(
        self, system_prompt: str, user_prompt: str,
        max_tokens: int = 8192, model: str = None,
    ) -> str:
        use_model = model or self.model
        logger.info(f"Sending request to Gemini API with model: {use_model}")
        body = self._build_body(system_prompt, user_prompt, max_tokens, model=use_model)
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    self._endpoint(use_model),
                    json=body,
                    headers={"Content-Type": "application/json"},
                    timeout=120.0,
                )
                if resp.status_code != 200:
                    logger.error(f"Gemini API failed {resp.status_code}: {resp.text[:500]}")
                    raise Exception(f"Gemini API failed with status {resp.status_code}: {resp.text[:500]}")

                data = resp.json()
                text = _extract_text(data)
                logger.info(f"Received Gemini response (first 100 chars): {text[:100]}...")
                return text
        except Exception as e:
            logger.error(f"Error in Gemini API request: {e}")
            raise

    async def _send_request_json(
        self, system_prompt: str, user_prompt: str,
        json_schema: Dict[str, Any],
        max_tokens: int = 8192, model: str = None,
    ) -> Dict[str, Any]:
        use_model = model or self.model
        logger.info(f"Sending structured JSON request to Gemini API with model: {use_model}")
        body = self._build_body(system_prompt, user_prompt, max_tokens, json_schema=json_schema, model=use_model)
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    self._endpoint(use_model),
                    json=body,
                    headers={"Content-Type": "application/json"},
                    timeout=120.0,
                )
                if resp.status_code != 200:
                    logger.error(f"Gemini JSON API failed {resp.status_code}: {resp.text[:500]}")
                    raise Exception(f"Gemini API failed with status {resp.status_code}: {resp.text[:500]}")

                data = resp.json()
                text = _extract_text(data)
                finish = data.get("candidates", [{}])[0].get("finishReason", "")
                logger.info(f"Received Gemini JSON response (finish={finish}, first 100): {text[:100]}...")
                if finish == "MAX_TOKENS":
                    logger.warning("[JSON] Gemini response hit max tokens — may be truncated")
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    # Truncated JSON — try to salvage complete array items
                    repaired = _repair_truncated_json(text)
                    if repaired is not None:
                        logger.warning(f"[JSON] Repaired truncated JSON (salvaged partial response)")
                        return repaired
                    raise
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Gemini JSON response: {e}")
            raise
        except Exception as e:
            logger.error(f"Error in Gemini JSON request: {e}")
            raise

    async def _stream_request(
        self, system_prompt: str, user_prompt: str,
        max_tokens: int = 8192, model: str = None,
    ) -> AsyncIterator[str]:
        use_model = model or self.model
        logger.info(f"Streaming request to Gemini API with model: {use_model}")
        body = self._build_body(system_prompt, user_prompt, max_tokens, model=use_model)
        async with httpx.AsyncClient() as client:
            async with client.stream(
                "POST",
                self._endpoint(use_model, stream=True),
                json=body,
                headers={"Content-Type": "application/json"},
                timeout=120.0,
            ) as resp:
                if resp.status_code != 200:
                    err = await resp.aread()
                    logger.error(f"Gemini stream failed {resp.status_code}: {err.decode()[:500]}")
                    raise Exception(f"Gemini stream failed with status {resp.status_code}")

                async for line in resp.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    data_str = line[6:].strip()
                    if not data_str:
                        continue
                    try:
                        chunk = json.loads(data_str)
                        parts = (
                            chunk.get("candidates", [{}])[0]
                            .get("content", {})
                            .get("parts", [])
                        )
                        for part in parts:
                            text = part.get("text", "")
                            if text:
                                yield text
                    except json.JSONDecodeError:
                        continue

    # ── Convenience methods (copied from ClaudeClient) ─────────────────────

    async def extract_company_info(self, job_description: str) -> Dict[str, Any]:
        system_prompt = (
            "You are an AI specialized in analyzing job descriptions. Extract key information "
            "about the company. Return ONLY a valid JSON object."
        )
        user_prompt = f"""Analyze this job description and extract:
1. company_name, 2. industry, 3. company_size (startup/mid-size/enterprise),
4. company_culture (list), 5. technologies (list), 6. location, 7. mission

Use "Unknown" for missing strings, empty lists for missing lists.

Job Description:
{job_description}

Return a valid JSON object with these fields."""

        default = {
            "company_name": "Unknown", "industry": "Unknown",
            "company_size": "Unknown", "company_culture": [],
            "technologies": [], "location": "Unknown", "mission": "Unknown",
        }
        try:
            text = await self._send_request(system_prompt, user_prompt, max_tokens=1024, model=self.fast_model)
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                import re
                m = re.search(r'({[\s\S]*})', text)
                if m:
                    try:
                        return json.loads(m.group(1))
                    except json.JSONDecodeError:
                        pass
                logger.warning("Failed to parse company info JSON from Gemini")
                return default
        except Exception as e:
            logger.error(f"Error extracting company info: {e}")
            return default

    async def extract_jd_fields(self, job_description: str) -> Dict[str, Any]:
        system_prompt = (
            "You are a job description parser. Extract specific contact and role details. "
            "Return ONLY valid JSON."
        )
        user_prompt = f"""Extract from this job description (use null if not found):
- recipient_email, recruiter_name, company_name, position_title,
  location, salary_range, department

Job Description:
{job_description}

Return a valid JSON object."""

        default = {
            "recipient_email": None, "recruiter_name": None,
            "company_name": None, "position_title": None,
            "location": None, "salary_range": None, "department": None,
        }
        try:
            text = await self._send_request(system_prompt, user_prompt, max_tokens=512, model=self.fast_model)
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                import re
                m = re.search(r'({[\s\S]*})', text)
                if m:
                    try:
                        return json.loads(m.group(1))
                    except json.JSONDecodeError:
                        pass
                return default
        except Exception as e:
            logger.error(f"Error extracting JD fields: {e}")
            return default

    async def generate_message(
        self, resume: str, job_description: str,
        company_info: Dict[str, Any], message_type: str,
    ) -> str:
        char_limits = {"linkedin": 300, "inmail": 2000, "email": 3000, "ycombinator": 500}
        limit = char_limits.get(message_type.lower(), 1000)

        system_prompt = (
            "You are an expert job application assistant. Craft personalized, professional "
            "outreach messages from job seekers to recruiters or hiring managers."
        )
        user_prompt = f"""Create a personalized {message_type} message:

RESUME:
{resume}

JOB DESCRIPTION:
{job_description}

COMPANY INFO:
{json.dumps(company_info, indent=2)}

Requirements:
- Under {limit} characters
- Highlight 2-3 relevant skills matching the job
- Reference specific company info
- Professional tone for the platform
- Clear call to action
- NO generic phrases like "I am writing to express my interest"

Return ONLY the message text."""

        try:
            text = await self._send_request(system_prompt, user_prompt)
            return text.strip()
        except Exception as e:
            logger.error(f"Error generating message: {e}")
            return "I apologize, but I encountered an issue generating your message. Please try again."


    # ── Tool-calling (agentic chat) ──────────────────────────────────────

    async def call_with_tools(
        self,
        messages: list,
        tools: list,
        system_prompt: str = "",
        max_tokens: int = 8192,
    ) -> Optional[Dict[str, Any]]:
        """Call Gemini with function-calling support.

        Accepts Anthropic-format messages and tools, converts to Gemini format,
        makes the API call, and returns an Anthropic-format response dict so the
        chat agent doesn't need to change.
        """
        use_model = self.model
        # Convert Anthropic tools → Gemini functionDeclarations
        func_decls = []
        for tool in tools:
            decl: Dict[str, Any] = {
                "name": tool["name"],
                "description": tool.get("description", ""),
            }
            schema = tool.get("input_schema", {})
            if schema:
                decl["parameters"] = _clean_schema_for_gemini(schema)
            func_decls.append(decl)

        # Convert Anthropic messages → Gemini contents
        contents = _anthropic_messages_to_gemini(messages)

        body: Dict[str, Any] = {
            "contents": contents,
            "tools": [{"functionDeclarations": func_decls}],
            "generationConfig": {
                "maxOutputTokens": max_tokens,
                "temperature": 0.7,
            },
        }
        if system_prompt:
            body["systemInstruction"] = {"parts": [{"text": system_prompt}]}
        # Thinking config
        if use_model.startswith("gemini-3"):
            body["generationConfig"]["thinkingConfig"] = {"thinkingBudget": 8192}
        else:
            body["generationConfig"]["thinkingConfig"] = {"thinkingBudget": 0}

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(
                    self._endpoint(use_model),
                    json=body,
                    headers={"Content-Type": "application/json"},
                )
                if resp.status_code != 200:
                    logger.error(f"Gemini tool call failed {resp.status_code}: {resp.text[:500]}")
                    return None
                data = resp.json()
                # Convert Gemini response → Anthropic format
                return _gemini_response_to_anthropic(data)
        except Exception as e:
            logger.error(f"Gemini tool call error: {e}")
            return None


# ── Helpers ────────────────────────────────────────────────────────────────

def _extract_text(response_data: Dict) -> str:
    """Extract text from Gemini generateContent response."""
    candidates = response_data.get("candidates", [])
    if not candidates:
        raise Exception(f"Gemini returned no candidates: {response_data}")
    parts = candidates[0].get("content", {}).get("parts", [])
    return "".join(p.get("text", "") for p in parts)


def _clean_schema_for_gemini(schema: Dict) -> Dict:
    """Remove JSON Schema keys that Gemini doesn't support.

    Gemini's responseSchema supports a subset: type, properties, required,
    items, enum, description, format, nullable. It does NOT support
    additionalProperties, $schema, definitions, $ref, etc.
    """
    if not isinstance(schema, dict):
        return schema

    cleaned = {}
    # Keys Gemini accepts
    ALLOWED = {
        "type", "properties", "required", "items", "enum",
        "description", "format", "nullable", "minimum", "maximum",
    }
    for k, v in schema.items():
        if k not in ALLOWED:
            continue
        if k == "properties" and isinstance(v, dict):
            cleaned[k] = {pk: _clean_schema_for_gemini(pv) for pk, pv in v.items()}
        elif k == "items" and isinstance(v, dict):
            cleaned[k] = _clean_schema_for_gemini(v)
        elif k == "required" and isinstance(v, list):
            cleaned[k] = v
        else:
            cleaned[k] = v
    return cleaned


def _anthropic_messages_to_gemini(messages: list) -> list:
    """Convert Anthropic-format messages to Gemini contents format.

    Anthropic:
      {"role": "user", "content": "text"}
      {"role": "assistant", "content": [{"type": "text", ...}, {"type": "tool_use", ...}]}
      {"role": "user", "content": [{"type": "tool_result", "tool_use_id": ..., "content": ...}]}

    Gemini:
      {"role": "user", "parts": [{"text": "..."}]}
      {"role": "model", "parts": [{"text": "..."}, {"functionCall": {"name": ..., "args": ...}}]}
      {"role": "user", "parts": [{"functionResponse": {"name": ..., "response": {"result": ...}}}]}
    """
    contents = []
    # Map of tool_use_id → tool_name for resolving tool_result references
    tool_id_to_name: Dict[str, str] = {}

    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")

        if role == "user":
            if isinstance(content, str):
                contents.append({"role": "user", "parts": [{"text": content}]})
            elif isinstance(content, list):
                parts = []
                for block in content:
                    if isinstance(block, str):
                        parts.append({"text": block})
                    elif block.get("type") == "tool_result":
                        # Tool result — convert to functionResponse
                        tool_id = block.get("tool_use_id", "")
                        tool_name = tool_id_to_name.get(tool_id, "unknown")
                        result_content = block.get("content", "")
                        if isinstance(result_content, str):
                            try:
                                result_obj = json.loads(result_content)
                            except (json.JSONDecodeError, TypeError):
                                result_obj = {"result": result_content}
                        else:
                            result_obj = result_content
                        parts.append({
                            "functionResponse": {
                                "name": tool_name,
                                "response": result_obj,
                            }
                        })
                    elif block.get("type") == "text":
                        parts.append({"text": block.get("text", "")})
                if parts:
                    contents.append({"role": "user", "parts": parts})

        elif role == "assistant":
            parts = []
            if isinstance(content, str):
                parts.append({"text": content})
            elif isinstance(content, list):
                for block in content:
                    if block.get("type") == "text":
                        text = block.get("text", "")
                        if text:
                            parts.append({"text": text})
                    elif block.get("type") == "tool_use":
                        tool_id = block.get("id", "")
                        tool_name = block.get("name", "")
                        tool_id_to_name[tool_id] = tool_name
                        fc_part: Dict[str, Any] = {
                            "functionCall": {
                                "name": tool_name,
                                "args": block.get("input", {}),
                            }
                        }
                        # Restore thought_signature for Gemini 3.x replay
                        if block.get("thought_signature"):
                            fc_part["thoughtSignature"] = block["thought_signature"]
                        parts.append(fc_part)
            if parts:
                contents.append({"role": "model", "parts": parts})

    return contents


def _gemini_response_to_anthropic(data: Dict) -> Dict:
    """Convert Gemini generateContent response to Anthropic format.

    Anthropic format:
      {"content": [{"type": "text", "text": "..."}, {"type": "tool_use", "id": ..., "name": ..., "input": ...}],
       "stop_reason": "end_turn" | "tool_use"}
    """
    import uuid
    candidates = data.get("candidates", [])
    if not candidates:
        return {"content": [{"type": "text", "text": "I encountered an error."}], "stop_reason": "end_turn"}

    parts = candidates[0].get("content", {}).get("parts", [])
    content_blocks = []
    has_tool_call = False

    for part in parts:
        # Skip thinking/thought parts (Gemini 3.x internal reasoning)
        if part.get("thought"):
            continue
        if "text" in part and part["text"]:
            content_blocks.append({"type": "text", "text": part["text"]})
        elif "functionCall" in part:
            has_tool_call = True
            fc = part["functionCall"]
            block = {
                "type": "tool_use",
                "id": f"toolu_{uuid.uuid4().hex[:20]}",
                "name": fc.get("name", ""),
                "input": fc.get("args", {}),
            }
            # Preserve thought_signature for Gemini 3.x replay
            if "thoughtSignature" in part:
                block["thought_signature"] = part["thoughtSignature"]
            content_blocks.append(block)

    if not content_blocks:
        content_blocks = [{"type": "text", "text": "Done."}]

    return {
        "content": content_blocks,
        "stop_reason": "tool_use" if has_tool_call else "end_turn",
    }
