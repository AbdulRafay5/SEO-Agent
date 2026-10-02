from flask import Flask, abort, render_template, jsonify, request
from dotenv import dotenv_values, load_dotenv
from datetime import date
from urllib.parse import unquote_plus
import os
import re
import random
import time
import tempfile
import base64
import difflib
import json
import requests
from google import genai
from groq import Groq
from pytrends.request import TrendReq
from keywords import all_keywords, keyword_links, CONTACT_URL
import github_store

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOTENV_PATH = os.path.join(BASE_DIR, ".env")
load_dotenv(DOTENV_PATH)
dotenv_settings = dotenv_values(DOTENV_PATH)
BUNDLED_BLOGS_FOLDER = os.path.join(BASE_DIR, "generated_blogs")
RUNTIME_DIR = os.path.join(tempfile.gettempdir(), "blog-generator") if os.getenv("VERCEL") else BASE_DIR
BLOGS_FOLDER = os.path.join(RUNTIME_DIR, "generated_blogs")
LAST_GEN_FILE = os.path.join(RUNTIME_DIR, "last_generated.txt")
COOLDOWN_SECONDS = 15
MIN_WORD_COUNT = 2000
CURRENT_DATE = date.today().strftime("%B %-d, %Y") if os.name != "nt" else date.today().strftime("%B %#d, %Y")

os.makedirs(BLOGS_FOLDER, exist_ok=True)

DRAFTS_REPO_DIR = "drafts"
MANIFEST_PATH = f"{DRAFTS_REPO_DIR}/manifest.json"


def _load_manifest():
    content, _ = github_store.get_file(MANIFEST_PATH)
    if not content:
        return []
    try:
        data = json.loads(content)
        return data if isinstance(data, list) else []
    except ValueError:
        return []


def _upsert_manifest_entry(entry):
    try:
        manifest = _load_manifest()
        manifest = [item for item in manifest if item.get("filename") != entry["filename"]]
        manifest.insert(0, entry)
        github_store.save_file(
            MANIFEST_PATH,
            json.dumps(manifest, indent=2),
            message=f"Update manifest: {entry.get('keyword', entry['filename'])}",
        )
    except Exception:
        app.logger.exception("Failed to update GitHub manifest for %s", entry.get("filename"))


_repo_settings = github_store.load_settings()
gemini_key = os.getenv("GEMINI_API_KEY") or dotenv_settings.get("GEMINI_API_KEY")
groq_key = _repo_settings.get("groqApiKey") or os.getenv("GROQ_API_KEY") or dotenv_settings.get("GROQ_API_KEY")
qwen_key = os.getenv("QWEN_API_KEY") or dotenv_settings.get("QWEN_API_KEY")
pexels_key = (
    _repo_settings.get("pexelsApiKey")
    or _repo_settings.get("PEXELS_API_KEY")
    or os.getenv("PEXELS_API_KEY")
    or dotenv_settings.get("PEXELS_API_KEY")
    or ""
).strip()

gemini_client = genai.Client(api_key=gemini_key) if gemini_key else None
client = Groq(api_key=groq_key)
qwen_client = Groq(api_key=qwen_key) if qwen_key else None
GEMINI_MODEL = "gemini-2.5-flash"
GROQ_MODEL = "openai/gpt-oss-120b"
QWEN_TITLE_MODEL = "qwen/qwen3.8-27b"

POWER_WORDS = [
    "Best", "Top", "Easy", "Simple", "Proven", "Smart", "Quick", "Complete",
    "Fast", "Modern", "Powerful", "Ultimate", "Essential", "Efficient",
    "Affordable", "Reliable", "Advanced", "Effortless", "Instant", "Seamless",
]


def generate_ai_text(prompt, max_tokens):
    if gemini_client:
        try:
            response = gemini_client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
                config={"max_output_tokens": max_tokens},
            )
            text = (response.text or "").strip()
            if text:
                return text
            raise RuntimeError("Gemini returned an empty response")
        except Exception:
            app.logger.exception("Gemini AI request failed; falling back to Groq")

    response = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens,
    )
    return (response.choices[0].message.content or "").strip()


def generate_title_text(prompt, max_tokens):
    if qwen_client:
        try:
            response = qwen_client.chat.completions.create(
                model=QWEN_TITLE_MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
            )
            message = response.choices[0].message
            text = (message.content or getattr(message, "reasoning", "") or "").strip()
            if text:
                return text
            raise RuntimeError("Qwen returned an empty response")
        except Exception:
            app.logger.exception("Qwen title request failed; falling back to primary AI provider")

    return generate_ai_text(prompt, max_tokens)


# ============================================================================
# PEXELS & IMAGE SANITIZATION
# ============================================================================

STOPWORDS = {
    "the", "and", "for", "with", "from", "into", "onto", "over", "under", "near",
    "that", "this", "their", "your", "its", "has", "have", "are", "was", "were",
}


def _is_acronym(word):
    return word.isupper() and len(word) <= 4


def clean_image_search_query(raw_query, primary_keyword="", section_context=""):
    clean = re.sub(
        r"(?i)\b(image|photo|photograph|illustration|picture|depicting|showing|a\s+view\s+of|conceptual|shot\s+of|realistic|vector|graphic)\b",
        "",
        raw_query,
    )
    clean = re.sub(r"[^\w\s]", " ", clean).strip()
    desc_words = [w for w in clean.split() if len(w) > 2 and w.lower() not in STOPWORDS]

    # Blend in the section heading so that if the model reuses the same marker
    # description in multiple places, the search still differs per section
    # instead of returning the same photo throughout the article.
    heading_words = [
        w for w in re.sub(r"[^\w\s]", " ", section_context).split()
        if len(w) > 2 and w.lower() not in STOPWORDS and not _is_acronym(w)
        and w.lower() not in {"software", "system", "management", "pakistan"}
    ]

    seen = set()
    combined = []
    for w in heading_words[:3] + desc_words:
        wl = w.lower()
        if wl not in seen:
            seen.add(wl)
            combined.append(w)

    if len(combined) >= 2:
        return " ".join(combined[:6])

    # Not enough to go on from the marker text alone - fall back to context,
    # skipping acronyms (FBR, POS, SRB, GST...) which return meaningless photos.
    context_words = [
        w for w in re.sub(r"[^\w\s]", " ", f"{section_context} {primary_keyword}").split()
        if len(w) > 2 and w.lower() not in STOPWORDS and not _is_acronym(w)
        and w.lower() not in {"software", "system", "management", "pakistan", "in"}
    ]
    if context_words:
        return " ".join(context_words[:3]) + " retail counter"

    return "pharmacy medicine store counter"


def get_pexels_image(query, primary_keyword="", section_context="", used_urls=None):
    fallback_image = "https://picsum.photos/1200/800"
    used_urls = used_urls if used_urls is not None else set()
    if not pexels_key:
        return fallback_image

    def first_unused(photos):
        for photo in photos:
            url = photo["src"]["large"]
            if url not in used_urls:
                return url
        return None

    search_query = clean_image_search_query(query, primary_keyword, section_context)
    headers = {"Authorization": pexels_key}
    params = {"query": search_query, "per_page": 5, "orientation": "landscape"}

    try:
        response = requests.get(
            "https://api.pexels.com/v1/search",
            headers=headers,
            params=params,
            timeout=7,
        )
        if response.status_code == 200:
            data = response.json()
            photos = data.get("photos") or []
            picked = first_unused(photos)
            if picked:
                return picked
    except Exception as e:
        app.logger.warning("Pexels fetch failed for '%s': %s", search_query, e)

    # Broad fallback that stays on-topic instead of an unrelated single word
    # or acronym (e.g. never search for "FBR store").
    try:
        fallback_words = [
            w for w in re.sub(r"[^\w\s]", " ", f"{section_context} {primary_keyword}").split()
            if len(w) > 2 and w.lower() not in STOPWORDS and not _is_acronym(w)
        ]
        broad_query = f"{' '.join(fallback_words[:2])} retail store".strip() if fallback_words else "pharmacy retail store"
        fallback_params = {"query": broad_query, "per_page": 5, "orientation": "landscape"}
        fallback_res = requests.get("https://api.pexels.com/v1/search", headers=headers, params=fallback_params, timeout=5)
        if fallback_res.status_code == 200:
            data = fallback_res.json()
            photos = data.get("photos") or []
            picked = first_unused(photos)
            if picked:
                return picked
    except Exception:
        pass

    return fallback_image


