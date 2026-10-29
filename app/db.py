"""SQLite storage for Proofmark.

One file database. Every request gets its own connection (stored on flask.g).
JSON columns are stored as TEXT and decoded by the helpers below.
"""
import json
import os
import sqlite3
from datetime import datetime, timezone

from flask import current_app, g

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    pw_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('creator','reviewer','owner','viewer')),
    team TEXT
);

CREATE TABLE IF NOT EXISTS brand (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    tagline TEXT,
    description TEXT,
    palette TEXT DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS rules (
    id INTEGER PRIMARY KEY,
    code TEXT UNIQUE NOT NULL,
    category TEXT NOT NULL,
    method TEXT NOT NULL CHECK (method IN ('exact','ai','human')),
    kind TEXT NOT NULL,
    text TEXT NOT NULL,
    params TEXT DEFAULT '{}',
    severity TEXT NOT NULL CHECK (severity IN ('high','medium','low')),
    status TEXT NOT NULL DEFAULT 'approved' CHECK (status IN ('proposed','approved','rejected','disabled')),
    ambiguous INTEGER DEFAULT 0,
    ambiguity_reason TEXT,
    source TEXT DEFAULT 'manual',
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS facts (
    id INTEGER PRIMARY KEY,
    code TEXT UNIQUE NOT NULL,
    statement TEXT NOT NULL,
    keywords TEXT DEFAULT '[]',
    value REAL,
    unit TEXT,
    comparison TEXT DEFAULT 'max' CHECK (comparison IN ('max','exact')),
    source TEXT,
    valid_until TEXT,
    confidential INTEGER DEFAULT 0,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS drafts (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    content_type TEXT NOT NULL,
    goal TEXT,
    creator_id INTEGER NOT NULL REFERENCES users(id),
    status TEXT NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft','in_review','changes_requested','approved')),
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS versions (
    id INTEGER PRIMARY KEY,
    draft_id INTEGER NOT NULL REFERENCES drafts(id) ON DELETE CASCADE,
    number INTEGER NOT NULL,
    body TEXT NOT NULL,
    note TEXT,
    created_by INTEGER REFERENCES users(id),
    created_at TEXT,
    locked INTEGER DEFAULT 0,
    UNIQUE (draft_id, number)
);

CREATE TABLE IF NOT EXISTS scans (
    id INTEGER PRIMARY KEY,
    version_id INTEGER NOT NULL REFERENCES versions(id) ON DELETE CASCADE,
    created_at TEXT,
    mode TEXT,
    summary TEXT DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS findings (
    id INTEGER PRIMARY KEY,
    scan_id INTEGER NOT NULL REFERENCES scans(id) ON DELETE CASCADE,
    rule_code TEXT,
    fact_code TEXT,
    category TEXT,
    method TEXT,
    severity TEXT,
    confidence TEXT,
    quote TEXT,
    start INTEGER,
    end INTEGER,
    explanation TEXT,
    evidence TEXT,
    suggestion TEXT,
    claim_state TEXT,
    status TEXT DEFAULT 'open'
        CHECK (status IN ('open','accepted','rejected','dismissed')),
    dismiss_reason TEXT,
    dismiss_note TEXT,
    decided_by INTEGER REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS comments (
    id INTEGER PRIMARY KEY,
    draft_id INTEGER NOT NULL REFERENCES drafts(id) ON DELETE CASCADE,
    version_number INTEGER,
    user_id INTEGER REFERENCES users(id),
    body TEXT NOT NULL,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY,
    draft_id INTEGER REFERENCES drafts(id) ON DELETE CASCADE,
    user_id INTEGER REFERENCES users(id),
    action TEXT NOT NULL,
    detail TEXT,
    created_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_versions_draft ON versions(draft_id);
CREATE INDEX IF NOT EXISTS idx_scans_version ON scans(version_id);
CREATE INDEX IF NOT EXISTS idx_findings_scan ON findings(scan_id);
CREATE INDEX IF NOT EXISTS idx_events_draft ON events(draft_id);
"""

JSON_COLUMNS = {"params", "keywords", "palette", "summary"}


def now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def db_path():
    return current_app.config["DB_PATH"]


def connect(path):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    conn = sqlite3.connect(path, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def get_db():
    if "db" not in g:
        g.db = connect(db_path())
    return g.db


def close_db(_exc=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def init_schema(conn):
    conn.executescript(SCHEMA)
    conn.commit()


def row_to_dict(row):
    if row is None:
        return None
    out = dict(row)
    for key in JSON_COLUMNS & out.keys():
        try:
            out[key] = json.loads(out[key]) if out[key] else ([] if key in ("keywords", "palette") else {})
        except (TypeError, ValueError):
            out[key] = {} if key in ("params", "summary") else []
    return out


def rows(conn, sql, args=()):
    return [row_to_dict(r) for r in conn.execute(sql, args).fetchall()]


def one(conn, sql, args=()):
    return row_to_dict(conn.execute(sql, args).fetchone())


def log_event(conn, action, user_id=None, draft_id=None, detail=None):
    conn.execute(
        "INSERT INTO events (draft_id, user_id, action, detail, created_at) VALUES (?,?,?,?,?)",
        (draft_id, user_id, action, detail, now_iso()),
    )
