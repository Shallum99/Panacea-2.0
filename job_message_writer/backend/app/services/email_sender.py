"""
Email sending service.
Tries Gmail API first (if user has a refresh token), falls back to SendGrid.
"""

import os
import logging
import base64
from typing import Optional

import httpx

from app.services.gmail_sender import send_via_gmail, GmailSendError

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
    gmail_refresh_token: Optional[str] = None,
) -> Optional[str]:
    """
    Send an application email.
    Tries Gmail API first (if user has a refresh token), falls back to SendGrid.
    Returns message ID on success, or None if sending fails.
    """
    # Try Gmail first
    if gmail_refresh_token:
        try:
            message_id = await send_via_gmail(
                refresh_token=gmail_refresh_token,
                to_email=to_email,
                subject=subject,
                body=body,
                from_name=from_name,
                from_email=from_email,
                attachment_bytes=resume_pdf_bytes,
                attachment_name=resume_filename,
            )
            return message_id
        except GmailSendError as e:
            logger.warning(f"Gmail send failed, falling back to SendGrid: {e}")
        except Exception as e:
            logger.warning(f"Unexpected Gmail error, falling back to SendGrid: {e}")

    # Fallback: SendGrid
    if not SENDGRID_API_KEY:
        logger.warning("No Gmail token and no SendGrid API key — email not sent")
        return None

    try:
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
                logger.info(f"Email sent via SendGrid to {to_email}, id={message_id}")
                return message_id
            else:
                logger.error(f"SendGrid error {response.status_code}: {response.text}")
                return None

    except Exception as e:
        logger.error(f"Failed to send email: {e}")
        return None
