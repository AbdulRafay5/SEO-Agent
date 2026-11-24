"""
GitHub-as-storage for the blog generator.

Why this exists
----------------
Vercel serverless functions have no persistent disk - anything app.py writes
to BLOGS_FOLDER (or tempfile.gettempdir()) vanishes as soon as that instance
is recycled, and different invocations can even land on different instances.
That's why blogs "disappear" and why env vars are the only thing that
reliably survives a redeploy.

This module provides persistent file storage:
instead of relying on local disk, generated blogs are saved as
files in a GitHub repo via the Contents API. GitHub is the "disk".

Only two real env vars are needed to bootstrap this:
  GITHUB_REPO   = "your-username/your-datastore-repo"
  GITHUB_TOKEN  = a token scoped to contents:read/write on that repo
Optional:
  GITHUB_BRANCH = defaults to "main"

If GITHUB_REPO / GITHUB_TOKEN aren't set, every function here becomes a
no-op / returns None, and app.py falls back to local-disk behavior exactly
like before - so this is safe to drop in without breaking local dev.
"""

import base64
import json
import os

import requests

API = "https://api.github.com"


def _configured():
    return bool(os.getenv("GITHUB_REPO") and os.getenv("GITHUB_TOKEN"))


def _repo_info():
    repo = os.getenv("GITHUB_REPO", "")
    owner, _, name = repo.partition("/")
    return {
        "owner": owner,
        "name": name,
        "token": os.getenv("GITHUB_TOKEN"),
        "branch": os.getenv("GITHUB_BRANCH", "main"),
    }


def _headers():
    info = _repo_info()
    return {
        "Authorization": f"Bearer {info['token']}",
        "Accept": "application/vnd.github+json",
    }


def get_file(path):
    """
    Returns (text_content, sha) for `path` in the datastore repo, or
    (None, None) if it doesn't exist / GitHub isn't configured.
    """
    if not _configured():
        return None, None

    info = _repo_info()
    url = f"{API}/repos/{info['owner']}/{info['name']}/contents/{path}"
    resp = requests.get(url, headers=_headers(), params={"ref": info["branch"]}, timeout=10)

    if resp.status_code == 404:
        return None, None
    resp.raise_for_status()

    data = resp.json()
    content = base64.b64decode(data["content"]).decode("utf-8")
    return content, data["sha"]


_LOOK_UP_SHA = object()


def save_file(path, content, message, *, expected_sha=_LOOK_UP_SHA):
    """
    Creates or updates `path` in the datastore repo with `content` (text).
    By default looks up the current SHA before writing. Read-modify-write
    callers must supply the SHA from their original read; explicit None
    means create only. A conflict is reported by the GitHub API.
    No-ops quietly if GitHub isn't configured.
    """
    if not _configured():
        return False

    info = _repo_info()
    if expected_sha is _LOOK_UP_SHA:
        _, sha = get_file(path)
    else:
        sha = expected_sha

    url = f"{API}/repos/{info['owner']}/{info['name']}/contents/{path}"
    body = {
        "message": message,
        "content": base64.b64encode(content.encode("utf-8")).decode("utf-8"),
        "branch": info["branch"],
    }
    if sha:
        body["sha"] = sha

    resp = requests.put(url, headers=_headers(), json=body, timeout=10)
    resp.raise_for_status()
    return True


def list_dir(path):
    """
    Returns a list of filenames (not full paths) inside `path` in the repo,
    or [] if the folder doesn't exist yet / GitHub isn't configured.
    """
    if not _configured():
        return []

    info = _repo_info()
    url = f"{API}/repos/{info['owner']}/{info['name']}/contents/{path}"
    resp = requests.get(url, headers=_headers(), params={"ref": info["branch"]}, timeout=10)

    if resp.status_code == 404:
        return []
    resp.raise_for_status()

    return [item["name"] for item in resp.json() if item["type"] == "file"]


