"""SQLite connection management and schema initialization.

We use the stdlib ``sqlite3`` module (no ORM) to keep the PyInstaller bundle
small and dependency-light. A single database file holds the entire
application state so it is trivial to back up, and forms the basis for the
portable League / Season / Game export files added in a later phase.
"""
from __future__ import annotations

import os
import secrets
import sqlite3
import threading
from pathlib import Path

# Public player IDs: 8 characters, unambiguous upper-case letters + digits.
# Excludes easily-confused glyphs (0/O, 1/I) so the code is easy to read aloud.
_PUBLIC_ID_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
_PUBLIC_ID_LEN = 8


def gen_public_id(existing: set[str] | None = None) -> str:
    """Return a random 8-char alphanumeric player ID unique within ``existing``."""
    existing = existing or set()
    while True:
        code = "".join(secrets.choice(_PUBLIC_ID_ALPHABET) for _ in range(_PUBLIC_ID_LEN))
        if code not in existing:
            return code

# ---------------------------------------------------------------------------
# Database location
# ---------------------------------------------------------------------------
# Stored next to the application data. On Windows this ends up under the user's
# app directory when packaged; during development it lives in the project root.
_DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "baseball.db"

_db_path = Path(os.environ.get("BASEBALL_DB", str(_DEFAULT_DB)))
_local = threading.local()


def set_db_path(path: str | os.PathLike) -> None:
    """Override the database file location (used by tests / import-load)."""
    BASE_DIR = Path(__file__).resolve().parent.parent
    _db_path = BASE_DIR / "data" / "mi_base.db" 
    # Drop any cached connection on this thread so the new path takes effect.
    conn = getattr(_local, "conn", None)
    if conn is not None:
        conn.close()
        _local.conn = None


def get_db_path() -> Path:
    return _db_path


