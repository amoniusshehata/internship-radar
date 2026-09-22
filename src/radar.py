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
    "machine learning", "machine-learning", "ml", "data science",
    "data scientist", "data analyst", "artificial intelligence",
    "ai engineer", "computer vision", "nlp", "natural language processing",
    "deep learning", "llm", "large language model", "rag",
    "retrieval augmented generation", "ai research", "research intern",
    "research engineer", "predictive modeling", "analytics"
]
INTERNSHIP_KEYWORDS = [
    "intern", "internship", "trainee", "co-op", "coop",
    "apprentice", "graduate program", "student"
]
LOCATION_KEYWORDS = [
    "egypt", "cairo", "giza", "alexandria", "aswan", "remote",
    "remotely", "worldwide", "anywhere", "mena", "middle east"
]
EXCLUDE_KEYWORDS = ["senior", "staff", "principal", "director", "vice president", "head of", "manager"]
HEADERS = {"User-Agent": "internship-radar/1.0"}

def get_json(url, params=None):
    r = requests.get(url, params=params, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()

def clean_text(value):
    if not value:
        return ""
    value = re.sub(r"<[^>]+>", " ", str(value))
    return re.sub(r"\s+", " ", html.unescape(value)).strip()

def canonical_url(url):
    if not url:
        return ""
    p = urlsplit(url.strip())
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path.rstrip("/"), "", ""))

def parse_date(value):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)
    except ValueError:
        return None

def normalize_job(title, company, location, url, description="", posted_at=None, source=""):
    url = canonical_url(url)
    return {
        "id": hashlib.sha256(f"{company}|{title}|{url}".lower().encode()).hexdigest()[:20],
        "title": clean_text(title),
        "company": clean_text(company),
        "location": clean_text(location) or "Remote",
        "url": url,
        "description": clean_text(description),
        "posted_at": posted_at.isoformat() if posted_at else "",
        "source": source,
    }

def fetch_jobicy():
    jobs = []
    try:
        data = get_json("https://jobicy.com/api/v2/remote-jobs", {"count": 200, "industry": "data-science"})
        for x in data.get("jobs", []):
            types = ", ".join(x.get("jobType", []))
            jobs.append(normalize_job(
                x.get("jobTitle"), x.get("companyName"), x.get("jobGeo") or "Remote",
                x.get("url"), f"{x.get('jobExcerpt', '')} {x.get('jobDescription', '')} {types}",
                parse_date(x.get("pubDate")), "Jobicy"
            ))
    except requests.RequestException as e:
        print(f"[Jobicy] skipped: {e}")
    return jobs

def fetch_remotive():
    jobs = []
    try:
        data = get_json("https://remotive.com/api/remote-jobs", {"limit": 100})
        for x in data.get("jobs", []):
            jobs.append(normalize_job(
                x.get("title"), x.get("company_name"),
                x.get("candidate_required_location") or "Remote",
                x.get("url"), f"{x.get('description', '')} {x.get('job_type', '')}",
                parse_date(x.get("publication_date")), "Remotive"
            ))
    except requests.RequestException as e:
        print(f"[Remotive] skipped: {e}")
    return jobs

def score_job(job):
    text = f"{job['title']} {job['location']} {job['description']}".lower()
    if any(x in job["title"].lower() for x in EXCLUDE_KEYWORDS):
        return 0
    score = sum(k in text for k in AI_KEYWORDS) * 2
    score += sum(k in job["title"].lower() for k in INTERNSHIP_KEYWORDS) * 4
    score += sum(k in job["location"].lower() for k in LOCATION_KEYWORDS) * 3
    if "internship" in text:
        score += 3
    posted = parse_date(job["posted_at"])
    if posted and datetime.now(timezone.utc) - posted <= timedelta(days=3):
        score += 2
    return score

def is_match(job):
    title = job["title"].lower()
    location = job["location"].lower()
    text = f"{title} {job['description'].lower()}"
    has_ai = any(k in text for k in AI_KEYWORDS)
    has_internship = any(k in title for k in INTERNSHIP_KEYWORDS) or "internship" in text
    has_location = any(k in location for k in LOCATION_KEYWORDS) or "remote" in text
    return has_ai and has_internship and has_location

def load_state():
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}

def save_state(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")

def send_telegram(message):
    r = requests.post(
        f"https://api.telegram.org/bot{os.environ['TELEGRAM_BOT_TOKEN']}/sendMessage",
        data={
            "chat_id": os.environ["TELEGRAM_CHAT_ID"],
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        },
        timeout=TIMEOUT,
    )
    r.raise_for_status()

def main():
    jobs = fetch_jobicy() + fetch_remotive()
    print(f"Collected {len(jobs)} jobs.")

    state = load_state()
    unique = {j["url"]: j for j in jobs if j["url"]}
    matches = [j for j in unique.values() if j["url"] not in state and is_match(j)]
    for j in matches:
        j["score"] = score_job(j)
    matches.sort(key=lambda j: (j["score"], j["posted_at"]), reverse=True)

    selected = matches[:int(os.getenv("MAX_JOBS_PER_REPORT", "10"))]
    if selected:
        lines = [
            "<b>Daily Internship Radar</b>",
            f"Found {len(selected)} new matching opportunities.",
            ""
        ]
        for i, j in enumerate(selected, 1):
            lines.extend([
                f"<b>{i}. {html.escape(j['title'])}</b>",
                f"Company: {html.escape(j['company'])}",
                f"Location: {html.escape(j['location'])}",
                f"Source: {html.escape(j['source'])}",
                f"<a href=\"{html.escape(j['url'], quote=True)}\">Open listing</a>",
                ""
            ])
        send_telegram("\n".join(lines))
        now = datetime.now(timezone.utc).isoformat()
        for j in selected:
            state[j["url"]] = {"first_sent_at": now, "title": j["title"], "company": j["company"]}
    else:
        send_telegram("<b>Daily Internship Radar</b>\nNo new matching internships were found today.")

    cutoff = datetime.now(timezone.utc) - timedelta(days=60)
    state = {
        u: x for u, x in state.items()
        if (parse_date(x.get("first_sent_at")) or datetime.min.replace(tzinfo=timezone.utc)) >= cutoff
    }
    save_state(state)

if __name__ == "__main__":
    main()
