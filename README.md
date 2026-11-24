# SEO Studio

A general-purpose AI SEO writing and keyword research application for any topic, audience and market.

## Run locally

```bash
python -m venv .venv
pip install -r requirements.txt
python app.py
```

Configure GEMINI_API_KEY or GROQ_API_KEY in a local .env file. Optional: QWEN_API_KEY, PEXELS_API_KEY. Google Trends uses Pytrends and may be rate limited. Country research accepts two-letter country codes; blank means worldwide. Article language, audience, market and reference links are optional. AI content requires editorial fact-checking.

This is currently a single-user prototype. Do not expose publicly without authentication, request limits, isolated article storage and secure credential handling.

## API

POST `/api/generate` with JSON containing `primary_keyword` and optional `title`, `language`, `audience`, `market`, `purpose`, `tone`, `links`, and `secondary_keywords`. Credentials belong in environment variables, not GitHub files. Optional GitHub draft storage is intended for a private datastore only. Without a Pexels key, unmatched photos are omitted.

Run tests with `python -m unittest discover -s tests`.
