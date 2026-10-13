# Automated Job Tracker & WhatsApp Alert Bot

An automated job search and alerting system tailored for **Banavaram Charan** (Early-Career Software / Backend / Full Stack Engineer, 0–2 Years Experience).

---

## 🌟 System Architecture

```
                       ┌──────────────────────────────┐
                       │    GitHub Actions (Cron)     │
                       │     (Every 2 Hours)          │
                       └──────────────┬───────────────┘
                                      │
                                      ▼
                       ┌──────────────────────────────┐
                       │           main.py            │
                       └───────┬──────────────┬───────┘
                               │              │
       ┌───────────────────────┘              └────────────────────────┐
       ▼                                                               ▼
┌──────────────┐                                                ┌──────────────┐
│  Resume Data │                                                │  Job Sourcing│
│(profile.json)│                                                │ (sourcing.py)│
└──────┬───────┘                                                └──────┬───────┘
       │                                                               │
       │     Greenhouse (Razorpay, Groww, etc.) ───────────────────────┤
       │     Lever (Postman, CleverTap, etc.)   ───────────────────────┤
       │     Ashby (Linear, Supabase, etc.)     ───────────────────────┘
       │                                                               │
       ▼                                                               ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                    Deduplication Filter (seen_jobs.txt)                      │
│                    • Filters out any previously seen jobs                    │
└──────────────────────────────────────┬───────────────────────────────────────┘
                                       │
                                       ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                         AI Matching (matcher.py)                             │
│                  Powered by Google Gemini 1.5 Flash API                      │
│                 Scores fit from 0 to 100 based on tech stack,                │
│                 experience level (0-2 yrs), and target roles                 │
└──────────────────────────────────────┬───────────────────────────────────────┘
                                       │
                        Is Match Score >= 75?
                                ├─── No  ──► Recorded into seen_jobs.txt (No alert)
                                │
                                └─── Yes ──► 🚨 WhatsApp Alert Dispatched!
                                             (CallMeBot API ➔ +91 8985897700)
```

---

## 🎯 Candidate Profile & Extracted Resume Specs

Extracted from Banavaram Charan's resume (`profile.json`):
- **Candidate:** Banavaram Charan
- **Contact:** `+91 8985897700` | `banavaramcharan@gmail.com` | Bengaluru, India
- **Experience Level:** 0–2 years (Early Career / Junior / Fresher / Standard Chartered Bank GBS Apprentice)
- **Education:** B.Tech Computer Science & Engineering, Christ (Deemed to be University), Bengaluru (2021–2025, CGPA 8.23/10)
- **Target Roles:** Full Stack Developer, Backend Developer, Software Engineer, SDE 1, Cloud / Ops Engineer
- **Core Tech Stack:**
  - **Languages:** Python, Java, JavaScript, SQL
  - **Full Stack / Backend:** React.js, Node.js, Express, REST APIs, HTML5, CSS3
  - **Databases:** MySQL, PostgreSQL, MongoDB
  - **AI & Automation:** Generative AI, LLM Fundamentals, Prompt Engineering, AI API Integration, Workflow Automation
  - **Tools & DevOps:** Git, GitHub, VS Code, CI/CD, Microsoft Excel, Power BI
  - **Core Concepts:** OOP, DBMS, Data Structures & Algorithms, SDLC, System Design, Authentication, RBAC

---

## 📡 Live ATS Sources & Coverage

The bot connects directly to public ATS endpoints without requiring private recruiter keys:

| ATS Provider | Companies Monitored | API Endpoint Format |
|---|---|---|
| **Greenhouse** | `phonepe`, `razorpay`, `cred`, `swiggy`, `meesho`, `groww`, `juspay` | `https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true` |
| **Lever** | `postman`, `clevertap` | `https://api.lever.co/v0/postings/{slug}?mode=json` |
| **Ashby** | `linear`, `retool`, `supabase` | `https://api.ashbyhq.com/posting-api/job-board/{slug}` |

*Resilient Fallback:* All requests feature automatic timeout guards and error shielding, allowing the crawler to seamlessly continue across active boards (e.g. Razorpay, Groww, Linear, Supabase) even if a company switches ATS platforms or temporarily has 0 listings.

---

## 🤖 AI Matching Engine (Gemini 1.5 Flash)