def get_mermaid_diagram(diagram_code):
    encoded = base64.urlsafe_b64encode(diagram_code.encode("utf-8")).decode("utf-8")
    return f"https://mermaid.ink/img/{encoded}"


def extract_bracket_blocks(text, start_marker):
    blocks = []
    search_start = 0

    while True:
        start_idx = text.find(start_marker, search_start)
        if start_idx == -1:
            break

        depth = 0
        end_idx = None
        for i in range(start_idx, len(text)):
            if text[i] == "[":
                depth += 1
            elif text[i] == "]":
                depth -= 1
                if depth == 0:
                    end_idx = i
                    break

        if end_idx is None:
            break

        full_match = text[start_idx : end_idx + 1]
        inner_content = text[start_idx + len(start_marker) : end_idx].strip()
        blocks.append((full_match, inner_content))
        search_start = end_idx + 1

    return blocks


def distribute_media_markers(body):
    """
    Spreads out [IMAGE:...]/[DIAGRAM:...] markers that the model dumped together
    (typically all at the end of the article) across different ## sections instead.
    Markers already placed on their own elsewhere in the body are left untouched.
    """
    marker_pattern = re.compile(r"\[(?:IMAGE|DIAGRAM):[^\[\]]*\]")
    paragraphs = body.split("\n\n")

    def is_marker_only(p):
        stripped = p.strip()
        return bool(stripped) and marker_pattern.fullmatch(stripped) is not None

    # Find runs of 2+ consecutive marker-only paragraphs - these are the clusters to fix.
    clustered_markers = []
    clustered_indices = set()
    run = []
    for idx, p in enumerate(paragraphs):
        if is_marker_only(p):
            run.append(idx)
        else:
            if len(run) >= 2:
                clustered_markers.extend(paragraphs[i].strip() for i in run)
                clustered_indices.update(run)
            run = []
    if len(run) >= 2:
        clustered_markers.extend(paragraphs[i].strip() for i in run)
        clustered_indices.update(run)

    if not clustered_markers:
        return body

    remaining = [p for i, p in enumerate(paragraphs) if i not in clustered_indices]

    heading_indices = [i for i, p in enumerate(remaining) if p.lstrip().startswith("## ")]
    if not heading_indices:
        return body

    slots = heading_indices[: len(clustered_markers)] or heading_indices
    for i, marker in enumerate(clustered_markers):
        slot = slots[i % len(slots)]
        # Insert after the section heading's first paragraph rather than mid-sentence.
        target = slot + 1 if slot + 1 < len(remaining) else slot
        remaining[target] = remaining[target].rstrip() + f"\n\n{marker}"

    return "\n\n".join(remaining)


def get_nearest_heading(text, position):
    heading = ""
    for match in re.finditer(r"^#{1,3}\s+(.+)$", text, re.MULTILINE):
        if match.start() > position:
            break
        heading = match.group(1).strip()
    return heading


def replace_image_markers(blog_text, primary_keyword=""):
    image_blocks = extract_bracket_blocks(blog_text, "[IMAGE:")
    diagram_blocks = extract_bracket_blocks(blog_text, "[DIAGRAM:")

    used_urls = set()
    for full_match, description in image_blocks:
        position = blog_text.find(full_match)
        section_context = get_nearest_heading(blog_text, position) if position != -1 else ""
        image_url = get_pexels_image(description, primary_keyword, section_context, used_urls)
        used_urls.add(image_url)
        clean_caption = re.sub(r"[\[\]]", "", description).strip()
        markdown_image = f"\n\n![{clean_caption}]({image_url})\n\n"
        blog_text = blog_text.replace(full_match, markdown_image, 1)

    for full_match, diagram_code in diagram_blocks:
        image_url = get_mermaid_diagram(diagram_code)
        markdown_image = f"\n\n![Process diagram]({image_url})\n\n"
        blog_text = blog_text.replace(full_match, markdown_image, 1)

    return blog_text, len(image_blocks), len(diagram_blocks)


def correct_keyword_input(keyword):
    matches = difflib.get_close_matches(keyword, all_keywords, n=1, cutoff=0.7)
    if matches:
        return matches[0]
    return keyword


def get_extra_internal_link_pool(current_keyword, limit=4):
    candidates = [url for kw, url in keyword_links.items() if kw != current_keyword]
    unique_urls = list(dict.fromkeys(candidates))
    if len(unique_urls) <= limit:
        return unique_urls
    return random.sample(unique_urls, limit)


def count_markdown_links(text):
    return re.findall(r"\[([^\]]+)\]\((https?://[^\)]+)\)", text)


def create_blog_slug(title_or_keyword):
    slug = re.sub(r"[^a-z0-9]+", "_", (title_or_keyword or "blog").lower()).strip("_")
    return slug or "blog"


def create_unique_blog_filename(keyword, title=None):
    base_title = (title or keyword or "blog").strip()
    base = create_blog_slug(base_title)
    suffix = time.strftime("%Y%m%d_%H%M%S", time.gmtime())
    unique = f"{base}_{suffix}_{random.randint(1000, 9999)}.md"
    return unique


AUTHORITY_EXTERNAL_LINKS = {
    "FBR": ("https://www.fbr.gov.pk/", "Federal Board of Revenue (FBR) official portal"),
    "SRB": ("https://srb.gos.pk/", "Sindh Revenue Board (SRB) portal"),
    "PRA": ("https://pra.punjab.gov.pk/", "Punjab Revenue Authority (PRA) portal"),
    "KPRA": ("https://kpra.kp.gov.pk/", "Khyber Pakhtunkhwa Revenue Authority (KPRA)"),
    "BRA": ("https://bra.gob.pk/", "Balochistan Revenue Authority (BRA)"),
}


def get_external_links_for_keyword(keyword):
    matched = []
    for authority, (url, label) in AUTHORITY_EXTERNAL_LINKS.items():
        if authority in keyword.upper():
            matched.append((url, label))
    if not matched:
        matched.append(("https://www.fbr.gov.pk/", "FBR tax regulations"))
        matched.append(("https://en.wikipedia.org/wiki/Point_of_sale", "Point of Sale (POS) reference"))
    return matched


# ============================================================================
# NATURAL LINKING & ARTIFACT CLEANING
# ============================================================================

