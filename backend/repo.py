"""Data-access layer: CRUD helpers for the Utilities module.

Each function returns plain dicts (JSON-serialisable) so the API layer can hand
them straight to the frontend. Kept deliberately explicit rather than a generic
ORM so the SQL stays readable and easy to extend as later phases add games,
plate appearances and pitches.
"""
from __future__ import annotations

from typing import Any

from .db import get_conn, gen_public_id


def _rows(cur) -> list[dict[str, Any]]:
    return [dict(r) for r in cur.fetchall()]


def _one(cur) -> dict[str, Any] | None:
    r = cur.fetchone()
    return dict(r) if r else None


# ---------------------------------------------------------------------------
# Leagues
# ---------------------------------------------------------------------------
def list_leagues() -> list[dict]:
    c = get_conn()
    return _rows(c.execute(
        "SELECT l.*, "
        "(SELECT COUNT(*) FROM seasons s WHERE s.league_id = l.id) AS season_count "
        "FROM leagues l ORDER BY l.name"
    ))


def get_league(league_id: int) -> dict | None:
    c = get_conn()
    return _one(c.execute("SELECT * FROM leagues WHERE id = ?", (league_id,)))


def create_league(data: dict) -> dict:
    c = get_conn()
    cur = c.execute(
        "INSERT INTO leagues (name, abbrev, level, notes) VALUES (?,?,?,?)",
        (data.get("name"), data.get("abbrev"), data.get("level"), data.get("notes")),
    )
    c.commit()
    return get_league(cur.lastrowid)


def update_league(league_id: int, data: dict) -> dict | None:
    c = get_conn()
    c.execute(
        "UPDATE leagues SET name=?, abbrev=?, level=?, notes=? WHERE id=?",
        (data.get("name"), data.get("abbrev"), data.get("level"), data.get("notes"), league_id),
    )
    c.commit()
    return get_league(league_id)


def delete_league(league_id: int) -> None:
    c = get_conn()
    c.execute("DELETE FROM leagues WHERE id = ?", (league_id,))
    c.commit()


# ---------------------------------------------------------------------------
# Seasons
# ---------------------------------------------------------------------------
def list_seasons(league_id: int | None = None) -> list[dict]:
    c = get_conn()
    sql = (
        "SELECT s.*, l.name AS league_name, "
        "(SELECT COUNT(*) FROM season_teams st WHERE st.season_id = s.id) AS team_count "
        "FROM seasons s JOIN leagues l ON l.id = s.league_id"
    )
    params: tuple = ()
    if league_id is not None:
        sql += " WHERE s.league_id = ?"
        params = (league_id,)
    sql += " ORDER BY s.year DESC, s.name"
    return _rows(c.execute(sql, params))


def get_season(season_id: int) -> dict | None:
    c = get_conn()
    return _one(c.execute(
        "SELECT s.*, l.name AS league_name FROM seasons s "
        "JOIN leagues l ON l.id = s.league_id WHERE s.id = ?", (season_id,)))


def create_season(data: dict) -> dict:
    c = get_conn()
    cur = c.execute(
        "INSERT INTO seasons (league_id, name, year, start_date, end_date, notes) "
        "VALUES (?,?,?,?,?,?)",
        (data.get("league_id"), data.get("name"), data.get("year"),
         data.get("start_date"), data.get("end_date"), data.get("notes")),
    )
    c.commit()
    return get_season(cur.lastrowid)


def update_season(season_id: int, data: dict) -> dict | None:
    c = get_conn()
    c.execute(
        "UPDATE seasons SET league_id=?, name=?, year=?, start_date=?, end_date=?, notes=? "
        "WHERE id=?",
        (data.get("league_id"), data.get("name"), data.get("year"),
         data.get("start_date"), data.get("end_date"), data.get("notes"), season_id),
    )
    c.commit()
    return get_season(season_id)


def delete_season(season_id: int) -> None:
    c = get_conn()
    c.execute("DELETE FROM seasons WHERE id = ?", (season_id,))
    c.commit()


# ---------------------------------------------------------------------------
# Teams (global entities)
# ---------------------------------------------------------------------------
def list_teams() -> list[dict]:
    c = get_conn()
    return _rows(c.execute("SELECT * FROM teams ORDER BY name"))


def get_team(team_id: int) -> dict | None:
    c = get_conn()
    return _one(c.execute("SELECT * FROM teams WHERE id = ?", (team_id,)))


def create_team(data: dict) -> dict:
    c = get_conn()
    cur = c.execute(
        "INSERT INTO teams (name, abbrev, city, color, notes) VALUES (?,?,?,?,?)",
        (data.get("name"), data.get("abbrev"), data.get("city"),
         data.get("color"), data.get("notes")),
    )
    c.commit()
    return get_team(cur.lastrowid)


def update_team(team_id: int, data: dict) -> dict | None:
    c = get_conn()
    c.execute(
        "UPDATE teams SET name=?, abbrev=?, city=?, color=?, notes=? WHERE id=?",
        (data.get("name"), data.get("abbrev"), data.get("city"),
         data.get("color"), data.get("notes"), team_id),
    )
    c.commit()
    return get_team(team_id)


def delete_team(team_id: int) -> None:
    c = get_conn()
    c.execute("DELETE FROM teams WHERE id = ?", (team_id,))
    c.commit()


# ---------------------------------------------------------------------------
# Players (global entities with persistent identity across leagues/seasons)
# ---------------------------------------------------------------------------
def list_players() -> list[dict]:
    c = get_conn()
    return _rows(c.execute(
        "SELECT p.*, (p.first_name || ' ' || p.last_name) AS full_name "
        "FROM players p ORDER BY p.last_name, p.first_name"))


