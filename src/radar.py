import hashlib
import html
import json
import os
import re
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit

import requests

STATE_FILE = Path("data/sent_jobs.json")
TIMEOUT = 25

AI_TITLE_PATTERNS = [
    r"machine\s*learning", r"\bml\b", r"artificial\s*intelligence",
    r"\bai\b", r"data\s*science", r"data\s*scientist", r"data\s*analyst",
    r"data\s*engineer", r"ai\s*engineer", r"ml\s*engineer",
    r"computer\s*vision", r"\bnlp\b", r"natural\s*language",
    r"deep\s*learning", r"\bllm\b", r"large\s*language\s*model",
    r"generative\s*ai", r"retrieval\s*augmented", r"\brag\b",
    r"predictive\s*modeling", r"analytics",
]

AI_DESCRIPTION_PATTERNS = [
    r"machine\s*learning", r"artificial\s*intelligence", r"data\s*science",
    r"data\s*analyst", r"data\s*engineer", r"computer\s*vision",
    r"natural\s*language", r"deep\s*learning", r"large\s*language\s*model",
    r"generative\s*ai", r"retrieval\s*augmented", r"predictive\s*modeling",
]

INTERNSHIP_PATTERNS = [
    r"\bintern\b", r"\binternship\b", r"\btrainee\b", r"\bco[- ]?op\b",
    r"\bapprentice\b", r"graduate\s+(program|internship)",
    r"student\s+(intern|program)", r"research\s+(assistant|student)",
]

ENTRY_LEVEL_PATTERNS = [
    r"\bentry[- ]?level\b",
    r"\bjunior\b",
    r"\bgraduate\b",
    r"\bearly\s+career\b",
]

UNSPECIFIED_EXCLUDED_PATTERNS = EXCLUDE_ENTRY_LEVEL_PATTERNS

EXCLUDE_ENTRY_LEVEL_PATTERNS = [
    r"\bsenior\b", r"\bstaff\b", r"\bprincipal\b",
    r"\bmanager\b", r"\bdirector\b", r"\blead\b",
    r"\bhead\s+of\b", r"\bvice\s+president\b", r"\bvp\b",
]

EGYPT_PATTERNS = [
    r"\begypt\b", r"\bcairo\b", r"\bgiza\b", r"\balexandria\b",
    r"\baswan\b", r"\bmansoura\b", r"\btanta\b", r"\bisma(ï|i)lia\b",
    r"\bport\s+said\b", r"\bsuez\b",
]

SAUDI_PATTERNS = [
    r"\bsaudi\s+arabia\b", r"\bksa\b", r"\briyadh\b",
    r"\bjeddah\b", r"\bdammam\b", r"\bdhahran\b", r"\bkhobar\b",
]

UAE_PATTERNS = [
    r"\buae\b", r"\bunited\s+arab\s+emirates\b", r"\bdubai\b",
    r"\babu\s+dhabi\b", r"\bsharjah\b", r"\bajman\b",
]

NATIONALITY_RESTRICTION_PATTERNS = [
    r"\bsaudi\s+nationals?\s+only\b",
    r"\bonly\s+saudi\s+nationals?\b",
    r"\bksa\s+nationals?\s+only\b",
    r"\bemirati\s+nationals?\s+only\b",
    r"\buae\s+nationals?\s+only\b",
    r"\b(u|united\s+arab\s+emirates)\s+nationals?\s+only\b",
]

REMOTE_PATTERNS = [
    r"\bremote\b", r"\bremotely\b", r"\bworldwide\b", r"\banywhere\b",
    r"\bwork\s+from\s+anywhere\b", r"\bglobal\b", r"\bmena\b",
    r"\bmiddle\s+east\b",
]

EXCLUDE_KEYWORDS = [
    "senior", "staff", "principal", "director", "vice president",
    "head of", "manager", "lead", "head"
]
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


def matches_any(text, patterns):
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)


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
                parse_date(x.get("pubDate")), "Jobicy",
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
                x.get("candidate_required_location") or "Remote", x.get("url"),
                f"{x.get('description', '')} {x.get('job_type', '')}",
                parse_date(x.get("publication_date")), "Remotive",
            ))
    except requests.RequestException as e:
        print(f"[Remotive] skipped: {e}")
    return jobs