def clean_keyword_artifacts(text, keyword):
    """
    Eliminates dangling markdown artifacts, orphan asterisks, and broken link fragments
    like 'in Keyword features](url)**' without altering body prose.
    """
    # Protect already well-formed links so the broken-link fix below can't re-match
    # inside them (that mismatch was corrupting text into "[S[a[daHisab...").
    protected_links = []

    def _stash_link(match):
        protected_links.append(match.group(0))
        return f"\x00LINK{len(protected_links) - 1}\x00"

    text = re.sub(r'\[[^\]]+\]\([^\)]+\)', _stash_link, text)

    # Fix broken links where opening bracket was omitted
    text = re.sub(
        r'(?<!\[)([A-Za-z0-9\s—|-]+features\]\([^\)]+\))',
        r'[\1',
        text
    )

    for i, link in enumerate(protected_links):
        text = text.replace(f"\x00LINK{i}\x00", link)

    # Remove dangling asterisks directly attached to markdown links: **[Label](url) or [Label](url)**
    text = re.sub(
        r'\*{1,3}(\[[^\]]+\]\([^\)]+\))',
        r'\1',
        text
    )
    text = re.sub(
        r'(\[[^\]]+\]\([^\)]+\))\*{1,3}',
        r'\1',
        text
    )

    # Clean orphaned bold asterisks attached directly to keyword boundaries: Keyword** or **Keyword
    escaped_kw = re.escape(keyword)
    text = re.sub(rf'\b{escaped_kw}\s*\*\*', keyword, text, flags=re.IGNORECASE)
    text = re.sub(rf'\*\*\s*{escaped_kw}\b', keyword, text, flags=re.IGNORECASE)

    # Remove duplicated location noise
    duplicated_location = re.compile(
        rf"(?:\*\*)?{escaped_kw}(?:\s+in\s+Pakistan)+(?:\*\*)?",
        re.IGNORECASE,
    )
    text = duplicated_location.sub(keyword, text)

    # Un-bold exact keyword in body text to maintain natural look
    text = re.sub(rf"\*{{2}}\s*{escaped_kw}\s*\*{{2}}", keyword, text, flags=re.IGNORECASE)

    # Fix sentences that lose their main verb due to model substitution
    text = re.sub(
        rf"(A dedicated\s+{escaped_kw})\s+(the visibility,\s+control)",
        r"\1 delivers \2",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        rf"(generic POS solution can record a sale, but\s+{escaped_kw})\s+adds",
        r"\1 solution adds",
        text,
        flags=re.IGNORECASE,
    )

    return text


def weave_natural_links(body, keyword, primary_internal_link, min_internal=3, min_external=2):
    """
    Seamlessly inserts missing contextual internal and external links directly into natural
    sentence structures without creating robotic, detached bulleted lists.
    """
    existing_links = [url for _, url in count_markdown_links(body)]
    paragraphs = body.split("\n\n")

    def is_valid_prose(p):
        stripped = p.strip()
        if len(stripped.split()) < 15 or len(stripped.split()) > 140:
            return False
        if stripped.startswith(("#", "!", "|", "-", "*", ">", "[")):
            return False
        return True

    eligible_indices = [i for i, p in enumerate(paragraphs) if is_valid_prose(p)]
    if not eligible_indices:
        return body

    current_internal_count = sum(1 for url in existing_links if "example.com" in url)
    current_external_count = len(existing_links) - current_internal_count

    # 1. Primary ExampleBrand feature & pricing link
    if current_internal_count < min_internal and primary_internal_link not in existing_links:
        for idx in eligible_indices:
            p = paragraphs[idx]
            if "ExampleBrand" in p.lower() and "[" not in p:
                paragraphs[idx] = p.rstrip() + f" You can explore the complete operational capabilities on the [ExampleBrand pricing and features]({primary_internal_link}) page."
                existing_links.append(primary_internal_link)
                current_internal_count += 1
                break

    # 2. Demo booking link
    if current_internal_count < min_internal and CONTACT_URL not in existing_links:
        for idx in reversed(eligible_indices):
            p = paragraphs[idx]
            if "[" not in p and any(w in p.lower() for w in ["business", "system", "setup", "manage", "store", "pharmacy"]):
                paragraphs[idx] = p.rstrip() + f" Pharmacy managers can also [book a free ExampleBrand demo]({CONTACT_URL}) to evaluate the register firsthand."
                existing_links.append(CONTACT_URL)
                current_internal_count += 1
                break

    # 3. Supplemental internal catalog links
    if current_internal_count < min_internal:
        extra_pool = get_extra_internal_link_pool(keyword, limit=4)
        for url in extra_pool:
            if current_internal_count >= min_internal:
                break
            if url in existing_links:
                continue
            topic_label = url.rstrip("/").split("/")[-1].replace("-", " ")
            for idx in eligible_indices:
                p = paragraphs[idx]
                if "[" not in p and len(p.split()) > 20:
                    paragraphs[idx] = p.rstrip() + f" For related counter workflows, review the [ExampleBrand {topic_label} options]({url})."
                    existing_links.append(url)
                    current_internal_count += 1
                    break

    # 4. External regulatory authority links
    if current_external_count < min_external:
        ext_targets = get_external_links_for_keyword(keyword)
        for url, label in ext_targets:
            if current_external_count >= min_external:
                break
            if url in existing_links:
                continue
            for idx in eligible_indices:
                p = paragraphs[idx]
                if "[" not in p and any(w in p.lower() for w in ["tax", "invoice", "compliance", "law", "fbr", "pos"]):
                    paragraphs[idx] = p.rstrip() + f" Statutory compliance requirements can be reviewed on the [{label}]({url})."
                    existing_links.append(url)
                    current_external_count += 1
                    break

    return "\n\n".join(paragraphs)


def fix_keyword_typos(text, keyword):
    keyword_word_count = len(keyword.split())
    target_clean = re.sub(r"[^\w\s]", "", keyword).lower()

    word_spans = [(m.group(), m.start(), m.end()) for m in re.finditer(r"\S+", text)]
    fixed_text = text
    offset = 0
    i = 0

    while i <= len(word_spans) - keyword_word_count:
        window = word_spans[i : i + keyword_word_count]
        window_text = " ".join(w[0] for w in window)
        window_clean = re.sub(r"[^\w\s]", "", window_text).lower()

        # High threshold: only fix genuine near-typos (e.g. one misspelled word), not
        # loosely-similar phrasing with a different grammatical structure - a lower
        # threshold here was swallowing verbs/subjects and breaking sentences.
        similarity = difflib.SequenceMatcher(None, window_clean, target_clean).ratio()
        if 0.92 <= similarity < 1.0:
            start = window[0][1] + offset
            end = window[-1][2] + offset
            fixed_text = fixed_text[:start] + keyword + fixed_text[end:]
            offset += len(keyword) - (end - start)
            i += keyword_word_count
        else:
            i += 1

    return fixed_text


def collapse_duplicate_words(text):
    return re.sub(r"\b(\w+)(\s+\1\b)+", r"\1", text, flags=re.IGNORECASE)


