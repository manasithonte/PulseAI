import asyncio
import logging
import os

import httpx
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

logger = logging.getLogger("pulseai.alerts")

SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL", "")
SENDGRID_API_KEY = os.environ.get("SENDGRID_API_KEY", "")
ALERT_EMAIL_FROM = os.environ.get("ALERT_EMAIL_FROM", "")
ALERT_EMAIL_TO = os.environ.get("ALERT_EMAIL_TO", "")


async def send_slack_alert(message: str) -> None:
    if not SLACK_WEBHOOK_URL:
        logger.info("SLACK_WEBHOOK_URL not set, skipping Slack alert: %s", message)
        return
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            resp = await client.post(SLACK_WEBHOOK_URL, json={"text": message})
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.error("Slack alert failed: %s", exc)


def _send_email_sync(subject: str, message: str) -> None:
    mail = Mail(
        from_email=ALERT_EMAIL_FROM,
        to_emails=ALERT_EMAIL_TO,
        subject=subject,
        plain_text_content=message,
    )
    sg = SendGridAPIClient(SENDGRID_API_KEY)
    sg.send(mail)


async def send_email_alert(subject: str, message: str) -> None:
    if not (SENDGRID_API_KEY and ALERT_EMAIL_FROM and ALERT_EMAIL_TO):
        logger.info("SendGrid not configured, skipping email alert: %s", message)
        return
    try:
        await asyncio.to_thread(_send_email_sync, subject, message)
    except Exception as exc:  # sendgrid client raises generic exceptions on failure
        logger.error("SendGrid alert failed: %s", exc)