def fetch_remote_ok():
    jobs = []
    try:
        data = get_json("https://remoteok.com/api")
        for x in data:
            if not isinstance(x, dict) or not x.get("position"):
                continue
            jobs.append(normalize_job(
                x.get("position"), x.get("company"), x.get("location") or "Remote",
                x.get("url") or x.get("apply_url"),
                f"{x.get('description', '')} {' '.join(x.get('tags', []))}",
                parse_date(x.get("date")), "Remote OK",
            ))
    except requests.RequestException as e:
        print(f"[Remote OK] skipped: {e}")
    return jobs


class WuzzufJobParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.jobs = []
        self.current_href = None
        self.current_text = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        href = attrs.get("href", "")
        if tag == "a" and ("/jobs/p/" in href or "/internship/" in href):
            self.current_href = href
            self.current_text = []

    def handle_data(self, data):
        if self.current_href:
            self.current_text.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self.current_href:
            title = clean_text(" ".join(self.current_text))
            if title:
                self.jobs.append((title, self.current_href))
            self.current_href = None
            self.current_text = []


def fetch_bayt():
    jobs = []
    countries = {
        "Egypt": "https://www.bayt.com/en/egypt/jobs/",
        "Saudi Arabia": "https://www.bayt.com/en/saudi-arabia/jobs/",
        "UAE": "https://www.bayt.com/en/uae/jobs/",
    }
    queries = [
        "ai-internship-jobs/",
        "machine-learning-internship-jobs/",
        "data-science-internships-jobs/",
        "ai-engineer-internship-jobs/",
    ]

    class BaytJobParser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.jobs = []
            self.current_href = None
            self.current_text = []

        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            href = attrs.get("href", "")
            if tag == "a" and "/jobs/" in href and href.rstrip("/").split("/")[-1] and re.search(r"-\d{7,}$", href.rstrip("/")):
                self.current_href = href
                self.current_text = []

        def handle_data(self, data):
            if self.current_href:
                self.current_text.append(data)

        def handle_endtag(self, tag):
            if tag == "a" and self.current_href:
                title = clean_text(" ".join(self.current_text))
                if title and len(title) <= 180:
                    self.jobs.append((title, self.current_href))
                self.current_href = None
                self.current_text = []

    try:
        for country, base_url in countries.items():
            seen_urls = set()
            for query in queries:
                response = requests.get(
                    urljoin(base_url, query),
                    headers=HEADERS,
                    timeout=TIMEOUT,
                )
                response.raise_for_status()
                parser = BaytJobParser()
                parser.feed(response.text)

                for title, href in parser.jobs:
                    url = urljoin("https://www.bayt.com", href)
                    if url in seen_urls:
                        continue
                    seen_urls.add(url)
                    jobs.append(normalize_job(
                        title=title,
                        company="Bayt listing",
                        location=country,
                        url=url,
                        description="",
                        source="Bayt",
                    ))
    except requests.RequestException as e:
        print(f"[Bayt] skipped: {e}")

    return jobs


def fetch_wuzzuf():
    jobs = []
    queries = [
        "data science intern",
        "machine learning intern",
        "artificial intelligence intern",
        "data analyst intern",
        "data engineer intern",
        "computer vision intern",
        "NLP intern",
    ]

    try:
        for query in queries:
            response = requests.get(
                "https://wuzzuf.net/search/jobs/",
                params={"q": query},
                headers=HEADERS,
                timeout=TIMEOUT,
            )
            response.raise_for_status()

            parser = WuzzufJobParser()
            parser.feed(response.text)

            seen_urls = set()
            for title, href in parser.jobs:
                url = urljoin("https://wuzzuf.net", href)
                if url in seen_urls:
                    continue
                seen_urls.add(url)

                jobs.append(normalize_job(
                    title=title,
                    company="Wuzzuf listing",
                    location="Egypt",
                    url=url,
                    description="",
                    source="Wuzzuf",
                ))
    except requests.RequestException as e:
        print(f"[Wuzzuf] skipped: {e}")

    return jobs


def is_ai_role(job):
    title = job["title"].lower()
    description = job["description"].lower()

    if matches_any(title, AI_TITLE_PATTERNS):
        return True

    if re.search(r"\bresearch\s+(intern|internship)\b", title, re.IGNORECASE):
        return matches_any(description, AI_DESCRIPTION_PATTERNS)

    return False


