from flask import Flask, abort, render_template, jsonify, request
from dotenv import dotenv_values, load_dotenv
from datetime import date
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

DRAFTS_REPO_DIR = "drafts"  # folder inside the GitHub datastore repo

# Key resolution order: GitHub settings.json (editable without a redeploy,
# and doesn't depend on Vercel's env vars actually being picked up) -> real
# env var -> local .env file. This fixes the "Vercel isn't picking up
# GROQ_API_KEY/PEXELS_API_KEY" issue: as long as GITHUB_REPO/GITHUB_TOKEN 
# are set, the actual API keys can live in the repo's settings.json instead
# and are re-read on every cold start.
_repo_settings = github_store.load_settings()
gemini_key = os.getenv("GEMINI_API_KEY") or dotenv_settings.get("GEMINI_API_KEY")
groq_key = _repo_settings.get("groqApiKey") or os.getenv("GROQ_API_KEY") or dotenv_settings.get("GROQ_API_KEY")
qwen_key = os.getenv("QWEN_API_KEY") or dotenv_settings.get("QWEN_API_KEY")
pexels_key = _repo_settings.get("pexelsApiKey") or os.getenv("PEXELS_API_KEY") or dotenv_settings.get("PEXELS_API_KEY")
gemini_client = genai.Client(api_key=gemini_key) if gemini_key else None
client = Groq(api_key=groq_key)
qwen_client = Groq(api_key=qwen_key) if qwen_key else None
GEMINI_MODEL = "gemini-2.5-flash"
GROQ_MODEL = "openai/gpt-oss-120b"
QWEN_TITLE_MODEL = "qwen/qwen3.8-27b"


def generate_ai_text(prompt, max_tokens):
    """Generate with Gemini first and use Groq only when Gemini is unavailable."""
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
            app.logger.exception("Qwen title request failed; falling back to the primary AI provider")

    return generate_ai_text(prompt, max_tokens)


def get_pexels_image(query):
    headers = {"Authorization": pexels_key}
    params = {"query": query, "per_page": 1, "orientation": "landscape"}
    response = requests.get("https://api.pexels.com/v1/search", headers=headers, params=params)
    data = response.json()
    if data.get("photos"):
        return data["photos"][0]["src"]["large"]
    return "https://via.placeholder.com/800x400?text=Image+not+found"


def get_mermaid_diagram(diagram_code):
    encoded = base64.urlsafe_b64encode(diagram_code.encode("utf-8")).decode("utf-8")
    return f"https://mermaid.ink/img/{encoded}"


def extract_bracket_blocks(text, start_marker):
    """
    Finds every `[MARKER: ...]` block in text, correctly handling nested
    square brackets inside (needed for Mermaid diagram syntax like A[Label]).
    """
    blocks = []
    search_start = 0

    while True:
        start_idx = text.find(start_marker, search_start)
        if start_idx == -1:
            break

        depth = 0
        end_idx = None
        for i in range(start_idx, len(text)):
            if text[i] == '[':
                depth += 1
            elif text[i] == ']':
                depth -= 1
                if depth == 0:
                    end_idx = i
                    break

        if end_idx is None:
            break

        full_match = text[start_idx:end_idx + 1]
        inner_content = text[start_idx + len(start_marker):end_idx].strip()
        blocks.append((full_match, inner_content))
        search_start = end_idx + 1

    return blocks


def replace_image_markers(blog_text):
    image_blocks = extract_bracket_blocks(blog_text, "[IMAGE:")
    diagram_blocks = extract_bracket_blocks(blog_text, "[DIAGRAM:")

    for full_match, description in image_blocks:
        image_url = get_pexels_image(description)
        markdown_image = f"![{description}]({image_url})"
        blog_text = blog_text.replace(full_match, markdown_image, 1)

    for full_match, diagram_code in diagram_blocks:
        image_url = get_mermaid_diagram(diagram_code)
        markdown_image = f"![Process diagram]({image_url})"
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
    return re.findall(r"\[[^\]]+\]\((https?://[^\)]+)\)", text)


AUTHORITY_EXTERNAL_LINKS = {
    "FBR": "https://www.fbr.gov.pk/",
    "SRB": "https://srb.gos.pk/",
    "PRA": "https://pra.punjab.gov.pk/",
    "KPRA": "https://kpra.kp.gov.pk/",
}


def get_external_link_for_keyword(keyword):
    for authority, url in AUTHORITY_EXTERNAL_LINKS.items():
        if authority in keyword:
            return url, f"{authority} official website"
    return "https://en.wikipedia.org/wiki/Point_of_sale", "Point of sale (Wikipedia)"


