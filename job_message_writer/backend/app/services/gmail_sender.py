"""
Gmail API sender — sends email from the user's own Gmail account
using their OAuth refresh token. No extra dependencies (uses httpx + stdlib).
"""

import base64
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from typing import Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class GmailSendError(Exception):
    """Raised when Gmail sending fails."""
    pass


async def refresh_access_token(refresh_token: str) -> str:
    """Exchange a Google refresh token for a fresh access token."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
        )
        if response.status_code != 200:
            logger.error(f"Google token refresh failed: {response.status_code} {response.text}")
            raise GmailSendError(f"Failed to refresh Google access token: {response.text}")

        return response.json()["access_token"]


async def send_via_gmail(
    refresh_token: str,
    to_email: str,
    subject: str,
    body: str,
    from_name: Optional[str] = None,
    from_email: Optional[str] = None,
    attachment_bytes: Optional[bytes] = None,
    attachment_name: Optional[str] = None,
) -> str:
    """
    Send an email via Gmail API using the user's OAuth refresh token.
    Returns the Gmail message ID.
    """
    access_token = await refresh_access_token(refresh_token)

    # Build MIME message
    msg = MIMEMultipart("mixed")
    msg["To"] = to_email
    msg["Subject"] = subject
    if from_name and from_email:
        msg["From"] = f"{from_name} <{from_email}>"
    elif from_email:
        msg["From"] = from_email

    # Body: plain + HTML alternative
    alt = MIMEMultipart("alternative")
    alt.attach(MIMEText(body, "plain"))
    alt.attach(MIMEText(body.replace("\n", "<br>"), "html"))
    msg.attach(alt)

    # PDF attachment
    if attachment_bytes and attachment_name:
        att = MIMEBase("application", "pdf")
        att.set_payload(attachment_bytes)
        encoders.encode_base64(att)
        att.add_header("Content-Disposition", f'attachment; filename="{attachment_name}"')
        msg.attach(att)

    # Base64url encode (Gmail API requires no padding)
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii").rstrip("=")

    # Send via Gmail API
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"raw": raw},
        )

    if response.status_code not in (200, 201):
        logger.error(f"Gmail send failed: {response.status_code} {response.text}")
        raise GmailSendError(f"Gmail API error: {response.status_code}")

    gmail_id = response.json().get("id", "")
    logger.info(f"Email sent via Gmail to {to_email}, id={gmail_id}")
    return gmail_id