def enforce_keyword_density(body, keyword, target_per_1000=8.0):
    current_density = keyword_density(body, keyword)
    if current_density >= target_per_1000:
        return body

    reference_sentences = [
        f"For a fast-paced retail business, deploying a {keyword} ensures product catalog, stock counts, and sales receipts stay accurate.",
        f"When choosing a {keyword}, store owners should verify how effectively it monitors expiration windows, returns, and daily totals.",
        f"In real-world retail workflows, the practical value of a {keyword} lies in keeping the checkout counter running without calculation errors.",
        f"A purpose-built {keyword} automates routine batch management while keeping fiscal documentation transparent and organized.",
        f"Retail pharmacies adopting a {keyword} typically see immediate efficiency gains across sales counters and backroom shelves.",
    ]

    paragraphs = body.split("\n\n")
    keyword_terms = {term.casefold() for term in re.findall(r"[A-Za-z]{3,}", keyword)}
    topic_terms = keyword_terms | {
        "pos", "sales", "retail", "store", "shop", "inventory", "stock",
        "billing", "invoice", "counter", "payment", "tax", "reporting", "pharmacy"
    }

    def suitable_prose(paragraph):
        stripped = paragraph.strip()
        lowered = stripped.casefold()
        words = re.findall(r"\b\w+\b", stripped)
        if len(words) < 15 or len(words) > 120:
            return False
        if not re.search(r"[.!?][\"')\]]?$", stripped):
            return False
        if stripped.startswith(("#", "![", "|", "-", "*", ">")):
            return False
        return bool(set(re.findall(r"[a-z]{3,}", lowered)) & topic_terms)

    prose_candidates = [
        (index, sum(w in topic_terms for w in re.findall(r"[a-z]{3,}", paragraph.casefold())))
        for index, paragraph in enumerate(paragraphs)
        if suitable_prose(paragraph)
    ]
    if not prose_candidates:
        return body

    random.shuffle(prose_candidates)
    prose_candidates.sort(key=lambda item: item[1], reverse=True)
    sentence_order = random.sample(reference_sentences, len(reference_sentences))

    sentence_index = 0
    used_indices = []
    for paragraph_index, _ in prose_candidates:
        if sentence_index >= len(sentence_order):
            break
        if paragraph_index in used_indices:
            continue
        candidate = sentence_order[sentence_index]
        proposed = "\n\n".join(
            paragraphs[:paragraph_index]
            + [paragraphs[paragraph_index].rstrip() + " " + candidate]
            + paragraphs[paragraph_index + 1:]
        )
        proposed_density = keyword_density(proposed, keyword)
        if proposed_density <= 10.0:
            paragraphs[paragraph_index] = paragraphs[paragraph_index].rstrip() + " " + candidate
            used_indices.append(paragraph_index)
            sentence_index += 1
            if proposed_density >= target_per_1000:
                break

    return "\n\n".join(paragraphs)


def keyword_density(text, keyword):
    word_count = len(text.split())
    keyword_count = text.lower().count(keyword.lower())
    return (keyword_count / word_count) * 1000 if word_count else 0


def enforce_secondary_keywords(body, secondary_keywords):
    paragraphs = body.split("\n\n")
    for item in secondary_keywords:
        keyword = item["keyword"]
        target_count = item["count"]
        current_count = body.lower().count(keyword.lower())
        needed = max(0, target_count - current_count)
        if not needed:
            continue

        for index, paragraph in enumerate(paragraphs):
            if needed <= 0:
                break
            words = paragraph.split()
            if len(words) < 15 or paragraph.lstrip().startswith(("#", "![", "- ", "* ", "> ", "|")):
                continue
            sentence = f"This integration also makes {keyword} straightforward to evaluate during regular counter audits."
            paragraphs[index] = paragraph.rstrip() + " " + sentence
            needed -= 1

        body = "\n\n".join(paragraphs)

    return body


# ============================================================================
# PERSUASIVE & BALANCED TITLE GENERATION
# ============================================================================

def parse_primary_keywords(raw_keyword):
    parts = re.split(r"[,;|\n]+", raw_keyword or "")
    cleaned = []
    seen = set()
    for part in parts:
        phrase = re.sub(r"\s+", " ", part).strip()
        if not phrase:
            continue
        key = phrase.casefold()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(phrase)
    return cleaned or [re.sub(r"\s+", " ", (raw_keyword or "")).strip()]


def normalize_for_match(text):
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", (text or "").casefold())).strip()


def title_contains_phrase(title, phrase):
    normalized_title = normalize_for_match(title)
    normalized_phrase = normalize_for_match(phrase)
    return bool(normalized_phrase) and f" {normalized_phrase} " in f" {normalized_title} "


def limit_words(text, max_words=12):
    words = re.findall(r"\S+", (text or "").strip())
    if len(words) <= max_words:
        return text.strip()
    return " ".join(words[:max_words]).rstrip(" |.-,:")


def ensure_title_has_keywords(title, primary_keywords):
    fixed = re.sub(r"\s+", " ", (title or "").strip())
    if not fixed:
        fixed = primary_keywords[0]
    # Phrases longer than 6 words are treated as a free-form heading/angle rather
    # than an SEO keyword, so they're only used as creative inspiration in the
    # prompt and never force-appended verbatim onto every title.
    missing = [
        kw for kw in primary_keywords
        if kw and len(kw.split()) <= 6 and not title_contains_phrase(fixed, kw)
    ]
    if missing:
        suffix = " | ".join(missing)
        fixed = f"{fixed} | {suffix}"
    return limit_words(fixed, max_words=12)


def title_has_power_word(title):
    lowered = f" {title.casefold()} "
    return any(f" {word.casefold()} " in lowered for word in POWER_WORDS)


