// Games hub: list games per season, create games, open the Live Scorer.
const Games = (() => {
  const state = { seasonId: null };
  const root = () => document.getElementById('view-root');

  const STATUS_TAG = {
    setup: 'Setup', in_progress: 'Live', paused: 'Paused',
    final: 'Final', forfeited: 'Forfeited',
  };

  async function render(r) {
    const seasons = await allSeasons();
    if (!seasons.length) {
      r.innerHTML = UI.empty('\u26be',
        'No seasons yet. Create a league, season, teams and rosters in Utilities first, then come back to schedule games.');
      return;
    }
    if (!state.seasonId || !seasons.some((s) => s.id === state.seasonId)) {
      state.seasonId = seasons[0].id;
    }
    const seasonOpts = seasons.map((s) =>
      `<option value="${s.id}" ${s.id===state.seasonId?'selected':''}>${UI.esc(s.league_name)} \u2014 ${UI.esc(s.name)}</option>`).join('');
    r.innerHTML = `
      <div class="panel" style="margin-bottom:16px"><div class="panel-body"
        style="display:flex;gap:12px;align-items:center;justify-content:space-between;flex-wrap:wrap">
        <label style="display:flex;gap:8px;align-items:center">Season
          <select id="gm-season" style="min-width:260px">${seasonOpts}</select></label>
        <span style="display:flex;gap:8px">
          <button class="btn" id="gm-import">⬇ Import Games</button>
          <button class="btn primary" id="gm-new">+ New Game</button>
        </span>
      </div></div>
      <div id="gm-list"></div>`;
    r.querySelector('#gm-season').onchange = (e) => { state.seasonId = Number(e.target.value); render(r); };
    r.querySelector('#gm-new').onclick = () => newGame();
    r.querySelector('#gm-import').onclick = () => importGames(r);
    await renderList(r.querySelector('#gm-list'));
  }

  async function allSeasons() {
    const leagues = await API.leagues();
    const out = [];
    for (const l of leagues) {
      const seasons = await API.seasons(l.id);
      seasons.forEach((s) => out.push({ ...s, league_name: l.name }));
    }
    return out;
  }

  async function renderList(host) {
    const games = await API.get(`/games?season_id=${state.seasonId}`);
    if (!games.length) {
      host.innerHTML = UI.empty('\ud83d\udcc5', 'No games scheduled in this season yet. Click \u201c+ New Game\u201d to add one.');
      return;
    }
    host.innerHTML = `<div class="grid-cards">` + games.map((g) => {
      const sc = g.score || { away: 0, home: 0 };
      return `<div class="card">
        <div class="card-row"><span class="tag">${STATUS_TAG[g.status]||g.status}</span>
          <span class="muted">${UI.esc(g.game_date||'')}</span></div>
        <div class="gm-match">
          <div class="gm-side"><span>${UI.esc(g.away_name)}</span><b>${sc.away}</b></div>
          <div class="gm-at">@</div>
          <div class="gm-side"><span>${UI.esc(g.home_name)}</span><b>${sc.home}</b></div>
        </div>
        <div class="muted" style="margin:6px 0">${UI.esc(g.venue||'')}</div>
        <div class="card-row" style="margin-top:10px"><span></span><span class="row-actions">
          <button class="btn sm primary" data-score="${g.id}">Score</button>
          <button class="btn sm" data-report="${g.id}">Report</button>
          <button class="btn sm" data-export="${g.id}">Export</button>
          <button class="btn sm danger" data-del="${g.id}">Delete</button>
        </span></div></div>`;
    }).join('') + `</div>`;
    host.querySelectorAll('[data-score]').forEach((b) => b.onclick = () => Scorer.open(Number(b.dataset.score)));
    host.querySelectorAll('[data-report]').forEach((b) => b.onclick = () => Report.open(Number(b.dataset.report)));
    host.querySelectorAll('[data-export]').forEach((b) => b.onclick = () => exportGame(Number(b.dataset.export)));
    host.querySelectorAll('[data-del]').forEach((b) => b.onclick = async () => {
      const g = games.find((x) => x.id == b.dataset.del);
      if (await UI.confirm('Delete game', `Delete ${g.away_name} @ ${g.home_name}? This removes all recorded plays.`,
        { danger: true, okLabel: 'Delete' })) {
        await API.del(`/games/${g.id}`); UI.toast('Game deleted'); renderList(host);
      }
    });
  }

  async function newGame() {
    const teams = await API.seasonTeams(state.seasonId);
    if (teams.length < 2) {
      UI.toast('Add at least two teams to this season in Utilities first.', 'err');
      return;
    }
    const opts = teams.map((t) => ({ value: t.id, label: t.name }));
    const vals = await UI.formModal('New Game', [
      { key: 'away_team_id', label: 'Away team', type: 'select', required: true, options: opts },
      { key: 'home_team_id', label: 'Home team', type: 'select', required: true, options: opts },
      { key: 'game_date', label: 'Date', type: 'date' },
      { key: 'venue', label: 'Venue' },
      { key: 'regulation_innings', label: 'Regulation innings', type: 'number', value: 9 },
    ]);
    if (!vals) return;
    if (String(vals.away_team_id) === String(vals.home_team_id)) {
      UI.toast('Away and home teams must differ.', 'err'); return;
    }
    const body = {
      season_id: state.seasonId,
      away_team_id: Number(vals.away_team_id),
      home_team_id: Number(vals.home_team_id),
      game_date: vals.game_date || null,
      venue: vals.venue || null,
      regulation_innings: vals.regulation_innings || 9,
    };
    const g = await API.post('/games', body);
    UI.toast('Game created');
    Scorer.open(g.id);
  }

  // ---- Per-game export / import ----
  function exportGame(id) {
    // Browser download of the portable single-game .zip.
    const a = document.createElement('a');
    a.href = `/api/games/${id}/export.zip`;
    a.download = '';
    document.body.appendChild(a); a.click(); a.remove();
    UI.toast('Exporting game\u2026');
  }

  async function importGames(r) {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.zip,application/zip';
    input.multiple = true;
    input.onchange = async () => {
      const files = Array.from(input.files || []);
      if (!files.length) return;
      let ok = 0, dup = 0, fail = 0;
      for (const file of files) {
        const fd = new FormData();
        fd.append('file', file, file.name);
        try {
          const res = await fetch('/api/games/import', { method: 'POST', body: fd });
          if (!res.ok) {
            let detail = res.statusText;
            try { const j = await res.json(); detail = j.detail || detail; } catch (e) {}
            throw new Error(detail);
          }
          const j = await res.json();
          if (j && j.duplicate) dup++; else ok++;
        } catch (e) { fail++; UI.toast(`${file.name}: ${e.message || 'import failed'}`, 'err'); }
      }
      const bits = [];
      if (ok) bits.push(`${ok} imported`);
      if (dup) bits.push(`${dup} already present`);
      if (fail) bits.push(`${fail} failed`);
      UI.toast(bits.join(' \u00b7 ') || 'Nothing imported', fail && !ok ? 'err' : 'ok');
      render(r);
    };
    input.click();
  }

  return { render, state };
})();