def get_target_tier(job):
    title = job["title"].lower()
    description = job["description"].lower()
    text = f"{title} {description}"

    if matches_any(title, EXCLUDE_ENTRY_LEVEL_PATTERNS):
        return 0

    if matches_any(title, INTERNSHIP_PATTERNS):
        return 1

    if matches_any(text, ENTRY_LEVEL_PATTERNS):
        return 2

    # AI/Data roles without an explicit seniority level are kept for review.
    return 3


def is_internship(job):
    return get_target_tier(job) in (1, 2, 3)


def is_location_eligible(job):
    location = job["location"].lower()
    description = job["description"].lower()
    text = f"{location} {description}"

    is_egypt = matches_any(text, EGYPT_PATTERNS)
    is_saudi = matches_any(text, SAUDI_PATTERNS)
    is_uae = matches_any(text, UAE_PATTERNS)
    is_remote = matches_any(text, REMOTE_PATTERNS)

    # Physical roles are allowed in Egypt, Saudi Arabia, and the UAE.
    # Roles explicitly restricted to local nationals are excluded.
    if matches_any(text, NATIONALITY_RESTRICTION_PATTERNS):
        return False

    if is_egypt or is_saudi or is_uae:
        return True

    # Outside the target countries, only remote roles are accepted.
    return is_remote


def score_job(job):
    title = job["title"].lower()
    location = job["location"].lower()

    if any(x in title for x in EXCLUDE_KEYWORDS):
        return 0

    score = sum(bool(re.search(pattern, title, re.IGNORECASE)) for pattern in AI_TITLE_PATTERNS) * 3
    score += sum(bool(re.search(pattern, title, re.IGNORECASE)) for pattern in INTERNSHIP_PATTERNS) * 4

    if matches_any(location, EGYPT_PATTERNS):
        score += 4
    if matches_any(location, REMOTE_PATTERNS):
        score += 3

    posted = parse_date(job["posted_at"])
    if posted and datetime.now(timezone.utc) - posted <= timedelta(days=3):
        score += 2

    return score


