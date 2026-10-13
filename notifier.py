"""
WhatsApp Alerting Module using CallMeBot API
Dispatches formatted notifications to WhatsApp for high-match job opportunities (score >= 75).
"""

import logging
import os
import urllib.parse
from typing import Any, Dict
import requests

logger = logging.getLogger(__name__)

CALLMEBOT_ENDPOINT = "https://api.callmebot.com/whatsapp.php"


def format_whatsapp_message(job: Dict[str, Any], evaluation: Dict[str, Any]) -> str:
    """Formats job and AI match details into an eye-catching WhatsApp message."""
    company = job.get("company", "Company")
    title = job.get("title", "Software Engineer")
    score = evaluation.get("match_score", 0)
    location = job.get("location", "Remote/Hybrid")
    source = job.get("source", "ATS")
    url = job.get("url", "")
    reasoning = evaluation.get("reasoning", "")
    matched_skills = evaluation.get("matched_skills", [])

    skills_text = ", ".join(matched_skills[:6]) if matched_skills else "Core Software Stack"

    # Truncate reasoning if too long for WhatsApp readability
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


class WhatsAppNotifier:
    def __init__(self, phone: str = None, api_key: str = None):
        # Defaults to candidate's phone if not overridden in env
        self.phone = (phone or os.getenv("CALLMEBOT_PHONE", "+918985897700")).strip()
        self.api_key = (api_key or os.getenv("CALLMEBOT_API_KEY", "")).strip()

    def send_alert(self, job: Dict[str, Any], evaluation: Dict[str, Any]) -> bool:
        """Sends a WhatsApp alert via CallMeBot if score >= 75."""
        score = evaluation.get("match_score", 0)
        if score < 75:
            logger.info(f"Skipping notification for '{job.get('title')}' (Score {score} < 75)")
            return False

        message_body = format_whatsapp_message(job, evaluation)

        # If API key is missing or placeholder, log simulated preview safely
        if not self.api_key or self.api_key in ["YOUR_CALLMEBOT_API_KEY", "YOUR_API_KEY", "test"]:
            logger.warning("[CallMeBot] CALLMEBOT_API_KEY not configured or in test mode.")
            logger.info(f"[CallMeBot Preview Alert]:\n{message_body}\n")
            return True

        encoded_text = urllib.parse.quote_plus(message_body)
        params = {
            "phone": self.phone,
            "text": message_body,
            "apikey": self.api_key,
        }

        try:
            # CallMeBot accepts GET request with params
            resp = requests.get(CALLMEBOT_ENDPOINT, params=params, timeout=15)
            if resp.status_code == 200:
                logger.info(f"WhatsApp alert successfully dispatched to {self.phone} for '{job.get('title')}' at '{job.get('company')}'.")
                return True
            else:
                logger.error(f"CallMeBot returned status {resp.status_code}: {resp.text}")
                return False
        except Exception as e:
            logger.error(f"Failed to send WhatsApp message via CallMeBot: {e}")
            return False
