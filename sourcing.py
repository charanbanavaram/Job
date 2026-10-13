"""
Job Sourcing Module
Fetches live, verified postings across Greenhouse, Lever, and Ashby APIs.
"""

import html
import logging
import re
from typing import Any, Dict, List
import requests

logger = logging.getLogger(__name__)

# Headers to emulate browser and prevent blocking
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
}

REQUEST_TIMEOUT = 6

# Company configurations
GREENHOUSE_COMPANIES = {
    "phonepe": ["phonepe", "phonepeindia"],
    "razorpay": ["razorpay", "razorpaysoftwareprivatelimited"],
    "cred": ["cred", "credclub", "dreamplug"],
    "swiggy": ["swiggy", "swiggyindia"],
    "meesho": ["meesho", "meeshoindia", "fashnear"],
    "groww": ["groww"],
    "juspay": ["juspay", "juspaytechnologies"],
}

LEVER_COMPANIES = {
    "postman": ["postman", "postmanlabs"],
    "clevertap": ["clevertap", "clever-tap", "wizrocket"],
}

ASHBY_COMPANIES = {
    "linear": ["linear"],
    "retool": ["retool", "tryretool"],
    "supabase": ["supabase"],
}


def clean_html(raw_html: str) -> str:
    """Removes HTML tags and unescapes HTML entities to produce clean text."""
    if not raw_html:
        return ""
    text = html.unescape(raw_html)
    text = re.sub(r"<script[^>]*>.*?</script>", " ", text, flags=re.DOTALL)
    text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def fetch_greenhouse_jobs_for_board(board_slug: str) -> List[Dict[str, Any]]:
    """Fetches jobs for a single Greenhouse board slug."""
    url = f"https://boards-api.greenhouse.io/v1/boards/{board_slug}/jobs?content=true"
    response = requests.get(url, headers=DEFAULT_HEADERS, timeout=REQUEST_TIMEOUT)
    if response.status_code == 404:
        raise FileNotFoundError(f"Greenhouse board '{board_slug}' not found (404)")
    response.raise_for_status()
    data = response.json()
    jobs = data.get("jobs", [])
    return jobs


def fetch_greenhouse_jobs(companies: Dict[str, List[str]] = GREENHOUSE_COMPANIES) -> List[Dict[str, Any]]:
    """Fetches live jobs from Greenhouse for configured companies."""
    all_jobs: List[Dict[str, Any]] = []

    for company_key, candidate_slugs in companies.items():
        found = False
        for slug in candidate_slugs:
            try:
                raw_jobs = fetch_greenhouse_jobs_for_board(slug)
                logger.info(f"[Greenhouse] Fetched {len(raw_jobs)} postings for '{company_key}' (board: {slug})")
                for item in raw_jobs:
                    job_id = str(item.get("id"))
                    title = item.get("title", "Untitled Role")
                    location_obj = item.get("location") or {}
                    location_str = location_obj.get("name") if isinstance(location_obj, dict) else str(location_obj)
                    job_url = item.get("absolute_url") or f"https://job-boards.greenhouse.io/{slug}/jobs/{job_id}"
                    content = clean_html(item.get("content", ""))

                    all_jobs.append({
                        "id": f"gh_{slug}_{job_id}",
                        "source": "Greenhouse",
                        "company": company_key.capitalize(),
                        "board_slug": slug,
                        "raw_id": job_id,
                        "title": title,
                        "location": location_str or "Unspecified",
                        "url": job_url,
                        "description": content,
                        "updated_at": item.get("updated_at", ""),
                    })
                found = True
                break
            except FileNotFoundError:
                continue
            except Exception as e:
                logger.warning(f"[Greenhouse] Error querying slug '{slug}' for {company_key}: {e}")
                continue

        if not found:
            logger.warning(f"[Greenhouse] No active public Greenhouse board found for '{company_key}'.")

    return all_jobs


def fetch_lever_jobs_for_company(company_slug: str) -> List[Dict[str, Any]]:
    """Fetches postings from Lever API for a company."""
    url = f"https://api.lever.co/v0/postings/{company_slug}?mode=json"
    response = requests.get(url, headers=DEFAULT_HEADERS, timeout=REQUEST_TIMEOUT)
    if response.status_code == 404:
        raise FileNotFoundError(f"Lever board '{company_slug}' not found (404)")
    response.raise_for_status()
    data = response.json()
    if isinstance(data, list):
        return data
    return []


