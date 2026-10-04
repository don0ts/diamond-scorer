// Visualization view: pick a game to open its report with the strike-zone
// heatmap. Spray charts arrive in a later pass. Visualization.render(root).
const Visualization = (() => {
  const state = { seasonId: null };

  async function allSeasons() {
    const leagues = await API.leagues();
    const out = [];
    for (const l of leagues) {
      const seasons = await API.seasons(l.id);
      seasons.forEach((s) => out.push({ ...s, league_name: l.name }));
    }
    return out;
  }

  async function render(r) {
    const seasons = await allSeasons();
    if (!seasons.length) {
      r.innerHTML = UI.empty('\ud83c\udfaf',
        'No data yet. Score a game with pitch-by-pitch tracking enabled to generate strike-zone heatmaps.');
      return;
    }
    if (!state.seasonId || !seasons.some((s) => s.id === state.seasonId)) {
      state.seasonId = seasons[0].id;
    }
    const seasonOpts = seasons.map((s) =>
      `<option value="${s.id}" ${s.id===state.seasonId?'selected':''}>${UI.esc(s.league_name)} \u2014 ${UI.esc(s.name)}</option>`).join('');
    r.innerHTML = `
      <div class="panel" style="margin-bottom:16px"><div class="panel-body"
        style="display:flex;gap:12px;align-items:center;flex-wrap:wrap">
        <label>Season <select id="vz-season" style="min-width:240px">${seasonOpts}</select></label>
        <span class="muted">Open a game to view its box score and color-graded strike-zone heatmap.</span>
      </div></div>
      <div id="vz-list"></div>`;
    r.querySelector('#vz-season').onchange = (e) => { state.seasonId = Number(e.target.value); render(r); };
    await renderList(r.querySelector('#vz-list'));
  }

  async function renderList(host) {
    const games = await API.get(`/games?season_id=${state.seasonId}`);
    if (!games.length) {
      host.innerHTML = UI.empty('\ud83d\udcc5', 'No games in this season yet.');
      return;
    }
    host.innerHTML = '<div class="grid-cards">' + games.map((g) => {
      const sc = g.score || { away: 0, home: 0 };
      return `<div class="card">
        <div class="card-row"><span class="tag">${g.status}</span>
          <span class="muted">${UI.esc(g.game_date||'')}</span></div>
        <div class="gm-match">
          <div class="gm-side"><span>${UI.esc(g.away_name)}</span><b>${sc.away}</b></div>
          <div class="gm-at">@</div>
          <div class="gm-side"><span>${UI.esc(g.home_name)}</span><b>${sc.home}</b></div>
        </div>
        <div class="card-row" style="margin-top:10px"><span></span>
          <button class="btn sm primary" data-rep="${g.id}">Report &amp; Heatmap</button></div>
      </div>`;
    }).join('') + '</div>';
    host.querySelectorAll('[data-rep]').forEach((b) => b.onclick = () => Report.open(Number(b.dataset.rep)));
  }

  return { render };
})();
