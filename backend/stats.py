"""Phase 4: statistics engine + Phase 5 strike-zone heatmap aggregation.

All numbers are DERIVED from the ordered ``game_events`` / ``game_pitches``
logs -- nothing is stored redundantly. We replay each game to attribute runs
and baserunning, then aggregate batting, pitching, fielding/catcher and team
standings across any scope (league / season / team / player).

Run attribution uses a lead-runner heuristic: on a scoring play the lead
runners (from 3rd, then 2nd, then 1st) that vanish from the bases are the ones
that scored; the batter is credited only on a home run (the one always-certain
case). Earned runs exclude runs that scored on a play flagged as an error.
"""
from __future__ import annotations

import json
from typing import Any, Iterable

from .db import get_conn
from .scoring import RESULTS, HIT_CODES

# Batter's own out(s) inherent to the result code (running outs are added on
# top via outs_recorded). Mirrors the scorer UI so replay stays consistent.
INHERENT_OUTS = {
    "K": 1, "KL": 1, "GO": 1, "FO": 1, "LO": 1, "POP": 1, "FOUL": 1,
    "SF": 1, "SAC": 1, "DP": 1, "TP": 1,
}
BB_CODES = {"BB", "IBB"}
K_CODES = {"K", "KL"}
TB_MAP = {"1B": 1, "2B": 2, "3B": 3, "HR": 4}


def _r(cur):
    return [dict(x) for x in cur.fetchall()]


# ---------------------------------------------------------------------------
# Scope resolution -- which games are in play
# ---------------------------------------------------------------------------
def _select_games(league_id=None, season_id=None, team_id=None, game_id=None) -> list[dict]:
    c = get_conn()
    sql = (
        "SELECT g.* FROM games g JOIN seasons s ON s.id=g.season_id "
        "WHERE g.status != 'setup'"
    )
    params: list[Any] = []
    if game_id is not None:
        sql += " AND g.id=?"; params.append(game_id)
    if league_id is not None:
        sql += " AND s.league_id=?"; params.append(league_id)
    if season_id is not None:
        sql += " AND g.season_id=?"; params.append(season_id)
    if team_id is not None:
        sql += " AND (g.away_team_id=? OR g.home_team_id=?)"; params += [team_id, team_id]
    sql += " ORDER BY COALESCE(g.game_date,''), g.id"
    return _r(c.execute(sql, params))


def _player_team_map(game_id: int, g: dict) -> dict[int, int]:
    """Map each player who appeared to their team in THIS game (via lineup side)."""
    c = get_conn()
    rows = _r(c.execute(
        "SELECT DISTINCT player_id, side FROM game_lineups WHERE game_id=?", (game_id,)))
    m = {}
    for r in rows:
        m[r["player_id"]] = g["away_team_id"] if r["side"] == "away" else g["home_team_id"]
    return m

# ---------------------------------------------------------------------------
# Per-game replay: attribute runs to the players who scored
# ---------------------------------------------------------------------------
def _replay(events: list[dict]) -> Iterable[tuple[dict, list[int], bool]]:
    """Yield (event, scorer_pids, batter_scored) for each event in order."""
    bases = {"1": None, "2": None, "3": None}
    for e in events:
        adv = None
        if e["advances"]:
            try:
                adv = json.loads(e["advances"])
            except Exception:
                adv = None
        before = dict(bases)
        after = ({"1": adv.get("1"), "2": adv.get("2"), "3": adv.get("3")}
                 if adv is not None else dict(bases))
        runs = e["runs_scored"] or 0
        scorers: list[int] = []
        batter_scored = False
        if runs:
            remaining = runs
            if e["kind"] == "PA" and e["result"] == "HR":
                batter_scored = True
                remaining -= 1
            after_ids = {v for v in after.values() if v}
            # Lead runners (3rd -> 2nd -> 1st) that left the bases scored first.
            for b in ("3", "2", "1"):
                pid = before[b]
                if remaining <= 0:
                    break
                if pid and pid not in after_ids:
                    scorers.append(pid)
                    remaining -= 1
        bases = after
        yield e, scorers, batter_scored