def fetch_lever_jobs(companies: Dict[str, List[str]] = LEVER_COMPANIES) -> List[Dict[str, Any]]:
    """Fetches live jobs from Lever for configured companies."""
    all_jobs: List[Dict[str, Any]] = []

    for company_key, candidate_slugs in companies.items():
        found = False
        for slug in candidate_slugs:
            try:
                raw_jobs = fetch_lever_jobs_for_company(slug)
                logger.info(f"[Lever] Fetched {len(raw_jobs)} postings for '{company_key}' (slug: {slug})")
                for item in raw_jobs:
                    job_id = str(item.get("id"))
                    title = item.get("text", "Untitled Role")
                    categories = item.get("categories") or {}
                    location_str = categories.get("location") if isinstance(categories, dict) else ""
                    job_url = item.get("hostedUrl") or item.get("applyUrl") or f"https://jobs.lever.co/{slug}/{job_id}"
                    description_plain = item.get("descriptionPlain")
                    if not description_plain:
                        description_plain = clean_html(item.get("description", ""))

                    all_jobs.append({
                        "id": f"lever_{slug}_{job_id}",
                        "source": "Lever",
                        "company": company_key.capitalize(),
                        "board_slug": slug,
                        "raw_id": job_id,
                        "title": title,
                        "location": location_str or "Unspecified",
                        "url": job_url,
                        "description": description_plain or "",
                        "updated_at": item.get("createdAt", ""),
                    })
                found = True
                break
            except FileNotFoundError:
                continue
            except Exception as e:
                logger.warning(f"[Lever] Error querying slug '{slug}' for {company_key}: {e}")
                continue

        if not found:
            logger.warning(f"[Lever] No active public Lever board found for '{company_key}'.")

    return all_jobs


def fetch_ashby_jobs_for_board(board_slug: str) -> List[Dict[str, Any]]:
    """Fetches postings from Ashby posting API for an organization."""
    url = f"https://api.ashbyhq.com/posting-api/job-board/{board_slug}"
    response = requests.get(url, headers=DEFAULT_HEADERS, timeout=REQUEST_TIMEOUT)
    if response.status_code == 404:
        raise FileNotFoundError(f"Ashby board '{board_slug}' not found (404)")
    response.raise_for_status()
    data = response.json()
    jobs = data.get("jobs", [])
    return jobs


def fetch_ashby_jobs(companies: Dict[str, List[str]] = ASHBY_COMPANIES) -> List[Dict[str, Any]]:
    """Fetches live jobs from Ashby for configured companies."""
    all_jobs: List[Dict[str, Any]] = []

    for company_key, candidate_slugs in companies.items():
        found = False
        for slug in candidate_slugs:
            try:
                raw_jobs = fetch_ashby_jobs_for_board(slug)
                logger.info(f"[Ashby] Fetched {len(raw_jobs)} postings for '{company_key}' (board: {slug})")
                for item in raw_jobs:
                    job_id = str(item.get("id"))
                    title = item.get("title", "Untitled Role")
                    location_str = item.get("location") or ""
                    job_url = item.get("jobUrl") or item.get("applyUrl") or f"https://jobs.ashbyhq.com/{slug}/{job_id}"
                    desc = item.get("descriptionPlain")
                    if not desc:
                        desc = clean_html(item.get("descriptionHtml", ""))

                    all_jobs.append({
                        "id": f"ashby_{slug}_{job_id}",
                        "source": "Ashby",
                        "company": company_key.capitalize(),
                        "board_slug": slug,
                        "raw_id": job_id,
                        "title": title,
                        "location": location_str or "Unspecified",
                        "url": job_url,
                        "description": desc or "",
                        "updated_at": item.get("publishedAt", ""),
                    })
                found = True
                break
            except FileNotFoundError:
                continue
            except Exception as e:
                logger.warning(f"[Ashby] Error querying slug '{slug}' for {company_key}: {e}")
                continue

        if not found:
            logger.warning(f"[Ashby] No active public Ashby board found for '{company_key}'.")

    return all_jobs


def fetch_all_jobs() -> List[Dict[str, Any]]:
    """Aggregates postings from Greenhouse, Lever, and Ashby."""
    all_jobs: List[Dict[str, Any]] = []

    logger.info("Fetching jobs from Greenhouse...")
    gh_jobs = fetch_greenhouse_jobs()
    all_jobs.extend(gh_jobs)
    logger.info(f"Retrieved {len(gh_jobs)} jobs from Greenhouse.")

    logger.info("Fetching jobs from Lever...")
    lever_jobs = fetch_lever_jobs()
    all_jobs.extend(lever_jobs)
    logger.info(f"Retrieved {len(lever_jobs)} jobs from Lever.")

    logger.info("Fetching jobs from Ashby...")
    ashby_jobs = fetch_ashby_jobs()
    all_jobs.extend(ashby_jobs)
    logger.info(f"Retrieved {len(ashby_jobs)} jobs from Ashby.")

    logger.info(f"Total live postings aggregated across all sources: {len(all_jobs)}")
    return all_jobs
