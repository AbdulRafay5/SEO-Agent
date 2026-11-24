"""Account-scoped GitHub storage. Account IDs must come from verified sessions."""
import json
import re
from uuid import uuid4
from datetime import datetime, timezone
import github_store


class AccountStore:
    def __init__(self, account_id):
        if not isinstance(account_id, str) or not re.fullmatch(r"[a-f0-9]{32}", account_id):
            raise ValueError("Invalid account ID.")
        self.prefix = f"users/{account_id}/drafts"

    def path(self, filename):
        if not isinstance(filename, str) or not re.fullmatch(r"[a-f0-9]{32}\.json", filename):
            raise ValueError("Invalid article ID.")
        return f"{self.prefix}/{filename}"

    def list_articles(self):
        return sorted(filename for filename in github_store.list_dir(self.prefix)
                      if re.fullmatch(r"[a-f0-9]{32}\.json", filename))

    def read_article(self, filename):
        content, _ = github_store.get_file(self.path(filename))
        if content is None:
            return None
        record = json.loads(content)
        if not isinstance(record, dict) or record.get("filename") != filename or not isinstance(record.get("content"), str):
            raise ValueError("Invalid stored article.")
        return record

    def create_article(self, content, keyword="", meta_description="", version_of=None):
        if not isinstance(content, str) or not content.strip() or len(content) > 40000:
            raise ValueError("Article must contain 1 to 40000 characters.")
        if not isinstance(keyword, str) or len(keyword) > 240:
            raise ValueError("Invalid keyword.")
        if not isinstance(meta_description, str) or len(meta_description) > 1000:
            raise ValueError("Invalid SEO description.")
        if version_of is not None and self.read_article(version_of) is None:
            raise ValueError("Source article not found.")
        filename = uuid4().hex + ".json"
        record = {"schema": 1, "filename": filename, "content": content,
                  "keyword": keyword, "meta_description": meta_description,
                  "version_of": version_of, "created_at": datetime.now(timezone.utc).isoformat()}
        if not github_store.save_file(self.path(filename), json.dumps(record, ensure_ascii=False),
                                      message="Save account article", expected_sha=None):
            raise RuntimeError("Article storage unavailable.")
        return record
