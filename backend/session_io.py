"""Portable session export / import.

A *session* here means the entire application database -- every league,
season, team, player, roster, game, lineup, event and pitch. It is dumped to a
single ``.zip`` that can be shared and later loaded back into the app, which is
handy for backups and moving a scorebook between machines.

The archive is schema-tolerant: on export we snapshot each table with whatever
columns currently exist, and on import we only write back the columns that
still exist in the running schema. That way an archive made by an older build
still loads after a migration adds new columns.

Format (inside the zip):
  * ``manifest.json`` -- format version + timestamp + row counts.
  * ``session.json``  -- ``{"tables": {<table>: {"columns": [...],
                         "rows": [[...], ...]}}}``.
"""
from __future__ import annotations

import io
import json
import time
import zipfile

from .db import get_conn, init_db

FORMAT_VERSION = 1

# Parent -> child order so that inserts respect foreign keys. Deletes run in
# the exact reverse of this list.
TABLES = [
    "leagues",
    "teams",
    "players",
    "seasons",
    "season_teams",
    "roster",
    "games",
    "game_lineups",
    "game_events",
    "game_pitches",
]


def _table_columns(conn, table: str) -> list[str]:
    return [r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]


def export_session_bytes() -> bytes:
    """Serialise the whole database to an in-memory ``.zip`` and return bytes."""
    init_db()
    conn = get_conn()
    tables: dict[str, dict] = {}
    counts: dict[str, int] = {}
    for table in TABLES:
        cols = _table_columns(conn, table)
        if not cols:
            continue
        col_sql = ", ".join(cols)
        rows = conn.execute(f"SELECT {col_sql} FROM {table}").fetchall()
        tables[table] = {"columns": cols, "rows": [list(r) for r in rows]}
        counts[table] = len(rows)
    manifest = {
        "format": "diamondscorer-session",
        "version": FORMAT_VERSION,
        "exported_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "counts": counts,
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))
        zf.writestr("session.json", json.dumps({"tables": tables}))
    return buf.getvalue()


def import_session_bytes(data: bytes) -> dict:
    """Replace the current database contents with the archive's data.

    This is a full restore: every table listed in the archive is wiped and
    repopulated. Returns a summary dict of how many rows were loaded per table.
    """
    init_db()
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            names = set(zf.namelist())
            if "session.json" not in names:
                raise ValueError("Not a Diamond Scorer session file (session.json missing).")
            payload = json.loads(zf.read("session.json").decode("utf-8"))
    except zipfile.BadZipFile as exc:
        raise ValueError(f"File is not a valid .zip archive: {exc}")
    dumped = payload.get("tables")
    if not isinstance(dumped, dict):
        raise ValueError("Session file is malformed (no 'tables' section).")

    conn = get_conn()
    # Foreign-key enforcement cannot be toggled inside a transaction, so make
    # sure nothing is pending, disable it, do the swap atomically, re-enable.
    conn.commit()
    conn.execute("PRAGMA foreign_keys = OFF")
    summary: dict[str, int] = {}
    try:
        conn.execute("BEGIN")
        # Wipe child-first.
        for table in reversed(TABLES):
            if _table_columns(conn, table):
                conn.execute(f"DELETE FROM {table}")
        # Insert parent-first, intersecting dumped columns with the live schema.
        for table in TABLES:
            live = _table_columns(conn, table)
            if not live:
                continue
            block = dumped.get(table)
            if not block:
                summary[table] = 0
                continue
            dumped_cols = block.get("columns", [])
            rows = block.get("rows", [])
            use = [c for c in dumped_cols if c in live]
            if not use:
                summary[table] = 0
                continue
            idx = [dumped_cols.index(c) for c in use]
            placeholders = ", ".join("?" for _ in use)
            col_sql = ", ".join(use)
            sql = f"INSERT INTO {table} ({col_sql}) VALUES ({placeholders})"
            conn.executemany(sql, [[row[i] for i in idx] for row in rows])
            summary[table] = len(rows)
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        conn.execute("PRAGMA foreign_keys = ON")
        raise
    conn.execute("PRAGMA foreign_keys = ON")
    # Integrity sanity check after re-enabling FK enforcement.
    bad = conn.execute("PRAGMA foreign_key_check").fetchall()
    if bad:
        raise ValueError(
            f"Imported data failed foreign-key validation ({len(bad)} issue(s)).")
    return {"ok": True, "loaded": summary}
