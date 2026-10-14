"""
AI Matching Module
Uses Google Gemini 1.5 Flash API to score job postings against candidate profile (0-100).
Strictly evaluates Experience Level (40%), Tech Stack (40%), and Geographic Alignment (20%).
Includes resilient fallbacks for offline testing, rate limits (429), or environments without active API keys.
"""

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional
import requests

logger = logging.getLogger(__name__)


def _build_scoring_prompt(job: Dict[str, Any], candidate: Dict[str, Any]) -> str:
    """Builds a structured prompt for scoring candidate against job description based on experience, tech stack, and geography."""
    return f"""You are an expert technical talent assessor and career matcher.
Evaluate how well the following candidate fits the specified job posting based on strict experience, technical skills, and geographic hierarchy.

Candidate Profile:
- Name: {candidate.get('name', 'Banavaram Charan')}
- Total Experience: 1 Year (Entry-Level / Junior / Associate / SDE 1 / Early Career)
- Background: {candidate.get('background', 'Operations & Software Development at Standard Chartered Global Business Services, Bengaluru')}
- Target Seniority: Entry-Level, Junior, Associate, SDE 1, Early Career (0 to 2 years experience). Reject or heavily penalize anything demanding 3+ years.
- Core Skills: Python, Java, JavaScript, React.js, Node.js, Express, FastAPI, REST APIs, SQL (MySQL, PostgreSQL), MongoDB, Git, Cloud / DevOps fundamentals.
- Geographic Preference Hierarchy:
  * 1st Priority (+20 pts): Bengaluru / Bangalore
  * 2nd Priority (+18 pts): Chennai
  * 3rd Priority (+15 pts): Hyderabad
  * Acceptable (+10 pts): Remote (India), Pune, Mumbai, Delhi NCR, Gurugram, Noida
  * Strictly Excluded (0 pts, Total Score = 0): Explicitly Foreign Onsite / US / UK / Europe / Non-India without India hiring entity.

Job Posting:
- Title: {job.get('title', 'N/A')}
- Company: {job.get('company', 'N/A')}
- Location: {job.get('location', 'N/A')}
- Description / Requirements:
{job.get('description', '')[:3000]}

Scoring Rubric (0 to 100 Integer):
1. Strict Experience Match (40% Weight / Max 40 points):
   - 0–2 years / Junior / Entry / SDE 1 / Early Career: 40 points (100% fit)
   - 2–3 years: 28 points (70% fit)
   - 3–5 years: 8 points (20% fit - strong penalty)
   - 5+ years / Staff / Principal / Lead / Senior: 0 points (Instant drop)
2. Technical Skills Overlap (40% Weight / Max 40 points):
   - Reward overlap with Python, React.js, SQL, FastAPI, Node.js, REST APIs, Backend / Full Stack / Cloud engineering.
3. Geographic Alignment (20% Weight / Max 20 points):
   - Bengaluru / Bangalore: +20 points (Top preference)
   - Chennai: +18 points (2nd preference)
   - Hyderabad: +15 points (3rd preference)
   - Remote (India) / Other India cities: +10 points (Acceptable)
   - Explicitly Non-India / Foreign Onsite: 0 points (Instant reject, Total Score = 0)

Score Calculation:
- Sum: Experience Points + Tech Points + Geo Points (0 to 100).
- If role requires 5+ years, Lead, Staff, or Principal, total score must NOT exceed 20.
- If location is non-India and foreign onsite, total score must be 0.

You MUST respond strictly with a valid JSON object in the following format with no markdown wrappers or other commentary:
{{
  "score": 88,
  "matched_skills": ["Python", "React.js", "PostgreSQL", "REST APIs"],
  "experience_fit": "0-2 years (Early Career / SDE 1 - Strong Fit)",
  "location_fit": "Bengaluru (Priority 1)",
  "reason": "1-year experience matches early-career role, strong Python and React overlap, located in top priority Bengaluru."
}}
"""


