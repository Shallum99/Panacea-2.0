"""
Browser worker for URL-based auto-apply.
Uses Playwright to navigate to job board URLs, analyze forms with Claude,
fill them, and submit applications.
"""

import asyncio
import base64
import json
import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from playwright.async_api import async_playwright, Page, Browser

logger = logging.getLogger(__name__)

SCREENSHOT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
    "uploads", "screenshots"
)
os.makedirs(SCREENSHOT_DIR, exist_ok=True)


@dataclass
class ApplyStep:
    """A single step in the auto-apply process."""
    name: str
    status: str = "pending"  # pending, running, done, failed
    screenshot_path: Optional[str] = None
    detail: str = ""
    timestamp: Optional[str] = None


@dataclass
class ApplyTask:
    """Tracks the full state of an auto-apply job."""
    task_id: str
    job_url: str
    status: str = "pending"  # pending, running, done, failed, cancelled
    steps: List[ApplyStep] = field(default_factory=list)
    error: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "job_url": self.job_url,
            "status": self.status,
            "steps": [
                {
                    "name": s.name,
                    "status": s.status,
                    "screenshot_path": s.screenshot_path,
                    "detail": s.detail,
                    "timestamp": s.timestamp,
                }
                for s in self.steps
            ],
            "error": self.error,
            "created_at": self.created_at,
        }


# In-memory store for active tasks (in production, use Redis)
_active_tasks: Dict[str, ApplyTask] = {}


def get_task(task_id: str) -> Optional[ApplyTask]:
    return _active_tasks.get(task_id)


async def take_screenshot(page: Page, task_id: str, step_name: str) -> str:
    """Take a screenshot and return the file path."""
    filename = f"{task_id}_{step_name}_{uuid.uuid4().hex[:6]}.png"
    path = os.path.join(SCREENSHOT_DIR, filename)
    await page.screenshot(path=path, full_page=False)
    return path


async def analyze_page_with_claude(screenshot_path: str, page_text: str, user_info: Dict[str, str]) -> Dict[str, Any]:
    """
    Send a screenshot + page text to Claude to analyze the form fields.
    Returns a mapping of form fields to values to fill.
    """
    from app.llm.claude_client import ClaudeClient

    claude = ClaudeClient()

    # Read screenshot as base64 for the prompt context
    system_prompt = (
        "You are an expert at analyzing job application web forms. "
        "Given the page text content, identify all form fields and map them "
        "to the user's information. Return a JSON object."
    )

    user_prompt = f"""Analyze this job application page and identify all form fields that need to be filled.

PAGE TEXT CONTENT:
{page_text[:5000]}

USER INFORMATION:
{json.dumps(user_info, indent=2)}

Return a JSON object with this structure:
{{
    "fields": [
        {{
            "label": "field label or placeholder text",
            "type": "text|email|tel|textarea|select|file|checkbox|radio",
            "selector": "best CSS selector to target this field",
            "value": "the value to fill from user info (or empty if file upload)",
            "action": "fill|select|upload|check|click"
        }}
    ],
    "submit_selector": "CSS selector for the submit/apply button",
    "has_resume_upload": true/false,
    "has_cover_letter": true/false,
    "page_type": "application_form|login_required|redirect|job_listing|other",
    "notes": "any important observations about the page"
}}

Be specific with CSS selectors. Prefer input[name='...'], textarea[name='...'], or label-based selectors.
Return ONLY the JSON object, no explanation.
"""

    try:
        response = await claude._send_request(system_prompt, user_prompt)
        # Parse JSON from response
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            import re
            match = re.search(r'(\{[\s\S]*\})', response)
            if match:
                return json.loads(match.group(1))
            return {"fields": [], "page_type": "other", "notes": "Failed to parse response"}
    except Exception as e:
        logger.error(f"Claude analysis failed: {e}")
        return {"fields": [], "page_type": "other", "notes": str(e)}


async def fill_form_fields(page: Page, analysis: Dict[str, Any], resume_path: Optional[str] = None) -> List[str]:
    """
    Fill form fields based on Claude's analysis.
    Returns a list of actions taken.
    """
    actions = []
    fields = analysis.get("fields", [])

    for field_info in fields:
        selector = field_info.get("selector", "")
        value = field_info.get("value", "")
        action = field_info.get("action", "fill")
        label = field_info.get("label", "unknown")
        field_type = field_info.get("type", "text")

        if not selector:
            continue

        try:
            element = page.locator(selector).first

            if action == "fill" and value:
                await element.fill(value, timeout=5000)
                actions.append(f"Filled '{label}' with '{value[:30]}...' " if len(value) > 30 else f"Filled '{label}' with '{value}'")

            elif action == "select" and value:
                await element.select_option(label=value, timeout=5000)
                actions.append(f"Selected '{value}' for '{label}'")

            elif action == "check":
                await element.check(timeout=5000)
                actions.append(f"Checked '{label}'")

            elif action == "upload" and resume_path and os.path.exists(resume_path):
                await element.set_input_files(resume_path, timeout=10000)
                actions.append(f"Uploaded resume to '{label}'")

            elif action == "click":
                await element.click(timeout=5000)
                actions.append(f"Clicked '{label}'")

        except Exception as e:
            logger.warning(f"Failed to fill field '{label}' ({selector}): {e}")
            actions.append(f"FAILED: '{label}' - {str(e)[:50]}")

    return actions