def ensure_minimum_links(body, keyword, internal_link, min_internal=4, min_external=3):
    links = count_markdown_links(body)
    internal_count = sum(1 for url in links if "example.com" in url)
    external_count = len(links) - internal_count

    additions = []

    if internal_count < min_internal:
        needed = min_internal - internal_count
        pool = get_extra_internal_link_pool(keyword, limit=needed + 1)
        for url in pool:
            if url not in links and needed > 0:
                label = url.rstrip("/").split("/")[-1].replace("-", " ").title() or "ExampleBrand"
                additions.append(f"- [{label}]({url})")
                needed -= 1
        if internal_link not in links and needed > 0:
            additions.append(f"- [Related ExampleBrand resource]({internal_link})")
            needed -= 1
        if CONTACT_URL not in links and needed > 0:
            additions.append(f"- [Book a free demo]({CONTACT_URL})")

    if external_count < min_external:
        needed = min_external - external_count
        keyword_url, keyword_label = get_external_link_for_keyword(keyword)
        external_pool = [(keyword_url, keyword_label)]
        external_pool.extend(
            (url, f"{authority} official website")
            for authority, url in AUTHORITY_EXTERNAL_LINKS.items()
            if url != keyword_url
        )
        external_pool.append(
            ("https://en.wikipedia.org/wiki/Point_of_sale", "Point of sale (Wikipedia)")
        )

        for ext_url, ext_label in external_pool:
            existing_urls = links + [
                re.search(r"\((https?://[^)]+)\)", addition).group(1)
                for addition in additions
                if re.search(r"\((https?://[^)]+)\)", addition)
            ]
            if ext_url not in existing_urls and needed > 0:
                additions.append(f"- [{ext_label}]({ext_url})")
                needed -= 1

    if not additions:
        return body

    section = "\n\n## Related Resources\n\n" + "\n".join(additions) + "\n"
    conclusion_match = re.search(r"\n##\s*Conclusion", body, re.IGNORECASE)
    if conclusion_match:
        idx = conclusion_match.start()
        body = body[:idx] + section + body[idx:]
    else:
        body = body.rstrip() + section

    return body


def fix_keyword_typos(text, keyword):
    keyword_word_count = len(keyword.split())
    target_clean = re.sub(r"[^\w\s]", "", keyword).lower()

    word_spans = [(m.group(), m.start(), m.end()) for m in re.finditer(r"\S+", text)]

    fixed_text = text
    offset = 0
    i = 0

    while i <= len(word_spans) - keyword_word_count:
        window = word_spans[i:i + keyword_word_count]
        window_text = " ".join(w[0] for w in window)
        window_clean = re.sub(r"[^\w\s]", "", window_text).lower()

        similarity = difflib.SequenceMatcher(None, window_clean, target_clean).ratio()

        if 0.75 <= similarity < 1.0:
            start = window[0][1] + offset
            end = window[-1][2] + offset
            fixed_text = fixed_text[:start] + keyword + fixed_text[end:]
            offset += len(keyword) - (end - start)
            i += keyword_word_count
        else:
            i += 1

    return fixed_text


def collapse_duplicate_words(text):
    """Safety net: fixes accidental word-stuffing like 'Lahore Lahore' or 'the the'."""
    return re.sub(r"\b(\w+)(\s+\1\b)+", r"\1", text, flags=re.IGNORECASE)


def clean_keyword_artifacts(text, keyword):
    escaped_keyword = re.escape(keyword)
    duplicated_location = re.compile(
        rf"(?:\*\*)?{escaped_keyword}(?:\s+in\s+Pakistan)+(?:\*\*)?",
        re.IGNORECASE,
    )
    text = duplicated_location.sub(keyword, text)

    bold_keyword = re.compile(
        rf"\*{{2}}\s*{escaped_keyword}\s*\*{{2}}",
        re.IGNORECASE,
    )
    text = bold_keyword.sub(keyword, text)
    text = re.sub(rf"\*{{2}}\s*{escaped_keyword}", keyword, text, flags=re.IGNORECASE)

    repair_patterns = [
        (rf"(Choosing the right\s+{escaped_keyword})\s+the most direct way", r"\1 is the most direct way"),
        (rf"(purpose-built\s+{escaped_keyword})\s+the manual bottlenecks", r"\1 removes the manual bottlenecks"),
        (rf"(comprehensive\s+{escaped_keyword})\s+scales", r"\1 solution that scales"),
        (rf"(hallmark of effective\s+{escaped_keyword})\s+eliminates", r"\1 that eliminates"),
        (rf"(ensures that.*?generated by the\s+{escaped_keyword})\s+Manager reviewing", r"\1. Manager reviewing"),
        (rf"(ensures that the\s+{escaped_keyword})\s+its promised", r"\1 delivers its promised"),
        (rf"(selecting the right\s+{escaped_keyword})\s+committing", r"\1 requires evaluating before committing"),
        (rf"(Choosing the right\s+{escaped_keyword})\s+no longer", r"\1 is no longer"),
    ]
    for pattern, replacement in repair_patterns:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

    return text


