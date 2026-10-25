// Statistics view: batting / pitching / fielding / standings across a scope,
// with Basic / Advanced / Detailed column presets. Statistics.render(root).
const Statistics = (() => {
  const state = { leagueId: null, seasonId: null, teamId: null,
                  mode: 'player', tab: 'all', level: 'basic', data: null,
                  sortKey: null, sortDir: null, minPa: 2.1, minIp: 1.0 };

  // Stats where a LOWER value is better (header-sort "best" = ascending).
  const LOWER_BETTER = new Set(['ERA', 'WHIP', 'BAA', 'BB9', 'BB/9', 'FIP', 'E']);

  // Tab layout per mode: [tabKey, label]. 'all' label varies by mode.
  const MODE_TABS = {
    player: [['all', 'All Individual'], ['batting', 'Batting'], ['pitching', 'Pitching'],
             ['fielding', 'Fielding'], ['standings', 'Standings']],
    team: [['all', 'All Collective'], ['batting', 'Batting'], ['pitching', 'Pitching'],
           ['fielding', 'Fielding']],
    leaders: [['all', 'All Leaders'], ['batting', 'Batting Leaders'],
              ['pitching', 'Pitching Leaders']],
  };
  const MODE_BTNS = [['player', 'Player'], ['team', 'Team'], ['leaders', 'Player Leaders']];

  // Leaders categories (Spanish labels). [label, key, dir, minKind, fmt]
  const LEAD_BAT = [
    ['AVG de Bateo', 'AVG', 'desc', 'pa', 'r3'],
    ['Sencillos', '1B', 'desc', null, 'int'],
    ['Dobles', '2B', 'desc', null, 'int'],
    ['Triples', '3B', 'desc', null, 'int'],
    ['Home Runs', 'HR', 'desc', null, 'int'],
    ['Bases Robadas', 'SB', 'desc', null, 'int'],
    ['Carreras Anotadas', 'R', 'desc', null, 'int'],
    ['Carreras Impulsadas', 'RBI', 'desc', null, 'int'],
    ['OBP', 'OBP', 'desc', 'pa', 'r3'],
    ['SLG', 'SLG', 'desc', 'pa', 'r3'],
    ['OPS', 'OPS', 'desc', 'pa', 'r3'],
  ];
  const LEAD_PIT = [
    ['Efectividad', 'ERA', 'asc', 'ip', 'r2'],
    ['Innings Lanzados', 'IPnum', 'desc', null, 'ip'],
    ['Ponches', 'SO', 'desc', null, 'int'],
    ['Porcentaje Juegos Ganados', 'WLPCT', 'desc', null, 'r3'],
    ['Juegos Ganados', 'W', 'desc', null, 'int'],
    ['Juegos Perdidos', 'L', 'desc', null, 'int'],
    ['Juegos Salvados', 'SV', 'desc', null, 'int'],
    ['WHIP', 'WHIP', 'asc', 'ip', 'r2'],
    ['Avg Bateo en Contra', 'BAA', 'asc', 'ip', 'r3'],
  ];

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
      ['R','R'],['ER','ER'],['BB','BB'],['SO','SO'],['ERA','ERA',2],['WHIP','WHIP',2],
      ['BAA','BAA',1]],
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

  // ---- mode rows + leaders helpers ----
  function modeRows(tab) {
    if (!state.data) return [];
    if (state.mode === 'team') return state.data['team_' + tab] || [];
    return state.data[tab] || [];
  }
  function teamGames() { return (state.data && state.data.team_games) || {}; }

  function leadVal(r, key) {
    if (key === '1B') return (r.H || 0) - (r['2B'] || 0) - (r['3B'] || 0) - (r.HR || 0);
    if (key === 'WLPCT') { const w = r.W || 0, l = r.L || 0; return (w + l) ? w / (w + l) : 0; }
    if (key === 'IPnum') return (r.Outs || 0) / 3;
    return r[key] || 0;
  }
  function leadQualifies(r, kind) {
    if (!kind) return true;
    const tg = teamGames()[r.team_id] || 0;
    if (kind === 'pa') return (r.PA || 0) >= state.minPa * tg;
    if (kind === 'ip') return ((r.Outs || 0) / 3) >= state.minIp * tg;
    return true;
  }
  function leadFmt(r, key, f) {
    if (f === 'ip') return r.IP === undefined || r.IP === null ? '' : String(r.IP);
    const v = leadVal(r, key);
    if (f === 'r3') return fmtRate(v);
    if (f === 'r2') return Number(v).toFixed(2);
    return String(Math.round(v));
  }
  function topFive(pool, spec) {
    const [, key, dir, kind] = spec;
    const cand = pool.filter((r) => leadQualifies(r, kind));
    cand.sort((a, b) => dir === 'desc'
      ? leadVal(b, key) - leadVal(a, key) : leadVal(a, key) - leadVal(b, key));
    return cand.slice(0, 5);
  }

  // ---- column-sort helpers ----
  function sortValue(r, key) {
    if (key === 'IP') return r.Outs || 0;
    if (key === 'name') return r.name || '';
    const v = r[key];
    return v === undefined || v === null ? 0 : v;
  }
  function applySort(rows) {
    if (!state.sortKey) return rows;
    const k = state.sortKey, dir = state.sortDir;
    const copy = rows.slice();
    copy.sort((a, b) => {
      const va = sortValue(a, k), vb = sortValue(b, k);
      if (typeof va === 'string' || typeof vb === 'string') {
        return dir === 'desc' ? String(vb).localeCompare(String(va))
                              : String(va).localeCompare(String(vb));
      }
      return dir === 'desc' ? vb - va : va - vb;
    });
    return copy;
  }
  function headerClick(key) {
    if (state.sortKey === key) {
      state.sortDir = state.sortDir === 'desc' ? 'asc' : 'desc';
    } else {
      state.sortKey = key;
      state.sortDir = LOWER_BETTER.has(key) ? 'asc' : 'desc';
    }
    renderBody();
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
          <span class="st-export" style="position:relative;display:inline-block">
            <button class="btn sm ghost" id="st-export-btn">Export ▾</button>
            <span id="st-export-menu" style="display:none;position:absolute;top:100%;left:0;z-index:50;background:#0f1b2e;border:1px solid #1e3050;border-radius:8px;min-width:150px;padding:4px;box-shadow:0 8px 24px rgba(0,0,0,.4)">
              <button class="btn sm ghost" data-export="html" style="display:block;width:100%;text-align:left">Export Web</button>
              <button class="btn sm ghost" data-export="pdf" style="display:block;width:100%;text-align:left">Export PDF</button>
            </span>
          </span>
          ${['basic','advanced','detailed'].map((lv) =>
            `<button class="btn sm ${state.level===lv?'primary':'ghost'}" data-lv="${lv}">${lv[0].toUpperCase()+lv.slice(1)}</button>`).join('')}
        </span>
      </div></div>
      <div class="panel" style="margin-bottom:16px"><div class="panel-body st-modes" style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
        <span class="muted" style="margin-right:4px">View:</span>
        ${MODE_BTNS.map(([m, lbl]) =>
          `<button class="btn sm ${state.mode===m?'primary':'ghost'}" data-mode="${m}">${lbl}</button>`).join('')}
        ${state.mode==='leaders' ?
          '<button class="btn sm ghost" id="st-mincrit" style="margin-left:auto">Set Minimum Criteria</button>' : ''}
      </div></div>
      <div class="panel"><div class="panel-head st-tabs">
        ${MODE_TABS[state.mode].map(([t, lbl]) =>
          `<button class="tabbtn ${state.tab===t?'active':''}" data-tab="${t}">${lbl}</button>`).join('')}
        <span class="st-gc muted" id="st-gc"></span>
      </div><div class="panel-body" id="st-body"><p class="muted">Loading\u2026</p></div></div>`;
    r.querySelector('#st-season').onchange = (e) => { state.seasonId = Number(e.target.value); state.teamId = null; state.data = null; render(r); };
    r.querySelector('#st-team').onchange = (e) => { state.teamId = e.target.value ? Number(e.target.value) : null; state.data = null; load(); };
    r.querySelectorAll('[data-lv]').forEach((b) => b.onclick = () => { state.level = b.dataset.lv; render(r); });
    r.querySelectorAll('[data-mode]').forEach((b) => b.onclick = () => {
      state.mode = b.dataset.mode;
      if (!MODE_TABS[state.mode].some(([t]) => t === state.tab)) state.tab = 'all';
      state.sortKey = null; state.sortDir = null;
      render(r);
    });
    r.querySelectorAll('[data-tab]').forEach((b) => b.onclick = () => {
      state.tab = b.dataset.tab; state.sortKey = null; state.sortDir = null;
      renderBody();
      document.querySelectorAll('[data-tab]').forEach((x) =>
        x.classList.toggle('active', x.dataset.tab === state.tab));
    });
    const mc = r.querySelector('#st-mincrit');
    if (mc) mc.onclick = () => openMinModal(r);
    bindExport(r);
    await load();
  }

  function bindExport(r) {
    const btn = r.querySelector('#st-export-btn');
    const menu = r.querySelector('#st-export-menu');
    if (!btn || !menu) return;
    btn.onclick = (e) => {
      e.stopPropagation();
      menu.style.display = menu.style.display === 'none' ? 'block' : 'none';
    };
    document.addEventListener('click', () => { menu.style.display = 'none'; }, { once: true });
    menu.querySelectorAll('[data-export]').forEach((b) => b.onclick = async (e) => {
      e.stopPropagation();
      menu.style.display = 'none';
      const ext = b.dataset.export;
      const q = [`season_id=${state.seasonId}`, `tab=${state.tab}`, `level=${state.level}`,
                 `mode=${state.mode}`];
      if (state.teamId) q.push(`team_id=${state.teamId}`);
      if (state.sortKey) q.push(`sort_key=${encodeURIComponent(state.sortKey)}`, `sort_dir=${state.sortDir}`);
      if (state.mode === 'leaders') q.push(`min_pa=${state.minPa}`, `min_ip=${state.minIp}`);
      const qs = q.join('&');
      try {
        const simple = state.mode === 'player' && !state.sortKey;
        const bridge = simple && window.pywebview && window.pywebview.api && window.pywebview.api.save_stats;
        if (bridge) {
          const res = await window.pywebview.api.save_stats(state.seasonId, state.teamId, state.tab, state.level, ext);
          if (res && res.ok) {
            UI.toast(`Saved to ${res.path}`, 'ok', 6000);
            if (window.pywebview.api.open_folder) { try { await window.pywebview.api.open_folder(res.path); } catch (err) { /* ignore */ } }
          } else if (res && res.cancelled) {
            UI.toast('Save cancelled', 'ok');
          } else {
            UI.toast('Export failed: ' + ((res && res.error) || 'unknown error'), 'err');
          }
        } else {
          const a = document.createElement('a');
          a.href = `/api/stats/export.${ext}?${qs}`;
          a.download = '';
          document.body.appendChild(a); a.click(); a.remove();
          UI.toast(ext === 'pdf' ? 'Downloading PDF…' : 'Downloading report…', 'ok');
        }
      } catch (err) {
        UI.toast('Export failed: ' + err.message, 'err');
      }
    });
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
    if (!host) return;
    if (!state.data) { host.innerHTML = '<p class="muted">Loading\u2026</p>'; return; }
    if (state.mode === 'leaders') { host.innerHTML = leadersHtml(); return; }
    if (state.tab === 'standings') { host.innerHTML = standingsHtml(); return; }
    if (state.tab === 'all') { host.innerHTML = allSectionsHtml(); return; }
    const rows = applySort(modeRows(state.tab));
    host.innerHTML = singleTableHtml(rows, state.tab, true);
    host.querySelectorAll('th[data-sortkey]').forEach((th) =>
      th.onclick = () => headerClick(th.dataset.sortkey));
  }

  function singleTableHtml(rows, tab, sortable) {
    if (!rows.length) return UI.empty('\ud83d\udcc8', 'No qualifying rows in this scope yet.');
    const cols = colsFor(tab);
    const first = state.mode === 'team' ? 'Team' : 'Player';
    const head = `<th class="lft">${first}</th><th class="lft">Tm</th>` +
      cols.map(([k, l]) => {
        if (!sortable) return `<th>${l}</th>`;
        const active = state.sortKey === k;
        const arrow = active ? (state.sortDir === 'desc' ? ' \u25bc' : ' \u25b2') : '';
        return `<th class="st-sortable" data-sortkey="${k}" style="cursor:pointer">${l}${arrow}</th>`;
      }).join('');
    const body = rows.map((r) => `<tr><td class="lft">${UI.esc(r.name)}</td><td class="lft muted">${UI.esc(r.team||'')}</td>` +
      cols.map(([k, , rate]) => `<td>${fmt(r[k], rate)}</td>`).join('') + '</tr>').join('');
    return `<div class="st-scroll"><table class="tbl stat-tbl"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`;
  }

  function allSectionsHtml() {
    return [['batting', 'Batting'], ['pitching', 'Pitching'], ['fielding', 'Fielding']]
      .map(([tab, label]) =>
        `<section class="st-card" style="margin-bottom:18px">
           <div class="panel"><div class="panel-head"><h2 style="margin:0;font-size:16px">${label}</h2></div>
           <div class="panel-body">${singleTableHtml(modeRows(tab), tab, false)}</div></div>
         </section>`).join('');
  }

  function leadersHtml() {
    const groups = [];
    if (state.tab === 'all' || state.tab === 'batting') groups.push(['batting', LEAD_BAT, 'Bateadores']);
    if (state.tab === 'all' || state.tab === 'pitching') groups.push(['pitching', LEAD_PIT, 'Lanzadores']);
    const out = [];
    groups.forEach(([poolKey, specs, heading]) => {
      const pool = state.data[poolKey] || [];
      const cards = specs.map((spec) => {
        const top = topFive(pool, spec);
        const rws = top.map((r, i) =>
          `<tr><td class="lft muted">${i+1}</td><td class="lft">${UI.esc(r.name)}</td>` +
          `<td class="lft muted">${UI.esc(r.team||'')}</td><td>${UI.esc(leadFmt(r, spec[1], spec[4]))}</td></tr>`).join('');
        const inner = top.length
          ? `<table class="tbl stat-tbl"><thead><tr><th class="lft">#</th><th class="lft">Player</th><th class="lft">Tm</th><th>Value</th></tr></thead><tbody>${rws}</tbody></table>`
          : '<p class="muted">No qualifying players.</p>';
        return `<section class="st-card"><div class="panel"><div class="panel-head"><h2 style="margin:0;font-size:14px">${spec[0]}</h2></div><div class="panel-body"><div class="st-scroll">${inner}</div></div></div></section>`;
      }).join('');
      out.push(`<div class="lead-group-head">${heading}</div><div class="lead-grid">${cards}</div>`);
    });
    return out.join('') || UI.empty('\ud83c\udfc6', 'No leaders to show yet.');
  }

  function openMinModal() {
    const prev = document.getElementById('st-min-modal');
    if (prev) prev.remove();
    const ov = document.createElement('div');
    ov.id = 'st-min-modal';
    ov.style.cssText = 'position:fixed;inset:0;z-index:200;background:rgba(0,0,0,.5);display:flex;align-items:center;justify-content:center';
    ov.innerHTML = `<div style="background:#0f1b2e;border:1px solid #1e3050;border-radius:14px;padding:22px;min-width:300px">
      <h3 style="margin:0 0 14px">Set Minimum Criteria</h3>
      <label style="display:block;margin-bottom:10px">PA / Game <input id="st-min-pa" type="number" step="0.1" value="${state.minPa}" style="width:90px;margin-left:8px"></label>
      <label style="display:block;margin-bottom:16px">IP / Game <input id="st-min-ip" type="number" step="0.1" value="${state.minIp}" style="width:90px;margin-left:8px"></label>
      <div style="display:flex;gap:8px;justify-content:flex-end">
        <button class="btn sm ghost" id="st-min-cancel">Cancel</button>
        <button class="btn sm primary" id="st-min-save">Save</button>
      </div></div>`;
    document.body.appendChild(ov);
    const close = () => ov.remove();
    ov.onclick = (e) => { if (e.target === ov) close(); };
    ov.querySelector('#st-min-cancel').onclick = close;
    ov.querySelector('#st-min-save').onclick = () => {
      const pa = parseFloat(ov.querySelector('#st-min-pa').value);
      const ip = parseFloat(ov.querySelector('#st-min-ip').value);
      if (!isNaN(pa)) state.minPa = pa;
      if (!isNaN(ip)) state.minIp = ip;
      close();
      renderBody();
    };
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