def _blank_bat() -> dict[str, Any]:
    return {k: 0 for k in (
        "G", "PA", "AB", "R", "H", "1B", "2B", "3B", "HR", "RBI", "BB", "IBB",
        "SO", "HBP", "SF", "SAC", "SB", "CS", "TB")}


def _blank_pit() -> dict[str, Any]:
    return {k: 0 for k in (
        "G", "BF", "Outs", "H", "R", "ER", "HR", "BB", "IBB", "SO", "HBP",
        "W", "L", "SV", "Pit", "Str", "Sw", "Whiff")}


def _blank_fld() -> dict[str, Any]:
    return {k: 0 for k in (
        "G", "E", "PO", "A", "DP", "cCS", "cSB", "cPB", "cPO", "pWP", "pPO")}


# Scoring position number (1..9) -> defensive position code.
_POS_NUM = {1: "P", 2: "C", 3: "1B", 4: "2B", 5: "3B", 6: "SS", 7: "LF", 8: "CF", 9: "RF"}


def _fielding_pos_map(game_id: int) -> dict[str, dict[int, int]]:
    """Return {'away': {posNum: player_id}, 'home': {posNum: player_id}} using the
    currently-active defensive assignments, so a fielder notation like '6-4-3'
    can be resolved to the actual players standing at those positions."""
    c = get_conn()
    rows = _r(c.execute(
        "SELECT side, player_id, position, entered_seq FROM game_lineups "
        "WHERE game_id=? AND active=1 ORDER BY entered_seq", (game_id,)))
    pos_to_num = {v: k for k, v in _POS_NUM.items()}
    out: dict[str, dict[int, int]] = {"away": {}, "home": {}}
    for r in rows:
        num = pos_to_num.get((r["position"] or "").upper())
        if num:
            out[r["side"]][num] = r["player_id"]
    return out


def _fielder_nums(detail) -> list[int]:
    """All fielder numbers (1-9) referenced in a scorer notation like '6-4-3'."""
    if not detail:
        return []
    return [int(ch) for ch in str(detail) if ch.isdigit() and ch != "0"]