def enforce_keyword_density(body, keyword, target_per_1000=8.0):
    current_density = keyword_density(body, keyword)
    if current_density >= target_per_1000:
        return body

    reference_sentences = [
        f"For a business managing more than one sales channel, {keyword} is most useful when it keeps product, order, and inventory records aligned.",
        f"When evaluating {keyword}, teams should look beyond the interface and confirm how it handles daily sales, stock changes, and reporting.",
        f"In practice, the value of {keyword} depends on whether staff can use it consistently during busy operating hours.",
        f"Before adopting {keyword}, document the current workflow so gaps in syncing, billing, and reconciliation are easy to identify.",
        f"A reliable {keyword} should reduce manual work without making returns, adjustments, or tax records harder to audit.",
        f"Businesses comparing {keyword} should test a realistic order-to-inventory workflow rather than relying only on a feature list.",
        f"The strongest case for {keyword} is a measurable improvement in how quickly teams move from a sale to an accurate stock update.",
        f"A practical review of {keyword} should include permissions, staff training, backups, and the support available after launch.",
        f"For growing retailers, {keyword} needs to remain dependable as product ranges, order volumes, and fulfilment locations increase.",
        f"The right {keyword} can make routine reconciliation easier by giving managers one consistent view of sales and stock activity.",
        f"Any decision about {keyword} should account for the work involved in importing products, matching SKUs, and validating the first transactions.",
        f"Teams get better results from {keyword} when they define ownership for catalogue changes, stock corrections, and exception handling.",
        f"A useful implementation plan for {keyword} starts with a small set of products and transactions that staff can verify end to end.",
        f"The day-to-day test for {keyword} is simple: a change made in one channel should reach the right records without avoidable manual copying.",
        f"When a business adopts {keyword}, clear rules for cancellations, refunds, and out-of-stock items prevent small exceptions from becoming data problems.",
        f"Managers assessing {keyword} should review not only features but also transaction history, export options, and the clarity of its reports.",
        f"A well-planned rollout of {keyword} gives staff time to practise common sales and correction workflows before the system handles full volume.",
        f"The practical benefit of {keyword} is strongest when it supports the existing team instead of forcing every process into an unfamiliar routine.",
        f"For finance and operations teams, {keyword} is easier to trust when adjustments leave a clear record of what changed and why.",
        f"The first review of {keyword} should focus on the routines staff perform every day, not only on features used once a month.",
        f"A sensible comparison of {keyword} includes the quality of its product search, barcode handling, order status updates, and exports.",
        f"Businesses get more value from {keyword} when the setup reflects their actual branches, sales channels, tax process, and fulfilment responsibilities.",
        f"The transition to {keyword} should include checks for duplicate products, inconsistent prices, and missing stock before live orders are enabled.",
        f"Good documentation makes {keyword} easier to maintain because staff know how to handle exceptions without creating a second unofficial process.",
        f"An effective {keyword} workflow connects customer service, inventory control, sales reporting, and invoice review instead of isolating each task.",
        f"The right controls around {keyword} help owners see which changes are routine, which need approval, and which require investigation.",
        f"A clear owner for each {keyword} workflow makes it easier to resolve mismatches before they affect customers or financial reports.",
        f"The onboarding effort for {keyword} is worthwhile when the team can explain what happens to a product, order, and payment at each step.",
        f"A dependable {keyword} setup should make everyday decisions faster while still leaving managers enough detail to investigate unusual activity.",
        f"Testing {keyword} with real product names, realistic quantities, and normal return cases reveals gaps that a simple demonstration may hide.",
        f"The best way to judge {keyword} is to compare the time and error rate of the old process with the same workflow after implementation.",
        f"Businesses should revisit their {keyword} process as they add channels or locations so small configuration gaps do not become recurring manual work.",
    ]

    paragraphs = body.split("\n\n")
    keyword_terms = {
        term.casefold() for term in re.findall(r"[A-Za-z]{3,}", keyword)
    }
    topic_terms = keyword_terms | {
        "pos", "sales", "retail", "store", "shop", "inventory", "stock",
        "order", "orders", "product", "products", "billing", "invoice",
        "ecommerce", "shopify", "woocommerce", "integration", "sync",
        "payment", "tax", "reporting", "customer", "branch", "channel",
    }

    def suitable_prose(paragraph):
        stripped = paragraph.strip()
        lowered = stripped.casefold()
        words = re.findall(r"\b\w+\b", stripped)
        if len(words) < 10 or len(words) > 500:
            return False
        if not re.search(r"[.!?][\"')\]]?$", stripped):
            return False
        if stripped.startswith(("#", "![", "|", "-", "*", ">")):
            return False
        if any(marker in stripped for marker in ("##", "![", "```", "|", "**")):
            return False
        if lowered.count(":") > 2:
            return False
        return bool(set(re.findall(r"[a-z]{3,}", lowered)) & topic_terms)

    prose_candidates = [
        (index, sum(lowered_word in topic_terms for lowered_word in re.findall(r"[a-z]{3,}", paragraph.casefold())))
        for index, paragraph in enumerate(paragraphs)
        if suitable_prose(paragraph)
    ]
    if not prose_candidates:
        return body

    # Let topic relevance choose the section; randomize ties so separate blogs
    # do not receive the same placement order.
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
            if len(words) < 10 or paragraph.lstrip().startswith(("#", "![", "- ", "* ", "> ", "|")):
                continue
            sentence = f"This also makes {keyword} easier to evaluate during the workflow."
            paragraphs[index] = paragraph.rstrip() + " " + sentence
            needed -= 1

        body = "\n\n".join(paragraphs)
        if needed > 0:
            fallback_sentences = " ".join(
                f"Businesses should also review {keyword} when planning this workflow."
                for _ in range(needed)
            )
            body = body.rstrip() + "\n\n" + fallback_sentences

    return body


