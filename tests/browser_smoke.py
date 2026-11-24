"""Exercise the real browser UI and Flask routes without paid or live provider calls."""
import os
import tempfile
import threading
from pathlib import Path
from unittest.mock import patch

for key in ("GITHUB_TOKEN", "GITHUB_REPO", "GEMINI_API_KEY", "GROQ_API_KEY", "QWEN_API_KEY", "PEXELS_API_KEY"):
    os.environ[key] = ""

from playwright.sync_api import sync_playwright, expect
from werkzeug.serving import make_server
from app import app

ARTICLE = "# Growing indoor herbs\n\nGrowing indoor herbs is a useful way to learn gardening.\n\n## Care\n\nWater when the soil is dry."
TITLES = "\n".join(f"{i}. Growing indoor herbs: {name} || A practical guide to growing herbs indoors." for i, name in enumerate(["Care", "Containers", "Water", "Light", "Soil", "Harvest"], 1))
KEYWORDS = '[{"keyword":"indoor herb garden","intent":"informational","cluster":"Gardening","article_angle":"Getting started"}]'


def fake_ai(prompt, max_tokens):
    if "Markdown article editor" in prompt:
        return "## Care\n\nRevised care instructions."
    return KEYWORDS if "keyword research assistant" in prompt else ARTICLE