# ---------------------------------------------------------------------------
# Core accumulation across a set of games
# ---------------------------------------------------------------------------
def _accumulate(games: list[dict]) -> dict[str, Any]:
    c = get_conn()
    bat: dict[int, dict] = {}
    pit: dict[int, dict] = {}
    fld: dict[int, dict] = {}
    player_team: dict[int, int] = {}
    seen_bat: dict[int, set] = {}
    seen_pit: dict[int, set] = {}
    seen_fld: dict[int, set] = {}

    def B(pid):
        return bat.setdefault(pid, _blank_bat())

    def P(pid):
        return pit.setdefault(pid, _blank_pit())

    def F(pid):
        return fld.setdefault(pid, _blank_fld())

    def mark(seen, pid, gid):
        s = seen.setdefault(pid, set())
        if gid not in s:
            s.add(gid)
            return True
        return False

    for g in games:
        gid = g["id"]
        player_team.update(_player_team_map(gid, g))
        posmap = _fielding_pos_map(gid)
        events = _r(c.execute(
            "SELECT * FROM game_events WHERE game_id=? ORDER BY seq", (gid,)))
        # Win / loss / save decisions.
        for role, key in (("win_pitcher_id", "W"), ("loss_pitcher_id", "L"),
                          ("save_pitcher_id", "SV")):
            pid = g.get(role)
            if pid:
                P(pid)[key] += 1
                if mark(seen_pit, pid, gid):
                    P(pid)["G"] += 1

        for e, scorers, batter_scored in _replay(events):
            res = e["result"]
            info = RESULTS.get(res, {})
            batter = e["batter_id"]
            pitcher = e["pitcher_id"]
            catcher = e["catcher_id"]
            # ---- batting (PA only) ----
            if e["kind"] == "PA" and batter:
                b = B(batter)
                if mark(seen_bat, batter, gid):
                    b["G"] += 1
                b["PA"] += 1
                if info.get("ab"):
                    b["AB"] += 1
                if res in HIT_CODES:
                    b["H"] += 1
                    b[res] += 1
                    b["TB"] += TB_MAP.get(res, 0)
                if res in BB_CODES:
                    b["BB"] += 1
                    if res == "IBB":
                        b["IBB"] += 1
                if res == "HBP":
                    b["HBP"] += 1
                if res in K_CODES:
                    b["SO"] += 1
                if res == "SF":
                    b["SF"] += 1
                if res == "SAC":
                    b["SAC"] += 1
                b["RBI"] += e["rbi"] or 0
                if batter_scored:
                    b["R"] += 1
            # ---- baserunning credited to the runner ----
            if e["kind"] == "BR" and e["runner_id"]:
                rb = B(e["runner_id"])
                if res == "SB":
                    rb["SB"] += 1
                elif res in ("CS", "POCS"):
                    rb["CS"] += 1
            # runs scored (base runners) credited from replay
            for pid in scorers:
                B(pid)["R"] += 1
            # ---- pitching ----
            if pitcher:
                p = P(pitcher)
                if mark(seen_pit, pitcher, gid):
                    p["G"] += 1
                if e["kind"] == "PA":
                    p["BF"] += 1
                    if res in HIT_CODES:
                        p["H"] += 1
                    if res == "HR":
                        p["HR"] += 1
                    if res in BB_CODES:
                        p["BB"] += 1
                        if res == "IBB":
                            p["IBB"] += 1
                    if res == "HBP":
                        p["HBP"] += 1
                    if res in K_CODES:
                        p["SO"] += 1
                p["Outs"] += e["outs_recorded"] or 0
                runs = e["runs_scored"] or 0
                p["R"] += runs
                if not e["is_error"]:
                    p["ER"] += runs
            # ---- fielding / catcher / battery ----
            if e["is_error"]:
                err_ids = []
                ej = e.get("errors_json")
                if ej:
                    try:
                        lst = json.loads(ej)
                        if isinstance(lst, list):
                            err_ids = [int(x) for x in lst]
                    except Exception:
                        err_ids = []
                if not err_ids and e["error_on"]:
                    err_ids = [e["error_on"]]
                for eid in err_ids:
                    fe = F(eid)
                    fe["E"] += 1
                    mark(seen_fld, eid, gid)
            # Putouts / assists from the fielder notation on batted-ball outs.
            if e["kind"] == "PA" and info.get("cat") == "out" and info.get("batted"):
                fld_side = "home" if e["half"] == "T" else "away"
                nums = _fielder_nums(e["detail"])
                pm = posmap.get(fld_side, {})
                if nums:
                    outs_on_play = e["outs_recorded"] or 1
                    po_count = min(max(1, outs_on_play), len(nums))
                    for n in nums[:-1]:
                        pid = pm.get(n)
                        if pid:
                            F(pid)["A"] += 1
                            mark(seen_fld, pid, gid)
                    for n in nums[-po_count:]:
                        pid = pm.get(n)
                        if pid:
                            F(pid)["PO"] += 1
                            mark(seen_fld, pid, gid)
                    if res in ("DP", "TP"):
                        for n in set(nums):
                            pid = pm.get(n)
                            if pid:
                                F(pid)["DP"] += 1
            if e["kind"] == "BR":
                # Position-play notation on caught-stealing / pickoffs, e.g.
                # "CS 2-6" => catcher throws to SS. Credit A to all but the last
                # fielder and a PO to the last fielder who applies the tag.
                if res in ("CS", "POCS", "PO") and not e["is_error"]:
                    fld_side = "home" if e["half"] == "T" else "away"
                    pm = posmap.get(fld_side, {})
                    nums = _fielder_nums(e["detail"])
                    if nums:
                        for n in nums[:-1]:
                            pid = pm.get(n)
                            if pid:
                                F(pid)["A"] += 1
                                mark(seen_fld, pid, gid)
                        last = pm.get(nums[-1])
                        if last:
                            F(last)["PO"] += 1
                            mark(seen_fld, last, gid)
                if res in ("CS", "POCS") and catcher:
                    F(catcher)["cCS"] += 1
                elif res == "SB" and catcher:
                    F(catcher)["cSB"] += 1
                elif res == "PB" and catcher:
                    F(catcher)["cPB"] += 1
                elif res == "PO":
                    if e["credited_to"] == "pitcher" and pitcher:
                        F(pitcher)["pPO"] += 1
                    elif catcher:
                        F(catcher)["cPO"] += 1
                elif res == "WP" and pitcher:
                    F(pitcher)["pWP"] += 1
        # pitch-level detail per pitcher for this game
        for pr in _r(c.execute(
                "SELECT pitcher_id, result, is_strike, is_swing FROM game_pitches "
                "WHERE game_id=?", (gid,))):
            pid = pr["pitcher_id"]
            if not pid:
                continue
            p = P(pid)
            p["Pit"] += 1
            p["Str"] += pr["is_strike"] or 0
            p["Sw"] += pr["is_swing"] or 0
            if pr["result"] == "SS":
                p["Whiff"] += 1

    return {"bat": bat, "pit": pit, "fld": fld, "player_team": player_team}