def build_title_prompt(chosen_keyword):
    return f"""You are a Lead SEO Content Strategist and Senior Copywriter specializing in Pakistani commerce, B2B software, tax compliance, and retail ecosystems.

You write headlines for ExampleBrand (a Pakistani POS, ERP, invoicing, inventory, and tax compliance platform).

USER SEARCH QUERY:
"{chosen_keyword}"

CURRENT CONTEXT:
Reference year is 2026. Current date: {CURRENT_DATE}.

==================================================
PHASE 1: KNOWLEDGE & CONTEXT EXPANSION (CRUCIAL)
==================================================
Before generating headlines, internally decode the query's business, legal, and operational reality:

1. PAKISTANI REGULATORY & TAX ENTITIES:
   - "SRB" = Sindh Revenue Board (Sales tax on services, POS integration rules, restaurants, hotels, beauty parlors, IT services, provincial compliance in Sindh/Karachi).
   - "PRA" = Punjab Revenue Authority (Sales tax on services in Punjab/Lahore/Rawalpindi/Multan).
   - "BRA" = Balochistan Revenue Authority.
   - "KPRA" = Khyber Pakhtunkhwa Revenue Authority.
   - "FBR" = Federal Board of Revenue (Tier-1 retail POS integration, STRN, income tax, sales tax on goods across Pakistan).
   Recognize these abbreviations immediately and grasp the practical compliance, audit, invoicing, and penalty risks business owners face regarding them.

2. INDUSTRY & OPERATIONAL CONTEXT:
   - "Pharmacy / Medical Store" = Batch numbers, expiry tracking, formula search, distributor credit, fast OTC billing.
   - "Restaurant / Cafe" = KOT (Kitchen Order Tickets), table turnaround, recipe/ingredient costing, recipe waste, SRB/PRA integration.
   - "Supermarket / Grocery" = Barcode speed, high-volume checkout, bulk distributor purchase orders, dead inventory.
   - "Wholesaler / Distributor" = Ledger/Khata, bulk discounts, credit recovery, multi-warehouse stock.

==================================================
PHASE 2: COPYWRITING & HEADLINE STRATEGY
==================================================
Generate exactly 6 distinct, eye-catching, high-CTR blog headlines.

Write in natural, confident, and professional English that real Pakistani founders, shopkeepers, accountants, and executives will click.

DO NOT use identical sentence structures across your options. Use 6 completely different editorial angles:

1. The Compliance / Risk / Legal Angle:
   Focus on regulations, audit readiness, penalties, registration steps, or staying compliant (especially critical for SRB, PRA, FBR, tax queries).
2. The Bottom-Line / Financial Angle:
   Focus on margins, profit leaks, tax deductions, cash flow, preventing theft, or cost calculations.
3. The Buyer’s Checklist / Evaluation Angle:
   Focus on what to verify, ask, or inspect before buying software or choosing a system.
4. The Operational / Pain-Point Angle:
   Tackle daily operational friction (e.g., checkout bottlenecks, manual khata errors, stockout headaches, billing disputes).
5. The Modernization / Strategic Growth Angle:
   Moving away from obsolete paper/Excel methods, automating workflows, or scaling branches.
6. The Pragmatic Software / Solution Angle:
   A clean, practical showcase of how modern software (naturally weaving in ExampleBrand where relevant) solves this exact search need.

==================================================
STRICT EDITORIAL RULES
==================================================
- Preserve the exact intent: If the query is about "SRB", the articles must genuinely discuss Sindh Revenue Board issues (tax rates, POS integration, filing, software requirements, service tax rules).
- Retain specific locations: If Karachi, Rawalpindi, Lahore, or Sindh is in the search query, keep it. Do not invent cities if none are specified.
- Natural flow: Do not awkwardly force exact-match keywords if they break grammar. Write fluid English.
- Avoid clickbait fluff: No empty buzzwords ("Skyrocket your revenue", "Revolutionize your world"). Make the value proposition clear and grounded in Pakistani business realities.
- Target Length: 7 to 14 words per title.

==================================================
OUTPUT FORMAT
==================================================
Output ONLY the 6 titles as a numbered list. Do not include markdown bolding, intro chatter, quotation marks, or labels like "Option #" or "H1".

1. Title
2. Title
3. Title
4. Title
5. Title
6. Title"""


