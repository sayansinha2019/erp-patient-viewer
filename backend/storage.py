"""L3 — optional encrypted storage, consent, accounts."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

from cryptography.fernet import Fernet, InvalidToken

_APP_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("KLARIFY_DATA_DIR") or (_APP_DIR / ".data"))
DB_PATH = DATA_DIR / "klarify.db"
SESSION_TTL = timedelta(days=int(os.getenv("KLARIFY_SESSION_DAYS", "30")))
MIN_PASSWORD_LEN = 8


class AuthError(ValueError):
    """Wrong credentials, expired session or wrong encryption password."""


_SCHEMA_READY: set[str] = set()


@contextmanager
def _conn() -> Iterator[sqlite3.Connection]:
    """Open a connection, commit on success, roll back on error, always close."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(DB_PATH))
    c.row_factory = sqlite3.Row
    try:
        if str(DB_PATH) not in _SCHEMA_READY:
            _init_schema(c)
            _SCHEMA_READY.add(str(DB_PATH))
        yield c
        c.commit()
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()


def _init_schema(c: sqlite3.Connection) -> None:
    c.executescript("""
    CREATE TABLE IF NOT EXISTS users (
      id TEXT PRIMARY KEY,
      email TEXT UNIQUE NOT NULL,
      password_hash TEXT NOT NULL,
      salt TEXT NOT NULL,
      created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS consent_log (
      id TEXT PRIMARY KEY,
      user_id TEXT,
      event TEXT NOT NULL,
      policy_version TEXT NOT NULL,
      created_at TEXT NOT NULL,
      meta TEXT
    );
    CREATE TABLE IF NOT EXISTS health_records (
      id TEXT PRIMARY KEY,
      user_id TEXT NOT NULL,
      document_type TEXT NOT NULL,
      title TEXT,
      encrypted_payload TEXT NOT NULL,
      created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS sessions (
      token TEXT PRIMARY KEY,
      user_id TEXT NOT NULL,
      expires_at TEXT NOT NULL
    );
    """)


def _hash_password(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 120_000).hex()


def _derive_fernet(password: str, salt: str) -> Fernet:
    key = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 120_000, dklen=32)
    return Fernet(base64.urlsafe_b64encode(key))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new_session(c: sqlite3.Connection, user_id: str) -> str:
    token = uuid.uuid4().hex
    expires = (_now() + SESSION_TTL).replace(microsecond=0).isoformat()
    c.execute("INSERT INTO sessions (token, user_id, expires_at) VALUES (?,?,?)", (token, user_id, expires))
    return token


def _validate_credentials(email: str, password: str) -> str:
    email = (email or "").strip().lower()
    if "@" not in email or "." not in email.split("@")[-1]:
        raise ValueError("Please enter a valid email address.")
    if len(password or "") < MIN_PASSWORD_LEN:
        raise ValueError(f"Password must be at least {MIN_PASSWORD_LEN} characters.")
    return email


def register_user(email: str, password: str) -> dict[str, str]:
    email = _validate_credentials(email, password)
    user_id = str(uuid.uuid4())
    salt = uuid.uuid4().hex
    pw_hash = _hash_password(password, salt)
    try:
        with _conn() as c:
            c.execute(
                "INSERT INTO users (id, email, password_hash, salt, created_at) VALUES (?,?,?,?,?)",
                (user_id, email, pw_hash, salt, _now().isoformat()),
            )
            token = _new_session(c, user_id)
    except sqlite3.IntegrityError as exc:
        raise ValueError("An account with this email already exists. Please log in instead.") from exc
    log_consent(user_id, "account_created", "1.0", {"email": email})
    return {"token": token, "user_id": user_id, "email": email}


def login_user(email: str, password: str) -> dict[str, str]:
    email = (email or "").strip().lower()
    with _conn() as c:
        row = c.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if not row or not hmac.compare_digest(_hash_password(password or "", row["salt"]), row["password_hash"]):
            raise AuthError("Invalid email or password")
        token = _new_session(c, row["id"])
    return {"token": token, "user_id": row["id"], "email": email}