def remove_power_words(text):
    cleaned = text
    for word in POWER_WORDS:
        cleaned = re.sub(rf"\b{re.escape(word)}\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" |:-.,")
    return limit_words(cleaned, max_words=12)


def find_phrase_start(text, phrase):
    phrase = (phrase or "").strip()
    if not phrase:
        return None
    pattern = re.compile(r"\s+".join(re.escape(word) for word in phrase.split()), re.IGNORECASE)
    match = pattern.search(text)
    return match.start() if match else None


def add_power_word(title, primary_keywords, word):
    for kw in primary_keywords:
        idx = find_phrase_start(title, kw)
        if idx is not None:
            before = title[:idx].rstrip()
            after = title[idx:]
            glue = f"{before} " if before else ""
            res = re.sub(r"\s+", " ", f"{glue}{word} {after}").strip()
            return limit_words(res, max_words=12)
    res = re.sub(r"\s+", " ", f"{word} {title}").strip()
    return limit_words(res, max_words=12)


def normalize_meta_description(meta, primary_keywords):
    cleaned = re.sub(r"\s+", " ", (meta or "").strip())
    if not cleaned:
        cleaned = f"Compare features, pricing, and key integrations for {primary_keywords[0]} in Pakistan. Practical guide for store owners."
    if len(cleaned) > 160:
        cleaned = cleaned[:157].rsplit(" ", 1)[0] + "..."
    return cleaned


def enforce_title_rules(options, primary_keywords, include_power_words):
    normalized = []
    for option in options:
        title = ensure_title_has_keywords(option.get("title", ""), primary_keywords)
        meta_description = normalize_meta_description(option.get("meta_description", ""), primary_keywords)
        normalized.append({"title": title, "meta_description": meta_description})

    target_power_count = 3 if include_power_words else 0
    power_indices = [idx for idx, item in enumerate(normalized) if title_has_power_word(item["title"])]

    if len(power_indices) > target_power_count:
        for idx in power_indices[target_power_count:]:
            normalized[idx]["title"] = remove_power_words(normalized[idx]["title"])

    power_indices = [idx for idx, item in enumerate(normalized) if title_has_power_word(item["title"])]
    if len(power_indices) < target_power_count:
        needed = target_power_count - len(power_indices)
        word_cycle = list(POWER_WORDS)
        random.shuffle(word_cycle)
        for idx, item in enumerate(normalized):
            if needed <= 0:
                break
            if idx in power_indices:
                continue
            word = word_cycle[needed % len(word_cycle)]
            item["title"] = add_power_word(item["title"], primary_keywords, word)
            needed -= 1

    for item in normalized:
        item["title"] = ensure_title_has_keywords(item["title"], primary_keywords)
        item["meta_description"] = normalize_meta_description(item["meta_description"], primary_keywords)

    return normalized


def build_title_prompt(chosen_keyword, primary_keywords, include_power_words):
    keyword_list = "\n".join(f"- {kw}" for kw in primary_keywords)
    power_word_catalog = "Best, Top, Easy, Simple, Proven, Smart, Quick, Complete, Fast, Modern, Powerful, Ultimate, Essential, Efficient, Affordable, Reliable, Advanced, Effortless, Instant, Seamless"

    power_rule = (
        f"""POWER WORDS (EXACTLY 3 OF THE 6 TITLES):
- Exactly THREE titles must feature ONE natural power word from: {power_word_catalog}.
- The remaining THREE titles MUST NOT contain any of those power words."""
        if include_power_words
        else f"""Do not include any power or hype words in any of the six titles (avoid: {power_word_catalog})."""
    )

    return f"""You are a High-Converting B2B & Retail Headline Specialist for ExampleBrand in Pakistan[cite: 1].

PRIMARY SEARCH QUERY:
"{chosen_keyword}"

CURRENT YEAR: 2026.

MANDATORY PRIMARY KEYWORDS (MUST APPEAR NATURALLY IN EVERY TITLE):
{keyword_list}

==================================================
HEADLINE CRITERIA (PERSUASIVE, COMMERCIAL & INFORMATIONAL):
==================================================
Generate exactly 6 distinct, eye-catching, and highly persuasive titles.

1. INTENT SPLIT (3 COMMERCIAL + 3 INFORMATIONAL):
   - Titles 1-3 MUST be COMMERCIAL / BUYER-FOCUSED (choosing, comparisons, pricing, reviews, top systems):
     Examples:
     * "Best POS System in Pakistan 2026 | Top 7 Compared"
     * "Free POS Software. Point of Sale System. Loyverse POS"
     * "Top POS Software in Lahore | Pricing & Features"
   - Titles 4-6 MUST be INFORMATIONAL / PROBLEM-SOLVING (how-to, setup, avoiding errors, tax integration, daily workflows):
     Examples:
     * "FBR Digital Invoicing System | Upload, Validate & Report"
     * "How to Setup Pharmacy POS Software | Practical Guide"
     * "Common Retail Billing Mistakes and How to Avoid Them"

2. STRICT LENGTH: Under 12 words per title (concise, punchy).
3. FORMAT: Use separators like '|', '.', or '—' to make headlines scannable.
4. LANGUAGE: Simple, clear English understood immediately by retail managers in Pakistan.
5. {power_rule}
6. META DESCRIPTION: Write a natural meta description (120 to 155 characters) for each title highlighting business benefits.

==================================================
OUTPUT FORMAT
==================================================
Output exactly 6 numbered lines. No introductory chatter or bullet formatting:
1. Title || Meta description
2. Title || Meta description
3. Title || Meta description
4. Title || Meta description
5. Title || Meta description
6. Title || Meta description"""


def get_fallback_title_options(primary_keywords, include_power_words):
    joined = " | ".join(primary_keywords)
    options = [
        {
            "title": f"Best {joined} in Pakistan | Top Reviewed",
            "meta_description": f"Compare top features, pricing, and integrations for {primary_keywords[0]} in Pakistan. Find the perfect system for your counter."
        },
        {
            "title": f"{joined} Software | Pricing and Features 2026",
            "meta_description": f"Explore affordable pricing, barcode scanning, and multi-branch tools for {primary_keywords[0]}. Boost counter productivity today."
        },
        {
            "title": f"Top {joined} for Retail Stores Compared",
            "meta_description": f"See how {primary_keywords[0]} compares against traditional khata. Choose the easiest system for your cash counter."
        },
        {
            "title": f"{joined} | Setup, Invoicing and Reports",
            "meta_description": f"Complete guide to managing {primary_keywords[0]}. Discover step-by-step setup, digital invoicing, and inventory control."
        },
        {
            "title": f"Common {joined} Mistakes and How to Fix",
            "meta_description": f"Avoid costly cash drawer leaks and stockout errors. Practical operational tips for {primary_keywords[0]} users."
        },
        {
            "title": f"How to Automate {joined} | Practical Guide",
            "meta_description": f"Streamline daily billing and tax filings with {primary_keywords[0]}. Save counter staff hours every single week."
        },
    ]
    return enforce_title_rules(options, primary_keywords, include_power_words)


def extract_title_meta_options(raw_text, primary_keywords, include_power_words):
    options = []

    for line in raw_text.splitlines():
        line = line.strip()
        if not line or not re.match(r"^\s*\d+\s*[.)]\s+", line):
            continue

        cleaned = re.sub(r"^\s*\d+\s*[.)]\s*", "", line).strip().strip('"\'`*#')
        if not cleaned:
            continue

        title = cleaned
        meta_description = ""
        if "||" in cleaned:
            left, right = cleaned.split("||", 1)
            title = left.strip()
            meta_description = re.sub(r"^(meta|description)\s*[:\-]\s*", "", right.strip(), flags=re.IGNORECASE)
        elif " - " in cleaned:
            left, right = cleaned.rsplit(" - ", 1)
            title = left.strip()
            meta_description = right.strip()

        title = limit_words(title, max_words=12)

        if len(title.split()) < 3 or not re.search(r"[A-Za-z]", title):
            continue

        if title.lower() in {item["title"].lower() for item in options}:
            continue

        options.append({"title": title, "meta_description": meta_description})

    fallback_options = get_fallback_title_options(primary_keywords, include_power_words)
    for option in fallback_options:
        if len(options) >= 6:
            break
        if option["title"].lower() not in {item["title"].lower() for item in options}:
            options.append(option)

    return enforce_title_rules(options[:6], primary_keywords, include_power_words)


def extract_ai_title_candidates(raw_text):
    candidates = []
    noise_patterns = [
        r"^option\s*#?\d+",
        r"^click\s+to\s+lock",
        r"^h1",
        r"^meta\s+title",
        r"^angle\s*\d+",
    ]

    for line in raw_text.splitlines():
        line = line.strip()
        if not line or any(re.search(pat, line, re.IGNORECASE) for pat in noise_patterns):
            continue

        if not re.match(r"^\s*(?:\d+\s*[.)]|[-*])\s+", line):
            continue

        cleaned = re.sub(r"^\s*(?:\d+\s*[.)]|[-*])\s*", "", line).strip().strip('"\'`*#')
        if "||" in cleaned:
            cleaned = cleaned.split("||")[0].strip()

        cleaned = limit_words(cleaned, max_words=12)

        if len(cleaned.split()) < 3 or not re.search(r"[A-Za-z]", cleaned):
            continue

        if cleaned.lower() in {title.lower() for title in candidates}:
            continue

        candidates.append(cleaned)

    return candidates


def _locate_title_end(text, title):
    if not title:
        return None
    lower_text = text.casefold()
    lower_title = title.casefold()

    idx = lower_text.find(lower_title)
    if idx >= 0:
        return idx + len(title)

    matcher = difflib.SequenceMatcher(None, lower_text, lower_title)
    match = matcher.find_longest_match(0, len(lower_text), 0, len(lower_title))
    if match.size >= len(lower_title) * 0.6:
        return match.a + match.size

    return None


def _split_heading_from_intro(heading_text, title):
    split_at = _locate_title_end(heading_text, title)

    if split_at is None:
        sentence_end = re.search(r"[.!?](?:\s+|$)", heading_text)
        if sentence_end and sentence_end.start() < 160:
            split_at = sentence_end.end()

    if split_at is None or split_at >= len(heading_text):
        return heading_text.strip(), ""

    final_title = (title or heading_text[:split_at]).strip(" :-")
    introduction = heading_text[split_at:].strip(" :-")

    sentence_match = re.match(r"(.+?[.!?])(?:\s+|$)(.*)", introduction)
    if sentence_match:
        introduction = "\n\n".join(part for part in sentence_match.groups() if part.strip())

    return final_title, introduction


def ensure_h1_title(body, chosen_title=None):
    body = body.strip()
    if not body:
        return body

    first_line, _, remaining = body.partition("\n")
    first_line = first_line.strip()
    title = chosen_title.strip() if chosen_title else ""

    heading_match = re.match(r"^#{1,6}\s+(.+)$", first_line)
    heading_text = heading_match.group(1).strip() if heading_match else first_line

    final_title, introduction = _split_heading_from_intro(heading_text, title)

    if remaining.strip():
        introduction = "\n\n".join(part for part in (introduction, remaining.strip()) if part)

    return f"# {final_title}\n\n{introduction}" if introduction else f"# {final_title}"


def build_prompt(chosen_keyword, chosen_title=None, blog_purpose="", audience_questions="", blog_tone="professional", secondary_keywords=None):
    internal_link = keyword_links.get(chosen_keyword, "https://example.com/pricing-plan/")
    extra_links = get_extra_internal_link_pool(chosen_keyword)
    extra_links_text = "\n".join(f"- {url}" for url in extra_links) if extra_links else "(none available)"

    ext_targets = get_external_links_for_keyword(chosen_keyword)
    ext_links_text = "\n".join(f"- {label}: {url}" for url, label in ext_targets)

    if chosen_title:
        title_instruction = f'Use this EXACT text as the H1 title: "{chosen_title}"'
    else:
        title_instruction = f'H1 title naming "{chosen_keyword}"'

    purpose_context = blog_purpose.strip() or "Create a practical, comprehensive guide for store managers and retail pharmacy owners."
    questions_context = audience_questions.strip() or "Address inventory leakage, stockout avoidance, batch expiry tracking, and billing operations."

    tone_instructions = {
        "professional": "Use a professional, authoritative, and direct tone. Open directly with the operational problem.",
        "conversational": "Use a conversational and approachable tone while maintaining technical rigor.",
        "informal": "Use a relaxed, friendly tone with simple language and relatable retail examples.",
    }
    tone_context = tone_instructions.get(blog_tone, tone_instructions["professional"])
    secondary_keywords = secondary_keywords or []
    secondary_context = ""
    if secondary_keywords:
        secondary_lines = "\n".join(
            f'- Use the secondary keyword "{item["keyword"]}" exactly {item["count"]} time(s) in natural, relevant body prose.'
            for item in secondary_keywords
        )
        secondary_context = f"\nSECONDARY KEYWORD RULES:\n{secondary_lines}\nDo not force secondary keywords into headings or metadata.\n"

    primary_keyword_context = f"""
PRIMARY KEYWORD USAGE RULES:
- Treat "{chosen_keyword}" as a descriptive phrase, not a proper product name. Never write
  constructions that imply it is a title, such as "X Is the {chosen_keyword}".
- Every time "{chosen_keyword}" appears, the surrounding sentence or heading must remain
  grammatically complete and make sense on its own (correct subject, verb, and articles like "a"/"the").
- Vary the surrounding phrasing between occurrences (e.g. "a {chosen_keyword}", "the right
  {chosen_keyword}", "this {chosen_keyword}") instead of repeating the identical sentence pattern,
  while keeping the required keyword density.
"""

    return f"""You are a Senior SEO Content Writer for ExampleBrand, a Pakistani business management, POS, ERP, inventory, billing and digital invoicing platform[cite: 1].

CURRENT YEAR: 2026.

Write ONE complete, publish-ready blog article about "{chosen_keyword}".

BLOG PURPOSE:
{purpose_context}

WRITING TONE:
{tone_context}

EDITORIAL DIRECTION:
{questions_context}
{secondary_context}
{primary_keyword_context}

The article MUST be at least {MIN_WORD_COUNT} words in the body content.

==================================================
CRITICAL NATURAL LINKING INSTRUCTIONS:
==================================================
Never create a disconnected "Related Resources" or "Links" list. Weave hyperlinks directly into natural body sentences:
- Pricing & Features: [ExampleBrand pricing and features]({internal_link})
- Demo Booking: [book a free ExampleBrand demo]({CONTACT_URL})
- Other internal resources:
{extra_links_text}
- External official references:
{ext_links_text}

FORMAT REQUIREMENTS:
Line 1: META_TITLE: <60 characters max, includes "{chosen_keyword}">
Line 2: META_DESCRIPTION: <160 characters max, includes "{chosen_keyword}">

Then a blank line, followed by:
# Title
Follow: {title_instruction}

FAQ REQUIREMENT:
- Near the end of the article, before the conclusion, include a "## Frequently Asked Questions"
  section with 4-6 real questions a buyer would ask about "{chosen_keyword}", each with a concise
  2-3 sentence answer in prose (not a table).

MEDIA RULES:
- Include 2-4 image markers ONLY in sections where a photo genuinely adds value (e.g. illustrating
  a physical process like scanning, counting stock, or reviewing a dashboard). Skip sections where
  an image would be filler.
- Each [IMAGE: ...] description MUST be unique and describe the SPECIFIC scene relevant to the
  section it appears in - never reuse the same wording twice, and never copy the example below
  verbatim. Example only (write your own for each marker): [IMAGE: retail pharmacist checking inventory stock at counter]
- Include 1 Mermaid flowchart: [DIAGRAM: flowchart LR; A[Received Order] --> B[Barcode POS Scan] --> C[Inventory Auto-Deduct]]
- Spread these markers out, immediately after a relevant section's first paragraph. Never place
  two or more markers back-to-back, and never stack them all at the end of the article.

Output only the finished article content."""


@app.route("/")
def home():
    local_files = set(os.listdir(BUNDLED_BLOGS_FOLDER) + os.listdir(BLOGS_FOLDER))
    repo_files = set(github_store.list_dir(DRAFTS_REPO_DIR))
    files = sorted(local_files | repo_files)
    file_meta = {entry["filename"]: entry for entry in _load_manifest() if entry.get("filename")}
    return render_template("index.html", files=files, keywords=all_keywords, file_meta=file_meta)


@app.route("/blog/<filename>")
def view_blog(filename):
    import markdown
    safe_filename = os.path.basename(filename)
    if safe_filename != filename:
        abort(404)

    runtime_filepath = os.path.join(BLOGS_FOLDER, safe_filename)
    bundled_filepath = os.path.join(BUNDLED_BLOGS_FOLDER, safe_filename)

    if os.path.exists(runtime_filepath):
        with open(runtime_filepath, "r", encoding="utf-8") as f:
            raw_text = f.read()
    elif os.path.isfile(bundled_filepath):
        with open(bundled_filepath, "r", encoding="utf-8") as f:
            raw_text = f.read()
    else:
        raw_text, _ = github_store.get_file(f"{DRAFTS_REPO_DIR}/{safe_filename}")
        if raw_text is None:
            abort(404)

    html_content = markdown.markdown(raw_text, extensions=["tables"])
    return render_template("blog.html", content=html_content)


def get_fallback_trend_data():
    return {
        "source": "unavailable",
        "searched_keyword": "",
        "timeframe": "1m",
        "interest_over_time": {"labels": [], "values": []},
        "region_data": [],
        "chart_labels": [],
        "chart_values": [],
        "region_scope": "Pakistan",
        "top_queries": [],
        "rising_queries": []
    }


def normalize_trends_keyword(keyword):
    return re.sub(r"\s+", " ", keyword).strip()


def _format_interest_over_time(interest, keyword):
    if interest is None or interest.empty or keyword not in interest.columns:
        return {"labels": [], "values": []}

    series = interest[keyword].fillna(0).astype(int)
    labels = [index.strftime("%b %d") for index in series.index]
    return {"labels": labels, "values": series.tolist()}


def _format_region_data(region_df, keyword, limit=30):
    if region_df is None or region_df.empty or keyword not in region_df.columns:
        return []
    series = region_df[keyword].fillna(0).astype(int)
    series = series[series > 0].sort_values(ascending=False).head(limit)
    return [{"region": str(region), "value": int(value)} for region, value in series.items()]


def is_related_query(query, keyword):
    keyword_terms = set(re.findall(r"[a-z0-9]+", keyword.casefold()))
    query_terms = set(re.findall(r"[a-z0-9]+", str(query).casefold()))
    meaningful_terms = {term for term in keyword_terms if len(term) >= 2}

    if meaningful_terms & query_terms:
        return True

    return any(
        len(keyword_term) >= 5
        and len(query_term) >= 5
        and (keyword_term.startswith(query_term) or query_term.startswith(keyword_term))
        for keyword_term in meaningful_terms
        for query_term in query_terms
    )


def _format_related_queries(query_df, keyword, limit=10):
    if query_df is None or query_df.empty:
        return []
    filtered = query_df[query_df["query"].map(lambda query: is_related_query(query, keyword))]
    return [
        {"query": str(row["query"]), "value": row["value"]}
        for _, row in filtered.head(limit).iterrows()
    ]


def _query_google_trends(pytrends, keyword, timeframe, geo):
    pytrends.geo = geo
    region_resolution = "REGION" if geo else "COUNTRY"
    try:
        pytrends.build_payload([keyword], timeframe=timeframe)
    except Exception as error:
        raise RuntimeError(f"Google Trends payload request failed: {error}") from error

    try:
        interest = _format_interest_over_time(pytrends.interest_over_time(), keyword)
    except Exception as error:
        raise RuntimeError(f"Google Trends interest request failed: {error}") from error

    try:
        region_df = pytrends.interest_by_region(resolution=region_resolution, inc_low_vol=True)
    except Exception as error:
        app.logger.warning("Google Trends interest-by-region request failed for %r: %s", keyword, error)
        region_df = None

    region_data = _format_region_data(region_df, keyword)

    top_queries = []
    rising_queries = []
    try:
        related = pytrends.related_queries() or {}
        query_data = next(
            (value for key, value in related.items() if key.casefold() == keyword.casefold()),
            {},
        ) or {}
        top_queries = _format_related_queries(query_data.get("top"), keyword)
        rising_queries = _format_related_queries(query_data.get("rising"), keyword)
    except Exception as error:
        app.logger.warning("Google Trends related-queries request failed for %r: %s", keyword, error)

    return {
        "interest_over_time": interest,
        "region_data": region_data,
        "top_queries": top_queries,
        "rising_queries": rising_queries,
    }


_TRENDS_CACHE = {}
_TRENDS_CACHE_TTL_SECONDS = 600
_TRENDS_NO_DATA_TTL_SECONDS = 300
_TRENDS_RATE_LIMIT_TTL_SECONDS = 300

_TRENDS_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edg/130.0.0.0 Safari/537.36",
]


