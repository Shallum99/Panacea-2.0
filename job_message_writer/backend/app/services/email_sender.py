"""
Email sending service using SendGrid.
Supports sending application emails with resume attachments.
"""

import os
import logging
import base64
from typing import Optional

logger = logging.getLogger(__name__)

SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY", "")
SENDGRID_FROM_EMAIL = os.getenv("SENDGRID_FROM_EMAIL", "")


async def send_application_email(
    to_email: str,
    subject: str,
    body: str,
    from_email: Optional[str] = None,
    from_name: Optional[str] = None,
    resume_pdf_bytes: Optional[bytes] = None,
    resume_filename: Optional[str] = None,
) -> Optional[str]:
    """
    Send an application email via SendGrid.
    Returns the SendGrid message ID for tracking, or None if sending fails.
    """
    if not SENDGRID_API_KEY:
        logger.warning("SendGrid API key not configured — email not sent")
        return None

    try:
        import httpx

        headers = {
            "Authorization": f"Bearer {SENDGRID_API_KEY}",
            "Content-Type": "application/json",
        }

        payload = {
            "personalizations": [{"to": [{"email": to_email}]}],
            "from": {
                "email": from_email or SENDGRID_FROM_EMAIL,
                "name": from_name or "Job Application",
            },
            "subject": subject,
            "content": [
                {"type": "text/plain", "value": body},
                {"type": "text/html", "value": body.replace("\n", "<br>")},
            ],
            "tracking_settings": {
                "open_tracking": {"enable": True},
                "click_tracking": {"enable": False},
            },
        }

        # Attach resume PDF if provided
        if resume_pdf_bytes and resume_filename:
            encoded = base64.b64encode(resume_pdf_bytes).decode("utf-8")
            payload["attachments"] = [
                {
                    "content": encoded,
                    "filename": resume_filename,
                    "type": "application/pdf",
                    "disposition": "attachment",
                }
            ]

        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.sendgrid.com/v3/mail/send",
                headers=headers,
                json=payload,
            )

            if response.status_code in (200, 201, 202):
                message_id = response.headers.get("X-Message-Id")
                logger.info(f"Email sent to {to_email}, message_id: {message_id}")
                return message_id
            else:
                logger.error(
                    f"SendGrid error {response.status_code}: {response.text}"
                )
                return None

    except Exception as e:
        logger.error(f"Failed to send email: {e}")
        return None