def _rate(num, den, nd=3):
    return round(num / den, nd) if den else 0.0


def _names(pids: Iterable[int]) -> dict[int, str]:
    pids = [p for p in set(pids) if p]
    if not pids:
        return {}
    c = get_conn()
    q = ",".join("?" * len(pids))
    rows = _r(c.execute(
        f"SELECT id, (TRIM(first_name||' '||last_name)) AS name FROM players WHERE id IN ({q})",
        pids))
    return {r["id"]: r["name"] for r in rows}


def _team_names(tids: Iterable[int]) -> dict[int, dict]:
    tids = [t for t in set(tids) if t]
    if not tids:
        return {}
    c = get_conn()
    q = ",".join("?" * len(tids))
    rows = _r(c.execute(
        f"SELECT id, name, abbrev FROM teams WHERE id IN ({q})", tids))
    return {r["id"]: r for r in rows}


def _finish_batting(pid, s, nm, tm, teams):
    ab, h, bb, hbp, sf = s["AB"], s["H"], s["BB"], s["HBP"], s["SF"]
    avg = _rate(h, ab)
    obp = _rate(h + bb + hbp, ab + bb + hbp + sf)
    slg = _rate(s["TB"], ab)
    babip_den = ab - s["SO"] - s["HR"] + sf
    row = dict(s)
    row.update({
        "player_id": pid, "name": nm.get(pid, f"#{pid}"),
        "team": (teams.get(tm.get(pid), {}) or {}).get("abbrev")
                 or (teams.get(tm.get(pid), {}) or {}).get("name", ""),
        "AVG": avg, "OBP": obp, "SLG": slg, "OPS": round(obp + slg, 3),
        "ISO": round(slg - avg, 3),
        "BABIP": _rate(h - s["HR"], babip_den),
        "BB%": _rate(bb, s["PA"], 3), "K%": _rate(s["SO"], s["PA"], 3),
        "SB%": _rate(s["SB"], s["SB"] + s["CS"]),
    })
    return row


