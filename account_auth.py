"""Optional PostgreSQL-backed authentication; no credentials stored in GitHub."""
import hashlib
import os
import re
import secrets
from datetime import datetime, timezone, timedelta
from werkzeug.security import generate_password_hash, check_password_hash

SCHEMA = """
CREATE TABLE IF NOT EXISTS seo_accounts (
    id TEXT PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS seo_sessions (
    token_hash TEXT PRIMARY KEY,
    account_id TEXT NOT NULL REFERENCES seo_accounts(id) ON DELETE CASCADE,
    expires_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS seo_sessions_expiry ON seo_sessions(expires_at);
"""


def connect():
    import psycopg
    return psycopg.connect(os.environ["SEO_DATABASE_URL"], connect_timeout=5,
                           options="-c statement_timeout=5000")


def initialize():
    with connect() as conn:
        conn.execute(SCHEMA)


def normalize_username(value):
    if not isinstance(value, str):
        raise ValueError("Invalid username.")
    value = value.strip().lower()
    if not re.fullmatch(r"[a-z0-9_]{3,32}", value):
        raise ValueError("Use 3 to 32 letters, numbers or underscores.")
    return value


def validate_password(value):
    if not isinstance(value, str) or not 12 <= len(value) <= 128:
        raise ValueError("Use a password of 12 to 128 characters.")
    return value


def register(username, password):
    username = normalize_username(username)
    password = validate_password(password)
    account_id = secrets.token_hex(16)
    hashed = generate_password_hash(password, method="scrypt")
    with connect() as conn:
        result = conn.execute(
            "INSERT INTO seo_accounts (id, username, password_hash) VALUES (%s,%s,%s) ON CONFLICT (username) DO NOTHING RETURNING id",
            (account_id, username, hashed)).fetchone()
    return bool(result)


def token_hash(token):
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def login(username, password):
    username = normalize_username(username)
    validate_password(password)
    with connect() as conn:
        row = conn.execute("SELECT id,password_hash FROM seo_accounts WHERE username=%s", (username,)).fetchone()
        if row is None:
            # Perform a comparable password hashing operation for unknown users.
            generate_password_hash(password, method="scrypt")
            return None
        if not check_password_hash(row[1], password):
            return None
        token = secrets.token_urlsafe(32)
        expiry = datetime.now(timezone.utc) + timedelta(hours=12)
        conn.execute("DELETE FROM seo_sessions WHERE expires_at <= now()")
        conn.execute("INSERT INTO seo_sessions(token_hash,account_id,expires_at) VALUES (%s,%s,%s)",
                     (token_hash(token), row[0], expiry))
        return token


def valid_token(token):
    return isinstance(token, str) and bool(re.fullmatch(r"[A-Za-z0-9_-]{43}", token))


def current_account(token):
    if not valid_token(token):
        return None
    with connect() as conn:
        row = conn.execute(
            "SELECT a.id,a.username FROM seo_sessions s JOIN seo_accounts a ON a.id=s.account_id WHERE s.token_hash=%s AND s.expires_at>now()",
            (token_hash(token),)).fetchone()
        return {"id":row[0], "username":row[1]} if row else None


def logout(token):
    if valid_token(token):
        with connect() as conn:
            conn.execute("DELETE FROM seo_sessions WHERE token_hash=%s", (token_hash(token),))


if __name__ == "__main__":
    initialize()
