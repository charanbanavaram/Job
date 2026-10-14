"""
AI Matching Module
Uses Google Gemini 1.5 Flash API to score job postings against candidate profile (0-100).
Includes resilient fallbacks for offline testing, rate limits (429), or environments without active API keys.
"""

import json
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional
import requests

logger = logging.getLogger(__name__)


def _build_scoring_prompt(job: Dict[str, Any], candidate: Dict[str, Any]) -> str:
    """Builds a structured prompt for scoring the candidate against the job description."""
    return f"""You are an expert technical talent assessor and career matcher.
Evaluate how well the following candidate fits the specified job posting.

Candidate Profile:
- Name: {candidate.get('name', 'Candidate')}
- Target Roles: {", ".join(candidate.get('target_roles', []))}
- Experience Level: {candidate.get('experience_level', '0-2 years')}
- Current Role: {candidate.get('current_role', 'Early career')}
- Programming Languages: {", ".join(candidate.get('core_tech_stack', {}).get('programming_languages', []))}
- Full Stack & Backend: {", ".join(candidate.get('core_tech_stack', {}).get('full_stack_and_backend', []))}
- Databases: {", ".join(candidate.get('core_tech_stack', {}).get('databases', []))}
- AI & Automation: {", ".join(candidate.get('core_tech_stack', {}).get('ai_and_automation', []))}
- Tools: {", ".join(candidate.get('core_tech_stack', {}).get('tools_and_platforms', []))}
- Core Concepts: {", ".join(candidate.get('core_tech_stack', {}).get('core_concepts', []))}

Job Posting:
- Title: {job.get('title', 'N/A')}
- Company: {job.get('company', 'N/A')}
- Location: {job.get('location', 'N/A')}
- Description / Requirements:
{job.get('description', '')[:3000]}

Evaluation Criteria:
1. Role alignment: Does the job title and core responsibility align with Software Engineer, Full Stack, Backend, or Cloud/Ops?
2. Experience alignment: The candidate has 0-2 years of experience (early career, entry-level, junior, SDE 1, associate, apprentice). Moderately penalize Senior / Lead / Staff roles requiring 5+ years.
3. Tech stack alignment: Reward overlap with Python, Java, JavaScript, React.js, Node.js, SQL, Databases (PostgreSQL, MySQL, MongoDB), REST APIs, Automation, and Git.
4. Final Score: An integer from 0 to 100.
   - 75 to 100: Strong match for early-career / 0-2 years software/backend/fullstack role matching skills.
   - 60 to 74: Good match / viable candidate (e.g. solid tech stack overlap, general software engineer, or mid-level role open to strong junior profiles).
   - 40 to 59: Partial match (adjacent tech stack or specialized field).
   - 0 to 39: Poor match (non-technical roles like HR, Sales, Legal, or high senior/principal leadership).

You MUST respond strictly with a valid JSON object in the following format with no markdown wrappers or other commentary:
{{
  "match_score": 85,
  "reasoning": "Clear explanation of score based on role title, experience level, and tech stack overlap.",
  "matched_skills": ["Python", "SQL", "Backend", "REST APIs"],
  "missing_skills": ["AWS", "Kubernetes"],
  "recommendation": "Strongly recommended / Good fit / Moderate / Not recommended"
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
        """Scores a job description against the candidate profile (0-100)."""
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
                "recommendation": "Not recommended"
            }

        # 1. Try Gemini API if key is present
        if self.api_key:
            # Try via SDK first
            if self._sdk_client:
                try:
                    prompt = _build_scoring_prompt(job, candidate)
                    response = self._sdk_client.generate_content(
                        prompt,
                        generation_config={"temperature": 0.2, "response_mime_type": "application/json"}
                    )
                    parsed = self._extract_json(response.text)
                    if parsed and "match_score" in parsed:
                        return self._normalize_result(parsed)
                except Exception as e:
                    err_msg = str(e)
                    if "429" in err_msg or "quota" in err_msg.lower():
                        logger.warning(f"Gemini API 429 Quota limit encountered on '{self.model_name}'. Falling back immediately to heuristic engine.")
                    else:
                        logger.warning(f"Gemini SDK generation failed: {e}. Falling back to heuristic engine.")

            # Try via direct REST API if SDK not configured
            rest_result = self._score_via_rest(job, candidate)
            if rest_result:
                return rest_result

        # 2. Intelligent local scoring fallback (deterministic heuristic engine)
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
                    if parsed and "match_score" in parsed:
                        self.model_name = m_name
                        return self._normalize_result(parsed)
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

    def _normalize_result(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """Ensures score is bounded integer 0-100 and fields are present."""
        raw_score = raw.get("score") if "score" in raw else raw.get("match_score", 0)
        score = int(raw_score)
        score = max(0, min(100, score))
        reason = str(raw.get("reason", raw.get("reasoning", "")))
        return {
            "score": score,
            "match_score": score,
            "reason": reason,
            "reasoning": reason,
            "matched_skills": list(raw.get("matched_skills", [])),
            "missing_skills": list(raw.get("missing_skills", [])),
            "recommendation": str(raw.get("recommendation", "Evaluated by Gemini Flash")),
        }

    def _local_rule_scoring(self, job: Dict[str, Any], candidate: Dict[str, Any]) -> Dict[str, Any]:
        """Deterministic heuristic scorer matching tech stack, target roles, and experience level."""
        title = (job.get("title") or "").lower()
        desc = (job.get("description") or "").lower()
        full_text = f"{title} {desc}"

        score = 0
        matched = []
        missing = []
        penalties = []

        # 1. Non-technical negative filters
        non_tech_keywords = ["audit", "sales", "recruiter", "talent acquisition", "legal", "hr", "accountant", "marketing", "content writer"]
        if any(kw in title for kw in non_tech_keywords):
            return {
                "score": 10,
                "match_score": 10,
                "reason": "Non-technical or unrelated domain role.",
                "reasoning": "Non-technical or unrelated domain role.",
                "matched_skills": [],
                "missing_skills": ["Software Engineering skills"],
                "recommendation": "Not recommended"
            }

        # 2. Seniority checks
        senior_keywords = ["staff", "principal", "director", "head of", "lead", "architect", "manager", "vp", "senior", "sr."]
        is_senior = any(re.search(r"\b" + re.escape(w) + r"\b", title) for w in senior_keywords)
        if is_senior:
            penalties.append("Requires Senior/Staff/Lead level experience")
            score -= 25

        # Junior / Fresher bonus
        junior_keywords = ["junior", "jr", "associate", "intern", "apprentice", "graduate", "fresher", "entry level", "sde 1", "sde i", "sde-1", "engineer 1", "early career"]
        is_junior = any(re.search(r"\b" + re.escape(w) + r"\b", title) for w in junior_keywords)
        if is_junior:
            score += 35

        # 3. Target role match
        target_role_tokens = ["software engineer", "developer", "backend", "full stack", "fullstack", "frontend", "sde", "cloud", "devops", "platform engineer"]
        role_match_count = sum(1 for token in target_role_tokens if token in title)
        if role_match_count > 0:
            score += 35

        # 4. Tech stack keyword matching
        tech_skills = {
            "python": "Python",
            "javascript": "JavaScript",
            "java": "Java",
            "react": "React.js",
            "node": "Node.js",
            "sql": "SQL",
            "postgres": "PostgreSQL",
            "mysql": "MySQL",
            "mongodb": "MongoDB",
            "rest api": "REST APIs",
            "fastapi": "FastAPI",
            "django": "Django",
            "docker": "Docker",
            "git": "Git",
            "aws": "AWS",
        }

        for kw, display_name in tech_skills.items():
            if re.search(r"\b" + re.escape(kw) + r"\b", full_text):
                matched.append(display_name)
                score += 5
            else:
                if kw in ["aws", "docker"]:
                    missing.append(display_name)

        # Base score scaling
        base_score = max(10, min(95, score + 25))

        reasoning = f"Heuristic match: '{job.get('title')}' in engineering domain. "
        if matched:
            reasoning += f"Skills: {', '.join(matched[:5])}. "
        if penalties:
            reasoning += f"Note: {', '.join(penalties)}."

        return {
            "score": base_score,
            "match_score": base_score,
            "reason": reasoning,
            "reasoning": reasoning,
            "matched_skills": list(set(matched)),
            "missing_skills": list(set(missing)),
            "recommendation": "Strong match" if base_score >= 60 else ("Moderate fit" if base_score >= 40 else "Low fit")
        }