def fetch_trends_data(searched_keyword, timeframe):
    cache_key = (searched_keyword.casefold(), timeframe)
    cached = _TRENDS_CACHE.get(cache_key)
    if cached and time.time() - cached["timestamp"] < cached["ttl"]:
        if cached.get("error"):
            raise cached["error"]
        return cached["data"]

    proxy_values = [
        value.strip()
        for value in os.getenv("GOOGLE_TRENDS_PROXIES", "").split(",")
        if value.strip()
    ]

    last_error = None
    attempts = 3
    for attempt in range(attempts):
        if attempt:
            time.sleep((attempt * 3) + random.uniform(0.5, 2.0))

        trends_options = {
            "hl": "en-US",
            "tz": 300,
            "geo": "",
            "retries": 0,
            "backoff_factor": 0,
            "timeout": (10, 60),
            "requests_args": {
                "headers": {"User-Agent": random.choice(_TRENDS_USER_AGENTS)}
            },
        }
        if proxy_values:
            trends_options["proxies"] = proxy_values

        pytrends = TrendReq(**trends_options)

        try:
            trends_data = _query_google_trends(pytrends, searched_keyword, timeframe, "PK")
            interest_over_time = trends_data["interest_over_time"]
            region_data = trends_data["region_data"]
            chart_labels = interest_over_time["labels"]
            chart_values = interest_over_time["values"]
            top_queries = trends_data["top_queries"]
            rising_queries = trends_data["rising_queries"]

            result = {
                "interest_over_time": interest_over_time,
                "chart_labels": chart_labels,
                "chart_values": chart_values,
                "region_data": region_data,
                "region_scope": "Pakistan",
                "top_queries": top_queries,
                "rising_queries": rising_queries,
            }
            has_data = bool(chart_values or region_data or top_queries or rising_queries)
            _TRENDS_CACHE[cache_key] = {
                "timestamp": time.time(),
                "ttl": _TRENDS_CACHE_TTL_SECONDS if has_data else _TRENDS_NO_DATA_TTL_SECONDS,
                "data": result,
                "error": None,
            }
            return result
        except Exception as error:
            last_error = error
            if "429" in str(error):
                break

    _TRENDS_CACHE[cache_key] = {
        "timestamp": time.time(),
        "ttl": _TRENDS_RATE_LIMIT_TTL_SECONDS,
        "data": None,
        "error": last_error,
    }
    raise last_error