def get_conn() -> sqlite3.Connection:
    """Return a per-thread SQLite connection with sane defaults."""
    conn = getattr(_local, "conn", None)
    if conn is None:
        _db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(_db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        _local.conn = conn
    return conn


def init_db() -> None:
    """Create all tables if they do not yet exist, then run light migrations."""
    conn = get_conn()
    conn.executescript(SCHEMA)
    _migrate(conn)
    conn.commit()


def _migrate(conn: sqlite3.Connection) -> None:
    """Idempotent, additive migrations for pre-existing databases.

    New columns/tables introduced by later phases are added here so an existing
    ``baseball.db`` upgrades in place without losing data.
    """
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(games)").fetchall()}
    if "pitch_tracking" not in cols:
        conn.execute("ALTER TABLE games ADD COLUMN pitch_tracking INTEGER NOT NULL DEFAULT 0")
    # Phase 4/5: players gain a default primary position.
    pcols = {r["name"] for r in conn.execute("PRAGMA table_info(players)").fetchall()}
    if "primary_position" not in pcols:
        conn.execute("ALTER TABLE players ADD COLUMN primary_position TEXT")
    # Phase 5: players gain a human-visible random public ID (10 alnum chars).
    if "public_id" not in pcols:
        conn.execute("ALTER TABLE players ADD COLUMN public_id TEXT")
    # Backfill any players still missing a public_id (new column or legacy rows).
    missing = conn.execute(
        "SELECT id FROM players WHERE public_id IS NULL OR public_id = ''"
    ).fetchall()
    if missing:
        existing = {
            r["public_id"]
            for r in conn.execute(
                "SELECT public_id FROM players WHERE public_id IS NOT NULL"
            ).fetchall()
        }
        for r in missing:
            pid = gen_public_id(existing)
            existing.add(pid)
            conn.execute("UPDATE players SET public_id=? WHERE id=?", (pid, r["id"]))
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_players_public_id "
        "ON players(public_id)"
    )
    # Phase 6: batted-ball drop location (normalised 0..1 field coords) so the
    # scorer can record where a ball actually landed on the field diagram and
    # the spray chart plots the true location instead of an estimate.
    ecols = {r["name"] for r in conn.execute("PRAGMA table_info(game_events)").fetchall()}
    if "hit_x" not in ecols:
        conn.execute("ALTER TABLE game_events ADD COLUMN hit_x REAL")
    if "hit_y" not in ecols:
        conn.execute("ALTER TABLE game_events ADD COLUMN hit_y REAL")
    # Multiple errors on a single play: JSON array of fielder player_ids charged
    # with an error (e.g. an errant throw AND a drop). ``error_on`` remains the
    # primary/first error for backward compatibility; ``errors_json`` is the
    # authoritative full list when present.
    if "errors_json" not in ecols:
        conn.execute("ALTER TABLE game_events ADD COLUMN errors_json TEXT")
    # Phase 9: store game duration / delay with second precision so the wrap-up
    # form can accept HH:MM:SS. ``duration_min``/``delay_min`` are kept in sync
    # (whole minutes) for backward compatibility with earlier reports/stats.
    if "duration_sec" not in cols:
        conn.execute("ALTER TABLE games ADD COLUMN duration_sec INTEGER")
    if "delay_sec" not in cols:
        conn.execute("ALTER TABLE games ADD COLUMN delay_sec INTEGER")
    # game_pitches table (Phase 3) -- created via executescript below if absent.
    conn.executescript(PITCH_SCHEMA)


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------
# Design notes:
#  * Players and Teams are GLOBAL entities with stable primary keys, so a
#    player's identity (and therefore their accumulated history) persists
#    across every league and season -- this satisfies the "assign IDs so their
#    progress is kept across leagues and seasons" requirement.
#  * season_teams links which teams participate in a given season.
#  * roster links a player to a team WITHIN a season, carrying the jersey
#    number and primary position for that stint. The same global player can
#    appear on different teams in different seasons while keeping one identity.
SCHEMA = """
CREATE TABLE IF NOT EXISTS leagues (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    abbrev      TEXT,
    level       TEXT,            -- e.g. 'MLB', 'AAA', 'College'
    notes       TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS seasons (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    league_id   INTEGER NOT NULL REFERENCES leagues(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    year        INTEGER,
    start_date  TEXT,
    end_date    TEXT,
    notes       TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS teams (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    abbrev      TEXT,
    city        TEXT,
    color       TEXT,            -- accent color for UI / spray charts
    notes       TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS players (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    first_name  TEXT NOT NULL,
    last_name   TEXT NOT NULL,
    bats        TEXT,            -- L / R / S (switch)
    throws      TEXT,            -- L / R
    primary_position TEXT,       -- default field position (P,C,1B..RF,DH,UT)
    public_id   TEXT,            -- human-visible random 8-char alnum ID
    birthdate   TEXT,
    height_cm   INTEGER,
    weight_kg   INTEGER,
    notes       TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS season_teams (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    season_id   INTEGER NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
    team_id     INTEGER NOT NULL REFERENCES teams(id)   ON DELETE CASCADE,
    UNIQUE(season_id, team_id)
);

CREATE TABLE IF NOT EXISTS roster (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    season_id   INTEGER NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
    team_id     INTEGER NOT NULL REFERENCES teams(id)   ON DELETE CASCADE,
    player_id   INTEGER NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    jersey      TEXT,
    position    TEXT,            -- primary position code (P,C,1B,2B,3B,SS,LF,CF,RF,DH)
    UNIQUE(season_id, team_id, player_id)
);

CREATE INDEX IF NOT EXISTS idx_seasons_league ON seasons(league_id);
CREATE INDEX IF NOT EXISTS idx_season_teams_season ON season_teams(season_id);
CREATE INDEX IF NOT EXISTS idx_roster_season ON roster(season_id);
CREATE INDEX IF NOT EXISTS idx_roster_team ON roster(team_id);
CREATE INDEX IF NOT EXISTS idx_roster_player ON roster(player_id);

-- ===========================================================================
-- Phase 2: Live Game Scorer
-- ===========================================================================
-- A game belongs to a season and links two teams. All the professional match
-- metadata (venue, umpires, scorer, weather, scheduled/actual start) lives on
-- the game row. The game is auto-saved continuously because every scoring
-- action is an immediately-persisted row -- "save/load at any time" is simply
-- reopening the game.
CREATE TABLE IF NOT EXISTS games (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    season_id       INTEGER NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
    away_team_id    INTEGER NOT NULL REFERENCES teams(id),
    home_team_id    INTEGER NOT NULL REFERENCES teams(id),
    -- Info tab
    game_date       TEXT,
    venue           TEXT,
    ump_home        TEXT,
    ump_first       TEXT,
    ump_second      TEXT,
    ump_third       TEXT,
    scorer          TEXT,
    scheduled_start TEXT,
    actual_start    TEXT,
    weather         TEXT,
    temperature     TEXT,
    wind            TEXT,
    attendance      INTEGER,
    notes           TEXT,
    -- Rules / lifecycle
    regulation_innings INTEGER NOT NULL DEFAULT 9,
    status          TEXT NOT NULL DEFAULT 'setup',  -- setup|in_progress|paused|final|forfeited
    end_reason      TEXT,        -- regulation|walkoff|called|forfeit|knockout|manual
    forfeit_team_id INTEGER,     -- team that FORFEITED (loses)
    -- Wrap-up
    duration_min    INTEGER,
    delay_min       INTEGER,
    duration_sec    INTEGER,      -- HH:MM:SS game duration, second precision
    delay_sec       INTEGER,      -- HH:MM:SS total delay, second precision
    win_pitcher_id  INTEGER REFERENCES players(id),
    loss_pitcher_id INTEGER REFERENCES players(id),
    save_pitcher_id INTEGER REFERENCES players(id),
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Batting order + defensive positions for each side. Substitutions are new
-- rows sharing a batting slot with a higher `entered_seq` and a `sub_for`.
CREATE TABLE IF NOT EXISTS game_lineups (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id       INTEGER NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    side          TEXT NOT NULL,          -- 'away' | 'home'
    batting_order INTEGER NOT NULL,       -- 1..9 (0 = bench/extra)
    player_id     INTEGER NOT NULL REFERENCES players(id),
    position      TEXT,                   -- P,C,1B,2B,3B,SS,LF,CF,RF,DH
    is_starter    INTEGER NOT NULL DEFAULT 1,
    entered_seq   INTEGER NOT NULL DEFAULT 0,
    sub_for       INTEGER,                -- lineup id being replaced
    active        INTEGER NOT NULL DEFAULT 1
);

-- Unified, ordered event log. Every scoring action is one row, which makes the
-- game trivially replayable, undoable (delete highest seq) and the single
-- source of truth for the Phase 4 statistics engine.
--   kind = 'PA'   plate appearance (at-bat outcome)
--   kind = 'BR'   baserunning / battery event (SB, CS, PO, WP, PB, BK)
--   kind = 'SUB'  substitution marker
CREATE TABLE IF NOT EXISTS game_events (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id      INTEGER NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    seq          INTEGER NOT NULL,       -- monotonically increasing per game
    inning       INTEGER NOT NULL,
    half         TEXT NOT NULL,          -- 'T' (top/away bats) | 'B' (bottom/home bats)
    kind         TEXT NOT NULL,
    -- participants
    batter_id    INTEGER REFERENCES players(id),
    pitcher_id   INTEGER REFERENCES players(id),
    catcher_id   INTEGER REFERENCES players(id),
    runner_id    INTEGER REFERENCES players(id),
    -- outcome
    result       TEXT,                   -- result code (see scoring.py)
    detail       TEXT,                   -- fielders e.g. '6-4-3'
    bb_type      TEXT,                   -- GB | LD | FB | PU
    contact      TEXT,                   -- soft | avg | hard
    from_base    INTEGER,                -- BR events: 0=home plate/batter,1,2,3
    to_base      TEXT,                   -- 1,2,3,'H' scored, 'OUT'
    charged_to   TEXT,                   -- 'pitcher' | 'catcher' (attribution)
    credited_to  TEXT,                   -- 'catcher' etc.
    is_error     INTEGER NOT NULL DEFAULT 0,
    error_on     INTEGER REFERENCES players(id),
    errors_json  TEXT,                   -- JSON array of fielder ids (multi-error)
    rbi          INTEGER NOT NULL DEFAULT 0,
    outs_recorded INTEGER NOT NULL DEFAULT 0,
    runs_scored  INTEGER NOT NULL DEFAULT 0,
    advances    TEXT,                   -- JSON: explicit runner movements
    hit_x        REAL,                   -- batted-ball drop location X (0..1)
    hit_y        REAL,                   -- batted-ball drop location Y (0..1)
    description  TEXT,                   -- human-readable summary
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_games_season ON games(season_id);
CREATE INDEX IF NOT EXISTS idx_lineups_game ON game_lineups(game_id);
CREATE INDEX IF NOT EXISTS idx_events_game ON game_events(game_id, seq);
"""

