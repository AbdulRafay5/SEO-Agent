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

## Section revision

Open a generated article or saved draft, click Revise, select a Markdown section and request a preview. Accepting a revision changes only the workspace; undo restores the preceding version. Copy or download the revised article to keep it. The saved original is not overwritten. Revision uses your configured AI provider and consumes its quota.

### Saving revisions

Save version creates a separate browser-local copy of the current article, including manual Markdown changes and the optional meta description. It does not overwrite server drafts or publish any data. Versions survive reloads on the same browser and origin, but are not synchronized across devices. Download important versions for backup. If browser storage is unavailable the editor reports the failure instead of claiming a save.

## Optional owner-only access

The existing workspace is single-owner, not multi-tenant. To protect a private deployment, set `SEO_OWNER_AUTH=1`, `SEO_OWNER_USERNAME` and a strong unique `SEO_OWNER_PASSWORD` in the deployment environment. Use HTTPS only (localhost HTTP is for development). The browser prompts for credentials using HTTP Basic authentication. All application routes require credentials while this mode is enabled, including draft access and AI requests. Missing credentials in enabled mode fail closed. Authentication is off by default to preserve existing local workflows. Browser-managed credentials may persist until the browser session is closed; there is no application logout or account registration. This is not a substitute for multi-user storage isolation or distributed request limits. Keep the datastore private and do not use shared browser profiles for confidential drafts. Never commit passwords. Redeploy after changing Vercel environment variables.

## Optional remote article versions

For a private, authenticated owner workspace, set SEO_REMOTE_VERSIONS=1 alongside SEO_OWNER_AUTH=1 and the existing private GitHub datastore configuration. Save remote creates a new Markdown file and attempts to index its metadata; it never replaces the source draft. The file survives redeployments and is discoverable from another browser. If indexing fails, the file is still listed by filename. GitHub retains saved content in its history; removing a draft from the browser library is not permanent remote deletion. Keep the datastore private. This remains a single-owner feature, not multi-user storage isolation.

Article index updates use the GitHub file revision from the original read and retry conflicts up to three attempts. Invalid index content is not overwritten. If indexing cannot be confirmed, the independently saved Markdown file remains discoverable by filename. This does not provide transactional storage or multi-user isolation.

## Editorial prompt and grounding

The generation prompt preserves topic-adaptive article structure, natural keyword usage, contextual links, useful FAQs and relevant media placement. Reference URLs are not fetched or treated as verified evidence. Keyword/trend and competitor research are separate tools; they do not automatically inject retrieved documents into generation. This is not a full retrieval-augmented generation pipeline.

## Optional evidence retrieval

In Article Studio, open Evidence grounding and paste up to five source excerpts (30,000 characters total). Preview retrieves relevant passages using deterministic BM25 lexical ranking; generation retrieves passages for the topic, title and editorial questions, then adds them to the prompt with source IDs. Source URLs are labels, not automatically fetched documents. Excerpts are unverified and are sent to the configured AI provider during generation. No additional API or vector database is needed. Citation IDs are requested, not guaranteed or independently fact-checked. Evidence is not automatically persisted with saved drafts; retain your source material separately. Retrieval is lexical, not semantic, and can miss paraphrases and languages without whitespace-delimited words.