@app.route("/api/trends")
def api_trends():
    keyword = request.args.get("keyword", "")
    searched_keyword = normalize_trends_keyword(keyword)
    if not searched_keyword:
        return jsonify({"error": "Please enter a search term."}), 400

    timeframe_options = {
        "7d": "now 7-d",
        "1m": "today 1-m",
        "12m": "today 12-m",
    }
    timeframe_key = request.args.get("timeframe", "1m")
    timeframe = timeframe_options.get(timeframe_key)
    if timeframe is None:
        return jsonify({"error": "Invalid timeframe. Use 7d, 1m, or 12m."}), 400

    try:
        data = fetch_trends_data(searched_keyword, timeframe)
        region_data = data["region_data"]
        top_queries = data["top_queries"]
        rising_queries = data["rising_queries"]

        has_data = bool(data["chart_values"] or region_data or top_queries or rising_queries)
        if not has_data:
            fallback = get_fallback_trend_data()
            fallback["searched_keyword"] = searched_keyword
            fallback["timeframe"] = timeframe_key
            return jsonify(fallback)

        return jsonify({
            "source": "live",
            "searched_keyword": searched_keyword,
            "timeframe": timeframe_key,
            "interest_over_time": data["interest_over_time"],
            "region_data": region_data,
            "chart_labels": data["chart_labels"],
            "chart_values": data["chart_values"],
            "region_scope": data["region_scope"],
            "top_queries": top_queries,
            "rising_queries": rising_queries,
        })
    except Exception as error:
        app.logger.warning("Google Trends request failed for %r: %s", searched_keyword, error)
        fallback = get_fallback_trend_data()
        fallback["searched_keyword"] = searched_keyword
        fallback["source"] = "rate-limited" if "429" in str(error) else "unavailable"
        response = jsonify(fallback)
        if fallback["source"] == "rate-limited":
            response.status_code = 429
            response.headers["Retry-After"] = str(_TRENDS_RATE_LIMIT_TTL_SECONDS)
        return response