def _finish_pitching(pid, s, nm, tm, teams):
    ip3 = s["Outs"]
    ip = ip3 / 3.0
    ip_disp = f"{ip3 // 3}.{ip3 % 3}"
    row = dict(s)
    row.update({
        "player_id": pid, "name": nm.get(pid, f"#{pid}"),
        "team": (teams.get(tm.get(pid), {}) or {}).get("abbrev")
                 or (teams.get(tm.get(pid), {}) or {}).get("name", ""),
        "IP": ip_disp,
        "ERA": round(9 * s["ER"] / ip, 2) if ip else 0.0,
        "RA9": round(9 * s["R"] / ip, 2) if ip else 0.0,
        "WHIP": round((s["H"] + s["BB"]) / ip, 2) if ip else 0.0,
        "K9": round(9 * s["SO"] / ip, 2) if ip else 0.0,
        "BB9": round(9 * s["BB"] / ip, 2) if ip else 0.0,
        "KBB": round(s["SO"] / s["BB"], 2) if s["BB"] else s["SO"],
        "Str%": _rate(s["Str"], s["Pit"], 3),
        "Sw%": _rate(s["Sw"], s["Pit"], 3),
        "Whiff%": _rate(s["Whiff"], s["Sw"], 3),
    })
    return row


def _finish_fielding(pid, s, nm, tm, teams):
    row = dict(s)
    tc = s["PO"] + s["A"] + s["E"]
    row.update({
        "player_id": pid, "name": nm.get(pid, f"#{pid}"),
        "team": (teams.get(tm.get(pid), {}) or {}).get("abbrev")
                 or (teams.get(tm.get(pid), {}) or {}).get("name", ""),
        "TC": tc,
        "FPCT": _rate(s["PO"] + s["A"], tc),
        "CS%": _rate(s["cCS"], s["cCS"] + s["cSB"]),
    })
    return row

# ---------------------------------------------------------------------------
# Standings (team W-L) from completed games
# ---------------------------------------------------------------------------
def _standings(games: list[dict]) -> list[dict]:
    from .scoring import compute_state
    rec: dict[int, dict] = {}
    order: list[tuple[int, int]] = []  # (team_id, +1 win / -1 loss / 0 tie) chronological
    for g in games:
        if g["status"] not in ("final", "forfeited"):
            continue
        st = compute_state(g["id"])
        a, h = g["away_team_id"], g["home_team_id"]
        ra, rh = st["score"]["away"], st["score"]["home"]
        for t in (a, h):
            rec.setdefault(t, {"team_id": t, "W": 0, "L": 0, "T": 0, "RF": 0, "RA": 0,
                              "_seq": []})
        rec[a]["RF"] += ra; rec[a]["RA"] += rh
        rec[h]["RF"] += rh; rec[h]["RA"] += ra
        if ra > rh:
            rec[a]["W"] += 1; rec[h]["L"] += 1
            rec[a]["_seq"].append("W"); rec[h]["_seq"].append("L")
        elif rh > ra:
            rec[h]["W"] += 1; rec[a]["L"] += 1
            rec[h]["_seq"].append("W"); rec[a]["_seq"].append("L")
        else:
            rec[a]["T"] += 1; rec[h]["T"] += 1
            rec[a]["_seq"].append("T"); rec[h]["_seq"].append("T")
    teams = _team_names(rec.keys())
    out = []
    for t, s in rec.items():
        gp = s["W"] + s["L"] + s["T"]
        seq = s.pop("_seq")
        # current streak
        streak = ""
        if seq:
            last = seq[-1]; n = 0
            for x in reversed(seq):
                if x == last:
                    n += 1
                else:
                    break
            streak = f"{last}{n}"
        last10 = seq[-10:]
        s.update({
            "team": (teams.get(t, {}) or {}).get("name", f"#{t}"),
            "abbrev": (teams.get(t, {}) or {}).get("abbrev", ""),
            "GP": gp, "PCT": round(s["W"] / (s["W"] + s["L"]), 3) if (s["W"] + s["L"]) else 0.0,
            "DIFF": s["RF"] - s["RA"], "STRK": streak,
            "L10": f"{last10.count('W')}-{last10.count('L')}",
        })
        out.append(s)
    out.sort(key=lambda r: (-r["PCT"], -r["DIFF"], -r["W"]))
    return out


