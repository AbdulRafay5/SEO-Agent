"""Deterministic editorial checks for Markdown articles, not a ranking predictor."""
import re
import unicodedata

WORD = re.compile(r"[^\W_]+(?:['’\-][^\W_]+)*", re.UNICODE)
LINK = re.compile(r"(!?)\[([^\]\n]*)\]\((https?://[^)\s]+)(?:\s+[^)]*)?\)", re.I)
HEADING = re.compile(r"^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$", re.M)


def strip_fenced_code(markdown):
    result = []
    fence = None
    for line in markdown.splitlines():
        match = re.match(r"^ {0,3}(\x60{3,}|~{3,})(.*)$", line)
        if fence:
            if match and match[1][0] == fence[0] and len(match[1]) >= len(fence) and not match[2].strip():
                fence = None
        elif match:
            fence = match[1]
        else:
            result.append(line)
    return "\n".join(result)


def plain_text(markdown):
    text = strip_fenced_code(markdown)
    text = LINK.sub(lambda m: "" if m[1] else m[2], text)
    text = re.sub(r"\[(?:S\d+\s*,\s*)*S\d+\]", "", text)
    return re.sub(r"<[^>]*>|https?://\S+", "", text)


def normalize(text):
    return " ".join(WORD.findall(unicodedata.normalize("NFKC", text).casefold()))


def contains(text, keyword):
    return (" " + keyword + " ") in (" " + normalize(text) + " ") if keyword else False


def analyze_article(content, keyword="", title="", description="", language=""):
    clean = plain_text(content)
    headings = [(len(m[1]), m[2]) for m in HEADING.finditer(clean)]
    words = WORD.findall(clean)
    count = len(words)
    key = normalize(keyword)
    h1s = [text for level, text in headings if level == 1]
    title = title.strip() or (h1s[0] if h1s else "")
    body = HEADING.sub("", clean).strip()
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]
    intro = paragraphs[0] if paragraphs else ""
    sentences = [s for s in re.split(r"[.!?。！？]+", body) if WORD.search(s)]
    average = round(len(WORD.findall(body)) / len(sentences), 1) if sentences else None
    visible_markdown = strip_fenced_code(content)
    images = [m for m in LINK.finditer(visible_markdown) if m[1]]
    links = [m for m in LINK.finditer(visible_markdown) if not m[1]]
    checks = []

    def check(name, status, advice):
        checks.append({"name": name, "status": status, "advice": advice})

    check("Single H1", "pass" if len(h1s) == 1 else "review",
          "Use one clear main heading." if len(h1s) != 1 else "One main heading found.")
    check("Heading structure", "pass" if any(level == 2 for level, _ in headings) and not any(b[0] > a[0]+1 for a,b in zip(headings,headings[1:])) else "review",
          "Use descriptive H2 sections and nest subheadings without skipping levels.")
    check("Title length", "pass" if 1 <= len(title) <= 60 else "review",
          "Aim for a concise, descriptive title; 60 characters is a rough preview heuristic, not a ranking rule.")
    check("Keyword in title", ("pass" if contains(title, key) else "review") if key else "not applicable",
          "Include the topic naturally in the title if appropriate.")
    check("Keyword in introduction", ("pass" if contains(intro, key) else "review") if key else "not applicable",
          "Introduce the topic early without forcing exact wording.")
    check("Meta description", "not applicable" if not description.strip() else ("pass" if 70 <= len(description.strip()) <= 160 else "review"),
          "Provide a useful summary, roughly 70–160 characters; search engines may display a different snippet.")
    check("Image descriptions", "not applicable" if not images else ("pass" if all(m[2].strip() for m in images) else "review"),
          "Describe meaningful images with relevant alternative text; decorative images can use empty alt text.")
    check("Paragraph length", "pass" if paragraphs and all(len(WORD.findall(p)) <= 120 for p in paragraphs) else "review",
          "Break up very long paragraphs where it improves reading.")
    eligible = [c for c in checks if c["status"] != "not applicable"]
    normalized = normalize(clean)
    occurrences = len(re.findall(r"(?<!\w)" + re.escape(key) + r"(?!\w)", normalized)) if key else 0
    return {"score": round(100 * sum(c["status"] == "pass" for c in eligible) / len(eligible)) if eligible else None,
            "word_count": count, "keyword_count": occurrences,
            "keyword_rate_per_1000": round(1000 * occurrences / count, 1) if count else 0,
            "heading_count": len(headings), "link_count": len(links), "image_count": len(images),
            "average_sentence_words": average, "title": title, "title_length": len(title),
            "description_length": len(description.strip()), "checks": checks,
            "note": "Editorial checklist only, not a Google ranking score. Word counts and sentence lengths are approximate and vary by language."}