def main():
    with tempfile.TemporaryDirectory() as folder, patch("app.BLOGS_FOLDER", folder), patch("app.BUNDLED_BLOGS_FOLDER", folder), patch("app.LAST_GEN_FILE", str(Path(folder) / "last.txt")), patch("app.MIN_WORD_COUNT", 5), patch("app.gemini_client", object()), patch("app.generate_ai_text", side_effect=fake_ai), patch("app.generate_title_text", return_value=TITLES), patch("app.fetch_trends_data", side_effect=RuntimeError("offline test")):
        server = make_server("127.0.0.1", 0, app, threaded=True)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch()
                context = browser.new_context(viewport={"width": 1440, "height": 1000})
                page = context.new_page()
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                # Keep browser checks deterministic: use real library builds installed by CI.
                vendors = {
                    "https://unpkg.com/lucide@latest": "node_modules/lucide/dist/umd/lucide.js",
                    "https://cdn.jsdelivr.net/npm/marked/marked.min.js": "node_modules/marked/marked.min.js",
                    "https://cdn.jsdelivr.net/npm/dompurify@3.2.6/dist/purify.min.js": "node_modules/dompurify/dist/purify.min.js",
                    "https://cdn.jsdelivr.net/npm/chart.js": "node_modules/chart.js/dist/chart.umd.js",
                }
                def external(route):
                    path = vendors.get(route.request.url)
                    if path:
                        route.fulfill(path=path, content_type="application/javascript")
                    else:
                        route.abort()
                page.route("https://**/*", external)
                page.goto(f"http://127.0.0.1:{server.server_port}/")
                expect(page.locator("#screen-studio")).to_be_visible()
                expect(page.locator("#keywords-table-body tr").first).to_be_attached()
                page.locator("#target-keyword").fill("Growing indoor herbs")
                page.get_by_text("Evidence grounding (optional)", exact=True).click()
                page.get_by_role("button", name="Add source", exact=True).click()
                page.get_by_label("Evidence title").fill("Herb guide")
                page.get_by_label("Evidence text").fill("Indoor herbs need sunlight and water.")
                page.get_by_text("Saved research library", exact=True).click()
                page.get_by_role("button", name="Save current sources").click()
                expect(page.locator("#knowledge-status")).to_contain_text("1 new source")
                page.get_by_role("button", name="Save current sources").click()
                expect(page.locator("#knowledge-status")).to_contain_text("1 duplicate")
                page.reload()
                page.locator("#target-keyword").fill("Growing indoor herbs")
                page.get_by_text("Evidence grounding (optional)", exact=True).click()
                page.get_by_text("Saved research library", exact=True).click()
                expect(page.locator("#knowledge-results")).to_contain_text("Herb guide")
                page.get_by_role("button", name="Reuse source").click()
                expect(page.get_by_label("Evidence text")).to_have_value("Indoor herbs need sunlight and water.")
                page.locator("#evidence-preview-btn").click()
                expect(page.locator("#evidence-results")).to_contain_text("Indoor herbs need sunlight and water.")
                page.get_by_text("Evidence grounding (optional)", exact=True).click()
                page.locator("#btn-fetch-titles").click()
                expect(page.locator(".brainstorm-card").first).to_be_visible()
                page.locator(".brainstorm-card").first.click()
                page.locator("#generate-btn").click()
                expect(page.locator("#markdown-rendered-view")).to_be_visible(timeout=20000)
                expect(page.locator("#markdown-rendered-view")).to_contain_text("Water when the soil is dry.")
                page.get_by_text("Evidence grounding (optional)", exact=True).click()
                expect(page.locator("#citation-report")).to_contain_text("No source ID citations detected.")
                page.get_by_text("Evidence grounding (optional)", exact=True).click()
                page.locator("#btn-view-raw").click()
                expect(page.locator("#markdown-raw-view")).to_be_visible()
                original = page.locator("#markdown-raw-view").input_value()
                page.locator("#btn-revise").click()
                page.locator("#revision-section").select_option("1")
                page.locator("#revision-request").click()
                expect(page.locator("#revision-preview")).to_have_value("## Care\n\nRevised care instructions.")
                expect(page.locator("#markdown-raw-view")).to_have_value(original)
                page.locator("#revision-accept").click()
                assert "Revised care instructions." in page.locator("#markdown-raw-view").input_value()
                page.locator("#btn-save-version").click()
                expect(page.locator("#toast-container")).to_contain_text("New version saved")
                versions=page.evaluate("JSON.parse(localStorage.getItem('seo_studio_blogs'))")
                assert versions[0]["isLocalVersion"]
                assert "Revised care instructions." in versions[0]["content"]
                assert "Revised care instructions." not in versions[1]["content"]
                page.locator("#revision-undo").click()
                expect(page.locator("#markdown-raw-view")).to_have_value(original)
                page.locator("#revision-panel").get_by_role("button", name="Close").click()
                page.locator("#btn-seo-analysis").click()
                expect(page.locator("#seo-analysis-summary")).to_contain_text("editorial score")
                page.locator("#seo-analysis-panel").get_by_role("button", name="Close").click()
                page.locator("#tab-btn-repository").click()
                expect(page.locator("#repository-grid .repo-card").first).to_be_visible()
                page.locator("#repository-grid .repo-card").filter(has_not_text="Local version").first.get_by_role("button", name="Load in Studio").click()
                expect(page.locator("#markdown-rendered-view")).to_contain_text("Water when the soil is dry.")
                page.locator("#tab-btn-keywords").click()
                page.locator("#research-topic").fill("Indoor gardening")
                page.locator("#research-btn").click()
                expect(page.locator("#keywords-table-body")).to_contain_text("indoor herb garden")
                page.get_by_text("Competitor research", exact=True).click()
                page.get_by_role("button", name="Add competitor").click()
                page.get_by_label("Competitor URL").fill("https://example.com/herbs")
                page.get_by_label("Competitor title").fill("Indoor gardening")
                page.get_by_label("Competitor headings").fill("Watering\nLight")
                page.locator("#compare-competitors-btn").click()
                expect(page.locator("#competitor-results")).to_contain_text("Watering")
                page.locator("#keywords-table-body tr").filter(has_text="indoor herb garden").get_by_role("button", name="Use in Studio").click()
                expect(page.locator("#target-keyword")).to_have_value("indoor herb garden")
                assert not errors, errors
                context.close()
                mobile = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True, device_scale_factor=2)
                page = mobile.new_page()
                mobile_errors = []
                page.on("pageerror", lambda error: mobile_errors.append(str(error)))
                page.route("https://**/*", external)
                page.goto(f"http://127.0.0.1:{server.server_port}/")
                expect(page.locator("#screen-studio")).to_be_visible()
                page.get_by_role("button", name="Open navigation").click()
                expect(page.locator("#mobile-drawer")).to_have_class("drawer open")
                page.locator("#m-tab-btn-keywords").click()
                expect(page.locator("#screen-keywords")).to_be_visible()
                page.locator("#research-topic").fill("Indoor gardening")
                page.locator("#research-btn").click()
                expect(page.locator("#keywords-table-body")).to_contain_text("indoor herb garden")
                page.locator("#keywords-table-body tr").filter(has_text="indoor herb garden").get_by_role("button", name="Use in Studio").click()
                expect(page.locator("#target-keyword")).to_have_value("indoor herb garden")
                page.locator("#btn-fetch-titles").click()
                expect(page.locator(".brainstorm-card").first).to_be_visible()
                assert not mobile_errors, mobile_errors
                mobile.close()
                browser.close()
        finally:
            server.shutdown()
            thread.join(timeout=5)


if __name__ == "__main__":
    main()
