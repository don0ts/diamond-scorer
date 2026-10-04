"""Scoring domain: result codes + authoritative game-state replay engine.

The game_events table stores primitive facts about each play. This module is
the single source of truth for interpreting them: it knows which results are
hits, which record outs, and it replays the ordered event log to reconstruct
the live state (inning, half, outs, bases, score, line score). Because state is
always derived from the persisted log, "save / load at any time" is automatic
and every action is undoable by removing the last event.
"""
from __future__ import annotations

import json
from typing import Any

from .db import get_conn

# ---------------------------------------------------------------------------
# Result-code catalogue (covers every standard batting outcome)
# ---------------------------------------------------------------------------
# Each entry: label, category, is_hit, is_ab (counts as at-bat), is_batted (a
# ball put in play -> eligible for contact quality / bb type), bases (default
# base the batter reaches: 1/2/3/4=home, 0=out/none).
RESULTS: dict[str, dict[str, Any]] = {
    # Hits
    "1B":  {"label": "Single",              "cat": "hit", "hit": True,  "ab": True,  "batted": True,  "bases": 1},
    "2B":  {"label": "Double",              "cat": "hit", "hit": True,  "ab": True,  "batted": True,  "bases": 2},
    "3B":  {"label": "Triple",              "cat": "hit", "hit": True,  "ab": True,  "batted": True,  "bases": 3},
    "HR":  {"label": "Home Run",            "cat": "hit", "hit": True,  "ab": True,  "batted": True,  "bases": 4},
    # On base without a hit
    "BB":  {"label": "Walk",                "cat": "bb",  "hit": False, "ab": False, "batted": False, "bases": 1},
    "IBB": {"label": "Intentional Walk",    "cat": "bb",  "hit": False, "ab": False, "batted": False, "bases": 1},
    "HBP": {"label": "Hit By Pitch",        "cat": "hbp", "hit": False, "ab": False, "batted": False, "bases": 1},
    "CI":  {"label": "Catcher Interference","cat": "ci",  "hit": False, "ab": False, "batted": False, "bases": 1},
    "ROE": {"label": "Reached On Error",    "cat": "roe", "hit": False, "ab": True,  "batted": True,  "bases": 1},
    "FC":  {"label": "Fielder's Choice",    "cat": "fc",  "hit": False, "ab": True,  "batted": True,  "bases": 1},
    "D3K": {"label": "Dropped 3rd Strike (reached)", "cat": "k", "hit": False, "ab": True, "batted": False, "bases": 1},
    # Outs (batted)
    "GO":  {"label": "Groundout",           "cat": "out", "hit": False, "ab": True,  "batted": True,  "bases": 0},
    "FO":  {"label": "Flyout",              "cat": "out", "hit": False, "ab": True,  "batted": True,  "bases": 0},
    "LO":  {"label": "Lineout",             "cat": "out", "hit": False, "ab": True,  "batted": True,  "bases": 0},
    "POP": {"label": "Popout",              "cat": "out", "hit": False, "ab": True,  "batted": True,  "bases": 0},
    "FOUL":{"label": "Foul Out",            "cat": "out", "hit": False, "ab": True,  "batted": False, "bases": 0},
    "DP":  {"label": "Double Play",         "cat": "out", "hit": False, "ab": True,  "batted": True,  "bases": 0},
    "TP":  {"label": "Triple Play",         "cat": "out", "hit": False, "ab": True,  "batted": True,  "bases": 0},
    # Outs (strikeout)
    "K":   {"label": "Strikeout (swinging)","cat": "k",   "hit": False, "ab": True,  "batted": False, "bases": 0},
    "KL":  {"label": "Strikeout (looking)", "cat": "k",   "hit": False, "ab": True,  "batted": False, "bases": 0},
    # Sacrifices (not at-bats)
    "SF":  {"label": "Sacrifice Fly",       "cat": "out", "hit": False, "ab": False, "batted": True,  "bases": 0},
    "SAC": {"label": "Sacrifice Bunt",      "cat": "out", "hit": False, "ab": False, "batted": True,  "bases": 0},
}

# Baserunning / battery events (kind='BR'). charge = who is charged/credited.
BR_RESULTS: dict[str, dict[str, Any]] = {
    "SB":   {"label": "Stolen Base",        "charge": None},
    "CS":   {"label": "Caught Stealing",    "charge": "catcher"},
    "PO":   {"label": "Pickoff",            "charge": "pitcher"},
    "POCS": {"label": "Pickoff-Caught Stealing", "charge": "catcher"},
    "WP":   {"label": "Wild Pitch",         "charge": "pitcher"},
    "PB":   {"label": "Passed Ball",        "charge": "catcher"},
    "BK":   {"label": "Balk",               "charge": "pitcher"},
    "ADV":  {"label": "Advance",            "charge": None},
    "OUT":  {"label": "Runner Out",         "charge": None},
}