def user_from_token(token: str) -> str | None:
    with _conn() as c:
        row = c.execute("SELECT user_id, expires_at FROM sessions WHERE token = ?", (token,)).fetchone()
        if not row:
            return None
        try:
            expired = datetime.fromisoformat(row["expires_at"]) <= _now()
        except ValueError:
            expired = True
        if expired:
            c.execute("DELETE FROM sessions WHERE token = ?", (token,))
            return None
    return row["user_id"]


def _user_fernet(c: sqlite3.Connection, user_id: str, password: str) -> Fernet:
    """Verify the password, then derive the encryption key from it."""
    user = c.execute("SELECT salt, password_hash FROM users WHERE id = ?", (user_id,)).fetchone()
    if not user:
        raise AuthError("User not found")
    if not hmac.compare_digest(_hash_password(password or "", user["salt"]), user["password_hash"]):
        raise AuthError("Wrong password — please log in again.")
    return _derive_fernet(password, user["salt"])


def log_consent(user_id: str | None, event: str, policy_version: str, meta: dict | None = None) -> None:
    with _conn() as c:
        c.execute(
        "INSERT INTO consent_log (id, user_id, event, policy_version, created_at, meta) VALUES (?,?,?,?,?,?)",
        (str(uuid.uuid4()), user_id, event, policy_version, datetime.now(timezone.utc).isoformat(), json.dumps(meta or {})),
      )


def save_health_record(user_id: str, password: str, record: dict[str, Any]) -> str:
    with _conn() as c:
        f = _user_fernet(c, user_id, password)
    payload = f.encrypt(json.dumps(record, ensure_ascii=False).encode()).decode()
    record_id = str(uuid.uuid4())
    with _conn() as c:
        c.execute(
        "INSERT INTO health_records (id, user_id, document_type, title, encrypted_payload, created_at) VALUES (?,?,?,?,?,?)",
        (
          record_id,
          user_id,
          record.get("document_type", "unknown"),
          record.get("document_title", ""),
          payload,
          datetime.now(timezone.utc).isoformat(),
        ),
      )
    log_consent(user_id, "health_data_stored", "1.0", {"record_id": record_id})
    return record_id


def list_timeline(user_id: str, password: str) -> list[dict[str, Any]]:
    with _conn() as c:
        f = _user_fernet(c, user_id, password)
        rows = c.execute(
            "SELECT id, document_type, title, encrypted_payload, created_at FROM health_records "
            "WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,),
        ).fetchall()
    timeline = []
    for row in rows:
      try:
        data = json.loads(f.decrypt(row["encrypted_payload"].encode()))
      except (InvalidToken, ValueError):
        data = {}
      timeline.append({
        "id": row["id"],
        "document_type": row["document_type"],
        "title": row["title"],
        "date": row["created_at"],
        "flag_count": len(data.get("flags", [])),
        "summary": ((data.get("humanized") or {}).get("patient_summary") or "")[:160],
      })
    return timeline


def compute_trends(user_id: str, password: str) -> list[dict[str, Any]]:
    """Lab value trends from stored records (Phase 3)."""
    with _conn() as c:
        f = _user_fernet(c, user_id, password)
        rows = c.execute(
            "SELECT encrypted_payload FROM health_records WHERE user_id = ? ORDER BY created_at ASC",
            (user_id,),
        ).fetchall()
    series: dict[str, list] = {}
    for row in rows:
      try:
        data = json.loads(f.decrypt(row["encrypted_payload"].encode()))
      except (InvalidToken, ValueError):
        continue
      parsed = data.get("parsed") or {}
      for obs in parsed.get("observations", []) or []:
        code = obs.get("loinc_code")
        val = obs.get("value")
        if code and val is not None:
          try:
            series.setdefault(code, []).append(float(val))
          except (TypeError, ValueError):
            continue
    trends = []
    for code, values in series.items():
      if len(values) >= 2:
        trends.append({
          "loinc_code": code,
          "values": values,
          "latest": values[-1],
          "change_pct": round((values[-1] - values[0]) / values[0] * 100, 1) if values[0] else 0,
        })
    return trends
