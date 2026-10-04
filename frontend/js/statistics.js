// Statistics view: batting / pitching / fielding / standings across a scope,
// with Basic / Advanced / Detailed column presets. Statistics.render(root).
const Statistics = (() => {
  const state = { leagueId: null, seasonId: null, teamId: null,
                  tab: 'batting', level: 'basic', data: null };

  // Column presets. Each entry: [key, header, isRate]. Levels are additive.
  const BAT = {
    basic: [['G','G'],['PA','PA'],['AB','AB'],['R','R'],['H','H'],['HR','HR'],
      ['RBI','RBI'],['BB','BB'],['SO','SO'],['AVG','AVG',1],['OBP','OBP',1],
      ['SLG','SLG',1],['OPS','OPS',1]],
    advanced: [['2B','2B'],['3B','3B'],['SB','SB'],['CS','CS'],['TB','TB'],
      ['ISO','ISO',1],['BB%','BB%',1],['K%','K%',1]],
    detailed: [['IBB','IBB'],['HBP','HBP'],['SF','SF'],['SAC','SAC'],
      ['BABIP','BABIP',1],['SB%','SB%',1]],
  };
  const PIT = {
    basic: [['G','G'],['W','W'],['L','L'],['SV','SV'],['IP','IP'],['H','H'],
      ['R','R'],['ER','ER'],['BB','BB'],['SO','SO'],['ERA','ERA',2],['WHIP','WHIP',2]],
    advanced: [['HR','HR'],['HBP','HBP'],['K9','K/9',2],['BB9','BB/9',2],
      ['KBB','K/BB',2],['RA9','RA/9',2]],
    detailed: [['BF','BF'],['Pit','Pit'],['Str%','Str%',1],['Sw%','Sw%',1],
      ['Whiff%','Whiff%',1],['IBB','IBB']],
  };
  const FLD = {
    basic: [['G','G'],['PO','PO'],['A','A'],['E','E'],['DP','DP'],['FPCT','FPCT',1]],
    advanced: [['TC','TC'],['cCS','CS'],['cSB','SB'],['CS%','CS%',1],['cPB','PB']],
    detailed: [['cPO','PO(C)'],['pWP','WP'],['pPO','PO(P)']],
  };
  const STAND = [['GP','GP'],['W','W'],['L','L'],['T','T'],['PCT','PCT',1],
    ['RF','RF'],['RA','RA'],['DIFF','DIFF'],['STRK','STRK'],['L10','L10']];

  function colsFor(tab) {
    const src = tab === 'batting' ? BAT : tab === 'pitching' ? PIT : FLD;
    let cols = src.basic.slice();
    if (state.level !== 'basic') cols = cols.concat(src.advanced);
    if (state.level === 'detailed') cols = cols.concat(src.detailed);
    return cols;
  }

  function fmtRate(v) {
    if (v === null || v === undefined) return '';
    return Number(v).toFixed(3).replace(/^0\./, '.').replace(/^-0\./, '-.');
  }
  function fmt(v, rate) {
    if (v === undefined || v === null) return '';
    if (rate === 1) return fmtRate(v);
    if (rate === 2) return Number(v).toFixed(2);
    return v;
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

  async function render(r) {
    const seasons = await allSeasons();
    if (!seasons.length) {
      r.innerHTML = UI.empty('\ud83d\udcca',
        'No data yet. Create leagues, seasons and score some games first \u2014 statistics are derived live from the play-by-play log.');
      return;
    }
    if (!state.seasonId || !seasons.some((s) => s.id === state.seasonId)) {
      state.seasonId = seasons[0].id;
    }
    const cur = seasons.find((s) => s.id === state.seasonId);
    state.leagueId = cur ? cur.league_id : null;
    const seasonOpts = seasons.map((s) =>
      `<option value="${s.id}" ${s.id===state.seasonId?'selected':''}>${UI.esc(s.league_name)} \u2014 ${UI.esc(s.name)}</option>`).join('');
    const teams = await API.seasonTeams(state.seasonId).catch(() => []);
    const teamOpts = ['<option value="">All teams</option>'].concat(
      teams.map((t) => `<option value="${t.id}" ${t.id==state.teamId?'selected':''}>${UI.esc(t.name)}</option>`)).join('');
    r.innerHTML = `
      <div class="panel" style="margin-bottom:16px"><div class="panel-body st-controls">
        <label>Season <select id="st-season" style="min-width:240px">${seasonOpts}</select></label>
        <label>Team <select id="st-team">${teamOpts}</select></label>
        <span class="st-levels">
          ${['basic','advanced','detailed'].map((lv) =>
            `<button class="btn sm ${state.level===lv?'primary':'ghost'}" data-lv="${lv}">${lv[0].toUpperCase()+lv.slice(1)}</button>`).join('')}
        </span>
      </div></div>
      <div class="panel"><div class="panel-head st-tabs">
        ${['batting','pitching','fielding','standings'].map((t) =>
          `<button class="tabbtn ${state.tab===t?'active':''}" data-tab="${t}">${t[0].toUpperCase()+t.slice(1)}</button>`).join('')}
        <span class="st-gc muted" id="st-gc"></span>
      </div><div class="panel-body" id="st-body"><p class="muted">Loading\u2026</p></div></div>`;
    r.querySelector('#st-season').onchange = (e) => { state.seasonId = Number(e.target.value); state.teamId = null; state.data = null; render(r); };
    r.querySelector('#st-team').onchange = (e) => { state.teamId = e.target.value ? Number(e.target.value) : null; state.data = null; load(); };
    r.querySelectorAll('[data-lv]').forEach((b) => b.onclick = () => { state.level = b.dataset.lv; render(r); });
    r.querySelectorAll('[data-tab]').forEach((b) => b.onclick = () => { state.tab = b.dataset.tab; renderBody(); });
    await load();
  }

  async function load() {
    const q = [`season_id=${state.seasonId}`];
    if (state.teamId) q.push(`team_id=${state.teamId}`);
    state.data = await API.get('/stats?' + q.join('&'));
    const gc = document.getElementById('st-gc');
    if (gc) gc.textContent = `${state.data.game_count} game${state.data.game_count===1?'':'s'}`;
    renderBody();
  }

  function renderBody() {
    document.querySelectorAll('[data-tab]').forEach((b) =>
      b.classList.toggle('active', b.dataset.tab === state.tab));
    const host = document.getElementById('st-body');
    if (!state.data) { host.innerHTML = '<p class="muted">Loading\u2026</p>'; return; }
    if (state.tab === 'standings') { host.innerHTML = standingsHtml(); return; }
    const rows = state.data[state.tab] || [];
    if (!rows.length) {
      host.innerHTML = UI.empty('\ud83d\udcc8', 'No qualifying players in this scope yet.');
      return;
    }
    const cols = colsFor(state.tab);
    const head = `<th class="lft">Player</th><th class="lft">Tm</th>` +
      cols.map(([, l]) => `<th>${l}</th>`).join('');
    const body = rows.map((r) => `<tr><td class="lft">${UI.esc(r.name)}</td><td class="lft muted">${UI.esc(r.team||'')}</td>` +
      cols.map(([k, , rate]) => `<td>${fmt(r[k], rate)}</td>`).join('') + '</tr>').join('');
    host.innerHTML = `<div class="st-scroll"><table class="tbl stat-tbl"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`;
  }

  function standingsHtml() {
    const rows = state.data.standings || [];
    if (!rows.length) return UI.empty('\ud83c\udfc6', 'No completed games yet \u2014 standings appear once games are marked final.');
    const head = `<th class="lft">#</th><th class="lft">Team</th>` + STAND.map(([, l]) => `<th>${l}</th>`).join('');
    const body = rows.map((r, i) => `<tr><td class="lft muted">${i+1}</td><td class="lft">${UI.esc(r.team)}</td>` +
      STAND.map(([k, , rate]) => `<td>${fmt(r[k], rate)}</td>`).join('') + '</tr>').join('');
    return `<div class="st-scroll"><table class="tbl stat-tbl"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`;
  }

  return { render, state };
})();