@app.route("/api/titles/<path:keyword>")
def api_titles(keyword):
    keyword = unquote_plus(keyword or "").strip()
    if not keyword:
        return jsonify({"error": "Please enter a keyword first."}), 400

    power_words_mode = request.args.get("power_words", "no").strip().lower()
    include_power_words = power_words_mode in {"yes", "true", "1", "on"}
    primary_keywords = parse_primary_keywords(keyword)

    try:
        prompt = build_title_prompt(keyword, primary_keywords, include_power_words)
        raw_text = generate_title_text(prompt, max_tokens=1200)

        ai_titles = extract_ai_title_candidates(raw_text)
        title_options = extract_title_meta_options(raw_text, primary_keywords, include_power_words)
        titles = [item["title"] for item in title_options]

        return jsonify({
            "keyword": keyword,
            "titles": titles,
            "title_options": title_options,
            "power_words_enabled": include_power_words,
            "source": "ai" if ai_titles else "fallback",
            "notice": None if ai_titles else "The AI returned no usable title lines, so relevant local titles were supplied.",
        })

    except Exception as e:
        app.logger.exception("AI title request failed")
        fallback_options = get_fallback_title_options(primary_keywords, include_power_words)
        return jsonify({
            "keyword": keyword,
            "titles": [item["title"] for item in fallback_options],
            "title_options": fallback_options,
            "power_words_enabled": include_power_words,
            "source": "fallback",
            "notice": "AI title generation failed, so relevant local title ideas were supplied.",
        })


@app.route("/api/generate/<path:keyword>")
def api_generate(keyword):
    keyword = unquote_plus(request.args.get("primary_keyword", keyword) or "").strip()
    chosen_title = request.args.get("title")
    blog_purpose = request.args.get("purpose", "")
    audience_questions = request.args.get("questions", "")
    blog_tone = request.args.get("tone", "professional")
    try:
        secondary_keywords = json.loads(request.args.get("secondary_keywords", "[]"))
    except json.JSONDecodeError:
        secondary_keywords = []
    normalized_secondary_keywords = []
    for item in secondary_keywords:
        if not isinstance(item, dict) or not str(item.get("keyword", "")).strip():
            continue
        try:
            count = int(item.get("count", 1))
        except (TypeError, ValueError):
            count = 1
        normalized_secondary_keywords.append({
            "keyword": str(item["keyword"]).strip(),
            "count": max(1, min(5, count)),
        })
    secondary_keywords = normalized_secondary_keywords

    if os.path.exists(LAST_GEN_FILE):
        with open(LAST_GEN_FILE, "r") as f:
            last_time = float(f.read())
    else:
        last_time = 0

    seconds_since = time.time() - last_time
    if seconds_since < COOLDOWN_SECONDS:
        wait_left = int(COOLDOWN_SECONDS - seconds_since)
        return jsonify({"error": f"Please wait {wait_left} more seconds before generating another blog."}), 429

    try:
        prompt = build_prompt(keyword, chosen_title, blog_purpose, audience_questions, blog_tone, secondary_keywords)
        raw_text = ""

        for attempt in range(3):
            raw_text = generate_ai_text(prompt, max_tokens=4000)
            body_preview = re.sub(r"META_TITLE:.*\n?", "", raw_text)
            body_preview = re.sub(r"META_DESCRIPTION:.*\n?", "", body_preview).strip()
            body_preview = clean_keyword_artifacts(body_preview, keyword)
            preview_word_count = len(body_preview.split())
            preview_density = keyword_density(body_preview, keyword)

            if preview_word_count >= MIN_WORD_COUNT and 8.0 <= preview_density <= 10.0:
                break

            feedback = []
            if preview_word_count < MIN_WORD_COUNT:
                feedback.append(
                    f"The previous attempt was only about {preview_word_count} words. Expand every section to reach at least {MIN_WORD_COUNT} words."
                )
            if preview_density < 8.0:
                feedback.append(
                    f"Add relevant references to {keyword} until natural rate is 8-10 per 1,000 words."
                )
            elif preview_density > 10.0:
                feedback.append(
                    f"Replace unnecessary repetitions with natural synonyms until rate is 8-10 per 1,000 words."
                )
            prompt += "\n\nRevise the complete article based on this quality feedback:\n- " + "\n- ".join(feedback)

        meta_title_match = re.search(r"META_TITLE:\s*(.*)", raw_text)
        meta_desc_match = re.search(r"META_DESCRIPTION:\s*(.*)", raw_text)
        meta_title = meta_title_match.group(1).strip() if meta_title_match else (chosen_title or keyword)
        meta_description = meta_desc_match.group(1).strip() if meta_desc_match else ""

        body = re.sub(r"META_TITLE:.*\n?", "", raw_text)
        body = re.sub(r"META_DESCRIPTION:.*\n?", "", body).strip()

        # Structural, typographical, and natural linking passes
        body = ensure_h1_title(body, chosen_title)
        body = fix_keyword_typos(body, keyword)
        body = collapse_duplicate_words(body)

        internal_link = keyword_links.get(keyword, "https://example.com/pricing-plan/")
        body = weave_natural_links(body, keyword, internal_link)
        body = clean_keyword_artifacts(body, keyword)

        body = distribute_media_markers(body)
        body, photo_count, diagram_count = replace_image_markers(body, primary_keyword=keyword)
        body = ensure_h1_title(body, chosen_title)
        body = enforce_keyword_density(body, keyword)
        body = enforce_secondary_keywords(body, secondary_keywords)
        body = clean_keyword_artifacts(body, keyword)

        word_count = len(body.split())
        keyword_count = body.lower().count(keyword.lower())
        rate_per_1000 = round((keyword_count / word_count) * 1000, 1) if word_count else 0

        safe_filename = create_unique_blog_filename(keyword, chosen_title or meta_title)
        filepath = os.path.join(BLOGS_FOLDER, safe_filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(body)

        try:
            github_store.save_file(
                f"{DRAFTS_REPO_DIR}/{safe_filename}",
                body,
                message=f"Generate draft: {keyword}",
            )
            _upsert_manifest_entry({
                "filename": safe_filename,
                "keyword": keyword,
                "wordCount": word_count,
                "createdAt": time.strftime("%b %d, %Y \u00b7 %H:%M UTC", time.gmtime()),
                "preview": (body[:180] + "\u2026") if len(body) > 180 else body,
            })
        except Exception:
            app.logger.exception("Failed to save draft to GitHub datastore repo")

        with open(LAST_GEN_FILE, "w") as f:
            f.write(str(time.time()))

        return jsonify({
            "keyword": keyword,
            "meta_title": meta_title,
            "meta_description": meta_description,
            "content": body,
            "word_count": word_count,
            "keyword_count": keyword_count,
            "secondary_keyword_counts": {
                item["keyword"]: body.lower().count(item["keyword"].lower())
                for item in secondary_keywords
            },
            "rate_per_1000": rate_per_1000,
            "photo_count": photo_count,
            "diagram_count": diagram_count,
            "filename": safe_filename,
        })

    except Exception as e:
        error_text = str(e)
        if "rate_limit" in error_text.lower() or "429" in error_text:
            return jsonify({"error": "Daily/rate limit reached on the AI service. Wait a bit and try again, or check your Groq dashboard for reset time."}), 429
        return jsonify({"error": error_text}), 500


if __name__ == "__main__":
    app.run(debug=True)
