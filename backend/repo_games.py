"""Data-access layer for the Live Game Scorer (Phase 2)."""
from __future__ import annotations

import json
from typing import Any

from .db import get_conn
from .scoring import compute_state


def _rows(cur):
    return [dict(r) for r in cur.fetchall()]


def _one(cur):
    r = cur.fetchone()
    return dict(r) if r else None


_GAME_FIELDS = [
    "season_id", "away_team_id", "home_team_id", "game_date", "venue",
    "ump_home", "ump_first", "ump_second", "ump_third", "scorer",
    "scheduled_start", "actual_start", "weather", "temperature", "wind",
    "attendance", "notes", "regulation_innings",
]


# ---------------------------------------------------------------------------
# Games
# ---------------------------------------------------------------------------
def list_games(season_id: int | None = None, team_id: int | None = None) -> list[dict]:
    c = get_conn()
    sql = (
        "SELECT g.*, s.name AS season_name, "
        "ta.name AS away_name, ta.abbrev AS away_abbrev, "
        "th.name AS home_name, th.abbrev AS home_abbrev "
        "FROM games g JOIN seasons s ON s.id=g.season_id "
        "JOIN teams ta ON ta.id=g.away_team_id "
        "JOIN teams th ON th.id=g.home_team_id"
    )
    where, params = [], []
    if season_id is not None:
        where.append("g.season_id=?"); params.append(season_id)
    if team_id is not None:
        where.append("(g.away_team_id=? OR g.home_team_id=?)"); params += [team_id, team_id]
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY g.game_date DESC, g.id DESC"
    games = _rows(c.execute(sql, params))
    for g in games:
        st = compute_state(g["id"])
        g["score"] = st["score"]
    return games


def get_game(game_id: int) -> dict | None:
    c = get_conn()
    g = _one(c.execute(
        "SELECT g.*, s.name AS season_name, s.league_id AS league_id, "
        "ta.name AS away_name, ta.abbrev AS away_abbrev, ta.color AS away_color, "
        "th.name AS home_name, th.abbrev AS home_abbrev, th.color AS home_color "
        "FROM games g JOIN seasons s ON s.id=g.season_id "
        "JOIN teams ta ON ta.id=g.away_team_id "
        "JOIN teams th ON th.id=g.home_team_id WHERE g.id=?", (game_id,)))
    return g


def create_game(data: dict) -> dict:
    c = get_conn()
    cols = [f for f in _GAME_FIELDS if f in data]
    ph = ",".join(["?"] * len(cols))
    cur = c.execute(
        f"INSERT INTO games ({','.join(cols)}) VALUES ({ph})",
        [data.get(f) for f in cols])
    c.commit()
    return get_game(cur.lastrowid)


def update_game(game_id: int, data: dict) -> dict | None:
    c = get_conn()
    cols = [f for f in _GAME_FIELDS if f in data]
    if cols:
        c.execute(
            f"UPDATE games SET {', '.join(f'{f}=?' for f in cols)} WHERE id=?",
            [data.get(f) for f in cols] + [game_id])
        c.commit()
    return get_game(game_id)


def set_game_fields(game_id: int, fields: dict) -> dict | None:
    """Update lifecycle / wrap-up fields (status, wrap-up, forfeit, etc.)."""
    allowed = {
        "status", "end_reason", "forfeit_team_id", "duration_min", "delay_min",
        "duration_sec", "delay_sec",
        "win_pitcher_id", "loss_pitcher_id", "save_pitcher_id", "actual_start",
        "pitch_tracking",
    }
    cols = [f for f in fields if f in allowed]
    if cols:
        c = get_conn()
        c.execute(
            f"UPDATE games SET {', '.join(f'{f}=?' for f in cols)} WHERE id=?",
            [fields.get(f) for f in cols] + [game_id])
        c.commit()
    return get_game(game_id)


def delete_game(game_id: int) -> None:
    c = get_conn()
    c.execute("DELETE FROM games WHERE id=?", (game_id,))
    c.commit()


