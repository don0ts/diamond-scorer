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

from .db import get_conn, init_db, gen_public_id

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
        # BEGIN IMMEDIATE reserves the write lock up front. A plain (deferred)
        # BEGIN would start as a reader and only try to upgrade to a writer on
        # the first INSERT; under WAL that upgrade can fail outright with
        # SQLITE_BUSY_SNAPSHOT (surfaced as "database is locked") and is NOT
        # retried by busy_timeout. Taking the lock immediately makes the
        # busy_timeout wait-and-retry instead.
        conn.execute("BEGIN IMMEDIATE")
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


# ===========================================================================
# Per-game export / import (portable single game)
# ===========================================================================
# A *game* archive bundles one game together with every entity it depends on:
# its league, season, the two teams, the season<->team links, the rosters for
# those teams in that season, all players that appear anywhere in the game
# (lineups / events / pitches / decisions), and the game's own lineups, events
# and pitches. Importing it into another database is additive and de-duplicates
# existing "profiles" (players by public_id, teams by name, leagues by name,
# seasons by league+name+year, roster/season_team links by their natural keys)
# while remapping all foreign keys to the local ids.
GAME_FORMAT = "diamondscorer-game"

# Columns that hold a player id on each child table (remapped on import).
_PLAYER_FK = {
    "game_lineups": ("player_id",),
    "game_events": ("batter_id", "pitcher_id", "catcher_id", "runner_id",
                    "error_on"),
    "game_pitches": ("batter_id", "pitcher_id"),
}
_GAME_PLAYER_FK = ("win_pitcher_id", "loss_pitcher_id", "save_pitcher_id")


def _rows(conn, sql, params=()):
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def _in_clause(n):
    return ",".join("?" for _ in range(n))


def export_game_bytes(game_id: int) -> bytes:
    """Serialise one game + its dependencies to an in-memory ``.zip``."""
    init_db()
    conn = get_conn()
    grow = conn.execute("SELECT * FROM games WHERE id=?", (game_id,)).fetchone()
    if not grow:
        raise ValueError("Game not found.")
    game = dict(grow)
    season = dict(conn.execute("SELECT * FROM seasons WHERE id=?",
                               (game["season_id"],)).fetchone())
    league = dict(conn.execute("SELECT * FROM leagues WHERE id=?",
                               (season["league_id"],)).fetchone())
    team_ids = [t for t in {game["away_team_id"], game["home_team_id"]} if t]
    teams = _rows(conn, "SELECT * FROM teams WHERE id IN (%s)"
                  % _in_clause(len(team_ids)), tuple(team_ids))
    lineups = _rows(conn, "SELECT * FROM game_lineups WHERE game_id=? ORDER BY id",
                    (game_id,))
    events = _rows(conn, "SELECT * FROM game_events WHERE game_id=? ORDER BY id",
                   (game_id,))
    pitches = _rows(conn, "SELECT * FROM game_pitches WHERE game_id=? ORDER BY id",
                    (game_id,))
    roster = _rows(conn, "SELECT * FROM roster WHERE season_id=? AND team_id IN (%s)"
                   % _in_clause(len(team_ids)), (season["id"], *team_ids)) \
        if team_ids else []
    season_teams = _rows(conn, "SELECT * FROM season_teams WHERE season_id=? "
                         "AND team_id IN (%s)" % _in_clause(len(team_ids)),
                         (season["id"], *team_ids)) if team_ids else []

    # Collect every player id referenced anywhere in the bundle.
    pid: set[int] = set()
    for ln in lineups:
        if ln.get("player_id"):
            pid.add(ln["player_id"])
    for ev in events:
        for k in _PLAYER_FK["game_events"]:
            if ev.get(k):
                pid.add(ev[k])
        if ev.get("errors_json"):
            try:
                pid.update(int(x) for x in json.loads(ev["errors_json"]))
            except Exception:
                pass
        if ev.get("advances"):
            try:
                for v in json.loads(ev["advances"]).values():
                    if v:
                        pid.add(int(v))
            except Exception:
                pass
    for p in pitches:
        for k in _PLAYER_FK["game_pitches"]:
            if p.get(k):
                pid.add(p[k])
    for k in _GAME_PLAYER_FK:
        if game.get(k):
            pid.add(game[k])
    for r in roster:
        if r.get("player_id"):
            pid.add(r["player_id"])
    pid.discard(None)
    players = _rows(conn, "SELECT * FROM players WHERE id IN (%s)"
                    % _in_clause(len(pid)), tuple(pid)) if pid else []

    payload = {
        "format": GAME_FORMAT,
        "version": FORMAT_VERSION,
        "exported_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "league": league,
        "season": season,
        "teams": teams,
        "players": players,
        "roster": roster,
        "season_teams": season_teams,
        "game": game,
        "lineups": lineups,
        "events": events,
        "pitches": pitches,
    }
    manifest = {
        "format": GAME_FORMAT,
        "version": FORMAT_VERSION,
        "exported_at": payload["exported_at"],
        "game": "%s @ %s" % (
            next((t["name"] for t in teams if t["id"] == game["away_team_id"]), "?"),
            next((t["name"] for t in teams if t["id"] == game["home_team_id"]), "?")),
        "game_date": game.get("game_date"),
        "counts": {"players": len(players), "teams": len(teams),
                   "lineups": len(lineups), "events": len(events),
                   "pitches": len(pitches)},
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))
        zf.writestr("game.json", json.dumps(payload))
    return buf.getvalue()


