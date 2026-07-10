"""L3 — optional encrypted storage, consent, accounts."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet

DB_PATH = Path(__file__).resolve().parent.parent.parent / ".data" / "klarify.db"


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(DB_PATH))
    c.row_factory = sqlite3.Row
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
    return c


def _hash_password(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 120_000).hex()


def _derive_fernet(password: str, salt: str) -> Fernet:
    key = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 120_000, dklen=32)
    return Fernet(base64.urlsafe_b64encode(key))


def register_user(email: str, password: str) -> dict[str, str]:
    user_id = str(uuid.uuid4())
    salt = uuid.uuid4().hex
    pw_hash = _hash_password(password, salt)
    now = datetime.now(timezone.utc).isoformat()
    with _conn() as c:
      c.execute(
        "INSERT INTO users (id, email, password_hash, salt, created_at) VALUES (?,?,?,?,?)",
        (user_id, email.lower(), pw_hash, salt, now),
      )
    log_consent(user_id, "account_created", "1.0", {"email": email})
    return {"user_id": user_id, "email": email}


def login_user(email: str, password: str) -> dict[str, str]:
    with _conn() as c:
      row = c.execute("SELECT * FROM users WHERE email = ?", (email.lower(),)).fetchone()
    if not row or _hash_password(password, row["salt"]) != row["password_hash"]:
      raise ValueError("Invalid email or password")
    token = uuid.uuid4().hex
    expires = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    with _conn() as c:
      c.execute("INSERT INTO sessions (token, user_id, expires_at) VALUES (?,?,?)", (token, row["id"], expires))
    return {"token": token, "user_id": row["id"]}


def user_from_token(token: str) -> str | None:
    with _conn() as c:
      row = c.execute("SELECT user_id FROM sessions WHERE token = ?", (token,)).fetchone()
    return row["user_id"] if row else None


def log_consent(user_id: str | None, event: str, policy_version: str, meta: dict | None = None) -> None:
    with _conn() as c:
      c.execute(
        "INSERT INTO consent_log (id, user_id, event, policy_version, created_at, meta) VALUES (?,?,?,?,?,?)",
        (str(uuid.uuid4()), user_id, event, policy_version, datetime.now(timezone.utc).isoformat(), json.dumps(meta or {})),
      )


def save_health_record(user_id: str, password: str, record: dict[str, Any]) -> str:
    with _conn() as c:
      row = c.execute("SELECT salt FROM users WHERE id = ?", (user_id,)).fetchone()
    if not row:
      raise ValueError("User not found")
    f = _derive_fernet(password, row["salt"])
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
      user = c.execute("SELECT salt FROM users WHERE id = ?", (user_id,)).fetchone()
      rows = c.execute(
        "SELECT id, document_type, title, encrypted_payload, created_at FROM health_records WHERE user_id = ? ORDER BY created_at DESC",
        (user_id,),
      ).fetchall()
    f = _derive_fernet(password, user["salt"])
    timeline = []
    for row in rows:
      try:
        data = json.loads(f.decrypt(row["encrypted_payload"].encode()))
      except Exception:
        data = {}
      timeline.append({
        "id": row["id"],
        "document_type": row["document_type"],
        "title": row["title"],
        "date": row["created_at"],
        "flag_count": len(data.get("flags", [])),
        "summary": (data.get("humanized") or {}).get("patient_summary", "")[:120],
      })
    return timeline


def compute_trends(user_id: str, password: str) -> list[dict[str, Any]]:
    """Lab value trends from stored records (Phase 3)."""
    with _conn() as c:
      user = c.execute("SELECT salt FROM users WHERE id = ?", (user_id,)).fetchone()
      rows = c.execute("SELECT encrypted_payload FROM health_records WHERE user_id = ?", (user_id,)).fetchall()
    f = _derive_fernet(password, user["salt"])
    series: dict[str, list] = {}
    for row in rows:
      try:
        data = json.loads(f.decrypt(row["encrypted_payload"].encode()))
      except Exception:
        continue
      parsed = data.get("parsed") or {}
      for obs in parsed.get("observations", []) or []:
        code = obs.get("loinc_code")
        val = obs.get("value")
        if code and val is not None:
          series.setdefault(code, []).append(float(val))
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