HIT_CODES = {k for k, v in RESULTS.items() if v["hit"]}

# ---------------------------------------------------------------------------
# Phase 3: pitch-by-pitch vocabulary
# ---------------------------------------------------------------------------
# Pitch types (label + short tag used for color/legend on the grid).
PITCH_TYPES: dict[str, dict[str, Any]] = {
    "FF": {"label": "Four-Seam Fastball", "short": "FF"},
    "SI": {"label": "Sinker / Two-Seam",  "short": "SI"},
    "FC": {"label": "Cutter",             "short": "FC"},
    "SL": {"label": "Slider",             "short": "SL"},
    "CB": {"label": "Curveball",          "short": "CB"},
    "CH": {"label": "Changeup",           "short": "CH"},
    "SP": {"label": "Splitter",           "short": "SP"},
    "KN": {"label": "Knuckleball",        "short": "KN"},
}

# Pitch outcomes. is_strike / is_swing drive the live ball-strike count and
# feed the Phase 4 plate-discipline stats (swing%, whiff%, called-strike%).
PITCH_RESULTS: dict[str, dict[str, Any]] = {
    "B":   {"label": "Ball",            "is_strike": False, "is_swing": False},
    "CS":  {"label": "Called Strike",   "is_strike": True,  "is_swing": False},
    "SS":  {"label": "Swinging Strike", "is_strike": True,  "is_swing": True},
    "F":   {"label": "Foul",            "is_strike": True,  "is_swing": True},
    "IP":  {"label": "In Play",         "is_strike": False, "is_swing": True},
    "HBP": {"label": "Hit By Pitch",    "is_strike": False, "is_swing": False},
}

# Zones 1..9 are the 3x3 in-strike-zone grid; 11..14 are the outside quadrants.
IN_ZONE = set(range(1, 10))
OUT_ZONE = {11, 12, 13, 14}


def _empty_bases() -> dict[str, Any]:
    return {"1": None, "2": None, "3": None}


def compute_state(game_id: int) -> dict[str, Any]:
    """Replay the event log and return the authoritative live game state."""
    c = get_conn()
    game = dict(c.execute("SELECT * FROM games WHERE id=?", (game_id,)).fetchone())
    reg = game["regulation_innings"] or 9
    events = [dict(r) for r in c.execute(
        "SELECT * FROM game_events WHERE game_id=? ORDER BY seq", (game_id,)).fetchall()]

    inning, half, outs = 1, "T", 0
    bases = _empty_bases()
    score = {"away": 0, "home": 0}
    hits = {"away": 0, "home": 0}
    errors = {"away": 0, "home": 0}
    line: dict[int, dict[str, int]] = {}
    # Phase 10 (feature 9): track which half-innings have actually had a play
    # recorded so the line score can stay blank until the first play lands.
    played: dict[int, dict[str, bool]] = {}

    def batting_side(h: str) -> str:
        return "away" if h == "T" else "home"

    def fielding_side(h: str) -> str:
        return "home" if h == "T" else "away"

    for e in events:
        inning, half = e["inning"], e["half"]
        bside = batting_side(half)
        line.setdefault(inning, {"T": 0, "B": 0})
        played.setdefault(inning, {"T": False, "B": False})
        # Any scoring action (PA/BR) marks this half-inning as having begun;
        # SUB markers alone do not "start" an inning on the line score.
        if e["kind"] in ("PA", "BR"):
            played[inning][half] = True
        if e["runs_scored"]:
            score[bside] += e["runs_scored"]
            line[inning][half] += e["runs_scored"]
        if e["kind"] == "PA" and e["result"] in HIT_CODES:
            hits[bside] += 1
        if e["is_error"]:
            n_err = 1
            ej = e.get("errors_json")
            if ej:
                try:
                    lst = json.loads(ej)
                    if isinstance(lst, list) and lst:
                        n_err = len(lst)
                except Exception:
                    n_err = 1
            errors[fielding_side(half)] += n_err
        outs += e["outs_recorded"] or 0
        if e["advances"]:
            try:
                snap = json.loads(e["advances"])
                bases = {"1": snap.get("1"), "2": snap.get("2"), "3": snap.get("3")}
            except Exception:
                pass
        if outs >= 3:
            outs = 0
            bases = _empty_bases()
            if half == "T":
                half = "B"
            else:
                half = "T"
                inning += 1

    return {
        "inning": inning, "half": half, "outs": outs,
        "bases": bases, "score": score, "hits": hits, "errors": errors,
        "line": line, "played": played, "regulation_innings": reg,
        "status": game["status"], "event_count": len(events),
    }


def result_catalogue() -> dict[str, Any]:
    """Expose the code tables to the frontend so the UI stays in sync."""
    return {
        "batting": RESULTS,
        "baserunning": BR_RESULTS,
        "pitch_types": PITCH_TYPES,
        "pitch_results": PITCH_RESULTS,
    }