# ---------------------------------------------------------------------------
# Public: full statistics bundle for a scope
# ---------------------------------------------------------------------------
def stats(league_id=None, season_id=None, team_id=None) -> dict[str, Any]:
    games = _select_games(league_id, season_id, team_id)
    acc = _accumulate(games)
    tm = acc["player_team"]
    all_pids = set(acc["bat"]) | set(acc["pit"]) | set(acc["fld"])
    nm = _names(all_pids)
    teams = _team_names(tm.values())

    def keep(pid):
        return team_id is None or tm.get(pid) == team_id

    batting = [_finish_batting(pid, s, nm, tm, teams)
               for pid, s in acc["bat"].items() if keep(pid) and s["PA"]]
    pitching = [_finish_pitching(pid, s, nm, tm, teams)
                for pid, s in acc["pit"].items() if keep(pid) and (s["BF"] or s["Outs"] or s["G"])]
    fielding = [_finish_fielding(pid, s, nm, tm, teams)
                for pid, s in acc["fld"].items() if keep(pid)]
    batting.sort(key=lambda r: (-r["OPS"], -r["H"]))
    pitching.sort(key=lambda r: (r["ERA"] if r["Outs"] else 9e9, -r["SO"]))
    fielding.sort(key=lambda r: (-r["cCS"], r["E"]))
    return {
        "batting": batting, "pitching": pitching, "fielding": fielding,
        "standings": _standings(games), "game_count": len(games),
    }


def player_gamelog(player_id: int, season_id=None, league_id=None) -> list[dict]:
    """Per-game batting + pitching line for one player."""
    games = _select_games(league_id, season_id)
    c = get_conn()
    log = []
    for g in games:
        evs = _r(c.execute(
            "SELECT * FROM game_events WHERE game_id=? ORDER BY seq", (g["id"],)))
        if not any(e["batter_id"] == player_id or e["pitcher_id"] == player_id
                   or e["runner_id"] == player_id for e in evs):
            continue
        acc = _accumulate([g])
        b = acc["bat"].get(player_id)
        p = acc["pit"].get(player_id)
        teams = _team_names([g["away_team_id"], g["home_team_id"]])
        opp_id = g["home_team_id"] if acc["player_team"].get(player_id) == g["away_team_id"] else g["away_team_id"]
        row = {
            "game_id": g["id"], "date": g["game_date"],
            "opp": (teams.get(opp_id, {}) or {}).get("abbrev") or (teams.get(opp_id, {}) or {}).get("name", ""),
        }
        if b:
            row["batting"] = _finish_batting(player_id, b, {player_id: ""}, {}, {})
        if p:
            row["pitching"] = _finish_pitching(player_id, p, {player_id: ""}, {}, {})
        log.append(row)
    return log

# ---------------------------------------------------------------------------
# Strike-zone heatmap (Phase 5 visualization, surfaced in game reports)
# ---------------------------------------------------------------------------
ALL_ZONES = [1, 2, 3, 4, 5, 6, 7, 8, 9, 11, 12, 13, 14]