def get_fallback_titles(keyword):
    keyword = keyword.strip()
    return [
        f"A Practical Guide to {keyword} for Pakistani Business Owners",
        f"Key Requirements and Compliance Rules for {keyword}",
        f"Common Costly Mistakes Businesses Make with {keyword}",
        f"What to Check Before Setting Up {keyword}",
        f"How to Automate and Streamline {keyword} in 2026",
        f"Managing {keyword} Efficiently with ExampleBrand",
    ]


def extract_title_options(raw_text, keyword):
    candidates = extract_ai_title_candidates(raw_text)

    fallback_titles = get_fallback_titles(keyword)
    for title in fallback_titles:
        if len(candidates) >= 6:
            break
        if title.lower() not in {candidate.lower() for candidate in candidates}:
            candidates.append(title)

    return candidates[:6]


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
        if not line:
            continue

        if any(re.search(pat, line, re.IGNORECASE) for pat in noise_patterns):
            continue

        if not re.match(r"^\s*(?:\d+\s*[.)]|[-*])\s+", line):
            continue

        cleaned = re.sub(r"^\s*(?:\d+\s*[.)]|[-*])\s*", "", line).strip()
        cleaned = cleaned.strip('"\'`*#')

        if len(cleaned.split()) < 4 or not re.search(r"[A-Za-z]", cleaned):
            continue

        if cleaned.lower() in {title.lower() for title in candidates}:
            continue

        candidates.append(cleaned)

    return candidates


