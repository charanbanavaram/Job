import html
import logging
import os
import re
import time
import urllib.parse
import requests

logger = logging.getLogger(__name__)

TELEGRAM_USER = os.getenv("TELEGRAM_USER", "@charanb07")


def sanitize_telegram_text(text: str) -> str:
    """Sanitizes text to avoid triggering Apache/ModSecurity WAF rules."""
    if not text:
        return ""
    # Strip HTML tags
    cleaned = re.sub(r"<[^>]+>", " ", str(text))
    # Remove apostrophes and quotes that can trigger SQLi/XSS WAF rules
    cleaned = cleaned.replace("'", "").replace('"', "").replace("`", "")
    # Normalize multiple whitespace
    cleaned = re.sub(r"[ \t]+", " ", cleaned).strip()
    return cleaned


class JobNotifier:
    def __init__(self):
        self.user = os.getenv("TELEGRAM_USER", TELEGRAM_USER)
        if not self.user.startswith("@"):
            self.user = f"@{self.user}"

    def send_alert(self, job: dict, eval_result: dict) -> bool:
        """Sends an alert to Telegram via CallMeBot API with WAF protection, experience fit, and throttling."""
        score = eval_result.get("score", eval_result.get("match_score", 0))
        skills_list = eval_result.get("matched_skills", [])
        skills = ", ".join(skills_list) if skills_list else "Technical Alignment"
        raw_reason = eval_result.get("reason", eval_result.get("reasoning", "Strong profile overlap."))
        raw_exp_fit = eval_result.get("experience_fit", "0-2 years (Entry / Junior)")
        
        # Sanitize text fields
        reason = sanitize_telegram_text(raw_reason)
        experience_fit = sanitize_telegram_text(raw_exp_fit)
        title = sanitize_telegram_text(job.get("title", "Untitled Role"))
        company = sanitize_telegram_text(job.get("company", "Company"))
        location = sanitize_telegram_text(job.get("location", "N/A"))
        source = sanitize_telegram_text(job.get("source", "ATS"))
        skills = sanitize_telegram_text(skills)
        url = job.get("url", "").strip()

        # NOTICE: Do NOT use "Location:" as a line starter.
        # CallMeBot Apache WAF (ModSecurity CRS Rule 921150) blocks "\nLocation:"
        # as an HTTP Header Injection / Response Splitting exploit.
        message = (
            f"🎯 *NEW JOB MATCH ({score}/100)*\n\n"
            f"🏢 *Company:* {company}\n"
            f"💼 *Role:* {title}\n"
            f"📍 *Office -* {location}\n"
            f"⏳ *Experience:* {experience_fit}\n"
            f"🌐 *Source:* {source}\n\n"
            f"✅ *Matched Skills:* {skills}\n"
            f"💡 *Fit Insight:* {reason}\n\n"
            f"🔗 *Apply:* {url}"
        )

        encoded_text = urllib.parse.quote(message)
        api_url = f"https://api.callmebot.com/text.php?user={self.user}&text={encoded_text}"

        try:
            res = requests.get(api_url, timeout=15)
            # Throttling delay between consecutive alerts so we never trip CallMeBot rate limits
            time.sleep(2.5)

            if res.status_code == 200:
                logger.info(f"[Notifier] Telegram alert successfully sent to {self.user} for {title}")
                return True
            else:
                logger.warning(
                    f"[Notifier] Delivery failed ({res.status_code}) for '{title}': {res.text[:120]}"
                )
                return False
        except Exception as e:
            logger.error(f"[Notifier] Request error dispatching alert for '{title}': {e}")
            return False


# Compatibility aliases
WhatsAppNotifier = JobNotifier
AlertNotifier = JobNotifier
