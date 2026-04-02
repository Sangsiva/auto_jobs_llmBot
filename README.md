# auto_jobs_llmBot

> **Personal fork of [AIHawk / Auto_Jobs_Applier_AIHawk](https://github.com/feder-cr/Auto_Jobs_Applier_AIHawk)**  
> Forked and heavily extended by [Sivakumar](https://github.com/Sangsiva)

---

## What this is

My personal automated LinkedIn Easy Apply bot, built on top of the open-source AIHawk project and significantly extended with Claude AI integrations, smarter resume tailoring, and anti-ban protections.

---

## What I added / changed from the original

### Claude AI Integration
- Replaced OpenAI with **Anthropic Claude** (Haiku for fast tasks, Sonnet for resume generation)
- Per-job **relevance scoring** using Claude Haiku (0–10 scale, skips irrelevant jobs)
- **JD Resume Matcher** — picks the best of 4 tailored resumes per job description
- Per-job **resume tailoring** using Claude Sonnet, saved as HTML + PDF per company
- Per-job **cover letter generation** using Claude Haiku (non-generic, no buzzwords)
- **Batched form Q&A** — all screening questions answered in a single Claude call per page

### Token Optimisation
- Analysis step uses Haiku + stripped HTML text (5x fewer input tokens, 20x cheaper model)
- Generation sends only selected resume's full HTML + stripped text of others
- Resume cache — 4 HTML files read from disk once per session, not per job
- Lazy cover letter — only generated when a textarea is detected on the form

### Anti-Ban & Human-like Behaviour
- **Session Guard** — daily application cap (20/day) and session limit (3/day) persisted in JSON across runs
- **Random wait 2–10 minutes** between applications with daily seed that shifts the pattern every day
- **User agent rotation** across 5 real Chrome UA strings per session
- **Human-like scrolling** before each job card click
- `navigator.webdriver` patched via CDP to reduce automation fingerprinting
- `undetected-chromedriver` support with graceful fallback to standard Selenium

### Application Tracking
- CSV tracker at `job_applications/applications.csv`
- Tracks: date, job title, company, location, URL, relevance score, resume used, status, notes
- Duplicate detection — never applies to the same company twice
- `update_status()` to manually mark Interview / Offer / Rejected

### Reliability
- Multiple CSS selector fallbacks for LinkedIn UI changes
- Handles safety reminder modal and save/discard dialog automatically
- Graceful recovery if Chrome session dies mid-run

---

## Setup

```bash
git clone https://github.com/Sangsiva/auto_jobs_llmBot.git
cd auto_jobs_llmBot
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Copy and fill in your credentials:
```bash
cp data_folder/secrets.yaml.example data_folder/secrets.yaml
```

Edit `data_folder/work_preferences.yaml` to set your target positions and locations.

---

## Usage

```bash
# Run the full auto-apply bot
python main.py --action auto-apply

# View application report
python main.py --action report

# Tailor resume to a specific JD
python main.py --action jd-match
```

---

## Tech stack

- **Python 3.9+** · Selenium · ChromeDriver
- **Anthropic Claude** (Haiku + Sonnet)
- YAML config · CSV tracking · HTML/PDF resume output

---

## Credits

Original project: [AIHawk by feder-cr](https://github.com/feder-cr/Auto_Jobs_Applier_AIHawk)  
All Claude AI integrations, resume tailoring, session guard, and bot logic extensions written by [Sivakumar](https://github.com/Sangsiva).