def zone_heatmap(game_id: int, pitcher_id=None, batter_id=None) -> dict[str, Any]:
    """Aggregate pitches by strike-zone location for a game (optionally filtered
    to one pitcher or batter). Returns per-zone counts + strike/swing/whiff so
    the UI can render a color-graded 3x3 grid with the four outside quadrants.
    """
    c = get_conn()
    sql = "SELECT * FROM game_pitches WHERE game_id=?"
    params: list[Any] = [game_id]
    if pitcher_id is not None:
        sql += " AND pitcher_id=?"; params.append(pitcher_id)
    if batter_id is not None:
        sql += " AND batter_id=?"; params.append(batter_id)
    rows = _r(c.execute(sql, params))
    zones = {z: {"pitches": 0, "strikes": 0, "swings": 0, "whiffs": 0, "balls": 0}
             for z in ALL_ZONES}
    total = {"pitches": 0, "strikes": 0, "swings": 0, "whiffs": 0, "balls": 0}
    velo_sum = velo_n = 0.0
    ptypes: dict[str, int] = {}
    for r in rows:
        z = r["zone"]
        total["pitches"] += 1
        cell = zones.get(z)
        if cell is not None:
            cell["pitches"] += 1
        for key, cond in (("strikes", r["is_strike"]), ("swings", r["is_swing"]),
                          ("whiffs", r["result"] == "SS"), ("balls", r["result"] == "B")):
            if cond:
                total[key] += 1
                if cell is not None:
                    cell[key] += 1
        if r["velocity"]:
            velo_sum += r["velocity"]; velo_n += 1
        if r["pitch_type"]:
            ptypes[r["pitch_type"]] = ptypes.get(r["pitch_type"], 0) + 1
    peak = max((z["pitches"] for z in zones.values()), default=0)
    for z in zones.values():
        z["pct"] = _rate(z["pitches"], total["pitches"], 3)
        z["strike_pct"] = _rate(z["strikes"], z["pitches"], 3)
        z["intensity"] = _rate(z["pitches"], peak, 3) if peak else 0.0
    return {
        "zones": zones, "total": total, "peak": peak,
        "avg_velo": round(velo_sum / velo_n, 1) if velo_n else None,
        "pitch_types": ptypes,
        "strike_pct": _rate(total["strikes"], total["pitches"], 3),
        "swing_pct": _rate(total["swings"], total["pitches"], 3),
        "whiff_pct": _rate(total["whiffs"], total["swings"], 3),
    }


# Field angle (degrees from straight-away center; negative = left / 3B side)
# and base depth (fraction of the home->fence distance) per scoring position
# number. 1=P 2=C 3=1B 4=2B 5=3B 6=SS 7=LF 8=CF 9=RF.
_POS_ANGLE = {1: 0, 2: 0, 3: 34, 4: 17, 5: -34, 6: -17, 7: -28, 8: 0, 9: 28}
_POS_DEPTH = {1: .30, 2: .12, 3: .34, 4: .40, 5: .34, 6: .40, 7: .72, 8: .78, 9: .72}
_BBTYPE_DEPTH = {"GB": -.06, "LD": .05, "FB": .16, "PU": .02}


def _first_fielder(detail):
    """First fielder number (1-9) referenced in a scorer detail like '6-4-3'."""
    if not detail:
        return None
    for ch in str(detail):
        if ch.isdigit() and ch != "0":
            return int(ch)
    return None


