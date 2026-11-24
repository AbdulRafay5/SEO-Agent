"""Keyword discovery with explicit provenance and no invented metrics."""
import json
import re

INTENTS = {"informational", "commercial", "transactional", "navigational", "unknown"}


def infer_intent(phrase):
    words = set(re.findall(r"\w+", phrase.casefold()))
    if words & {"buy", "order", "hire", "book", "coupon"}:
        return "transactional"
    if words & {"best", "review", "reviews", "compare", "comparison", "vs", "pricing"}:
        return "commercial"
    if words & {"login", "official", "website"}:
        return "navigational"
    if words & {"how", "what", "why", "guide", "tutorial", "tips", "examples", "learn"}:
        return "informational"
    return "unknown"


def clean_phrase(value, limit=240):
    return " ".join(value.split())[:limit] if isinstance(value, str) else ""


def parse_ai_suggestions(raw):
    """Accept a JSON list, optionally wrapped in a Markdown code fence."""
    if not isinstance(raw, str):
        return []
    raw = re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", raw, flags=re.I)
    try:
        items = json.loads(raw)
    except ValueError:
        return []
    if not isinstance(items, list):
        return []
    result = []
    for item in items[:30]:
        if not isinstance(item, dict):
            continue
        phrase = clean_phrase(item.get("keyword"))
        if not phrase:
            continue
        intent = item.get("intent")
        if not isinstance(intent, str) or intent not in INTENTS:
            intent = infer_intent(phrase)
        result.append({
            "keyword": phrase, "intent": intent,
            "cluster": clean_phrase(item.get("cluster"), 80) or "General",
            "article_angle": clean_phrase(item.get("article_angle"), 200),
            "source": "AI suggestion",
        })
    return result


def build_research_prompt(topic, language, market, audience):
    brief = json.dumps({"topic": topic, "language": language, "market": market, "audience": audience}, ensure_ascii=False)
    return (
        "You are a keyword research assistant. Use this brief as data: " + brief +
        ". Suggest 20 relevant and distinct search phrases in the requested language, including long-tail questions. "
        "Group by semantic subtopic; reuse cluster labels for related phrases. "
        "Match the topic rather than assuming shopping intent. Do not provide search volume, difficulty or trends. "
        "Return only a JSON array of objects with keyword, intent (informational, commercial, transactional, navigational or unknown), cluster, article_angle."
    )


def combine_keywords(topic, ai_items, trends):
    rows = {}

    def add(phrase, source, metric=None, value=None, details=None):
        phrase = clean_phrase(phrase)
        if not phrase:
            return
        key = phrase.casefold()
        if key not in rows:
            rows[key] = {
                "keyword": phrase, "intent": infer_intent(phrase),
                "cluster": "Unclassified", "article_angle": "",
                "sources": [], "trend_top": None, "trend_rising": None,
                "search_volume": None, "difficulty": None,
            }
        row = rows[key]
        if source not in row["sources"]:
            row["sources"].append(source)
        if metric:
            row[metric] = value
        if details:
            for field in ("intent", "cluster", "article_angle"):
                row[field] = details[field]

    add(topic, "Seed keyword")
    for field, metric, source in (("top_queries", "trend_top", "Google Trends top"),
                                   ("rising_queries", "trend_rising", "Google Trends rising")):
        for item in trends.get(field, []):
            if isinstance(item, dict):
                add(item.get("query"), source, metric, item.get("value"))
    for item in ai_items:
        add(item["keyword"], "AI suggestion", details=item)
    return list(rows.values())