def _locate_title_end(text, title):
    """Return the index right after `title` inside `text`, tolerating minor
    wording differences from the model (punctuation, pluralization, etc.),
    or None if it can't be confidently located."""
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
    """Split a raw H1 line into (title, introduction) so a run-on line from
    the model - where the intro got glued onto the title with no break -
    never gets rendered as one giant heading."""
    split_at = _locate_title_end(heading_text, title)

    if split_at is None:
        # Title text couldn't be matched closely enough - fall back to the
        # first sentence boundary so at least something splits off as the
        # title instead of leaving the whole line as one heading.
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

    if chosen_title:
        title_instruction = f'Use this EXACT text as the H1 title (do not alter it): "{chosen_title}"'
    else:
        title_instruction = f'H1 title that names "{chosen_keyword}" plus a short descriptive subtitle after a colon (e.g. "X: Complete Guide to Y, Z & Compliance") - avoid generic "Best/Ultimate X" phrasing here'

    purpose_context = blog_purpose.strip() or "Create a practical, useful guide that satisfies the search intent behind the keyword."
    questions_context = audience_questions.strip() or "No extra reader questions were provided; infer the most useful questions from the keyword."
    tone_instructions = {
        "professional": "Use a professional, authoritative, and direct tone. Do not use fictional stories, personal anecdotes, dramatic scenes, or informal filler. Open with a concise statement of the real problem or decision the reader faces.",
        "conversational": "Use a conversational and approachable tone while staying accurate and useful. You may use relatable examples, but do not invent personal experiences, named people, or unsupported stories.",
        "informal": "Use a relaxed, friendly tone with simple language and relatable examples. Keep the advice credible and focused; do not add fictional personal stories or exaggerated claims.",
    }
    tone_context = tone_instructions.get(blog_tone, tone_instructions["professional"])
    secondary_keywords = secondary_keywords or []
    secondary_context = ""
    if secondary_keywords:
        secondary_lines = "\n".join(
            f'- Use the secondary keyword "{item["keyword"]}" exactly {item["count"]} time(s) in natural, relevant body prose.'
            for item in secondary_keywords
        )
        secondary_context = f"""

SECONDARY KEYWORD RULES:
{secondary_lines}
Do not put secondary keywords in headings, metadata, image markers, diagram code, or unrelated sentences. Do not repeat them back-to-back or force awkward wording."""

    return f"""You are an expert SEO content writer for ExampleBrand, a Pakistani business management, POS, ERP, inventory, billing and digital invoicing platform.

CURRENT DATE:
{CURRENT_DATE}

YEAR ACCURACY RULE:
Use 2026 for current-year references. Do not describe current laws, tax updates, software trends, or business conditions as being from 2024 or 2025. Mention an older year only when clearly discussing historical background and label it as historical. Never invent a dated tax reform or notice.

Write ONE complete, publish-ready blog article about "{chosen_keyword}". The article must feel original and specific to this keyword, not like a reusable template.

BLOG PURPOSE:
{purpose_context}

WRITING TONE:
{tone_context}

READER QUESTIONS AND EDITORIAL DIRECTION:
{questions_context}

OPENING RULE:
Do not open with a broad industry statistic. Follow the selected writing tone. For a professional tone, start directly with the real business problem, decision, or relevant context in clear factual language; do not turn it into a story or fictional scenario. For conversational or informal tones, a brief relatable example is acceptable, but it must not be presented as a real event or personal experience.

TITLE QUALITY RULE:
The H1 must be a practical, specific article title that tells the reader what decision, workflow, or problem the article covers. Do not use vague marketing slogans such as "From Ecommerce to Retail" or "Automate Your Business" without naming the POS, Shopify, WooCommerce, inventory, integration, or evaluation topic.

TOPIC AND ORIGINALITY RULE:
Every section must directly serve "{chosen_keyword}" and the stated blog purpose. Use concrete examples, decisions, workflows, and tradeoffs that fit this topic. Do not reuse a generic sequence of headings or repeat the same explanation in different words.
{secondary_context}

ANTI-HALLUCINATION RULE:
Never invent specific statistics, prices, customer counts, named competitors, awards, or certifications. Where you reference a regulation, authority, or process, describe it in general, accurate terms (e.g. "SRB's official services include...") rather than fabricating exact figures. You may factually describe ExampleBrand's real features: POS billing, digital invoicing, inventory management, purchases, vendors, sales, customers, Udhaar/credit management, expenses, profit and loss, analytics, multi-branch management, multi-user access, attendance, payroll, barcode scanning, low-stock alerts, batch/expiry tracking, quotations, loyalty programs, CRM, e-commerce integrations, and APIs.

EDITORIAL BRIEF:
Treat the keyword, purpose, audience questions, tone, and selected title as the article brief, not as phrases to repeat. Before drafting, decide the reader's business situation, the decision they need to make, the operational problems involved, and the evidence or checks that would help them act. Build sections around that reasoning. For a Shopify and WooCommerce POS topic, cover channel synchronization, product and SKU mapping, inventory updates, order and return workflows, taxes and invoicing in Pakistan, reporting, implementation risks, support, and a practical evaluation checklist when relevant. Explain tradeoffs and give concrete examples. Every paragraph must add a fact, step, example, comparison, or decision rule.

FOCUS-PHRASE PLACEMENT:
If the exact focus phrase needs to appear more often, choose sections that are substantively about the product, workflow, evaluation, implementation, or business outcome. Add it inside a sentence that explains the section's point. Never place it in a heading, table label, list label, image marker, bold fragment, or a sentence that interrupts a list. Keep the phrase out of unrelated paragraphs and do not attach it to a heading or another fragment.

FORMATTING AND LANGUAGE RULES:
Every Markdown heading must be on its own line and contain only the heading text. Never begin a heading with a broken fragment such as "What is {chosen_keyword}" followed by a repeated phrase. Use natural grammar: for example, "What Is PRA Software Integration?" and "How Does It Fit Into an Existing Invoicing Workflow?". Do not put Markdown bold markers inside headings. Do not make the exact keyword appear in every heading.

Never wrap the exact focus keyword in Markdown bold markers. Use the keyword as ordinary prose inside a complete grammatical sentence. Do not insert the keyword where a verb, article, or connector is missing; reread every sentence containing the focus keyword before returning the article.

The article MUST be at least {MIN_WORD_COUNT} words in the body content (not counting meta title/description). Every section should add genuine detail - do not pad with repetition to reach the count.

Format the first two lines exactly as:
META_TITLE: <60 characters max, includes "{chosen_keyword}", includes a power word like Best/Top/Ultimate>
META_DESCRIPTION: <160 characters max, includes "{chosen_keyword}">

Then a blank line, followed by a natural article structure. The first article line MUST be the H1 in Markdown format (`# Title`) on its own line, followed by a blank line and the introduction. Include the most useful topic-specific sections, practical implementation or evaluation guidance where relevant, exactly five useful FAQs, and a conclusion. Choose section names that fit the subject; do not force "What is..." sections or a fixed heading template. Use the selected H1 title when provided: {title_instruction}.

KEYWORD RULES:
- Use the exact phrase "{chosen_keyword}" naturally 8-10 times per 1,000 words, mainly in the title, introduction, relevant sections, and conclusion. Reach this range by planning relevant references in useful paragraphs, never by repeating a sentence, adding filler, or forcing the phrase into unrelated sections.
- Do not force the exact phrase into headings, every paragraph, FAQs, or unrelated sentences. Use clear grammatical variations and related terminology elsewhere.
- Never place the keyword as a detached fragment, repeat it back-to-back, or use bold markers around it in a heading.

LINKING RULES:
- Include the required internal link to {internal_link} with relevant anchor text, and the required link to {CONTACT_URL} with anchor text like "Book a free demo".
- In addition, naturally weave in 1-3 more internal links from this list of other real ExampleBrand pages, wherever genuinely relevant to something you're discussing (do not force one in if nothing fits naturally):
{extra_links_text}
- Include as many external links as genuinely support a specific factual claim (at least 1, often 2-3 is better) - real, well-known official government/regulatory sites or Wikipedia. Never invent a URL that doesn't exist.

MEDIA RULES:
- Mark 5-7 regular photo spots with [IMAGE: description], each depicting something genuinely relevant to "{chosen_keyword}", placed every 2-3 paragraphs.
- Mark 1-2 conceptual process visuals as a single-line Mermaid flowchart: [DIAGRAM: flowchart LR; A[Step One] --> B[Step Two] --> C[Step Three]] - 3-6 steps, short labels, letters/numbers/spaces only inside the brackets.

Output only the finished article content described above - no commentary, no explanation, no repeated instructions."""

