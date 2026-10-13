"""
Alerting Module using CallMeBot API (WhatsApp & Telegram)
Dispatches formatted notifications for high-match job opportunities (score >= 75).
"""

import logging
import os
import urllib.parse
from typing import Any, Dict
import requests

logger = logging.getLogger(__name__)

CALLMEBOT_WHATSAPP_ENDPOINT = "https://api.callmebot.com/whatsapp.php"
CALLMEBOT_TELEGRAM_ENDPOINT = "https://api.callmebot.com/text.php"


def format_alert_message(job: Dict[str, Any], evaluation: Dict[str, Any]) -> str:
    """Formats job and AI match details into an eye-catching notification message."""
    company = job.get("company", "Company")
    title = job.get("title", "Software Engineer")
    score = evaluation.get("match_score", 0)
    location = job.get("location", "Remote/Hybrid")
    source = job.get("source", "ATS")
    url = job.get("url", "")
    reasoning = evaluation.get("reasoning", "")
    matched_skills = evaluation.get("matched_skills", [])

    skills_text = ", ".join(matched_skills[:6]) if matched_skills else "Core Software Stack"

    # Truncate reasoning if too long for readability
    if len(reasoning) > 280:
        reasoning = reasoning[:277] + "..."

    message = (
        f"🎯 *NEW HIGH-MATCH JOB ALERT!* 🎯\n\n"
        f"🏢 *Company:* {company}\n"
        f"💼 *Role:* {title}\n"
        f"📊 *Score:* {score}/100\n"
        f"📍 *Location:* {location}\n"
        f"🌐 *Platform:* {source}\n\n"
        f"✅ *Matched Skills:*\n{skills_text}\n\n"
        f"💡 *AI Match Insight:*\n{reasoning}\n\n"
        f"🔗 *Apply Here:*\n{url}"
    )
    return message


class AlertNotifier:
    def __init__(self, phone: str = None, whatsapp_key: str = None, telegram_user: str = None):
        self.phone = (phone or os.getenv("CALLMEBOT_PHONE", "+918985897700")).strip()
        self.whatsapp_key = (whatsapp_key or os.getenv("CALLMEBOT_API_KEY", "")).strip()
        self.telegram_user = (telegram_user or os.getenv("TELEGRAM_USER", "")).strip()

    def send_alert(self, job: Dict[str, Any], evaluation: Dict[str, Any]) -> bool:
        """Sends alerts via Telegram and/or WhatsApp if score >= 75."""
        score = evaluation.get("match_score", 0)
        if score < 75:
            logger.info(f"Skipping notification for '{job.get('title')}' (Score {score} < 75)")
            return False

        message_body = format_alert_message(job, evaluation)
        dispatched = False

        # 1. Send via Telegram if TELEGRAM_USER is configured
        if self.telegram_user:
            tg_sent = self._send_telegram(message_body, job)
            if tg_sent:
                dispatched = True

        # 2. Send via WhatsApp if CALLMEBOT_API_KEY is configured
        if self.whatsapp_key and self.whatsapp_key not in ["YOUR_CALLMEBOT_API_KEY", "YOUR_API_KEY", "test"]:
            wa_sent = self._send_whatsapp(message_body, job)
            if wa_sent:
                dispatched = True

        # 3. If neither destination was active or keys are in test mode
        if not dispatched:
            logger.warning("[AlertNotifier] No active external notification channel configured or in test mode.")
            logger.info(f"[Alert Notification Preview]:\n{message_body}\n")
            return True

        return dispatched

    def _send_telegram(self, message: str, job: Dict[str, Any]) -> bool:
        """Sends Telegram notification via CallMeBot text API."""
        try:
            params = {
                "user": self.telegram_user,
                "text": message,
            }
            resp = requests.get(CALLMEBOT_TELEGRAM_ENDPOINT, params=params, timeout=15)
            if resp.status_code == 200 and "Successful" in resp.text:
                logger.info(f"Telegram alert successfully dispatched to {self.telegram_user} for '{job.get('title')}' at '{job.get('company')}'.")
                return True
            else:
                logger.warning(f"Telegram alert response {resp.status_code}: {resp.text[:200]}")
                return False
        except Exception as e:
            logger.error(f"Failed to send Telegram message via CallMeBot: {e}")
            return False

    def _send_whatsapp(self, message: str, job: Dict[str, Any]) -> bool:
        """Sends WhatsApp notification via CallMeBot WhatsApp API."""
        try:
            params = {
                "phone": self.phone,
                "text": message,
                "apikey": self.whatsapp_key,
            }
            resp = requests.get(CALLMEBOT_WHATSAPP_ENDPOINT, params=params, timeout=15)
            if resp.status_code == 200:
                logger.info(f"WhatsApp alert successfully dispatched to {self.phone} for '{job.get('title')}' at '{job.get('company')}'.")
                return True
            else:
                logger.error(f"WhatsApp alert response {resp.status_code}: {resp.text[:200]}")
                return False
        except Exception as e:
            logger.error(f"Failed to send WhatsApp message via CallMeBot: {e}")
            return False


# Backward compatibility alias
WhatsAppNotifier = AlertNotifier