# ---------------------------------------------------------------------------
# Lineups
# ---------------------------------------------------------------------------
def get_lineups(game_id: int) -> dict[str, list[dict]]:
    c = get_conn()
    rows = _rows(c.execute(
        "SELECT l.*, (p.first_name||' '||p.last_name) AS full_name "
        "FROM game_lineups l JOIN players p ON p.id=l.player_id "
        "WHERE l.game_id=? AND l.active=1 ORDER BY l.side, l.batting_order, l.entered_seq",
        (game_id,)))
    out = {"away": [], "home": []}
    for r in rows:
        out[r["side"]].append(r)
    return out


def set_lineup(game_id: int, side: str, entries: list[dict]) -> dict:
    """Replace the starting lineup for one side."""
    c = get_conn()
    c.execute("DELETE FROM game_lineups WHERE game_id=? AND side=?", (game_id, side))
    for e in entries:
        c.execute(
            "INSERT INTO game_lineups (game_id, side, batting_order, player_id, position, is_starter) "
            "VALUES (?,?,?,?,?,1)",
            (game_id, side, e.get("batting_order"), e.get("player_id"), e.get("position")))
    c.commit()
    return get_lineups(game_id)


def substitute(game_id: int, data: dict) -> dict:
    """Replace a lineup slot with a new player (pinch hit / defensive sub)."""
    c = get_conn()
    old = _one(c.execute("SELECT * FROM game_lineups WHERE id=?", (data["lineup_id"],)))
    seq = _next_seq(game_id)
    if old:
        c.execute("UPDATE game_lineups SET active=0 WHERE id=?", (old["id"],))
        c.execute(
            "INSERT INTO game_lineups (game_id, side, batting_order, player_id, position, "
            "is_starter, entered_seq, sub_for) VALUES (?,?,?,?,?,0,?,?)",
            (game_id, old["side"], old["batting_order"], data["player_id"],
             data.get("position") or old["position"], seq, old["id"]))
    c.commit()
    return get_lineups(game_id)


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------
def _next_seq(game_id: int) -> int:
    c = get_conn()
    row = c.execute("SELECT COALESCE(MAX(seq),0)+1 AS n FROM game_events WHERE game_id=?",
                    (game_id,)).fetchone()
    return row["n"]


def list_events(game_id: int) -> list[dict]:
    c = get_conn()
    return _rows(c.execute(
        "SELECT e.*, (bp.first_name||' '||bp.last_name) AS batter_name, "
        "(rp.first_name||' '||rp.last_name) AS runner_name "
        "FROM game_events e "
        "LEFT JOIN players bp ON bp.id=e.batter_id "
        "LEFT JOIN players rp ON rp.id=e.runner_id "
        "WHERE e.game_id=? ORDER BY e.seq", (game_id,)))


