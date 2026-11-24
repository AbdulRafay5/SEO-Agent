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
