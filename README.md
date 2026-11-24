# SEO Studio

A general-purpose AI SEO writing and keyword research application for any topic, audience and market.

## Run locally

```bash
python -m venv .venv
# Windows PowerShell: .\.venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
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

Online evidence discovery optionally reuses the Brave Search API. Enter a topic and optional country/language codes, review results and select Use snippet. Search snippets are explicitly labelled and treated as limited evidence, not fetched pages. Open the source and replace the text with relevant excerpts when stronger grounding is needed. No network request is made merely by generating an article. Manual source ingestion works without a search key.

Optional webpage extraction requires SEO_WEB_EXTRACTION=1 and SEO_OWNER_AUTH=1. Add a source URL and click Extract webpage. Only public HTTPS hostnames on port 443 are accepted; DNS addresses are checked and the connection is pinned to a validated address with TLS hostname verification. Redirects, private addresses, compressed content, PDFs and pages exceeding 512 KiB are rejected. Extracted text is capped at 12,000 characters and may omit or include irrelevant content. No JavaScript rendering or access-control bypass is attempted. Review text and respect site access and usage rules. Manual excerpts remain available. Public multi-user extraction is not enabled.

Hybrid retrieval is opt-in: set SEO_SEMANTIC_RETRIEVAL=1 with an existing Gemini key and a supported GEMINI_EMBEDDING_MODEL, then select Hybrid semantic matching. Query and passage text are sent to Gemini for embeddings. BM25 and cosine-similarity rankings are combined using reciprocal rank fusion; the similarity cutoff is heuristic, not calibrated confidence. Missing configuration, provider failure or excessive passage counts fall back to BM25 and the UI reports the actual method. Embedding calls may incur provider costs. No vector database is required; embeddings are not persisted. Default lexical retrieval makes no embedding requests.

### Reusable research library

Open Evidence grounding → Saved research library to save selected source text and provenance with its current topic. Search by title, topic, URL or text, reuse individual sources, remove unwanted saved entries or export JSON for backup. Exact normalized text, URL and source-type duplicates are skipped. Storage is browser-local (100 sources / 500,000 source characters maximum), not account-scoped or synced; clearing browser data removes the library. Saving does not send material to an external service. Reusing sources in generation or embedding retrieval sends selected text to the configured AI provider as before. Exported JSON is a backup; automatic import is not implemented. Embeddings are not cached by this feature.

### Embedding caching

For an authenticated owner workspace, enable SEO_EMBEDDING_CACHE=1 alongside SEO_SEMANTIC_RETRIEVAL=1 and SEO_OWNER_AUTH=1. The process-local cache reuses identical query and passage embeddings for the same provider model and owner configuration. It stores hashes and float32 vectors in memory, capped at 256 entries with a 30-minute expiry; expired entries are removed on cache access. It does not persist across process restarts, Vercel cold starts or separate workers, and simultaneous cache misses may repeat a request. No source text or vector database is written to disk. Anonymous deployments bypass the cache. Embedding calls remain subject to provider quotas and charges. Disabling caching stops reuse but restarting the process is needed to immediately clear its memory.

### Citation reference checks

Evidence-backed generation reports explicit bracketed source IDs (for example [S1] or [S1, S2]), unknown IDs, cited sources and unused retrieved sources. The original generated content is not silently changed. Checks only compare identifiers against retrieved passages; factual entailment, arbitrary hyperlinks and external source accuracy are not verified. The report is for the latest generation and is cleared when opening another draft or editing content; reports are not persisted. Review the underlying evidence before publication.

### Offline RAG evaluation

Run `python rag_evaluation.py` from the repository root to print a JSON benchmark report. Ten synthetic labelled cases exercise English, Spanish, French, Urdu, unsegmented Japanese, no-match queries, distractors and a semantic paraphrase. Source-level precision@3, recall@3, MRR@3 and nDCG@3 use unique source IDs from the returned passages; precision uses fixed k. No-match accuracy is reported separately. Hybrid comparison uses supplied mock vectors only and does not measure Gemini embedding quality. Tests assert selected regression cases and exercise actual Flask generation with a mocked model, verifying evidence injection and citation IDs. CI prints results. Japanese lexical segmentation is a known limitation and is measured rather than asserted as supported. This small synthetic benchmark does not establish production retrieval accuracy, factual grounding or live article quality.

Generated local drafts retain their final displayed Markdown, SEO description and original retrieved evidence. Reopening a local draft restores its evidence preview; edited local versions retain the original passages but do not inherit a stale citation report. Reports are withheld if browser formatting changes the returned Markdown. Server-only drafts and remote versions do not yet persist evidence. This data is stored in the same browser and may include source excerpts; avoid shared devices. Storage failures warn rather than silently claiming persistence.

### Remote evidence and storage confirmation

Generated drafts report whether remote Markdown, metadata and evidence writes succeeded. Enable SEO_REMOTE_EVIDENCE=1 only with SEO_OWNER_AUTH=1 and a **private** GitHub datastore that you control. Retrieved excerpts are stored in separate evidence/ JSON files, not the article index or public Markdown. The application cannot verify repository visibility; do not enable this for a public datastore or confidential material. Evidence is loaded only when owner authentication and the feature are enabled, and only when its stored article SHA-256 matches the loaded Markdown. Citation IDs are recalculated on load. Existing articles without evidence remain readable. Partial failures return the article and a warning rather than hiding generated output. This feature covers newly generated articles, not remote edited versions; GitHub commits retain history even if the setting is later disabled.

### Isolated guest deployment

Set SEO_GUEST_MODE=1 and leave SEO_OWNER_AUTH disabled on a separate deployment/origin for browser-local guest usage. Guest home pages never load the owner draft directory or manifest; both server article read routes return 404 and generation never writes article content or evidence to local server or GitHub storage. Guest drafts and research use separate browser storage keys, and legacy migration is disabled for guests. Do not share an origin with the private owner deployment: localStorage namespaces are not a security boundary against scripts or people with browser access. The existing owner/legacy mode is unchanged when guest mode is off. The feature is not a registered-user account system. Provider credentials are still server-owned and process-local cooldown is not a distributed quota; do not open unrestricted public access until quota enforcement is configured. In guest mode users must download or retain browser-local copies; clearing browser storage removes them.

### Account authentication foundation (not public-ready)

Account mode is disabled by default and mutually exclusive with owner and guest deployment modes. It requires a separate PostgreSQL database (SEO_DATABASE_URL) and a random setup key of at least 32 characters (SEO_ACCOUNT_SETUP_KEY). Run `python account_auth.py` with the database URL exported in your environment to create the schema. The register/login/logout JSON endpoints are restricted by the X-Account-Setup-Key header for provisioning and integration testing. Passwords are scrypt-hashed; random session tokens are stored only as SHA-256 hashes in PostgreSQL, expire after 12 hours and are revoked on logout. Cookies are HTTPS-only, HttpOnly and SameSite=Strict. No registration or login page is exposed yet. All article/workspace routes remain blocked in account mode until individual storage and distributed usage controls are implemented. Existing modes are unchanged. A live PostgreSQL integration test is still required before enabling this mode. Database hosting may have costs; no provider is mandated.

### Hybrid account storage foundation

PostgreSQL retains accounts and hashed sessions; account article records are stored in the existing private GitHub datastore under `users/<verified-account-id>/drafts/<random-id>.json`. Each immutable JSON record contains Markdown, SEO metadata and an optional same-account parent version. Keeping these fields together avoids partial writes between article and metadata files. The owner draft directory is unchanged. Restricted account testing exposes GET/POST `/api/accounts/articles` and GET `/api/accounts/articles/<filename>` only with a valid session and setup key. Caller-supplied ownership fields are rejected. Use a private datastore; GitHub retains commit history and the application cannot verify repository visibility. Article lists currently contain IDs, not full previews; RAG evidence, research, UI and distributed limits remain outstanding. This is not a public workspace yet.

Account research is stored as individual immutable records under `users/<verified-account-id>/research/`. Restricted GET/POST `/api/accounts/research` and GET `/api/accounts/research/<filename>` use the same session and setup-key checks as article endpoints. Article creation accepts up to five same-account `research_ids`, retrieves relevant excerpts lexically against the keyword, and stores passages alongside the Markdown and metadata. This attaches evidence to manually submitted articles; it does not yet enable account AI generation. Versions inherit parent passages unless new research IDs are supplied; citations are recalculated against the submitted content. Citation checks verify reference IDs, not factual support. No source deletion or UI is implemented yet. GitHub history retains research and article records; do not store confidential source material.

## Generation behaviour

The 2000-word target is advisory; article generation makes one generation request (with the existing provider fallback on failure), rather than repeating successful short responses solely to reach a word count. Review output for completeness. Chinese and Japanese title candidates can pass validation without spaces. Word counts remain whitespace-based estimates, not language-aware segmentation. Request bodies are capped at 256 KiB while existing per-field limits remain in force, allowing larger valid UTF-8 research excerpts. Optional account infrastructure is disabled by default and is not required for the core SEO workflow.

Choose a target word count from 300 to 3000 in the article studio (default 2000). API clients can pass integer `target_words`. The generator adapts the editorial prompt and output token budget; exact length is not guaranteed and successful responses are not regenerated merely to match the target.

### Core reliability repairs
The server is the single source of generated Markdown formatting. Explicit headings are preserved and missing headings no longer discard the opening paragraph. Generated content is not globally deduplicated, preserving quotations and code. Filenames use bounded slugs and UUIDs. Generation attempts at most four photo lookups (each can have a fallback request) and two diagram markers; diagram rendering is not verified by the server. Editor metrics refresh on raw edits, reopen and target changes. Clearing browser drafts writes an empty collection to prevent legacy migration from restoring deleted records. Server files are still retained by browser-library removal.

### Relevant stock photos and bounded Trends requests
Pexels searches up to 15 candidates per query and ranks their provider-supplied alternative descriptions against concrete scene terms and article/section context. Missing descriptions, generic scenes, duplicate URLs and weak matches are rejected. A second query is optional and retains scene terms; no unrelated nature fallback is used. This is metadata-based matching, not visual verification, and may omit good photos when their metadata is sparse. Live Pexels credentials are required to assess real-world relevance. Google Trends now uses a bounded process-local cache, one attempt with shorter network timeouts, and hourly labels for subdaily data. Network calls are still subject to provider availability and do not have a strict overall deadline.

Title suggestions now preserve the AI's wording instead of force-inserting English keywords or power words. English fallback options are labelled separately; other languages report an unavailable provider instead of returning English templates. Power-word selection remains a prompt preference, not a guaranteed exact count. Markdown downloads append retrieved source IDs, titles, provenance and URLs when available; this does not verify the claims. The editor warns before generating, brainstorming, opening another draft or leaving the page if article content or description differs from the last saved baseline.

### Retrieval and metric consistency
Chinese and Japanese script runs use overlapping two-character lexical tokens; longer unsegmented evidence is split into overlapping character windows. This is a lightweight heuristic, not a language-specific morphological analyser. Evidence preview accepts optional title and questions, with the current UI passing the article title. Generation and the SEO analyser share backend word and keyword statistics, excluding fenced code, image URLs and source IDs. Editor metrics approximate the same rules locally; Unicode case folding and segmentation may still differ. The Japanese synthetic benchmark is now a regression assertion rather than an expected limitation.

### Local metadata and workspace requests
Local article metadata is saved as an atomic, content-hash-bound JSON sidecar beside Markdown. Older drafts remain readable; local files on serverless temporary storage remain ephemeral. Generated browser drafts and local versions retain editorial settings, while the remote manifest deliberately excludes the editorial brief. Superseded article requests save their successful results to the library instead of replacing the currently selected editor. Browser removal is explicitly not server deletion. Storage errors during removal are reported; multi-key browser writes are not atomic.

### Provider reliability
Explicit token-limit and selected incomplete-response finish reasons are rejected, with the configured Gemini-to-Groq fallback retained. A response marked complete by a provider is not guaranteed to be editorially complete. Title and keyword AI requests now share the existing process-local generation lock. This is not a distributed or per-user quota system. Frontend CDN versions match browser test dependencies. Studio related Trends searches are explicitly requested rather than triggered on every typing pause.

### Hosted workspace safety
Set `SEO_REQUIRE_PROTECTED_WORKSPACE=1` alongside `SEO_OWNER_AUTH=1` and strong owner credentials on a private HTTPS deployment. This explicit opt-in avoids breaking existing local or hosted installations; it does not change deployed environment variables automatically. Guest mode still permits anonymous provider use and is not appropriate for unrestricted public generation without distributed quotas. All Flask responses now disable shared caching and framing, suppress referrer information and set nosniff. Remote versions use create-only writes and the shared editorial word-count algorithm. Draft filenames are restricted to simple safe names; older files with spaces or non-ASCII names may need renaming before reopening.
