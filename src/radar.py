import hashlib
import html
import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import requests

STATE_FILE = Path("data/sent_jobs.json")
TIMEOUT = 25

AI_KEYWORDS = [
    "machine learning", "machine-learning", "ml engineer", "ml intern",
    "data science", "data scientist", "data analyst", "artificial intelligence",
    "ai engineer", "ai intern", "computer vision", "nlp",
    "natural language processing", "deep learning", "llm", "large language model",
    "rag", "retrieval augmented generation", "ai research", "research intern",
    "research engineer", "analytics", "predictive modeling"
]
INTERNSHIP_KEYWORDS = [
    "intern", "internship", "trainee", "training", "co-op", "coop",
    "apprentice", "graduate program", "student"
]
LOCATION_KEYWORDS = [
    "egypt", "cairo", "giza", "alexandria", "aswan", "remote",
    "remotely", "worldwide", "anywhere", "mena", "middle east"
]
EXCLUDE_KEYWORDS = [
    "senior", "staff", "principal", "director", "vp ", "vice president",
    "head of", "manager", "lead software engineer"
]
HEADERS = {
    "User-Agent": "internship-radar/1.0 (+https://github.com/amoniusshehata/internship-radar)"
}

def get_json(url, params=None):
    response = requests.get(url, params=params, headers=HEADERS, timeout=TIMEOUT)
    response.raise_for_status()
    return response.json()

def clean_text(value):
    if not value:
        return ""
    value = re.sub(r"<[^>]+>", " ", str(value))
    value = html.unescape(value)
    return re.sub(r"\s+", " ", value).strip()

def canonical_url(url):
    if not url:
        return ""
    parts = urlsplit(url.strip())
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), "", ""))

def parse_date(value):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        return None

def normalize_job(title, company, location, url, description="", posted_at=None):
    clean_url = canonical_url(url)
    return {
        "id": hashlib.sha256(f"{company}|{title}|{clean_url}".lower().encode()).hexdigest()[:20],
        "title": clean_text(title),
        "company": clean_text(company),
        "location": clean_text(location) or "Not specified",
        "url": clean_url,
        "description": clean_text(description),
        "posted_at": posted_at.isoformat() if posted_at else "",
    }

def fetch_greenhouse():
    jobs = []
    boards = os.getenv(
        "GREENHOUSE_BOARDS",
        "microsoft;stripe;datadog;cloudflare;canva;figma;openai"
    ).split(";")
    for board in filter(None, boards):
        try:
            data = get_json(f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs", {"content": "true"})
            for item in data.get("jobs", []):
                jobs.append(normalize_job(
                    item.get("title"), board.replace("-", " ").title(),
                    (item.get("location") or {}).get("name", ""),
                    item.get("absolute_url"), item.get("content", ""),
                    parse_date(item.get("updated_at"))
                ))
        except requests.RequestException as exc:
            print(f"[Greenhouse] skipped {board}: {exc}")
    return jobs

def fetch_lever():
    jobs = []
    boards = os.getenv("LEVER_BOARDS", "netflix;notion;scaleai;anthropic").split(";")
    for board in filter(None, boards):
        try:
            data = get_json(f"https://api.lever.co/v0/postings/{board}", {"mode": "json"})
            for item in data:
                categories = item.get("categories", {})
                jobs.append(normalize_job(
                    item.get("text"), board.replace("-", " ").title(),
                    categories.get("location", ""),
                    item.get("hostedUrl") or item.get("applyUrl"),
                    item.get("descriptionPlain", "")
                ))
        except requests.RequestException as exc:
            print(f"[Lever] skipped {board}: {exc}")
    return jobs

def fetch_remotive():
    jobs = []
    try:
        data = get_json("https://remotive.com/api/remote-jobs", {"limit": 100})
        for item in data.get("jobs", []):
            jobs.append(normalize_job(
                item.get("title"), item.get("company_name"),
                item.get("candidate_required_location") or "Remote",
                item.get("url"), item.get("description", ""),
                parse_date(item.get("publication_date"))
            ))
    except requests.RequestException as exc:
        print(f"[Remotive] skipped: {exc}")
    return jobs

def score_job(job):
    text = f"{job['title']} {job['location']} {job['description']}".lower()
    if any(word in job["title"].lower() for word in EXCLUDE_KEYWORDS):
        return 0
    ai_hits = sum(k in text for k in AI_KEYWORDS)
    internship_hits = sum(k in job["title"].lower() for k in INTERNSHIP_KEYWORDS)
    location_hits = sum(k in job["location"].lower() for k in LOCATION_KEYWORDS)
    score = ai_hits * 2 + internship_hits * 4 + location_hits * 3
    posted = parse_date(job.get("posted_at"))
    if posted and datetime.now(timezone.utc) - posted <= timedelta(days=3):
        score += 2
    if any(k in text for k in ["llm", "rag", "computer vision", "deep learning", "ai research"]):
        score += 2
    return score

def is_match(job):
    title = job["title"].lower()
    location = job["location"].lower()
    text = f"{title} {job['description'].lower()}"
    return (
        any(k in text for k in AI_KEYWORDS)
        and any(k in title for k in INTERNSHIP_KEYWORDS)
        and any(k in location for k in LOCATION_KEYWORDS)
    )

def load_state():
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}

def save_state(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")

def filter_new_jobs(jobs, state):
    unique = {}
    for job in jobs:
        if job["url"]:
            unique[job["url"]] = job
    matches = []
    for job in unique.values():
        if is_match(job) and job["url"] not in state:
            job["score"] = score_job(job)
            matches.append(job)
    return sorted(matches, key=lambda x: (x["score"], x.get("posted_at", "")), reverse=True)

def format_job(job):
    return (
        f"<b>{html.escape(job['title'])}</b>\n"
        f"Company: {html.escape(job['company'])}\n"
        f"Location: {html.escape(job['location'])}\n"
        f"<a href=\"{html.escape(job['url'], quote=True)}\">Apply</a>"
    )

def send_telegram(message):
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    response = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data={
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        },
        timeout=TIMEOUT,
    )
    response.raise_for_status()

def main():
    print("Starting internship radar...")
    jobs = fetch_greenhouse() + fetch_lever() + fetch_remotive()
    print(f"Collected {len(jobs)} jobs.")

    state = load_state()
    new_jobs = filter_new_jobs(jobs, state)
    selected = new_jobs[:int(os.getenv("MAX_JOBS_PER_REPORT", "10"))]

    if selected:
        lines = ["<b>Daily Internship Radar</b>", f"Found {len(selected)} new matching opportunities.", ""]
        for i, job in enumerate(selected, 1):
            lines.extend([f"<b>{i}. {html.escape(job['company'])}</b>", format_job(job), ""])
        send_telegram("\n".join(lines))
        now = datetime.now(timezone.utc).isoformat()
        for job in selected:
            state[job["url"]] = {"first_sent_at": now, "title": job["title"], "company": job["company"]}
    else:
        send_telegram("<b>Daily Internship Radar</b>\nNo new matching internships were found today.")

    cutoff = datetime.now(timezone.utc) - timedelta(days=60)
    state = {
        url: item for url, item in state.items()
        if (parse_date(item.get("first_sent_at")) or datetime.min.replace(tzinfo=timezone.utc)) >= cutoff
    }
    save_state(state)
    print(f"New matches sent: {len(selected)}")

if __name__ == "__main__":
    main()