# ---------------------------------------------------------------------------
# Phase 3: optional pitch-by-pitch tracking
# ---------------------------------------------------------------------------
# Each pitch belongs to a game and (once the plate appearance resolves) to the
# PA event that terminated the at-bat. Pitches are attached to their PA event
# when the result is recorded, so deleting the event (undo) cascades to its
# pitches and the log stays perfectly consistent and replayable.
#   zone       1..9  = 3x3 strike-zone grid (1=up-in ... 9=low-away, catcher's
#                      view, left-to-right, top-to-bottom); 11..14 = the four
#                      outside "chase" quadrants (Statcast-style).
#   result     B  = ball, CS = called strike, SS = swinging strike,
#              F  = foul, IP = in play, HBP = hit by pitch.
PITCH_SCHEMA = """
CREATE TABLE IF NOT EXISTS game_pitches (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id      INTEGER NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    event_id     INTEGER REFERENCES game_events(id) ON DELETE CASCADE,
    inning       INTEGER,
    half         TEXT,
    batter_id    INTEGER REFERENCES players(id),
    pitcher_id   INTEGER REFERENCES players(id),
    pitch_num    INTEGER NOT NULL,       -- 1-based within the plate appearance
    zone         INTEGER,                -- 1..9 in-zone, 11..14 out-of-zone
    velocity     REAL,                   -- mph
    pitch_type   TEXT,                   -- FF,SI,FC,SL,CB,CH,SP,KN ...
    result       TEXT,                   -- B|CS|SS|F|IP|HBP
    is_strike    INTEGER NOT NULL DEFAULT 0,
    is_swing     INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_pitches_game ON game_pitches(game_id);
CREATE INDEX IF NOT EXISTS idx_pitches_event ON game_pitches(event_id);
"""
