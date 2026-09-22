# Internship Radar

A free GitHub Actions based internship monitoring system for AI, Machine Learning, Data Science, Data Analysis, Computer Vision, NLP, LLM, RAG, and AI Research opportunities.

The project collects jobs from public job-board APIs, filters them using transparent rules, removes previously sent jobs, and sends a daily Telegram report.

## Features

- Runs automatically with GitHub Actions.
- Sends results to Telegram.
- Uses public job-board endpoints.
- Filters for AI and data-related internships.
- Filters for Egypt and remote opportunities.
- Deduplicates jobs.
- Stores sent jobs so the same opportunity is not repeatedly reported.
- Supports manual workflow execution.
- Can also be run locally.
- Requires no paid server.

## Project Structure

```text
internship-radar/
├── .github/
│   └── workflows/
│       └── daily_radar.yml
├── data/
│   └── sent_jobs.json
├── src/
│   └── radar.py
├── .gitignore
├── requirements.txt
└── README.md
```

## How It Works

```text
Public Job APIs
      |
      v
Collect Jobs
      |
      v
Normalize + Deduplicate
      |
      v
AI / Internship / Location Filters
      |
      v
Remove Previously Sent Jobs
      |
      v
Telegram Bot
      |
      v
Commit sent_jobs.json
```

## Current Sources

The first version supports:

- Greenhouse public job boards
- Lever public job postings
- Remotive public remote jobs API

The source list can be customized with environment variables.

## Telegram Setup

### 1. Create a Telegram bot

Open Telegram and talk to `@BotFather`.

Create a bot and copy its bot token.

Never put the token inside the repository.

### 2. Get the chat ID

Send at least one message to your bot.

Then obtain the chat ID using Telegram's Bot API or another Telegram bot utility.

The chat ID is also stored as a GitHub Actions secret in this project.

## GitHub Secrets

Open:

```text
Repository
-> Settings
-> Secrets and variables
-> Actions
-> New repository secret
```

Create:

```text
TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID
```

Do not commit either value.

## Run the Workflow

After adding the two secrets:

1. Open the repository.
2. Open the Actions tab.
3. Select `Daily Internship Radar`.
4. Select `Run workflow`.
5. Start the workflow.
6. Check Telegram.

This manual run is the recommended first test.

## Daily Schedule

The workflow currently uses:

```text
0 4 * * *
```

GitHub Actions cron uses UTC. This is 7:00 AM Egypt time while Egypt is UTC+3.

If Egypt changes its UTC offset, update the cron expression to keep the report at 7:00 AM local time.

## Run Locally

Clone:

```bash
git clone https://github.com/amoniusshehata/internship-radar.git
cd internship-radar
```

Create a virtual environment.

Windows:

```bash
python -m venv .venv
.venv\Scripts\activate
```

Linux/macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install:

```bash
pip install -r requirements.txt
```

Windows PowerShell:

```powershell
$env:TELEGRAM_BOT_TOKEN="YOUR_BOT_TOKEN"
$env:TELEGRAM_CHAT_ID="YOUR_CHAT_ID"
python src/radar.py
```

Linux/macOS:

```bash
export TELEGRAM_BOT_TOKEN="YOUR_BOT_TOKEN"
export TELEGRAM_CHAT_ID="YOUR_CHAT_ID"
python src/radar.py
```

## Filtering

A job must contain:

1. An AI or data-related keyword.
2. An internship-related keyword in the title.
3. A target location.

Target roles include:

- Machine Learning Intern
- Data Science Intern
- AI Research Intern
- Computer Vision Intern
- NLP Intern
- LLM Intern
- Data Analyst Intern
- AI Engineer Intern

Target locations include:

- Egypt
- Cairo
- Giza
- Alexandria
- Aswan
- Remote
- Worldwide
- MENA
- Middle East

The score only orders matching opportunities in the report. It is not a measure of job quality.

## Adding More Companies

Greenhouse boards can be configured with:

```text
GREENHOUSE_BOARDS=company1;company2;company3
```

Lever boards can be configured with:

```text
LEVER_BOARDS=company1;company2;company3
```

These can be supplied as environment variables in the workflow.

## State Management

`data/sent_jobs.json` stores opportunities already sent.

The workflow has repository write permission so it can commit the updated state after a successful run.

Entries older than 60 days are removed automatically.

## Security

- Never commit Telegram bot tokens.
- Use GitHub Actions Secrets.
- If a token is exposed, revoke it through BotFather and create a new one.
- Do not store personal credentials in the repository.
- Only public job data is processed.

## Limitations

This project cannot guarantee that every internship on the internet will be found.

Some companies do not expose public APIs, some job boards require authentication, APIs can change, and keyword filtering cannot understand every variation of an internship description.

The project intentionally starts with public sources instead of scraping private or authenticated platforms.

## Roadmap

Possible next stages:

1. Add more public job APIs.
2. Add company-specific career adapters.
3. Add RSS support.
4. Extract application deadlines.
5. Add application tracking.
6. Add SQLite storage.
7. Add historical job analytics.
8. Add optional semantic matching.
9. Add a web dashboard.
10. Add richer Telegram commands.

The recommended architecture is to keep the first version rule-based and observable before adding an ML or LLM ranking layer.

## License

Adapt and extend the project for personal use. Check the terms of each job source before adding a new integration.
