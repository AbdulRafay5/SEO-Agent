"""Account-scoped GitHub storage. Account IDs must come from verified sessions."""
import json
import re
from uuid import uuid4
from datetime import datetime, timezone
import github_store
from evidence_retrieval import validate_sources, retrieve, citation_report


class AccountStore:
    def __init__(self, account_id):
        if not isinstance(account_id, str) or not re.fullmatch(r"[a-f0-9]{32}", account_id):
            raise ValueError("Invalid account ID.")
        self.prefix = f"users/{account_id}/drafts"
        self.research_prefix = f"users/{account_id}/research"

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
        if isinstance(record.get("evidence"), dict):
            record["evidence"]["citations"] = citation_report(record["content"], record["evidence"]["passages"])
        return record

    def create_article(self, content, keyword="", meta_description="", version_of=None, research_ids=None):
        if not isinstance(content, str) or not content.strip() or len(content) > 40000:
            raise ValueError("Article must contain 1 to 40000 characters.")
        if not isinstance(keyword, str) or len(keyword) > 240:
            raise ValueError("Invalid keyword.")
        if not isinstance(meta_description, str) or len(meta_description) > 1000:
            raise ValueError("Invalid SEO description.")
        parent = self.read_article(version_of) if version_of is not None else None
        if version_of is not None and parent is None:
            raise ValueError("Source article not found.")
        evidence = None
        if research_ids is not None:
            sources = self.resolve_research(research_ids)
            passages = retrieve(keyword, sources)
            evidence = {"method": "BM25 lexical retrieval", "passages": passages,
                        "status": "retrieved" if passages else "no_matches"}
        elif parent and isinstance(parent.get("evidence"), dict):
            evidence = {key: parent["evidence"][key] for key in ("method", "passages", "status")}
        if evidence is not None:
            evidence["citations"] = citation_report(content, evidence["passages"])
        filename = uuid4().hex + ".json"
        record = {"schema": 1, "filename": filename, "content": content,
                  "keyword": keyword, "meta_description": meta_description,
                  "version_of": version_of, "created_at": datetime.now(timezone.utc).isoformat()}
        if evidence is not None:
            record["evidence"] = evidence
        if not github_store.save_file(self.path(filename), json.dumps(record, ensure_ascii=False),
                                      message="Save account article", expected_sha=None):
            raise RuntimeError("Article storage unavailable.")
        return record


    def research_path(self, filename):
        if not isinstance(filename, str) or not re.fullmatch(r"[a-f0-9]{32}\.json", filename):
            raise ValueError("Invalid research ID.")
        return f"{self.research_prefix}/{filename}"

    def list_research(self):
        return sorted(filename for filename in github_store.list_dir(self.research_prefix)
                      if re.fullmatch(r"[a-f0-9]{32}\.json", filename))

    def read_research(self, filename):
        content, _ = github_store.get_file(self.research_path(filename))
        if content is None:
            return None
        if len(content) > 100000:
            raise ValueError("Invalid stored research.")
        record = json.loads(content)
        if not isinstance(record, dict) or record.get("filename") != filename:
            raise ValueError("Invalid stored research.")
        return {**record, "source": validate_sources([record.get("source")])[0]}

    def create_research(self, source):
        source = validate_sources([source])[0]
        filename = uuid4().hex + ".json"
        record = {"schema": 1, "filename": filename, "source": source,
                  "created_at": datetime.now(timezone.utc).isoformat()}
        if not github_store.save_file(self.research_path(filename), json.dumps(record, ensure_ascii=False),
                                      message="Save account research", expected_sha=None):
            raise RuntimeError("Research storage unavailable.")
        return record

    def resolve_research(self, filenames):
        if not isinstance(filenames, list) or len(filenames) > 5:
            raise ValueError("Provide up to five research IDs.")
        for filename in filenames:
            self.research_path(filename)
        if len(set(filenames)) != len(filenames):
            raise ValueError("Duplicate research IDs.")
        sources = []
        for filename in filenames:
            record = self.read_research(filename)
            if record is None:
                raise ValueError("Research source not found.")
            sources.append(record["source"])
        return validate_sources(sources)
