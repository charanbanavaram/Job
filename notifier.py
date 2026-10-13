import os
import urllib.parse
import requests

TELEGRAM_USER = os.getenv("TELEGRAM_USER", "@charanb07")


class JobNotifier:
    def __init__(self):
        self.user = os.getenv("TELEGRAM_USER", "@charanb07")

    def send_alert(self, job: dict, eval_result: dict) -> bool:
        score = eval_result.get("score", eval_result.get("match_score", 0))
        skills = ", ".join(eval_result.get("matched_skills", [])) or "Technical Alignment"
        reason = eval_result.get("reason", eval_result.get("reasoning", "Strong profile overlap."))

        message = (
            f"🎯 *NEW JOB MATCH ({score}/100)*\n\n"
            f"🏢 *Company:* {job['company']}\n"
            f"💼 *Role:* {job['title']}\n"
            f"📍 *Location:* {job.get('location', 'N/A')}\n"
            f"🌐 *Source:* {job.get('source', 'ATS')}\n\n"
            f"✅ *Matched Skills:* {skills}\n"
            f"💡 *Insight:* {reason}\n\n"
            f"🔗 *Apply:* {job['url']}"
        )

        encoded_text = urllib.parse.quote(message)
        api_url = f"https://api.callmebot.com/text.php?user={self.user}&text={encoded_text}"

        try:
            res = requests.get(api_url, timeout=12)
            if res.status_code == 200:
                print(f"[Notifier] Telegram alert sent to {self.user} for {job['title']}")
                return True
            else:
                print(f"[Notifier] Delivery failed ({res.status_code}): {res.text[:120]}")
                return False
        except Exception as e:
            print(f"[Notifier] Request error: {e}")
            return False


# Compatibility aliases
WhatsAppNotifier = JobNotifier
AlertNotifier = JobNotifier