- Scores candidate fit on a **0 to 100 scale**.
- Strict criteria:
  - **75 – 100:** Strong match with early-career (0–2 years) and core engineering skills (Python, SQL, React, Node, Full Stack, Backend).
  - **50 – 74:** Moderate fit (e.g. requires 3+ years or adjacent technologies like Go/C++).
  - **0 – 49:** Non-technical (sales, marketing, HR) or executive/staff leadership.
- Includes an intelligent local heuristic evaluator for offline testing or development before API key provisioning.

---

## 📲 Instant Alerts via Telegram (@charanb07) & WhatsApp

When `match_score >= 75`, a formatted notification is immediately dispatched:
* **Telegram**: Instantly sent to `@charanb07` via CallMeBot Telegram API (Already verified and active!).
* **WhatsApp**: Dispatched to `+918985897700` via CallMeBot WhatsApp API (configured when key is added).

```text
🎯 *NEW HIGH-MATCH JOB ALERT!* 🎯

🏢 *Company:* Razorpay
💼 *Role:* Junior Software Engineer (Backend)
📊 *Score:* 95/100
📍 *Location:* Bengaluru, India
🌐 *Platform:* Greenhouse

✅ *Matched Skills:*
Python, SQL, REST APIs, Git, Backend Development

💡 *AI Match Insight:*
The role perfectly aligns with candidate's target roles (Junior Software Engineer, Backend), experience level (0-2 years), and technical stack. Every requirement specified—Python, SQL, REST APIs, and Git—is explicitly present.

🔗 *Apply Here:*
https://job-boards.greenhouse.io/razorpaysoftwareprivatelimited/jobs/...
```

### Alert Channel Setup:
1. **Telegram (@charanb07)**:
   * Search for `@CallMeBot_txtbot` on Telegram and send `/start` once if you haven't already.
   * Notifications are automatically routed to your Telegram user!
2. **WhatsApp (+91 8985897700)**:
   * Send WhatsApp message: `I allow callmebot to send me messages` to `+34 644 44 49 53`.
   * Add your returned key to `CALLMEBOT_API_KEY`.

---

## ⚡ Setup & Local Execution

### 1. Clone & Create Virtual Environment
```powershell
git clone <your-repo-url>
cd job-tracker-bot

# With uv (recommended)
uv venv .venv --python 3.11
.venv\Scripts\activate
uv pip install -r requirements.txt

# Or with standard python
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure Environment Variables
Copy `.env.example` to `.env`:
```powershell
cp .env.example .env
```
Fill in your credentials:
```env
GEMINI_API_KEY=AIzaSy...
CALLMEBOT_PHONE=+918985897700
CALLMEBOT_API_KEY=123456
```

### 3. Run the Bot
```powershell
# Full automated run
python main.py

# Test run with limited jobs and dry-run (no WhatsApp messages sent)
python main.py --limit 5 --dry-run

# Custom matching score threshold (e.g., 80)
python main.py --threshold 80
```

---

## ⏰ 24/7 Automation via GitHub Actions

The system is configured in `.github/workflows/job_run.yml` to run **every 2 hours** via GitHub Actions cron:
- Schedule: `0 */2 * * *`
- Automatically updates `seen_jobs.txt` and commits it back to the repository so you **never receive duplicate alerts**.

### Configuring Secrets in GitHub
In your GitHub repository, navigate to:
**Settings** ➔ **Secrets and variables** ➔ **Actions** ➔ **New repository secret**

Add the following 3 secrets:
1. `GEMINI_API_KEY`: Your Google Gemini API Key
2. `CALLMEBOT_PHONE`: `+918985897700`
3. `CALLMEBOT_API_KEY`: Your CallMeBot API key

---

## 📂 Project Structure

```
job-tracker-bot/
├── .github/
│   └── workflows/
│       └── job_run.yml          # GitHub Actions cron workflow (every 2 hours)
├── profile.json                 # Parsed candidate profile & tech stack
├── sourcing.py                  # ATS fetchers (Greenhouse, Lever, Ashby)
├── matcher.py                   # Google Gemini 1.5 Flash AI scoring engine
├── notifier.py                  # CallMeBot WhatsApp alert dispatcher
├── dedup.py                     # Deduplication state manager
├── main.py                      # Main pipeline orchestrator
├── requirements.txt             # Python project dependencies
├── seen_jobs.txt                # Persistent deduplication job ID database
├── .env.example                 # Environment variables template
├── .gitignore                   # Ignore .venv, .env, __pycache__
└── README.md                    # System documentation
```