def _insert_row(conn, table, row, overrides=None):
    """Insert ``row`` into ``table`` (minus id), applying ``overrides``.

    Only columns that exist in the live schema are written, so an archive made
    by an older/newer build still loads. Returns the new row id.
    """
    live = _table_columns(conn, table)
    overrides = overrides or {}
    data = {}
    for c in live:
        if c == "id":
            continue
        if c in overrides:
            data[c] = overrides[c]
        elif c in row:
            data[c] = row[c]
    cols = list(data.keys())
    sql = "INSERT INTO %s (%s) VALUES (%s)" % (
        table, ", ".join(cols), ", ".join("?" for _ in cols))
    cur = conn.execute(sql, [data[c] for c in cols])
    return cur.lastrowid


def import_game(data: bytes) -> dict:
    """Load one game archive into the current DB, de-duplicating profiles."""
    init_db()
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            names = set(zf.namelist())
            if "game.json" not in names:
                raise ValueError(
                    "Not a Diamond Scorer game file (game.json missing).")
            payload = json.loads(zf.read("game.json").decode("utf-8"))
    except zipfile.BadZipFile as exc:
        raise ValueError("File is not a valid .zip archive: %s" % exc)
    if "game" not in payload:
        raise ValueError("Game file is malformed (no 'game' section).")

    conn = get_conn()
    conn.commit()
    try:
        # BEGIN IMMEDIATE (not a plain deferred BEGIN): this transaction reads
        # (dedup lookups) BEFORE it writes, so a deferred begin would take a
        # read snapshot and then fail to upgrade to a writer with
        # SQLITE_BUSY_SNAPSHOT ("database is locked") whenever another request
        # wrote in between -- and that error is not covered by busy_timeout.
        # Reserving the write lock immediately lets busy_timeout wait instead.
        conn.execute("BEGIN IMMEDIATE")
        result = _import_game_tx(conn, payload)
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return result


