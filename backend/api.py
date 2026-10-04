"""FastAPI routes for the Utilities module (Phase 1).

All routes are mounted under ``/api``. The frontend is a single-page app that
calls these endpoints. Everything runs locally (bound to 127.0.0.1) so there is
no authentication layer -- this is a single-user desktop application, not a
network service.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel

from . import repo, repo_games, reports, scoring, session_io, stats

router = APIRouter(prefix="/api")


# ---------------------------------------------------------------------------
# Pydantic request models (loose -- optional fields default to None)
# ---------------------------------------------------------------------------
class LeagueIn(BaseModel):
    name: str
    abbrev: str | None = None
    level: str | None = None
    notes: str | None = None


class SeasonIn(BaseModel):
    league_id: int
    name: str
    year: int | None = None
    start_date: str | None = None
    end_date: str | None = None
    notes: str | None = None


class TeamIn(BaseModel):
    name: str
    abbrev: str | None = None
    city: str | None = None
    color: str | None = None
    notes: str | None = None


class PlayerIn(BaseModel):
    first_name: str
    last_name: str
    bats: str | None = None
    throws: str | None = None
    primary_position: str | None = None
    birthdate: str | None = None
    height_cm: int | None = None
    weight_kg: int | None = None
    notes: str | None = None


class RosterIn(BaseModel):
    player_id: int
    jersey: str | None = None
    position: str | None = None


# ---------------------------------------------------------------------------
# Leagues
# ---------------------------------------------------------------------------
@router.get("/leagues")
def api_list_leagues():
    return repo.list_leagues()


@router.get("/leagues/{league_id}")
def api_get_league(league_id: int):
    out = repo.get_league(league_id)
    if not out:
        raise HTTPException(404, "League not found")
    return out


@router.post("/leagues")
def api_create_league(body: LeagueIn):
    return repo.create_league(body.model_dump())


@router.put("/leagues/{league_id}")
def api_update_league(league_id: int, body: LeagueIn):
    out = repo.update_league(league_id, body.model_dump())
    if not out:
        raise HTTPException(404, "League not found")
    return out


@router.delete("/leagues/{league_id}")
def api_delete_league(league_id: int):
    repo.delete_league(league_id)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Seasons
# ---------------------------------------------------------------------------
@router.get("/seasons")
def api_list_seasons(league_id: int | None = None):
    return repo.list_seasons(league_id)


@router.get("/seasons/{season_id}")
def api_get_season(season_id: int):
    out = repo.get_season(season_id)
    if not out:
        raise HTTPException(404, "Season not found")
    return out


@router.post("/seasons")
def api_create_season(body: SeasonIn):
    return repo.create_season(body.model_dump())


@router.put("/seasons/{season_id}")
def api_update_season(season_id: int, body: SeasonIn):
    out = repo.update_season(season_id, body.model_dump())
    if not out:
        raise HTTPException(404, "Season not found")
    return out


@router.delete("/seasons/{season_id}")
def api_delete_season(season_id: int):
    repo.delete_season(season_id)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Teams
# ---------------------------------------------------------------------------
@router.get("/teams")
def api_list_teams():
    return repo.list_teams()


@router.post("/teams")
def api_create_team(body: TeamIn):
    return repo.create_team(body.model_dump())


@router.put("/teams/{team_id}")
def api_update_team(team_id: int, body: TeamIn):
    out = repo.update_team(team_id, body.model_dump())
    if not out:
        raise HTTPException(404, "Team not found")
    return out


@router.delete("/teams/{team_id}")
def api_delete_team(team_id: int):
    repo.delete_team(team_id)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Players
# ---------------------------------------------------------------------------
@router.get("/players")
def api_list_players():
    return repo.list_players()


@router.get("/players/{player_id}")
def api_get_player(player_id: int):
    out = repo.get_player(player_id)
    if not out:
        raise HTTPException(404, "Player not found")
    return out


@router.get("/players/{player_id}/history")
def api_player_history(player_id: int):
    return repo.player_history(player_id)


@router.post("/players")
def api_create_player(body: PlayerIn):
    return repo.create_player(body.model_dump())


@router.put("/players/{player_id}")
def api_update_player(player_id: int, body: PlayerIn):
    out = repo.update_player(player_id, body.model_dump())
    if not out:
        raise HTTPException(404, "Player not found")
    return out


@router.delete("/players/{player_id}")
def api_delete_player(player_id: int):
    repo.delete_player(player_id)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Season participation + rosters
# ---------------------------------------------------------------------------
@router.get("/seasons/{season_id}/teams")
def api_season_teams(season_id: int):
    return repo.list_season_teams(season_id)


@router.post("/seasons/{season_id}/teams/{team_id}")
def api_add_season_team(season_id: int, team_id: int):
    repo.add_team_to_season(season_id, team_id)
    return {"ok": True}


@router.delete("/seasons/{season_id}/teams/{team_id}")
def api_remove_season_team(season_id: int, team_id: int):
    repo.remove_team_from_season(season_id, team_id)
    return {"ok": True}


@router.get("/seasons/{season_id}/teams/{team_id}/roster")
def api_roster(season_id: int, team_id: int):
    return repo.list_roster(season_id, team_id)


@router.get("/seasons/{season_id}/assignments")
def api_season_assignments(season_id: int):
    """Which player is on which team already, within this season."""
    return repo.season_player_assignments(season_id)


@router.post("/seasons/{season_id}/teams/{team_id}/roster")
def api_add_roster(season_id: int, team_id: int, body: RosterIn):
    try:
        repo.add_player_to_roster(season_id, team_id, body.model_dump())
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {"ok": True}


@router.delete("/roster/{roster_id}")
def api_remove_roster(roster_id: int):
    repo.remove_player_from_roster(roster_id)
    return {"ok": True}


# ===========================================================================
# Phase 2: Games / Scorer
# ===========================================================================
class GameIn(BaseModel):
    season_id: int
    away_team_id: int
    home_team_id: int
    game_date: str | None = None
    venue: str | None = None
    ump_home: str | None = None
    ump_first: str | None = None
    ump_second: str | None = None
    ump_third: str | None = None
    scorer: str | None = None
    scheduled_start: str | None = None
    actual_start: str | None = None
    weather: str | None = None
    temperature: str | None = None
    wind: str | None = None
    attendance: int | None = None
    notes: str | None = None
    regulation_innings: int | None = 9


@router.get("/games")
def api_list_games(season_id: int | None = None, team_id: int | None = None):
    return repo_games.list_games(season_id, team_id)


@router.get("/games/catalogue")
def api_result_catalogue():
    return scoring.result_catalogue()


@router.get("/games/{game_id}")
def api_get_game(game_id: int):
    g = repo_games.get_game(game_id)
    if not g:
        raise HTTPException(404, "Game not found")
    return g


@router.post("/games")
def api_create_game(body: GameIn):
    return repo_games.create_game(body.model_dump(exclude_none=True))


@router.put("/games/{game_id}")
def api_update_game(game_id: int, body: GameIn):
    out = repo_games.update_game(game_id, body.model_dump(exclude_none=True))
    if not out:
        raise HTTPException(404, "Game not found")
    return out


class GameStateIn(BaseModel):
    status: str | None = None
    end_reason: str | None = None
    forfeit_team_id: int | None = None
    duration_min: int | None = None
    delay_min: int | None = None
    duration_sec: int | None = None
    delay_sec: int | None = None
    win_pitcher_id: int | None = None
    loss_pitcher_id: int | None = None
    save_pitcher_id: int | None = None
    actual_start: str | None = None
    pitch_tracking: int | None = None


@router.patch("/games/{game_id}/state")
def api_set_game_state(game_id: int, body: GameStateIn):
    return repo_games.set_game_fields(game_id, body.model_dump(exclude_none=True))


@router.delete("/games/{game_id}")
def api_delete_game(game_id: int):
    repo_games.delete_game(game_id)
    return {"ok": True}


# ---- Lineups ----
@router.get("/games/{game_id}/lineups")
def api_get_lineups(game_id: int):
    return repo_games.get_lineups(game_id)


class LineupIn(BaseModel):
    side: str
    entries: list[dict]


@router.post("/games/{game_id}/lineups")
def api_set_lineup(game_id: int, body: LineupIn):
    return repo_games.set_lineup(game_id, body.side, body.entries)


class SubIn(BaseModel):
    lineup_id: int
    player_id: int
    position: str | None = None


@router.post("/games/{game_id}/sub")
def api_substitute(game_id: int, body: SubIn):
    return repo_games.substitute(game_id, body.model_dump())


# ---- Events / live state ----
@router.get("/games/{game_id}/state")
def api_game_state(game_id: int):
    return repo_games.line_score(game_id)


@router.get("/games/{game_id}/events")
def api_game_events(game_id: int):
    return repo_games.list_events(game_id)


@router.get("/games/{game_id}/pitches")
def api_game_pitches(game_id: int):
    return repo_games.list_pitches(game_id)


@router.post("/games/{game_id}/events")
def api_add_event(game_id: int, body: dict):
    return repo_games.add_event(game_id, body)


@router.post("/games/{game_id}/undo")
def api_undo(game_id: int):
    return repo_games.undo_last(game_id)


# ---- Statistics (Phase 4) ----
@router.get("/stats")
def api_stats(league_id: int | None = None, season_id: int | None = None,
              team_id: int | None = None):
    return stats.stats(league_id=league_id, season_id=season_id, team_id=team_id)


@router.get("/stats/player/{player_id}/gamelog")
def api_player_gamelog(player_id: int, season_id: int | None = None,
                       league_id: int | None = None):
    return stats.player_gamelog(player_id, season_id=season_id, league_id=league_id)


# ---- Game report + strike-zone heatmap (Phase 5 viz in reports) ----
@router.get("/games/{game_id}/report")
def api_game_report(game_id: int):
    return stats.game_report(game_id)


@router.get("/games/{game_id}/heatmap")
def api_game_heatmap(game_id: int, pitcher_id: int | None = None,
                     batter_id: int | None = None):
    return stats.zone_heatmap(game_id, pitcher_id=pitcher_id, batter_id=batter_id)


@router.get("/games/{game_id}/spray")
def api_game_spray(game_id: int, team_id: int | None = None,
                   player_id: int | None = None):
    return stats.spray_chart(game_id, team_id=team_id, player_id=player_id)


def _report_filename(game_id: int, ext: str) -> str:
    g = repo_games.get_game(game_id)
    if not g:
        raise HTTPException(status_code=404, detail="Game not found")
    import re
    slug = re.sub(r"[^A-Za-z0-9]+", "_",
                  f"{g['away_name']}_at_{g['home_name']}").strip("_")
    return f"{slug or 'game'}_report.{ext}"


@router.get("/games/{game_id}/export.html")
def api_export_html(game_id: int):
    fn = _report_filename(game_id, "html")
    html_str = reports.build_report_html(game_id)
    return HTMLResponse(content=html_str, headers={
        "Content-Disposition": f'attachment; filename="{fn}"'})


@router.get("/games/{game_id}/export.pdf")
def api_export_pdf(game_id: int):
    fn = _report_filename(game_id, "pdf")
    pdf_bytes = reports.build_report_pdf(game_id)
    return Response(content=pdf_bytes, media_type="application/pdf", headers={
        "Content-Disposition": f'attachment; filename="{fn}"'})


def _exports_dir():
    """User-visible folder for saved reports.

    Prefer ``~/Documents/DiamondScorer`` (present on Windows/macOS and most
    Linux desktops); fall back to ``~/DiamondScorer`` and finally to a folder
    beside the database if the home directory is not writable.
    """
    from pathlib import Path
    candidates = [
        Path.home() / "Documents" / "DiamondScorer",
        Path.home() / "DiamondScorer",
    ]
    for d in candidates:
        try:
            d.mkdir(parents=True, exist_ok=True)
            return d
        except Exception:
            continue
    from .db import get_db_path
    d = Path(get_db_path()).resolve().parent / "exports"
    d.mkdir(parents=True, exist_ok=True)
    return d


@router.post("/games/{game_id}/save.html")
def api_save_html(game_id: int):
    """Write the standalone HTML report to disk (works inside pywebview, which
    cannot trigger browser downloads) and return the saved file path."""
    fn = _report_filename(game_id, "html")
    try:
        html_str = reports.build_report_html(game_id)
        path = _exports_dir() / fn
        path.write_text(html_str, encoding="utf-8")
    except Exception as exc:
        raise HTTPException(500, f"Could not save HTML report: {exc}")
    return {"ok": True, "path": str(path), "folder": str(path.parent), "filename": fn}


@router.post("/games/{game_id}/save.pdf")
def api_save_pdf(game_id: int):
    """Write the PDF report to disk and return the saved file path."""
    fn = _report_filename(game_id, "pdf")
    try:
        pdf_bytes = reports.build_report_pdf(game_id)
    except ImportError as exc:
        raise HTTPException(
            500,
            "PDF export needs the 'reportlab' library, which is not installed. "
            f"({exc})")
    except Exception as exc:  # render error
        raise HTTPException(500, f"Could not build PDF: {exc}")
    try:
        path = _exports_dir() / fn
        path.write_bytes(pdf_bytes)
    except Exception as exc:
        raise HTTPException(500, f"Could not write PDF to disk: {exc}")
    return {"ok": True, "path": str(path), "folder": str(path.parent), "filename": fn}


@router.post("/reveal")
def api_reveal(payload: dict):
    """Open a saved file's containing folder in the OS file manager.

    Used by the browser/dev fallback; in the packaged desktop app the native
    ``JsApi.open_folder`` bridge is preferred.
    """
    import os
    import subprocess
    import sys
    from pathlib import Path
    target = payload.get("path") or payload.get("folder")
    if not target:
        raise HTTPException(400, "No path provided")
    folder = str(Path(target).parent if Path(target).suffix else Path(target))
    try:
        if sys.platform.startswith("win"):
            os.startfile(folder)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", folder])
        else:
            subprocess.Popen(["xdg-open", folder])
    except Exception as exc:
        raise HTTPException(500, f"Could not open folder: {exc}")
    return {"ok": True, "folder": folder}


# ===========================================================================
# Phase 9: whole-session export / import (portable .zip backup)
# ===========================================================================
def _session_filename() -> str:
    import time
    return f"diamondscorer_session_{time.strftime('%Y%m%d_%H%M%S')}.zip"


@router.get("/session/export")
def api_session_export():
    """Download the entire session (all data) as a .zip (browser download)."""
    data = session_io.export_session_bytes()
    return Response(content=data, media_type="application/zip", headers={
        "Content-Disposition": f'attachment; filename="{_session_filename()}"'})


@router.post("/session/export.save")
def api_session_export_save():
    """Write the session .zip to disk and return its path (for the desktop app,
    which cannot trigger browser downloads)."""
    fn = _session_filename()
    try:
        data = session_io.export_session_bytes()
        path = _exports_dir() / fn
        path.write_bytes(data)
    except Exception as exc:
        raise HTTPException(500, f"Could not save session file: {exc}")
    return {"ok": True, "path": str(path), "folder": str(path.parent), "filename": fn}


@router.post("/session/import")
async def api_session_import(file: UploadFile = File(...)):
    """Load a previously exported session .zip, replacing all current data."""
    try:
        data = await file.read()
    except Exception as exc:
        raise HTTPException(400, f"Could not read uploaded file: {exc}")
    try:
        return session_io.import_session_bytes(data)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        raise HTTPException(500, f"Import failed: {exc}")