def get_player(player_id: int) -> dict | None:
    c = get_conn()
    return _one(c.execute(
        "SELECT p.*, (p.first_name || ' ' || p.last_name) AS full_name "
        "FROM players p WHERE id = ?", (player_id,)))


def create_player(data: dict) -> dict:
    c = get_conn()
    existing = {
        r["public_id"]
        for r in c.execute(
            "SELECT public_id FROM players WHERE public_id IS NOT NULL"
        ).fetchall()
    }
    public_id = gen_public_id(existing)
    cur = c.execute(
        "INSERT INTO players (first_name, last_name, bats, throws, primary_position, "
        "public_id, birthdate, height_cm, weight_kg, notes) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (data.get("first_name"), data.get("last_name"), data.get("bats"),
         data.get("throws"), data.get("primary_position"), public_id,
         data.get("birthdate"), data.get("height_cm"), data.get("weight_kg"),
         data.get("notes")),
    )
    c.commit()
    return get_player(cur.lastrowid)


def update_player(player_id: int, data: dict) -> dict | None:
    c = get_conn()
    c.execute(
        "UPDATE players SET first_name=?, last_name=?, bats=?, throws=?, "
        "primary_position=?, birthdate=?, height_cm=?, weight_kg=?, notes=? WHERE id=?",
        (data.get("first_name"), data.get("last_name"), data.get("bats"),
         data.get("throws"), data.get("primary_position"), data.get("birthdate"),
         data.get("height_cm"), data.get("weight_kg"), data.get("notes"), player_id),
    )
    c.commit()
    return get_player(player_id)


def delete_player(player_id: int) -> None:
    c = get_conn()
    c.execute("DELETE FROM players WHERE id = ?", (player_id,))
    c.commit()


# ---------------------------------------------------------------------------
# Season <-> Team participation
# ---------------------------------------------------------------------------
def list_season_teams(season_id: int) -> list[dict]:
    c = get_conn()
    return _rows(c.execute(
        "SELECT t.*, st.id AS link_id FROM season_teams st "
        "JOIN teams t ON t.id = st.team_id WHERE st.season_id = ? ORDER BY t.name",
        (season_id,)))


def add_team_to_season(season_id: int, team_id: int) -> None:
    c = get_conn()
    c.execute(
        "INSERT OR IGNORE INTO season_teams (season_id, team_id) VALUES (?,?)",
        (season_id, team_id))
    c.commit()


def remove_team_from_season(season_id: int, team_id: int) -> None:
    c = get_conn()
    c.execute(
        "DELETE FROM season_teams WHERE season_id = ? AND team_id = ?",
        (season_id, team_id))
    c.commit()


# ---------------------------------------------------------------------------
# Roster (player on a team within a season)
# ---------------------------------------------------------------------------
def list_roster(season_id: int, team_id: int) -> list[dict]:
    c = get_conn()
    return _rows(c.execute(
        "SELECT r.id AS roster_id, r.jersey, r.position, p.* , "
        "(p.first_name || ' ' || p.last_name) AS full_name "
        "FROM roster r JOIN players p ON p.id = r.player_id "
        "WHERE r.season_id = ? AND r.team_id = ? "
        "ORDER BY p.last_name, p.first_name", (season_id, team_id)))


def season_player_assignments(season_id: int) -> list[dict]:
    """Every (player, team) pairing already set in a season.

    Used to enforce "one team per player per season" and to let the UI hide
    players who are already rostered on another team in the same season.
    """
    c = get_conn()
    return _rows(c.execute(
        "SELECT r.player_id, r.team_id, t.name AS team_name, "
        "(p.first_name || ' ' || p.last_name) AS full_name "
        "FROM roster r JOIN teams t ON t.id = r.team_id "
        "JOIN players p ON p.id = r.player_id "
        "WHERE r.season_id = ?", (season_id,)))


def add_player_to_roster(season_id: int, team_id: int, data: dict) -> None:
    c = get_conn()
    player_id = data.get("player_id")
    # Phase 9: a player may belong to only ONE team within a given season.
    # Re-adding to the SAME team is allowed (updates jersey/position); adding to
    # a different team in the same season is rejected.
    other = c.execute(
        "SELECT t.name AS team_name FROM roster r JOIN teams t ON t.id = r.team_id "
        "WHERE r.season_id = ? AND r.player_id = ? AND r.team_id != ? LIMIT 1",
        (season_id, player_id, team_id)).fetchone()
    if other is not None:
        raise ValueError(
            f"Player is already on \"{other['team_name']}\" this season. "
            "A player can be rostered on only one team per season.")
    c.execute(
        "INSERT OR REPLACE INTO roster (season_id, team_id, player_id, jersey, position) "
        "VALUES (?,?,?,?,?)",
        (season_id, team_id, player_id, data.get("jersey"), data.get("position")))
    c.commit()


def remove_player_from_roster(roster_id: int) -> None:
    c = get_conn()
    c.execute("DELETE FROM roster WHERE id = ?", (roster_id,))
    c.commit()


def player_history(player_id: int) -> list[dict]:
    """Every league/season/team stint for a player -- proves identity persists."""
    c = get_conn()
    return _rows(c.execute(
        "SELECT r.jersey, r.position, t.name AS team_name, s.name AS season_name, "
        "s.year, l.name AS league_name FROM roster r "
        "JOIN teams t ON t.id = r.team_id "
        "JOIN seasons s ON s.id = r.season_id "
        "JOIN leagues l ON l.id = s.league_id "
        "WHERE r.player_id = ? ORDER BY s.year DESC", (player_id,)))
