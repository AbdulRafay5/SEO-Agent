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

## Keyword research

Open Keyword research, enter a seed topic, choose a language and optional country code, then discover ideas. Live Google Trends is opt-in and can be rate limited. AI suggestions and inferred intent are estimates; Google Trends top scores are relative indices and rising values represent growth, not monthly searches. Export results as CSV or send a keyword to the article studio.

## SEO analysis

Open an article and click SEO analysis. The editorial checklist measures headings, title, topic placement, metadata, paragraph length and image descriptions without AI calls. It is not a ranking prediction. The optional description is editable and the analysis can be refreshed.

### Upgrading an existing installation

Set GEMINI_API_KEY or GROQ_API_KEY and optional PEXELS_API_KEY in the deployment environment. Credentials previously stored in a datastore settings file are no longer loaded; rotate any keys that were committed. The browser attempts a one-time migration of a recognizable previous studio storage namespace on the same origin if the current keys are absent. Old keys are retained. A different deployment domain has separate browser storage.

## Competitor comparison

In Keyword research, expand Competitor research and add up to five search results with their URLs, titles and headings. Compare heading coverage against the current draft if desired. No provider key is needed. This is a manual SERP comparison, not live search scraping or rank tracking; headings are matched by normalized exact text.

Optional live competitor discovery: set BRAVE_SEARCH_API_KEY in your environment and use Find live results in Competitor research. Brave results are not Google rankings. Manual comparison remains available without a key. Set the provider spending limit before enabling; no API calls are made until a user requests live search. Headings still require manual input.