@app.route("/")
def home():
    # Local disk (BLOGS_FOLDER) only survives within one serverless
    # instance's lifetime, so it's unioned with whatever's saved in the
    # GitHub datastore repo, which survives cold starts and redeploys.
    local_files = set(os.listdir(BUNDLED_BLOGS_FOLDER) + os.listdir(BLOGS_FOLDER))
    repo_files = set(github_store.list_dir(DRAFTS_REPO_DIR))
    files = sorted(local_files | repo_files)
    return render_template("index.html", files=files, keywords=all_keywords)


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
        # Not on local disk (likely a fresh serverless instance) - fall
        # back to the GitHub datastore repo before giving up.
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
    """Interest-by-region, sorted high to low, matching the map view on the
    real Google Trends site (minus the map graphic itself)."""
    if region_df is None or region_df.empty or keyword not in region_df.columns:
        return []
    series = region_df[keyword].fillna(0).astype(int)
    series = series[series > 0].sort_values(ascending=False).head(limit)
    return [{"region": str(region), "value": int(value)} for region, value in series.items()]


def is_related_query(query, keyword):
    """Loose relevance check so we drop Google's occasional unrelated
    breakout suggestions that share no words at all with the searched term."""
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
    # geo="PK" scopes every view below to Pakistan only, so a country already
    # scoped this way needs a REGION (province-level) breakdown, not COUNTRY.
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
        app.logger.warning(
            "Google Trends interest-by-region request failed for %r: %s", keyword, error
        )
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
        app.logger.warning(
            "Google Trends related-queries request failed for %r: %s", keyword, error
        )

    return {
        "interest_over_time": interest,
        "region_data": region_data,
        "top_queries": top_queries,
        "rising_queries": rising_queries,
    }


# Cache Google Trends responses briefly so repeated searches (same keyword/timeframe)
# don't re-hit Google, which is the main thing that triggers its rate limit.
_TRENDS_CACHE = {}
_TRENDS_CACHE_TTL_SECONDS = 600
_TRENDS_NO_DATA_TTL_SECONDS = 300
_TRENDS_RATE_LIMIT_TTL_SECONDS = 300

