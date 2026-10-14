"""
Automated Job Notification System - Main Orchestrator

1. Resume Profile: Loads candidate profile (skills, 0-2 yrs experience, target roles).
2. Job Sourcing: Fetches live postings from Greenhouse, Lever, Ashby.
3. Deduplication: Ensures no job in seen_jobs.txt is ever alerted or re-processed.
4. AI Matching: Evaluates each job using Google Gemini 1.5 Flash (0-100 score).
5. Alerting: Sends WhatsApp alert via CallMeBot API when match_score >= 75.
6. Updates: Records processed jobs in seen_jobs.txt.
"""

import argparse
import json
import logging
import os
import sys
from typing import Any, Dict, List
from dotenv import load_dotenv

from dedup import DeduplicationManager
from matcher import JobMatcher
from notifier import JobNotifier
from sourcing import fetch_all_jobs

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


def run_job_tracker(
    profile_path: str = "profile.json",
    seen_file: str = "seen_jobs.txt",
    limit: int = None,
    dry_run: bool = False,
    score_threshold: int = 60,
) -> Dict[str, int]:
    """Executes a full run of the job sourcing, matching, and notification pipeline."""
    # 1. Load Environment Variables (.env)
    load_dotenv()

    logger.info("=" * 60)
    logger.info("Starting Automated Job Notification Run")
    logger.info("=" * 60)

    # 2. Load Resume Profile
    profile = load_candidate_profile(profile_path)
    cand_info = profile.get("candidate", {})
    logger.info(f"Loaded Candidate: {cand_info.get('name')} | Exp: {cand_info.get('experience_level')}")
    logger.info(f"Target Roles: {', '.join(cand_info.get('target_roles', [])[:4])}...")

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

    # 7. Evaluate and Alert
    for idx, job in enumerate(unseen_jobs, start=1):
        job_id = job["id"]
        job_title = job["title"]
        job_comp = job["company"]
        logger.info(f"[{idx}/{len(unseen_jobs)}] Evaluating: '{job_title}' @ {job_comp} ({job['source']})")

        # Score with Gemini 1.5 Flash
        evaluation = matcher.score_job(job, profile)
        score = evaluation.get("match_score", 0)
        logger.info(f"  -> Score: {score}/100 | Recommendation: {evaluation.get('recommendation')}")

        if score >= score_threshold:
            high_matches_count += 1
            logger.info(f"  ★ High Match Detected ({score} >= {score_threshold})! Dispatching alert...")
            if not dry_run:
                sent = notifier.send_alert(job, evaluation)
                if sent:
                    alerts_sent_count += 1
                    import time
                    time.sleep(2)
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
        "high_matches": high_matches_count,
        "alerts_sent": alerts_sent_count,
        "total_seen_now": dedup.count(),
    }

    logger.info("=" * 60)
    logger.info("Execution Summary:")
    logger.info(f"  • Total Postings Sourced: {metrics['total_fetched']}")
    logger.info(f"  • Already Seen & Skipped: {metrics['skipped_seen']}")
    logger.info(f"  • New Jobs Evaluated:     {metrics['processed']}")
    logger.info(f"  • High Matches (>= {score_threshold}): {metrics['high_matches']}")
    logger.info(f"  • WhatsApp Alerts Sent:   {metrics['alerts_sent']}")
    logger.info(f"  • Total Seen Jobs Stored: {metrics['total_seen_now']}")
    logger.info("=" * 60)

    return metrics


def main():
    parser = argparse.ArgumentParser(description="Automated Job Notification System")
    parser.add_argument("--profile", default="profile.json", help="Path to profile JSON")
    parser.add_argument("--seen-file", default="seen_jobs.txt", help="Path to seen_jobs.txt")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of jobs to score")
    parser.add_argument("--dry-run", action="store_true", help="Perform dry run without updating seen jobs or sending live alerts")
    parser.add_argument("--threshold", type=int, default=60, help="Match score threshold for alert (default: 60)")
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