class JobMatcher:
    CANDIDATE_MODELS = [
        "gemini-flash-latest",
        "gemini-1.5-flash",
    ]

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY", "").strip()
        self.model_name = self.CANDIDATE_MODELS[0]
        self._sdk_client = None

        if self.api_key:
            try:
                import google.generativeai as genai
                genai.configure(api_key=self.api_key)
                for m_name in self.CANDIDATE_MODELS:
                    try:
                        client = genai.GenerativeModel(m_name)
                        self.model_name = m_name
                        self._sdk_client = client
                        logger.info(f"Initialized Google Gemini SDK with model '{self.model_name}'.")
                        break
                    except Exception:
                        continue
            except Exception as e:
                logger.warning(f"Could not initialize google.generativeai SDK: {e}. Will use REST API fallback.")

    def score_job(self, job: Dict[str, Any], candidate_profile: Dict[str, Any]) -> Dict[str, Any]:
        """Scores a job description against candidate experience, tech stack, and location."""
        candidate = candidate_profile.get("candidate", candidate_profile)
        title = (job.get("title") or "").lower()

        # Obvious non-technical keywords
        non_tech_keywords = [
            "audit", "sales", "recruiter", "talent acquisition", "legal", "hr",
            "accountant", "marketing", "content writer", "vigilance", "alliances",
            "compliance", "facilities", "collections", "customer support"
        ]
        if any(kw in title for kw in non_tech_keywords):
            return {
                "score": 10,
                "match_score": 10,
                "reason": f"Role '{job.get('title')}' is in a non-technical domain.",
                "reasoning": f"Role '{job.get('title')}' is in a non-technical domain.",
                "matched_skills": [],
                "missing_skills": ["Software Engineering skills"],
                "experience_fit": "Non-technical",
                "location_fit": job.get("location", "N/A"),
                "recommendation": "Not recommended"
            }

        # 1. Try Gemini API if key is present
        if self.api_key:
            if self._sdk_client:
                try:
                    prompt = _build_scoring_prompt(job, candidate)
                    response = self._sdk_client.generate_content(
                        prompt,
                        generation_config={"temperature": 0.2, "response_mime_type": "application/json"}
                    )
                    parsed = self._extract_json(response.text)
                    if parsed and ("score" in parsed or "match_score" in parsed):
                        return self._normalize_result(parsed, job)
                except Exception as e:
                    err_msg = str(e)
                    if "429" in err_msg or "quota" in err_msg.lower():
                        logger.warning(f"Gemini API 429 Quota limit on '{self.model_name}'. Falling back to heuristic engine.")
                    else:
                        logger.warning(f"Gemini SDK generation failed: {e}. Falling back to heuristic engine.")

            # Try via direct REST API
            rest_result = self._score_via_rest(job, candidate)
            if rest_result:
                return rest_result

        # 2. Intelligent local scoring fallback (deterministic heuristic engine matching the rubric)
        logger.info(f"Using local rule-based matching engine for '{job.get('title')}' at '{job.get('company')}'.")
        return self._local_rule_scoring(job, candidate)

    def _score_via_rest(self, job: Dict[str, Any], candidate: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Direct REST call to Gemini Flash."""
        for m_name in self.CANDIDATE_MODELS:
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{m_name}:generateContent?key={self.api_key}"
                prompt = _build_scoring_prompt(job, candidate)
                payload = {
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"temperature": 0.2}
                }
                res = requests.post(url, json=payload, timeout=12)
                if res.status_code == 200:
                    data = res.json()
                    text = data["candidates"][0]["content"]["parts"][0]["text"]
                    parsed = self._extract_json(text)
                    if parsed and ("score" in parsed or "match_score" in parsed):
                        self.model_name = m_name
                        return self._normalize_result(parsed, job)
                elif res.status_code == 429:
                    logger.warning(f"Gemini REST 429 Quota reached on {m_name}.")
                    break
            except Exception as e:
                logger.warning(f"Gemini REST call failed on {m_name}: {e}")
        return None

    def _extract_json(self, text: str) -> Optional[Dict[str, Any]]:
        """Parses JSON from response text, stripping markdown codeblocks if present."""
        clean = text.strip()
        if clean.startswith("```json"):
            clean = clean[7:]
        elif clean.startswith("```"):
            clean = clean[3:]
        if clean.endswith("```"):
            clean = clean[:-3]
        clean = clean.strip()
        try:
            return json.loads(clean)
        except Exception:
            match = re.search(r"\{.*\}", clean, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(0))
                except Exception:
                    pass
        return None

    def _normalize_result(self, raw: Dict[str, Any], job: Dict[str, Any]) -> Dict[str, Any]:
        """Ensures score is bounded integer 0-100 and all fields are formatted."""
        raw_score = raw.get("score") if "score" in raw else raw.get("match_score", 0)
        score = int(raw_score)
        score = max(0, min(100, score))
        reason = str(raw.get("reason", raw.get("reasoning", "")))
        exp_fit = str(raw.get("experience_fit", "0-2 years (Entry / Junior)"))
        loc_fit = str(raw.get("location_fit", job.get("location", "India / Remote")))
        matched_skills = list(raw.get("matched_skills", []))
        
        return {
            "score": score,
            "match_score": score,
            "reason": reason,
            "reasoning": reason,
            "experience_fit": exp_fit,
            "location_fit": loc_fit,
            "matched_skills": matched_skills,
            "missing_skills": list(raw.get("missing_skills", [])),
            "recommendation": "Strongly recommended" if score >= 75 else ("Good fit" if score >= 60 else "Moderate fit"),
        }

    def _local_rule_scoring(self, job: Dict[str, Any], candidate: Dict[str, Any]) -> Dict[str, Any]:
        """Deterministic heuristic scorer matching strict experience, tech stack, and location rubric."""
        title = (job.get("title") or "").lower()
        desc = (job.get("description") or "").lower()
        loc = (job.get("location") or "").lower()
        full_text = f"{title} {desc}"

        # 1. Experience Match (Max 40 points)
        senior_keywords = ["staff", "principal", "director", "head of", "lead", "architect", "manager", "vp", "senior", "sr."]
        is_senior = any(re.search(r"\b" + re.escape(w) + r"\b", title) for w in senior_keywords)
        
        junior_keywords = ["junior", "jr", "associate", "intern", "apprentice", "graduate", "fresher", "entry level", "sde 1", "sde i", "sde-1", "engineer 1", "early career", "0-2", "1 year"]
        is_junior = any(re.search(r"\b" + re.escape(w) + r"\b", title) for w in junior_keywords)

        if is_senior:
            exp_score = 0
            exp_fit = "5+ years (Senior / Lead - Disqualified)"
        elif is_junior:
            exp_score = 40
            exp_fit = "0-2 years (Junior / Early Career - 100% Fit)"
        else:
            # General engineering title (e.g., Software Engineer, Backend Engineer)
            exp_score = 30
            exp_fit = "1-3 years (Early / Mid-level - Viable Fit)"

        # 2. Technical Skills Match (Max 40 points)
        tech_skills = {
            "python": "Python",
            "react": "React.js",
            "fastapi": "FastAPI",
            "node": "Node.js",
            "express": "Express",
            "sql": "SQL",
            "postgres": "PostgreSQL",
            "mysql": "MySQL",
            "mongodb": "MongoDB",
            "rest api": "REST APIs",
            "docker": "Docker",
            "git": "Git",
            "devops": "DevOps",
            "cloud": "Cloud Fundamentals",
        }

        matched_skills = []
        tech_score = 0
        for kw, display_name in tech_skills.items():
            if re.search(r"\b" + re.escape(kw) + r"\b", full_text):
                matched_skills.append(display_name)
                tech_score += 6
        tech_score = min(40, tech_score + 10 if matched_skills else 5)

        # 3. Geographic Alignment (Max 20 points)
        if any(b in loc for b in ["bengaluru", "bangalore"]):
            geo_score = 20
            loc_fit = "Bengaluru (1st Priority)"
        elif "chennai" in loc:
            geo_score = 18
            loc_fit = "Chennai (2nd Priority)"
        elif "hyderabad" in loc:
            geo_score = 15
            loc_fit = "Hyderabad (3rd Priority)"
        elif any(c in loc for c in ["remote", "india", "pune", "mumbai", "delhi", "gurgaon", "gurugram", "noida"]):
            geo_score = 10
            loc_fit = "India / Remote (Acceptable)"
        else:
            geo_score = 0
            loc_fit = "Foreign / Excluded Location"

        # Final Score Compilation
        if exp_score == 0:
            final_score = min(15, tech_score // 2)
            reason = f"Role '{job.get('title')}' demands Senior/Lead experience (Charan has 1 year)."
        elif geo_score == 0:
            final_score = 0
            reason = f"Location '{job.get('location')}' is non-India and foreign onsite."
        else:
            final_score = exp_score + tech_score + geo_score
            final_score = max(0, min(100, final_score))
            reason = f"Matches 1-year experience profile ({exp_fit}). Strong tech overlap in {', '.join(matched_skills[:4])}. Location: {loc_fit}."

        return {
            "score": final_score,
            "match_score": final_score,
            "reason": reason,
            "reasoning": reason,
            "experience_fit": exp_fit,
            "location_fit": loc_fit,
            "matched_skills": list(set(matched_skills)),
            "missing_skills": [],
            "recommendation": "Strong match" if final_score >= 60 else "Moderate fit"
        }