def add_event(game_id: int, data: dict) -> dict:
    c = get_conn()
    seq = _next_seq(game_id)
    adv = data.get("advances")
    errs = data.get("errors_json")
    if errs is None and data.get("error_on") is not None:
        errs = [data.get("error_on")]
    # Normalise to a de-duplicated list of ints; keep error_on as the primary.
    err_list = None
    if errs:
        seen = []
        for x in errs:
            try:
                xi = int(x)
            except (TypeError, ValueError):
                continue
            if xi not in seen:
                seen.append(xi)
        err_list = seen or None
    primary_err = data.get("error_on")
    if primary_err is None and err_list:
        primary_err = err_list[0]
    is_err = 1 if (data.get("is_error") or err_list) else 0
    # Phase 9: Catcher's Interference is, by rule, an error charged to the
    # defending catcher. Enforce this server-side so the error is attributed to
    # the catcher and counts toward the fielding team's E regardless of what the
    # client sent.
    if (data.get("result") or "").upper() == "CI":
        cat_id = data.get("catcher_id")
        if cat_id is not None:
            try:
                cat_id = int(cat_id)
            except (TypeError, ValueError):
                cat_id = None
        if cat_id is not None:
            err_list = err_list or []
            if cat_id not in err_list:
                err_list.append(cat_id)
            if primary_err is None:
                primary_err = cat_id
        is_err = 1
    cur = c.execute(
        "INSERT INTO game_events (game_id, seq, inning, half, kind, batter_id, pitcher_id, "
        "catcher_id, runner_id, result, detail, bb_type, contact, from_base, to_base, "
        "charged_to, credited_to, is_error, error_on, errors_json, rbi, outs_recorded, runs_scored, "
        "advances, hit_x, hit_y, description) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (game_id, seq, data.get("inning"), data.get("half"), data.get("kind", "PA"),
         data.get("batter_id"), data.get("pitcher_id"), data.get("catcher_id"),
         data.get("runner_id"), data.get("result"), data.get("detail"),
         data.get("bb_type"), data.get("contact"), data.get("from_base"),
         data.get("to_base"), data.get("charged_to"), data.get("credited_to"),
         is_err, primary_err,
         json.dumps(err_list) if err_list else None,
         data.get("rbi", 0), data.get("outs_recorded", 0), data.get("runs_scored", 0),
         json.dumps(adv) if adv is not None else None,
         data.get("hit_x"), data.get("hit_y"), data.get("description")))
    event_id = cur.lastrowid
    # Phase 3: attach any pitch-by-pitch sequence recorded for this PA.
    pitches = data.get("pitches") or []
    for i, p in enumerate(pitches, start=1):
        _insert_pitch(c, game_id, event_id, data, i, p)
    if get_game(game_id)["status"] == "setup":
        c.execute("UPDATE games SET status='in_progress' WHERE id=?", (game_id,))
    c.commit()
    return compute_state(game_id)


_PITCH_STRIKE = {"CS", "SS", "F"}
_PITCH_SWING = {"SS", "F", "IP"}


def _insert_pitch(c, game_id: int, event_id: int | None, data: dict, num: int, p: dict) -> None:
    res = p.get("result")
    c.execute(
        "INSERT INTO game_pitches (game_id, event_id, inning, half, batter_id, pitcher_id, "
        "pitch_num, zone, velocity, pitch_type, result, is_strike, is_swing) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (game_id, event_id, data.get("inning"), data.get("half"),
         data.get("batter_id"), data.get("pitcher_id"), p.get("pitch_num", num),
         p.get("zone"), p.get("velocity"), p.get("pitch_type"), res,
         1 if res in _PITCH_STRIKE else 0, 1 if res in _PITCH_SWING else 0))


def list_pitches(game_id: int) -> list[dict]:
    c = get_conn()
    return _rows(c.execute(
        "SELECT * FROM game_pitches WHERE game_id=? ORDER BY id", (game_id,)))


def undo_last(game_id: int) -> dict:
    c = get_conn()
    row = c.execute("SELECT id FROM game_events WHERE game_id=? ORDER BY seq DESC LIMIT 1",
                    (game_id,)).fetchone()
    if row:
        c.execute("DELETE FROM game_events WHERE id=?", (row["id"],))
        c.commit()
    return compute_state(game_id)


def line_score(game_id: int) -> dict:
    """Assemble the classic R/H/E line score for display."""
    st = compute_state(game_id)
    innings = sorted(st["line"].keys())
    reg = st["regulation_innings"]
    max_inn = max([reg] + innings) if innings else reg
    rows = {"away": [], "home": []}
    for i in range(1, max_inn + 1):
        cell = st["line"].get(i, {"T": 0, "B": 0})
        rows["away"].append(cell.get("T", 0))
        rows["home"].append(cell.get("B", 0))
    return {
        "innings": list(range(1, max_inn + 1)),
        "away": rows["away"], "home": rows["home"],
        "totals": {
            "away": {"R": st["score"]["away"], "H": st["hits"]["away"], "E": st["errors"]["away"]},
            "home": {"R": st["score"]["home"], "H": st["hits"]["home"], "E": st["errors"]["home"]},
        },
        "state": st,
    }