def is_match(job):
    title = job["title"].lower()
    if any(x in title for x in EXCLUDE_KEYWORDS):
        return False

    return is_ai_role(job) and is_internship(job) and is_location_eligible(job)


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
    sources = {
        "Jobicy": fetch_jobicy,
        "Remotive": fetch_remotive,
        "Remote OK": fetch_remote_ok,
        "Wuzzuf": fetch_wuzzuf,
        "Bayt": fetch_bayt,
    }

    jobs = []
    source_counts = {}
    for source_name, fetcher in sources.items():
        source_jobs = fetcher()
        source_counts[source_name] = len(source_jobs)
        print(f"[{source_name}] collected {len(source_jobs)} jobs.")
        jobs.extend(source_jobs)

    print(f"Collected {len(jobs)} jobs total.")

    state = load_state()
    unique = {j["url"]: j for j in jobs if j["url"]}

    stats = {
        "unique": len(unique),
        "tier1": 0,
        "tier2": 0,
        "tier3": 0,
        "ai_data": 0,
        "location": 0,
        "excluded_seniority": 0,
        "eligible": 0,
        "already_sent": 0,
        "already_sent_eligible": 0,
    }
    rejection_examples = []

    for job in unique.values():
        title = job["title"].lower()
        tier = get_target_tier(job)
        internship = tier > 0
        ai_data = is_ai_role(job)
        location = is_location_eligible(job)
        excluded = any(x in title for x in EXCLUDE_KEYWORDS)

        if tier == 1:
            stats["tier1"] += 1
        elif tier == 2:
            stats["tier2"] += 1
        elif tier == 3:
            stats["tier3"] += 1
        if ai_data:
            stats["ai_data"] += 1
        if location:
            stats["location"] += 1
        if excluded:
            stats["excluded_seniority"] += 1

        if job["url"] in state:
            stats["already_sent"] += 1
            if is_match(job):
                stats["already_sent_eligible"] += 1
            continue

        if is_match(job):
            stats["eligible"] += 1
        elif len(rejection_examples) < 8:
            reasons = []
            if excluded:
                reasons.append("seniority excluded")
            elif tier == 0:
                reasons.append("seniority excluded")
            if not ai_data:
                reasons.append("not AI/Data")
            if not location:
                reasons.append("location not eligible")
            if matches_any(f"{job['location']} {job['description']}", NATIONALITY_RESTRICTION_PATTERNS):
                reasons.append("nationality restricted")
            rejection_examples.append(
                f"{job['title']} | {job['location']} | {', '.join(reasons)}"
            )

    print("Diagnostics:")
    for name, count in source_counts.items():
        print(f"  {name}: {count}")
    print(f"  Unique URLs: {stats['unique']}")
    print(f"  Tier 1 - Internship: {stats['tier1']}")
    print(f"  Tier 2 - Junior/Graduate: {stats['tier2']}")
    print(f"  Tier 3 - Seniority not specified: {stats['tier3']}")
    print(f"  AI/Data: {stats['ai_data']}")
    print(f"  Location eligible: {stats['location']}")
    print(f"  Seniority excluded: {stats['excluded_seniority']}")
    print(f"  New eligible: {stats['eligible']}")
    print(f"  Already sent: {stats['already_sent']}")
    print(f"  Already sent eligible: {stats['already_sent_eligible']}")
    if rejection_examples:
        print("Rejection examples:")
        for example in rejection_examples:
            print(f"  - {example}")

    matches = [
        j for j in unique.values()
        if j["url"] not in state and is_match(j)
    ]

    for j in matches:
        j["score"] = score_job(j)

    matches.sort(key=lambda j: (j["score"], j["posted_at"]), reverse=True)
    selected = matches[:int(os.getenv("MAX_JOBS_PER_REPORT", "10"))]

    if selected:
        lines = [
            "<b>Daily Internship Radar</b>",
            f"Found {len(selected)} new matching opportunities.",
            "",
            "<b>Diagnostics</b>",
            f"Sources: {sum(source_counts.values())}",
            f"Unique: {stats['unique']}",
            f"Tier 1 - Internship: {stats['tier1']}",
            f"Tier 2 - Junior/Graduate: {stats['tier2']}",
            f"Tier 3 - Seniority not specified: {stats['tier3']}",
            f"AI/Data: {stats['ai_data']}",
            f"Location eligible: {stats['location']}",
            f"Seniority excluded: {stats['excluded_seniority']}",
            f"New eligible: {stats['eligible']}",
            "",
        ]

        for i, j in enumerate(selected, 1):
            lines.extend([
                f"<b>{i}. {html.escape(j['title'])}</b>",
                f"Company: {html.escape(j['company'])}",
                f"Location: {html.escape(j['location'])}",
                f"Source: {html.escape(j['source'])}",
                f"<a href=\"{html.escape(j['url'], quote=True)}\">Open listing</a>",
                "",
            ])

        send_telegram("\n".join(lines))

        now = datetime.now(timezone.utc).isoformat()
        for j in selected:
            state[j["url"]] = {
                "first_sent_at": now,
                "title": j["title"],
                "company": j["company"],
            }
    else:
        lines = [
            "<b>Daily Internship Radar</b>",
            "No new matching internships were found today.",
            "",
            "<b>Diagnostics</b>",
            f"Sources: {sum(source_counts.values())}",
            f"Unique: {stats['unique']}",
            f"Tier 1 - Internship: {stats['tier1']}",
            f"Tier 2 - Junior/Graduate: {stats['tier2']}",
            f"Tier 3 - Seniority not specified: {stats['tier3']}",
            f"AI/Data: {stats['ai_data']}",
            f"Location eligible: {stats['location']}",
            f"New eligible: {stats['eligible']}",
            f"Already sent: {stats['already_sent']}",
            f"Already sent eligible: {stats['already_sent_eligible']}",
        ]
        if rejection_examples:
            lines.extend(["", "<b>Examples of rejected jobs</b>"])
            for example in rejection_examples[:5]:
                lines.append(html.escape(example))
        send_telegram("\n".join(lines))

    cutoff = datetime.now(timezone.utc) - timedelta(days=60)
    state = {
        u: x for u, x in state.items()
        if (parse_date(x.get("first_sent_at")) or datetime.min.replace(tzinfo=timezone.utc)) >= cutoff
    }
    save_state(state)


if __name__ == "__main__":
    main()
