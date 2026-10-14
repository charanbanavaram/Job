"""
Automated Job Notification System - Main Orchestrator

1. Resume Profile: Loads candidate profile (1 yr exp, 0-2 yrs target, Bengaluru/Chennai/Hyderabad priority).
2. Job Sourcing: Fetches live postings from Greenhouse, Lever, Ashby.
3. Deduplication: Ensures no job in seen_jobs.txt is ever alerted or re-processed.
4. Pre-filtering:
   - Technical Role Filter: Shields non-engineering jobs.
   - Hard Geographic Filter: Shields non-India / foreign onsite locations.
5. AI Matching: Evaluates qualified jobs using Google Gemini 1.5 Flash (0-100 score).
6. Alerting: Sends Telegram alert via CallMeBot API when match_score >= 60.
7. Updates: Records processed jobs in seen_jobs.txt.
"""

import argparse
import json
import logging
import os
import re
import sys
import time
from typing import Any, Dict, List
from dotenv import load_dotenv

from dedup import DeduplicationManager
from matcher import JobMatcher
from notifier import JobNotifier
from sourcing import fetch_all_jobs

# Default alert threshold tuned for early career / high profile overlap
ALERT_THRESHOLD = 60

# Technical role keywords to filter out non-engineering jobs before calling Gemini
TECH_KEYWORDS = [
    "engineer",
    "developer",
    "sde",
    "backend",
    "frontend",
    "full stack",
    "fullstack",
    "software",
    "cloud",
    "devops",
    "platform",
    "intern",
    "infrastructure",
    "systems",
    "qa",
    "test",
]

# Allowed geographic terms for India and Global Remote
ALLOWED_GEO_KEYWORDS = [
    "india",
    "bengaluru",
    "bangalore",
    "chennai",
    "hyderabad",
    "pune",
    "mumbai",
    "gurgaon",
    "gurugram",
    "noida",
    "delhi",
    "remote",
    "anywhere",
    "worldwide",
]

# Explicit foreign indicators that disqualify a job (unless India or Anywhere is explicitly specified)
FOREIGN_GEO_INDICATORS = [
    r"\bus\b", r"\busa\b", r"\bunited states\b", r"\buk\b", r"\bunited kingdom\b",
    r"\blondon\b", r"\beurope\b", r"\bemea\b", r"\bamer\b", r"\bapac\b",
    r"\bcanada\b", r"\btoronto\b", r"\bvancouver\b", r"\bgermany\b", r"\bberlin\b",
    r"\bfrance\b", r"\bparis\b", r"\bjapan\b", r"\btokyo\b", r"\bsingapore\b",
    r"\baustralia\b", r"\bsydney\b", r"\bmelbourne\b", r"\bphilippines\b",
    r"\bmalaysia\b", r"\bindonesia\b", r"\bsan francisco\b", r"\bbay area\b",
    r"\bnew york\b", r"\bnyc\b", r"\bchicago\b", r"\baustin\b", r"\bseattle\b",
    r"\bfoster city\b", r"\bpalo alto\b", r"\bcalifornia\b", r"\btexas\b",
    r"\billinois\b", r"\bireland\b", r"\bdublin\b", r"\bnetherlands\b",
    r"\bamsterdam\b", r"\bbrazil\b", r"\blatam\b", r"\bnorth america\b",
]

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("job_tracker")


