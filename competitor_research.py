"""Compare user-supplied search results and competitor headings.

No network requests or claims about current search rankings are made.
"""
import re
from collections import Counter
from urllib.parse import urlsplit
from seo_analysis import normalize, contains


def compare_competitors(topic, entries, draft=""):
    key = normalize(topic)
    rows = []
    coverage = Counter()
    labels = {}
    for entry in entries:
        url = entry.get("url", "").strip()
        title = entry.get("title", "").strip()
        headings = [line.strip().lstrip("#").strip() for line in entry.get("headings", "").splitlines() if line.strip().lstrip("#").strip()]
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("Use a valid HTTP or HTTPS competitor URL.")
        unique = {}
        for heading in headings:
            normalized = normalize(heading)
            if normalized:
                unique.setdefault(normalized, heading)
        for normalized, heading in unique.items():
            coverage[normalized] += 1
            labels.setdefault(normalized, heading)
        rows.append({"url": url, "domain": parsed.hostname, "title": title,
                     "heading_count": len(headings), "topic_in_title": contains(title, key),
                     "headings": headings})
    draft_headings = {normalize(match) for match in re.findall(r"(?m)^\s{0,3}#{1,6}\s+(.+?)\s*$", draft)}
    themes = [{"heading": labels[k], "competitors": n,
               "in_draft": k in draft_headings if draft.strip() else None}
              for k, n in sorted(coverage.items(), key=lambda pair: (-pair[1], pair[0]))]
    return {"topic": topic, "competitors": rows, "themes": themes,
            "source": "User-supplied search results and headings",
            "note": "Heading comparison uses normalized exact matches, not semantic equivalence. Missing headings are editorial ideas, not evidence of ranking opportunities. No live ranking or traffic data is measured."}
