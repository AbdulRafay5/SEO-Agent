# SEO Studio

AI-assisted article writing and keyword research for a chosen topic, language, audience and market. Built with Flask, Markdown and a browser-based editor.

## Quick start

Requires Python 3.11 or later. From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python app.py
```

On macOS/Linux, activate with `source .venv/bin/activate` and copy the example using `cp .env.example .env`. Open http://127.0.0.1:5000. Edit .env before starting the server to configure at least one writing provider. Never commit keys or passwords.

## Configuration

| Setting | Purpose |
| --- | --- |
| GEMINI_API_KEY / GROQ_API_KEY | Article, title and research generation. Gemini first, Groq fallback. |
| QWEN_API_KEY | Optional title provider, with existing AI fallback. |
| PEXELS_API_KEY | Optional relevant stock photographs. |
| BRAVE_SEARCH_API_KEY | Optional live competitor and evidence discovery. |
| GEMINI_MODEL / GROQ_MODEL / QWEN_TITLE_MODEL | Optional provider model overrides. |
| GITHUB_REPO / GITHUB_TOKEN / GITHUB_BRANCH | Optional private GitHub draft datastore; branch defaults to main. |
| SEO_OWNER_AUTH / SEO_OWNER_USERNAME / SEO_OWNER_PASSWORD | Optional single-owner HTTP Basic authentication. |
| SEO_REQUIRE_PROTECTED_WORKSPACE | Refuse unprotected shared mode when set to 1. |
| SEO_REMOTE_VERSIONS | Optional remote version saving, with owner authentication and private datastore. |
| SEO_REMOTE_EVIDENCE | Optional remote evidence persistence, with owner authentication and private datastore. |
| SEO_WEB_EXTRACTION | Optional public HTTPS page extraction, owner mode only. |
| SEO_SEMANTIC_RETRIEVAL / GEMINI_EMBEDDING_MODEL | Optional Gemini embedding retrieval. |
| SEO_EMBEDDING_CACHE | Optional owner-only process-local embedding cache. |
| SEO_GUEST_MODE | Separate browser-local guest deployment, without server draft access. |

See .env.example for defaults. AI, search, embedding and image services have their own quotas and possible costs; no paid service is mandatory beyond any provider access required for writing. Google Trends uses Pytrends and may be unavailable or rate limited. Rotate keys previously committed to any repository.

## Main workflow

1. Enter a topic, optional secondary keywords, language, audience, market, purpose, tone and reference URLs.
2. Choose an article heading or request title suggestions. Non-English requests do not receive English fallback templates. Power words are a prompt preference.
3. Choose a target of 300–3000 words (default 2000). This is an editorial target, not an exact guarantee.
4. Optionally add research excerpts and preview retrieved passages.
5. Generate the article. Explicitly incomplete provider output is rejected; the configured provider fallback is retained.
6. Review the Markdown or formatted preview, SEO description and editorial checks. Revise individual sections with a preview, accept or undo, or edit Markdown directly.
7. Save a separate version, copy formatted content or download Markdown. Downloads include available source references. Nothing publishes automatically.

Pexels candidates are ranked using descriptive metadata, the scene description and article/section context. Weak or duplicate candidates are omitted. No unrelated generic image fallback is used. The generator targets two or three relevant photos for photographable topics, depending on article length, using up to four initial photo candidates and two additional context-derived candidates when needed. Searches inspect up to 30 provider results per query. No additional AI call is required for the bounded fallback. Photo count is a target, not a guarantee; unsuitable or unavailable photos are omitted. Up to two diagram markers are processed. Media stays in its original context rather than being moved into arbitrary sections. Mermaid diagrams use an external rendering service and are not visually verified by the server. External services receive the relevant queries or diagram text.

## Research and editorial analysis

Keyword research combines AI ideas and optionally requested Trends data. Country codes are two letters; blank means worldwide. Intent is inferred, Trends scores are relative indices, and rising values represent growth rather than monthly search volume. Export keyword ideas as CSV or transfer one to the studio.

Competitor comparison accepts up to five distinct URLs, titles and manually supplied headings. It compares normalized exact headings, not semantic coverage or measured ranking opportunities. Optional Brave discovery provides search result snippets, not Google rankings or complete page headings.

SEO analysis is a deterministic editorial checklist, not a search-ranking score. It reviews headings, title, topic placement, description, paragraphs and images. Word and keyword counts exclude fenced code, image URLs and bracketed source IDs. Frontend estimates and Unicode segmentation can differ from backend analysis. Review multilingual output manually.

## Retrieval-augmented generation

Paste up to five evidence excerpts (12,000 characters per source, 30,000 total). Preview and generation retrieve relevant passages using BM25 lexical ranking, with overlapping character pairs and bounded character windows for Chinese and Japanese text. Generation adds selected passages with source IDs to the writing prompt. Reference links alone are not automatically fetched.

Optional Brave search allows selection of snippets. Optional webpage extraction accepts public HTTPS hostnames on port 443 in authenticated owner mode. DNS addresses are checked and connections pinned to validated addresses with TLS verification. Redirects, private addresses, compressed responses, PDFs and content over 512 KiB are rejected. Extracted text is limited to 12,000 characters; review it for accuracy and relevance. No JavaScript rendering or access-control bypass.

Hybrid matching uses Gemini embeddings when enabled; BM25 and cosine rankings are combined with reciprocal rank fusion, with lexical fallback on provider or size-limit failures. Its similarity threshold is heuristic. The optional authenticated-owner cache holds up to 256 entries for 30 minutes in process memory, not across workers or restarts.

The browser research library stores up to 100 sources / 500,000 text characters. It supports reuse, removal and JSON export, but not import or cross-device sync. Selected source text is sent to the configured generation or embedding provider. Avoid confidential excerpts.

Citation checks validate source-ID membership, not factual entailment or accuracy. Edited articles can invalidate the earlier citation report. Remote evidence is checked against the saved Markdown hash and citations are recalculated on load. Remote revisions inherit available server-side parent evidence when enabled. Browser-only evidence needs a local backup or export.

## Storage and deployment

Browser drafts and versions retain Markdown, metadata, editorial settings and available evidence. Unsaved edits trigger confirmation before replacement. Browser removal does not delete server copies or GitHub history. Back up important work before clearing browser data or changing deployment domains. Browser storage is not an authentication boundary.

Local server drafts use Markdown and content-hash-bound metadata sidecars. Vercel's temporary filesystem is ephemeral. Optional GitHub storage persists Markdown and its manifest across deployments. Index writes retry conflicts; article, index and evidence writes are not transactional. The UI reports partial failures. The remote manifest excludes the full editorial brief.

For private HTTPS hosting, use SEO_OWNER_AUTH=1, strong unique credentials and SEO_REQUIRE_PROTECTED_WORKSPACE=1. Redeploy after changing environment variables. Use a separate private datastore and verify its visibility yourself. The app does not verify repository privacy. Remote evidence stores excerpts in Git history. Do not use shared browser profiles for private drafts. Owner mode uses browser-managed Basic authentication, not account registration or application logout.

For a separate guest deployment, set SEO_GUEST_MODE=1 with owner mode disabled. Use a different origin from your private workspace. Guest generation does not write server drafts; users must retain browser copies or downloads.

**Do not expose unrestricted public generation with server-owned API keys.** Process-local locks and cooldowns are not distributed per-user quotas. Hosted protection is opt-in to preserve existing installations. The experimental account foundation is disabled by default and not public-ready; keep SEO_ACCOUNT_MODE=0 for the normal workflow. It requires PostgreSQL, a setup key and restricted integration testing. It does not expose a public writing workspace.

## API overview

POST /api/generate accepts JSON with primary_keyword and optional title, language, audience, market, purpose, questions, tone, links, secondary_keywords, target_words, evidence_sources and evidence_mode. Reference links are HTTP(S), one per line. Request bodies are capped at 256 KiB.

POST /api/titles accepts JSON with keyword, power_words, language and audience. Passing text in JSON avoids percent-encoded URL path problems on hosted deployments. The legacy GET /api/titles/<keyword> route remains available for compatibility.

Other endpoints include /api/trends, /api/keywords/research, /api/competitors/compare, /api/competitors/search, /api/evidence/preview, /api/evidence/search, /api/evidence/extract, /api/seo/analyze and /api/editor/revise. Owner storage endpoints include /api/blog/<filename> and /api/blog/versions.

## Testing

```bash
python -m unittest discover -s tests
python rag_evaluation.py
```

GitHub Actions runs Python checks and a Chromium browser smoke test with mocked provider responses. The synthetic RAG benchmark reports source-level precision, recall, MRR and nDCG; hybrid vectors are mocked. These tests do not establish live model quality, factual accuracy or stock photo relevance.

Before publishing or sharing an installation, test with your own configured providers:

- Generate a short and long article in English and another language.
- Confirm titles, article structure, metadata and actual Pexels relevance.
- Test evidence preview, generation, citations and export with known excerpts.
- Revise, undo, edit, save versions, reload and download.
- Test research with and without Trends, and optional provider failures.
- Verify private deployment access, storage and persistence after redeploy.
- Check desktop and mobile layout and browser console.

Remaining limitations include approximate multilingual word counts, metadata-only photo relevance, unverified diagram rendering, provider-dependent latency, process-local usage controls and non-transactional remote storage. Live provider and cross-device tests require actual configured credentials. Review AI output before publication.