def load_candidate_profile(profile_path: str = "profile.json") -> Dict[str, Any]:
    """Loads candidate resume details from profile.json."""
    if not os.path.exists(profile_path):
        raise FileNotFoundError(f"Resume profile file not found at {profile_path}")

    with open(profile_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data


def is_technical_role(title: str) -> bool:
    """Pre-filters role title against technical engineering keywords."""
    title_lower = (title or "").lower()
    return any(kw in title_lower for kw in TECH_KEYWORDS)


def is_geographic_match(location_str: str) -> bool:
    """
    Hard geographic pre-filter:
    - Allows India, Bengaluru, Chennai, Hyderabad, Pune, Mumbai, Delhi/NCR, Remote, Anywhere, Worldwide.
    - Excludes explicit US, UK, Europe, Canada, APAC-ex-India, or foreign cities.
    """
    if not location_str or location_str.strip().lower() in ["n/a", "unspecified"]:
        return False

    loc = location_str.lower()

    # Explicit global or India remote overrides
    if any(k in loc for k in ["india remote", "anywhere", "worldwide", "remote, global"]):
        return True

    # Check for foreign country or city indicators
    for pattern in FOREIGN_GEO_INDICATORS:
        if re.search(pattern, loc):
            # If a foreign token is present, only permit if it explicitly mentions India or target Indian cities
            if any(k in loc for k in ["india", "bengaluru", "bangalore", "chennai", "hyderabad"]):
                return True
            return False

    # Check if location contains any allowed geographic keywords
    return any(k in loc for k in ALLOWED_GEO_KEYWORDS)


def run_job_tracker(
    profile_path: str = "profile.json",
    seen_file: str = "seen_jobs.txt",
    limit: int = None,
    dry_run: bool = False,
    score_threshold: int = ALERT_THRESHOLD,
) -> Dict[str, int]:
    """Executes a full run of the job sourcing, filtering, matching, and notification pipeline."""
    # 1. Load Environment Variables (.env)
    load_dotenv()

    logger.info("=" * 60)
    logger.info("Starting Automated Job Notification Run")
    logger.info(f"Target Alert Threshold: >= {score_threshold}/100")
    logger.info("=" * 60)

    # 2. Load Resume Profile
    profile = load_candidate_profile(profile_path)
    cand_info = profile.get("candidate", {})
    logger.info(f"Loaded Candidate: {cand_info.get('name')} | Exp: {cand_info.get('experience_level')}")
    logger.info(f"Target Seniority: {', '.join(cand_info.get('target_seniority', [])[:3])}...")
    logger.info(f"Geo Priorities: 1. Bengaluru | 2. Chennai | 3. Hyderabad | Remote (India)")

    # 3. Initialize Deduplication Manager
    dedup = DeduplicationManager(filepath=seen_file)
    logger.info(f"Loaded {dedup.count()} previously processed jobs from '{seen_file}'.")

    # 4. Fetch Live Postings
    all_postings = fetch_all_jobs()
    total_fetched = len(all_postings)
    logger.info(f"Total live postings sourced: {total_fetched}")

    # 5. Filter Unseen Jobs
    unseen_jobs: List[Dict[str, Any]] = [j for j in all_postings if not dedup.is_seen(j["id"])]
    skipped_count = total_fetched - len(unseen_jobs)
    logger.info(f"Skipped {skipped_count} previously seen jobs. New unseen jobs to process: {len(unseen_jobs)}")

    if limit and limit > 0:
        unseen_jobs = unseen_jobs[:limit]
        logger.info(f"Applying limit: processing first {len(unseen_jobs)} jobs.")

    # 6. Initialize AI Matcher & Notifier
    gemini_key = os.getenv("GEMINI_API_KEY", "")
    matcher = JobMatcher(api_key=gemini_key)
    notifier = JobNotifier()

    high_matches_count = 0
    alerts_sent_count = 0
    processed_count = 0
    non_tech_skipped_count = 0
    geo_skipped_count = 0
    ai_evaluated_count = 0

    # 7. Evaluate and Alert
    for idx, job in enumerate(unseen_jobs, start=1):
        job_id = job["id"]
        job_title = job["title"]
        job_comp = job["company"]
        job_loc = job.get("location", "N/A")

        # Pre-filter 1: Strict Technical Role Filter
        if not is_technical_role(job_title):
            non_tech_skipped_count += 1
            logger.info(f"[{idx}/{len(unseen_jobs)}] [Non-Tech Shield] '{job_title}' @ {job_comp} -> Skipped")
            if not dry_run:
                dedup.mark_seen(job_id)
            processed_count += 1
            continue

        # Pre-filter 2: Hard Geographic Filter (India / Remote only)
        if not is_geographic_match(job_loc):
            geo_skipped_count += 1
            logger.info(f"[{idx}/{len(unseen_jobs)}] [Geo Shield] '{job_title}' @ {job_comp} (Loc: '{job_loc}') -> Outside India/Remote preference")
            if not dry_run:
                dedup.mark_seen(job_id)
            processed_count += 1
            continue

        logger.info(f"[{idx}/{len(unseen_jobs)}] Evaluating: '{job_title}' @ {job_comp} | Loc: '{job_loc}' ({job['source']})")
        ai_evaluated_count += 1

        # 1.5-second pacing delay to shield Gemini Free-Tier RPM quota
        time.sleep(1.5)

        # Score with Gemini 1.5 Flash (or heuristic fallback)
        evaluation = matcher.score_job(job, profile)
        score = evaluation.get("score", evaluation.get("match_score", 0))
        logger.info(f"  -> Score: {score}/100 | Exp: {evaluation.get('experience_fit')} | Loc: {evaluation.get('location_fit')}")

        if score >= score_threshold:
            high_matches_count += 1
            logger.info(f"  [*] High Match Detected ({score} >= {score_threshold})! Dispatching alert...")
            if not dry_run:
                sent = notifier.send_alert(job, evaluation)
                if sent:
                    alerts_sent_count += 1
            else:
                logger.info("  [Dry Run] Alert not sent to network.")

        # Mark as seen so it is never re-processed
        if not dry_run:
            dedup.mark_seen(job_id)

        processed_count += 1

    # 8. Summary Report
    metrics = {
        "total_fetched": total_fetched,
        "skipped_seen": skipped_count,
        "processed": processed_count,
        "non_tech_shielded": non_tech_skipped_count,
        "geo_shielded": geo_skipped_count,
        "ai_evaluated": ai_evaluated_count,
        "high_matches": high_matches_count,
        "alerts_sent": alerts_sent_count,
        "total_seen_now": dedup.count(),
    }

    logger.info("=" * 60)
    logger.info("Execution Summary:")
    logger.info(f"  - Total Postings Sourced:   {metrics['total_fetched']}")
    logger.info(f"  - Already Seen & Skipped:   {metrics['skipped_seen']}")
    logger.info(f"  - New Jobs Processed:       {metrics['processed']}")
    logger.info(f"  - Non-Tech Filter Shield:   {metrics['non_tech_shielded']}")
    logger.info(f"  - Geo Filter Shield:        {metrics['geo_shielded']}")
    logger.info(f"  - AI Evaluated:             {metrics['ai_evaluated']}")
    logger.info(f"  - High Matches (>= {score_threshold}):   {metrics['high_matches']}")
    logger.info(f"  - Telegram Alerts Sent:     {metrics['alerts_sent']}")
    logger.info(f"  - Total Seen Jobs Stored:   {metrics['total_seen_now']}")
    logger.info("=" * 60)

    return metrics


def main():
    parser = argparse.ArgumentParser(description="Automated Job Notification System")
    parser.add_argument("--profile", default="profile.json", help="Path to profile JSON")
    parser.add_argument("--seen-file", default="seen_jobs.txt", help="Path to seen_jobs.txt")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of jobs to score")
    parser.add_argument("--dry-run", action="store_true", help="Perform dry run without updating seen jobs or sending live alerts")
    parser.add_argument("--threshold", type=int, default=ALERT_THRESHOLD, help="Match score threshold for alert (default: 60)")
    args = parser.parse_args()

    run_job_tracker(
        profile_path=args.profile,
        seen_file=args.seen_file,
        limit=args.limit,
        dry_run=args.dry_run,
        score_threshold=args.threshold,
    )


if __name__ == "__main__":
    main()