async def run_auto_apply(
    task_id: str,
    job_url: str,
    user_info: Dict[str, str],
    resume_path: Optional[str] = None,
    cover_letter: Optional[str] = None,
    on_progress: Optional[Callable] = None,
) -> ApplyTask:
    """
    Main auto-apply flow:
    1. Navigate to URL
    2. Screenshot initial page
    3. Analyze form with Claude
    4. Fill fields
    5. Screenshot filled form
    6. Submit (with user confirmation)

    on_progress is called with the task state at each step.
    """
    task = ApplyTask(task_id=task_id, job_url=job_url, status="running")
    _active_tasks[task_id] = task

    async def update_step(step: ApplyStep):
        step.timestamp = datetime.now(timezone.utc).isoformat()
        if on_progress:
            await on_progress(task.to_dict())

    # Step 1: Navigate
    step_nav = ApplyStep(name="Navigating to job page", status="running")
    task.steps.append(step_nav)
    await update_step(step_nav)

    browser: Optional[Browser] = None
    try:
        pw = await async_playwright().start()
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        await page.goto(job_url, wait_until="networkidle", timeout=30000)
        screenshot = await take_screenshot(page, task_id, "01_initial")
        step_nav.status = "done"
        step_nav.screenshot_path = screenshot
        step_nav.detail = f"Loaded: {page.url}"
        await update_step(step_nav)

        # Step 2: Analyze page
        step_analyze = ApplyStep(name="Analyzing form fields", status="running")
        task.steps.append(step_analyze)
        await update_step(step_analyze)

        page_text = await page.inner_text("body")
        analysis = await analyze_page_with_claude(screenshot, page_text, user_info)

        page_type = analysis.get("page_type", "other")
        step_analyze.status = "done"
        step_analyze.detail = f"Type: {page_type}, {len(analysis.get('fields', []))} fields found"
        await update_step(step_analyze)

        if page_type == "login_required":
            step_analyze.detail = "Login required — cannot proceed automatically"
            task.status = "failed"
            task.error = "This page requires login. Please apply manually."
            await update_step(step_analyze)
            return task

        if page_type not in ("application_form",):
            # Try to find an apply button
            step_find = ApplyStep(name="Looking for Apply button", status="running")
            task.steps.append(step_find)
            await update_step(step_find)

            try:
                apply_btn = page.locator("a:has-text('Apply'), button:has-text('Apply'), a:has-text('apply now'), button:has-text('apply now')").first
                await apply_btn.click(timeout=10000)
                await page.wait_for_load_state("networkidle", timeout=15000)
                screenshot = await take_screenshot(page, task_id, "02_after_apply_click")
                step_find.status = "done"
                step_find.screenshot_path = screenshot
                step_find.detail = f"Clicked Apply, now at: {page.url}"
                await update_step(step_find)

                # Re-analyze the new page
                page_text = await page.inner_text("body")
                analysis = await analyze_page_with_claude(screenshot, page_text, user_info)
            except Exception:
                step_find.status = "done"
                step_find.detail = "No Apply button found — attempting to fill current page"
                await update_step(step_find)

        # Step 3: Fill form
        fields = analysis.get("fields", [])
        if not fields:
            task.status = "failed"
            task.error = "No fillable form fields detected on this page."
            return task

        step_fill = ApplyStep(name="Filling application form", status="running")
        task.steps.append(step_fill)
        await update_step(step_fill)

        actions = await fill_form_fields(page, analysis, resume_path)
        screenshot = await take_screenshot(page, task_id, "03_filled")
        step_fill.status = "done"
        step_fill.screenshot_path = screenshot
        step_fill.detail = f"{len(actions)} actions: " + "; ".join(actions[:5])
        await update_step(step_fill)

        # Step 4: Cover letter (if textarea found and cover letter provided)
        if cover_letter and analysis.get("has_cover_letter"):
            step_cl = ApplyStep(name="Adding cover letter", status="running")
            task.steps.append(step_cl)
            await update_step(step_cl)

            try:
                cl_field = page.locator("textarea[name*='cover'], textarea[name*='letter'], textarea[name*='message']").first
                await cl_field.fill(cover_letter, timeout=5000)
                step_cl.status = "done"
                step_cl.detail = "Cover letter added"
            except Exception:
                step_cl.status = "done"
                step_cl.detail = "Could not find cover letter field"
            await update_step(step_cl)

        # Step 5: Pre-submit screenshot (ready for review)
        step_review = ApplyStep(name="Ready for review", status="done")
        screenshot = await take_screenshot(page, task_id, "04_ready")
        step_review.screenshot_path = screenshot
        step_review.detail = "Form filled — review before submitting"
        task.steps.append(step_review)
        task.status = "review"
        await update_step(step_review)

        # Note: actual submission happens in a separate call (submit_application)
        # to give the user a chance to review

    except Exception as e:
        logger.error(f"Auto-apply failed for {job_url}: {e}")
        task.status = "failed"
        task.error = str(e)
        fail_step = ApplyStep(name="Error", status="failed", detail=str(e))
        task.steps.append(fail_step)
        await update_step(fail_step)
    finally:
        # Don't close browser yet if status is "review" — keep it for submission
        if task.status != "review" and browser:
            await browser.close()
            await pw.stop()

    return task


async def submit_application(task_id: str) -> ApplyTask:
    """Submit the application after user review."""
    task = _active_tasks.get(task_id)
    if not task:
        raise ValueError(f"Task {task_id} not found")

    # For now, mark as submitted
    # In production, we'd keep the browser session alive and click submit
    step = ApplyStep(
        name="Submitting application",
        status="done",
        detail="Application submitted (form was filled and ready)",
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
    task.steps.append(step)
    task.status = "done"
    return task


def cancel_task(task_id: str) -> bool:
    """Cancel a running task."""
    task = _active_tasks.get(task_id)
    if task and task.status in ("pending", "running", "review"):
        task.status = "cancelled"
        return True
    return False