def _import_game_tx(conn, payload) -> dict:
    # --- league (dedup by name) ---
    lg = payload["league"]
    row = conn.execute("SELECT id FROM leagues WHERE name=?",
                       (lg.get("name"),)).fetchone()
    league_id = row["id"] if row else _insert_row(conn, "leagues", lg)

    # --- season (dedup by league + name + year) ---
    se = payload["season"]
    row = conn.execute(
        "SELECT id FROM seasons WHERE league_id=? AND name=? "
        "AND IFNULL(year,-1)=IFNULL(?,-1)",
        (league_id, se.get("name"), se.get("year"))).fetchone()
    season_id = row["id"] if row else _insert_row(
        conn, "seasons", se, {"league_id": league_id})

    # --- teams (dedup by name) ---
    team_map = {}
    for t in payload.get("teams", []):
        row = conn.execute("SELECT id FROM teams WHERE name=?",
                           (t.get("name"),)).fetchone()
        team_map[t["id"]] = row["id"] if row else _insert_row(conn, "teams", t)

    # --- players (dedup by public_id) ---
    player_map = {}
    existing_pub = {r["public_id"] for r in conn.execute(
        "SELECT public_id FROM players WHERE public_id IS NOT NULL").fetchall()}
    new_players = 0
    for p in payload.get("players", []):
        pub = p.get("public_id")
        row = conn.execute("SELECT id FROM players WHERE public_id=?",
                           (pub,)).fetchone() if pub else None
        if row:
            player_map[p["id"]] = row["id"]
            continue
        ov = {}
        if not pub or pub in existing_pub:
            ov["public_id"] = gen_public_id(existing_pub)
        existing_pub.add(ov.get("public_id", pub))
        player_map[p["id"]] = _insert_row(conn, "players", p, ov)
        new_players += 1

    def premap(old):
        return player_map.get(old) if old else old

    # --- season_teams links (dedup by season+team) ---
    for st in payload.get("season_teams", []):
        tnew = team_map.get(st.get("team_id"))
        if not tnew:
            continue
        if not conn.execute("SELECT 1 FROM season_teams WHERE season_id=? "
                            "AND team_id=?", (season_id, tnew)).fetchone():
            _insert_row(conn, "season_teams", st,
                        {"season_id": season_id, "team_id": tnew})

    # --- roster (dedup by season+team+player) ---
    for r in payload.get("roster", []):
        tnew = team_map.get(r.get("team_id"))
        pnew = player_map.get(r.get("player_id"))
        if not tnew or not pnew:
            continue
        if not conn.execute("SELECT 1 FROM roster WHERE season_id=? AND team_id=? "
                            "AND player_id=?", (season_id, tnew, pnew)).fetchone():
            _insert_row(conn, "roster", r, {"season_id": season_id,
                                            "team_id": tnew, "player_id": pnew})

    # --- game (dedup by season+teams+date to avoid re-importing the same one) ---
    g = payload["game"]
    away = team_map.get(g.get("away_team_id"))
    home = team_map.get(g.get("home_team_id"))
    dup = conn.execute(
        "SELECT id FROM games WHERE season_id=? AND away_team_id=? "
        "AND home_team_id=? AND IFNULL(game_date,'')=IFNULL(?,'')",
        (season_id, away, home, g.get("game_date"))).fetchone()
    if dup:
        return {"ok": True, "duplicate": True, "game_id": dup["id"],
                "new_players": new_players,
                "message": "This game is already in your database."}
    gov = {"season_id": season_id, "away_team_id": away, "home_team_id": home}
    for k in _GAME_PLAYER_FK:
        gov[k] = premap(g.get(k))
    if g.get("forfeit_team_id"):
        gov["forfeit_team_id"] = team_map.get(g["forfeit_team_id"])
    game_id = _insert_row(conn, "games", g, gov)

    # --- lineups (two passes: insert, then fix sub_for self-reference) ---
    lineup_map = {}
    for ln in payload.get("lineups", []):
        lineup_map[ln["id"]] = _insert_row(conn, "game_lineups", ln, {
            "game_id": game_id, "player_id": premap(ln.get("player_id")),
            "sub_for": None})
    for ln in payload.get("lineups", []):
        if ln.get("sub_for") and lineup_map.get(ln["sub_for"]):
            conn.execute("UPDATE game_lineups SET sub_for=? WHERE id=?",
                         (lineup_map[ln["sub_for"]], lineup_map[ln["id"]]))

    # --- events (remap player FKs, errors_json list, advances id values) ---
    event_map = {}
    for ev in payload.get("events", []):
        ov = {"game_id": game_id}
        for k in _PLAYER_FK["game_events"]:
            if k in ev:
                ov[k] = premap(ev.get(k))
        if ev.get("errors_json"):
            try:
                ids = json.loads(ev["errors_json"])
                ov["errors_json"] = json.dumps(
                    [premap(int(x)) for x in ids if premap(int(x))])
            except Exception:
                pass
        if ev.get("advances"):
            try:
                snap = json.loads(ev["advances"])
                ov["advances"] = json.dumps(
                    {k: (premap(int(v)) if v else v) for k, v in snap.items()})
            except Exception:
                pass
        event_map[ev["id"]] = _insert_row(conn, "game_events", ev, ov)

    # --- pitches (remap player FKs + event id) ---
    for p in payload.get("pitches", []):
        ov = {"game_id": game_id}
        for k in _PLAYER_FK["game_pitches"]:
            if k in p:
                ov[k] = premap(p.get(k))
        if p.get("event_id"):
            ov["event_id"] = event_map.get(p["event_id"])
        _insert_row(conn, "game_pitches", p, ov)

    return {"ok": True, "duplicate": False, "game_id": game_id,
            "new_players": new_players,
            "counts": {"lineups": len(lineup_map), "events": len(event_map),
                       "pitches": len(payload.get("pitches", []))}}