def spray_chart(game_id: int, team_id=None, player_id=None) -> dict[str, Any]:
    """Derive approximate batted-ball spray locations for a game from the
    fielder(s) involved, the batted-ball trajectory and the hit value, so the
    UI can plot a color-coded spray chart. Coordinates are normalised: home
    plate at (0.5, 0.95), straight-away center field at (0.5, ~0.08)."""
    import math
    from .repo_games import get_game
    c = get_conn()
    g = get_game(game_id)
    tm = _player_team_map(game_id, g)
    events = _r(c.execute(
        "SELECT * FROM game_events WHERE game_id=? AND kind='PA' ORDER BY seq",
        (game_id,)))
    nm = _names([e["batter_id"] for e in events if e["batter_id"]])
    pts: list[dict] = []
    counts = {"hit": 0, "out": 0, "other": 0}
    for e in events:
        info = RESULTS.get(e["result"], {})
        if not info.get("batted"):
            continue
        bt = e["batter_id"]
        if player_id is not None and bt != player_id:
            continue
        if team_id is not None and tm.get(bt) != team_id:
            continue
        f = _first_fielder(e["detail"])
        # Prefer the exact location the scorer clicked on the field diagram.
        if e["hit_x"] is not None and e["hit_y"] is not None:
            x = max(0.02, min(0.98, float(e["hit_x"])))
            y = max(0.02, min(0.98, float(e["hit_y"])))
        elif e["result"] == "HR":
            ang = ((e["id"] * 37) % 61) - 30
            depth = .96
            rad = math.radians(ang)
            x = 0.5 + depth * 0.5 * math.sin(rad)
            y = 0.95 - depth * 0.86 * math.cos(rad)
        else:
            ang = _POS_ANGLE.get(f, 0)
            depth = _POS_DEPTH.get(f, .5) + _BBTYPE_DEPTH.get(e["bb_type"], 0)
            if info.get("hit"):
                depth += .05 + .06 * (info.get("bases", 1) - 1)
            depth = max(.08, min(.98, depth))
            ang += (((e["id"] * 13) % 11) - 5) / 90.0 * 12
            rad = math.radians(ang)
            x = 0.5 + depth * 0.5 * math.sin(rad)
            y = 0.95 - depth * 0.86 * math.cos(rad)
        cat = "hit" if info.get("hit") else ("out" if info.get("cat") == "out" else "other")
        counts[cat] += 1
        pts.append({
            "x": round(x, 4), "y": round(y, 4),
            "result": e["result"], "label": info.get("label", e["result"]),
            "cat": cat, "bb_type": e["bb_type"], "contact": e["contact"],
            "batter": nm.get(bt, ""), "bases": info.get("bases", 0),
            "inning": e["inning"], "half": e["half"],
            "detail": e["detail"] or "",
            "exact": e["hit_x"] is not None and e["hit_y"] is not None,
        })
    return {"points": pts, "counts": counts, "total": len(pts)}


def pitchers_in_game(game_id: int) -> list[dict]:
    c = get_conn()
    rows = _r(c.execute(
        "SELECT DISTINCT pitcher_id FROM game_pitches WHERE game_id=? AND pitcher_id IS NOT NULL",
        (game_id,)))
    nm = _names([r["pitcher_id"] for r in rows])
    return [{"player_id": r["pitcher_id"], "name": nm.get(r["pitcher_id"], f"#{r['pitcher_id']}")}
            for r in rows]


def game_report(game_id: int) -> dict[str, Any]:
    """Box-score style report for a single game: batting + pitching lines per
    side plus the game's line score and a strike-zone heatmap summary."""
    from .repo_games import get_game, line_score
    g = get_game(game_id)
    acc = _accumulate([g])
    tm = acc["player_team"]
    nm = _names(set(acc["bat"]) | set(acc["pit"]))
    teams = _team_names([g["away_team_id"], g["home_team_id"]])

    def side_rows(kind, team_id):
        src = acc[kind]
        fin = _finish_batting if kind == "bat" else _finish_pitching
        rows = [fin(pid, s, nm, tm, teams) for pid, s in src.items()
                if tm.get(pid) == team_id]
        if kind == "bat":
            rows.sort(key=lambda r: -r["PA"])
        else:
            rows.sort(key=lambda r: -r["BF"])
        return rows

    return {
        "game": g,
        "line": line_score(game_id),
        "away": {"team": teams.get(g["away_team_id"], {}),
                 "batting": side_rows("bat", g["away_team_id"]),
                 "pitching": side_rows("pit", g["away_team_id"])},
        "home": {"team": teams.get(g["home_team_id"], {}),
                 "batting": side_rows("bat", g["home_team_id"]),
                 "pitching": side_rows("pit", g["home_team_id"])},
        "heatmap": zone_heatmap(game_id),
        "spray": spray_chart(game_id),
        "pitchers": pitchers_in_game(game_id),
    }