# Rotate between a few realistic desktop browser User-Agents so repeated
# requests don't all look like the exact same client hammering Google, which
# is one of the things that trips its bot detection / rate limiting.
_TRENDS_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Edg/130.0.0.0 Safari/537.36",
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
            # Growing, jittered backoff so retries don't land on Google in a
            # predictable rhythm - a flat sleep(3) is easy to keep tripping.
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
            # Use the exact typed term (not an auto-resolved Topic) so results match
            # what a user sees typing the same phrase into Google Trends and pressing Enter,
            # scoped to Pakistan since this tool only serves Pakistani businesses.
            trends_data = _query_google_trends(
                pytrends, searched_keyword, timeframe, "PK"
            )
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
            has_data = bool(
                chart_values
                or region_data
                or top_queries
                or rising_queries
            )
            _TRENDS_CACHE[cache_key] = {
                "timestamp": time.time(),
                "ttl": _TRENDS_CACHE_TTL_SECONDS if has_data else _TRENDS_NO_DATA_TTL_SECONDS,
                "data": result,
                "error": None,
            }
            return result
        except Exception as error:
            last_error = error
            # A 429 won't clear up within the next couple of seconds; stop burning
            # more requests against an already rate-limited session.
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

        has_data = bool(
            data["chart_values"]
            or region_data
            or top_queries
            or rising_queries
        )
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
            "rising_queries": rising_queries
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
    keyword = keyword.strip()
    if not keyword:
        return jsonify({"error": "Please enter a keyword first."}), 400

    try:
        prompt = build_title_prompt(keyword)
        raw_text = generate_title_text(prompt, max_tokens=1200)

        ai_titles = extract_ai_title_candidates(raw_text)
        titles = extract_title_options(raw_text, keyword)

        return jsonify({
            "keyword": keyword,
            "titles": titles,
            "source": "ai" if ai_titles else "fallback",
            "notice": None if ai_titles else "The AI returned no usable title lines, so relevant local titles were supplied."
        })

    except Exception as e:
        app.logger.exception("AI title request failed")
        return jsonify({
            "keyword": keyword,
            "titles": get_fallback_titles(keyword),
            "source": "fallback",
            "notice": "AI title generation failed, so relevant local title ideas were supplied."
        })


@app.route("/api/generate/<path:keyword>")
def api_generate(keyword):
    keyword = request.args.get("primary_keyword", keyword).strip()
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
                    f"The previous attempt was only about {preview_word_count} words. Expand every section with useful examples, steps, tradeoffs, and decision criteria to reach at least {MIN_WORD_COUNT} words."
                )
            if preview_density < 8.0:
                feedback.append(
                    f"The previous draft used the exact focus phrase at {preview_density:.1f} per 1,000 words. Add relevant, topic-specific references to the phrase in sections where it is genuinely being discussed until the natural rate is 8-10 per 1,000 words. Do not add filler or repeat sentences."
                )
            elif preview_density > 10.0:
                feedback.append(
                    f"The previous draft used the exact focus phrase at {preview_density:.1f} per 1,000 words. Replace unnecessary repetitions with natural synonyms and topic-specific wording until the rate is 8-10 per 1,000 words. Do not remove useful detail."
                )
            prompt += "\n\nRevise the complete article based on this quality feedback:\n- " + "\n- ".join(feedback)

        meta_title_match = re.search(r"META_TITLE:\s*(.*)", raw_text)
        meta_desc_match = re.search(r"META_DESCRIPTION:\s*(.*)", raw_text)
        meta_title = meta_title_match.group(1).strip() if meta_title_match else (chosen_title or keyword)
        meta_description = meta_desc_match.group(1).strip() if meta_desc_match else ""

        body = re.sub(r"META_TITLE:.*\n?", "", raw_text)
        body = re.sub(r"META_DESCRIPTION:.*\n?", "", body).strip()

        body = ensure_h1_title(body, chosen_title)
        body = fix_keyword_typos(body, keyword)
        body = collapse_duplicate_words(body)
        body = clean_keyword_artifacts(body, keyword)
        internal_link = keyword_links.get(keyword, "https://example.com/pricing-plan/")
        body = ensure_minimum_links(body, keyword, internal_link)
        body, photo_count, diagram_count = replace_image_markers(body)
        body = ensure_h1_title(body, chosen_title)
        body = clean_keyword_artifacts(body, keyword)
        body = enforce_keyword_density(body, keyword)
        body = enforce_secondary_keywords(body, secondary_keywords)
        body = clean_keyword_artifacts(body, keyword)

        word_count = len(body.split())
        keyword_count = body.lower().count(keyword.lower())
        rate_per_1000 = round((keyword_count / word_count) * 1000, 1) if word_count else 0

        safe_filename = keyword.lower().replace(" ", "_")
        filepath = os.path.join(BLOGS_FOLDER, f"{safe_filename}.md")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(body)

        # Best-effort persistence to the GitHub datastore repo, so the blog
        # survives past this serverless instance's lifetime. If GitHub
        # isn't configured (local dev, or env vars not set yet) this is a
        # silent no-op and the local-disk copy above still works as before.
        try:
            github_store.save_file(
                f"{DRAFTS_REPO_DIR}/{safe_filename}.md",
                body,
                message=f"Generate draft: {keyword}",
            )
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
            "filename": f"{safe_filename}.md"
        })

    except Exception as e:
        error_text = str(e)
        if "rate_limit" in error_text.lower() or "429" in error_text:
            return jsonify({"error": "Daily/rate limit reached on the AI service. Wait a bit and try again, or check your Groq dashboard for reset time."}), 429
        return jsonify({"error": error_text}), 500


if __name__ == "__main__":
    app.run(debug=True)
