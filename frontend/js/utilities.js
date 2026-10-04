// Utilities module: CRUD for Leagues, Seasons, Teams, Players + rosters.
const Utilities = (() => {
  const state = { tab: 'leagues', leagueId: null, seasonId: null, teamId: null };
  const POSITIONS = ['P','C','1B','2B','3B','SS','LF','CF','RF','DH','UT'];
  const POS_LABELS = {P:'Pitcher',C:'Catcher','1B':'First Base','2B':'Second Base',
    '3B':'Third Base',SS:'Shortstop',LF:'Left Field',CF:'Center Field',
    RF:'Right Field',DH:'Designated Hitter',UT:'Utility'};
  const root = () => document.getElementById('view-root');

  function actions() {
    const session = `<button class="btn ghost" data-act="export-session" title="Save all data to a .zip">⬇ Export Session</button>`
      + `<button class="btn ghost" data-act="import-session" title="Load data from a .zip">⬆ Import Session</button>`;
    let main = '';
    if (state.tab === 'leagues' && !state.leagueId) main = `<button class="btn primary" data-act="new-league">+ New League</button>`;
    else if (state.tab === 'teams') main = `<button class="btn primary" data-act="new-team">+ New Team</button>`;
    else if (state.tab === 'players') main = `<button class="btn primary" data-act="new-player">+ New Player</button>`;
    return main + session;
  }

  function tabsBar() {
    const tabs = [['leagues','Leagues & Seasons'],['teams','Teams'],['players','Players']];
    return `<div class="nav" style="flex-direction:row;gap:8px;margin-bottom:20px">` +
      tabs.map(([k,l]) => `<button class="btn ${state.tab===k?'primary':'ghost'} sm" data-tab="${k}">${l}</button>`).join('') +
      `</div>`;
  }

  async function render(r) {
    r.innerHTML = tabsBar() + `<div id="util-body"></div>`;
    r.querySelectorAll('[data-tab]').forEach((b) => b.onclick = () => {
      state.tab = b.dataset.tab; state.leagueId = null; state.seasonId = null; state.teamId = null;
      App.refreshActions(); render(r);
    });
    const body = r.querySelector('#util-body');
    if (state.tab === 'leagues') await renderLeagues(body);
    else if (state.tab === 'teams') await renderTeams(body);
    else if (state.tab === 'players') await renderPlayers(body);
  }

  function onAction(a) {
    if (a === 'new-league') editLeague();
    else if (a === 'new-team') createTeam();
    else if (a === 'new-player') createPlayer();
    else if (a === 'export-session') exportSession();
    else if (a === 'import-session') importSession();
  }

  // ---------------- Whole-session export / import ----------------
  async function exportSession() {
    // In the packaged desktop app browser downloads do not work, so write the
    // file to disk and reveal it. In a real browser, trigger a normal download.
    if (window.pywebview) {
      try {
        const r = await API.post('/session/export.save');
        UI.toast(`Session saved: ${r.filename}`);
        try {
          if (window.pywebview.api && window.pywebview.api.open_folder) await window.pywebview.api.open_folder(r.path);
          else await API.post('/reveal', { path: r.path });
        } catch (e) {}
      } catch (e) { UI.toast(e.message || 'Export failed', 'err'); }
      return;
    }
    const a = document.createElement('a');
    a.href = '/api/session/export';
    a.download = '';
    document.body.appendChild(a); a.click(); a.remove();
    UI.toast('Downloading session…');
  }

  async function importSession() {
    const ok = await UI.confirm('Import session',
      'Importing a session REPLACES all current data (leagues, teams, players, games…) with the contents of the file. This cannot be undone. Continue?',
      { danger:true, okLabel:'Choose file…' });
    if (!ok) return;
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.zip,application/zip';
    input.onchange = async () => {
      const file = input.files && input.files[0];
      if (!file) return;
      const fd = new FormData();
      fd.append('file', file, file.name);
      try {
        const res = await fetch('/api/session/import', { method:'POST', body: fd });
        if (!res.ok) {
          let detail = res.statusText;
          try { const j = await res.json(); detail = j.detail || detail; } catch (e) {}
          throw new Error(detail);
        }
        UI.toast('Session imported');
        state.leagueId = null; state.seasonId = null; state.teamId = null;
        App.refreshActions(); render(root());
      } catch (e) { UI.toast(e.message || 'Import failed', 'err'); }
    };
    input.click();
  }

  // ---------------- Leagues ----------------
  async function renderLeagues(body) {
    if (state.leagueId) return renderSeasons(body);
    const leagues = await API.leagues();
    if (!leagues.length) {
      body.innerHTML = UI.empty('🏆', 'No leagues yet. Create your first league to get started.',
        `<div class="coming-soon"><button class="btn primary" id="e1">+ New League</button></div>`);
      body.querySelector('#e1').onclick = () => editLeague();
      return;
    }
    body.innerHTML = `<div class="grid-cards">` + leagues.map((l) => `
      <div class="card" data-open="${l.id}">
        <div class="card-row"><h3>${UI.esc(l.name)}</h3><span class="pill">${UI.esc(l.abbrev||l.level||'League')}</span></div>
        <div class="muted">${l.season_count} season(s)</div>
        <div class="card-row" style="margin-top:12px">
          <span class="muted">${UI.esc(l.level||'')}</span>
          <span class="row-actions">
            <button class="btn sm ghost" data-edit="${l.id}">Edit</button>
            <button class="btn sm danger" data-del="${l.id}">Delete</button>
          </span></div></div>`).join('') + `</div>`;
    body.querySelectorAll('[data-open]').forEach((c) => c.onclick = (e) => {
      if (e.target.dataset.edit || e.target.dataset.del) return;
      state.leagueId = Number(c.dataset.open); App.refreshActions(); render(root());
    });
    body.querySelectorAll('[data-edit]').forEach((b) => b.onclick = (e) => {
      e.stopPropagation(); editLeague(leagues.find((x) => x.id == b.dataset.edit)); });
    body.querySelectorAll('[data-del]').forEach((b) => b.onclick = async (e) => {
      e.stopPropagation(); const l = leagues.find((x) => x.id == b.dataset.del);
      if (await UI.confirm('Delete league', `Delete "${l.name}" and all its seasons?`, {danger:true, okLabel:'Delete'})) {
        await API.del(`/leagues/${l.id}`); UI.toast('League deleted'); renderLeagues(body);
      }
    });
  }

  async function editLeague(l) {
    const vals = await UI.formModal(l ? 'Edit League' : 'New League', [
      {key:'name', label:'League Name', required:true, placeholder:'e.g. Pacific Coast League'},
      {key:'abbrev', label:'Abbreviation', placeholder:'PCL'},
      {key:'level', label:'Level', type:'select', options:['MLB','AAA','AA','A','College','Independent','Amateur']},
      {key:'notes', label:'Notes', type:'textarea'},
    ], l || {});
    if (!vals) return;
    if (l) { await API.put(`/leagues/${l.id}`, vals); UI.toast('League updated'); }
    else { await API.post('/leagues', vals); UI.toast('League created'); }
    render(root());
  }

  // ---------------- Seasons within a league ----------------
  async function renderSeasons(body) {
    if (state.seasonId) return renderSeasonDetail(body);
    const league = await API.get(`/leagues/${state.leagueId}`);
    const seasons = await API.seasons(state.leagueId);
    body.innerHTML = `
      <div class="breadcrumb"><a id="bc-l">Leagues</a> › <span>${UI.esc(league.name)}</span></div>
      <div class="panel"><div class="panel-head"><h2>Seasons</h2>
        <button class="btn primary sm" id="new-season">+ New Season</button></div>
        <div class="panel-body">${seasons.length ? seasonTable(seasons) : '<p class="muted">No seasons yet.</p>'}</div></div>`;
    body.querySelector('#bc-l').onclick = () => { state.leagueId = null; App.refreshActions(); render(root()); };
    body.querySelector('#new-season').onclick = () => editSeason();
    body.querySelectorAll('[data-open-season]').forEach((rr) => rr.onclick = (e) => {
      if (e.target.dataset.edit || e.target.dataset.del) return;
      state.seasonId = Number(rr.dataset.openSeason); render(root());
    });
    body.querySelectorAll('[data-edit]').forEach((b) => b.onclick = (e) => {
      e.stopPropagation(); editSeason(seasons.find((x) => x.id == b.dataset.edit)); });
    body.querySelectorAll('[data-del]').forEach((b) => b.onclick = async (e) => {
      e.stopPropagation(); const s = seasons.find((x) => x.id == b.dataset.del);
      if (await UI.confirm('Delete season', `Delete "${s.name}"?`, {danger:true, okLabel:'Delete'})) {
        await API.del(`/seasons/${s.id}`); UI.toast('Season deleted'); renderSeasons(body);
      }
    });
  }

  function seasonTable(seasons) {
    return `<table class="tbl"><thead><tr><th>Season</th><th>Year</th><th>Teams</th><th></th></tr></thead><tbody>` +
      seasons.map((s) => `<tr data-open-season="${s.id}" style="cursor:pointer">
        <td>${UI.esc(s.name)}</td><td>${UI.esc(s.year||'')}</td><td>${s.team_count}</td>
        <td class="row-actions">
          <button class="btn sm ghost" data-edit="${s.id}">Edit</button>
          <button class="btn sm danger" data-del="${s.id}">Delete</button></td></tr>`).join('') +
      `</tbody></table>`;
  }

  async function editSeason(s) {
    const vals = await UI.formModal(s ? 'Edit Season' : 'New Season', [
      {key:'name', label:'Season Name', required:true, placeholder:'e.g. 2026 Regular Season'},
      {key:'year', label:'Year', type:'number', placeholder:'2026'},
      {key:'start_date', label:'Start Date', type:'date'},
      {key:'end_date', label:'End Date', type:'date'},
      {key:'notes', label:'Notes', type:'textarea'},
    ], s || {});
    if (!vals) return;
    vals.league_id = state.leagueId;
    if (s) { await API.put(`/seasons/${s.id}`, vals); UI.toast('Season updated'); }
    else { await API.post('/seasons', vals); UI.toast('Season created'); }
    render(root());
  }

  // ---------------- Season detail: teams + rosters ----------------
  async function renderSeasonDetail(body) {
    const season = await API.get(`/seasons/${state.seasonId}`);
    const league = await API.get(`/leagues/${state.leagueId}`);
    const teams = await API.seasonTeams(state.seasonId);
    body.innerHTML = `
      <div class="breadcrumb">
        <a id="bc-l">Leagues</a> › <a id="bc-s">${UI.esc(league.name)}</a> › <span>${UI.esc(season.name)}</span></div>
      <div class="grid-2">
        <div class="panel"><div class="panel-head"><h2>Teams in Season</h2>
          <button class="btn primary sm" id="add-team">+ Add</button></div>
          <div class="panel-body" id="team-list"></div></div>
        <div class="panel"><div class="panel-head"><h2 id="roster-title">Roster</h2>
          <button class="btn primary sm" id="add-roster" disabled>+ Add Player</button></div>
          <div class="panel-body" id="roster-body"><p class="muted">Select a team to view its roster.</p></div></div>
      </div>`;
    body.querySelector('#bc-l').onclick = () => { state.leagueId=null; state.seasonId=null; App.refreshActions(); render(root()); };
    body.querySelector('#bc-s').onclick = () => { state.seasonId=null; render(root()); };
    const tl = body.querySelector('#team-list');
    tl.innerHTML = teams.length ? teams.map((t) => `
      <div class="card ${state.teamId===t.id?'selected':''}" data-team="${t.id}" style="margin-bottom:10px">
        <div class="card-row"><h3>${UI.esc(t.name)}</h3>
          <button class="btn sm danger" data-remove="${t.id}">Remove</button></div>
        <div class="muted">${UI.esc(t.city||'')} ${t.abbrev?('· '+UI.esc(t.abbrev)):''}</div></div>`).join('')
      : '<p class="muted">No teams added yet.</p>';
    tl.querySelectorAll('[data-team]').forEach((c) => c.onclick = (e) => {
      if (e.target.dataset.remove) return;
      state.teamId = Number(c.dataset.team); loadRoster();
      tl.querySelectorAll('[data-team]').forEach((x)=>x.classList.toggle('selected', x===c));
    });
    tl.querySelectorAll('[data-remove]').forEach((b) => b.onclick = async (e) => {
      e.stopPropagation();
      if (await UI.confirm('Remove team', 'Remove this team from the season?', {danger:true, okLabel:'Remove'})) {
        await API.del(`/seasons/${state.seasonId}/teams/${b.dataset.remove}`);
        if (state.teamId == b.dataset.remove) state.teamId = null;
        renderSeasonDetail(body);
      }
    });
    body.querySelector('#add-team').onclick = () => addTeamToSeason(teams.map((t)=>t.id));
    if (state.teamId && teams.some((t)=>t.id===state.teamId)) await loadRoster();

    async function loadRoster() {
      const rb = document.getElementById('roster-body');
      const rt = document.getElementById('roster-title');
      const addBtn = document.getElementById('add-roster');
      const team = teams.find((t) => t.id === state.teamId);
      if (!team || !rb) return;
      rt.textContent = `Roster — ${team.name}`;
      addBtn.disabled = false; addBtn.onclick = () => addRosterPlayer();
      const roster = await API.roster(state.seasonId, state.teamId);
      rb.innerHTML = roster.length ? `<table class="tbl"><thead><tr><th>#</th><th>Player</th><th>Pos</th><th></th></tr></thead><tbody>` +
        roster.map((r) => `<tr><td>${UI.esc(r.jersey||'')}</td><td>${UI.esc(r.full_name)}</td>
          <td><span class="tag">${UI.esc(r.position||'')}</span></td>
          <td class="row-actions"><button class="btn sm danger" data-rm="${r.roster_id}">Remove</button></td></tr>`).join('') +
        `</tbody></table>` : '<p class="muted">No players on this roster yet.</p>';
      rb.querySelectorAll('[data-rm]').forEach((b) => b.onclick = async () => {
        await API.del(`/roster/${b.dataset.rm}`); UI.toast('Removed'); loadRoster();
      });
    }
    async function addTeamToSeason(existing) {
      const all = await API.teams();
      const avail = all.filter((t) => !existing.includes(t.id));
      if (!avail.length) { UI.toast('No teams available. Create them in the Teams tab.', 'err'); return; }
      const vals = await UI.formModal('Add Team to Season', [
        {key:'team_id', label:'Team', type:'select', required:true, options: avail.map((t)=>({value:t.id,label:t.name}))}]);
      if (!vals) return;
      await API.post(`/seasons/${state.seasonId}/teams/${vals.team_id}`);
      UI.toast('Team added'); renderSeasonDetail(body);
    }
    async function addRosterPlayer() {
      const all = await API.players();
      if (!all.length) { UI.toast('No players exist. Create them in the Players tab.', 'err'); return; }
      // One team per player per season: hide anyone already on another team.
      const assigned = await API.get(`/seasons/${state.seasonId}/assignments`).catch(() => []);
      const takenElsewhere = new Set(assigned.filter((a) => a.team_id !== state.teamId).map((a) => a.player_id));
      const avail = all.filter((p) => !takenElsewhere.has(p.id));
      if (!avail.length) { UI.toast('All players are already assigned to a team this season.', 'err'); return; }
      const vals = await UI.formModal('Add Player to Roster', [
        {key:'player_id', label:'Player', type:'select', required:true, options: avail.map((p)=>({value:p.id,label:p.primary_position?`${p.full_name} (${p.primary_position})`:p.full_name}))},
        {key:'jersey', label:'Jersey #'},
        {key:'position', label:'Position', type:'select', options: POSITIONS}]);
      if (!vals) return;
      // Default the roster position to the player's primary position if unset.
      if (!vals.position) {
        const chosen = avail.find((p) => String(p.id) === String(vals.player_id));
        if (chosen && chosen.primary_position) vals.position = chosen.primary_position;
      }
      try {
        await API.post(`/seasons/${state.seasonId}/teams/${state.teamId}/roster`, vals);
        UI.toast('Player added'); loadRoster();
      } catch (e) { UI.toast(e.message || 'Could not add player', 'err'); }
    }
  }

  // ---------------- Teams ----------------
  async function renderTeams(body) {
    const teams = await API.teams();
    if (!teams.length) {
      body.innerHTML = UI.empty('🧢', 'No teams yet. Teams are global and reusable across leagues and seasons.',
        `<div class="coming-soon"><button class="btn primary" id="e1">+ New Team</button></div>`);
      body.querySelector('#e1').onclick = () => createTeam(); return;
    }
    body.innerHTML = `<div class="grid-cards">` + teams.map((t) => `
      <div class="card card-click" data-detail="${t.id}">
        <div class="card-row"><h3>${UI.esc(t.name)}</h3>
          <span class="pill" style="background:${UI.esc(t.color||'var(--blue-soft)')};color:#fff">${UI.esc(t.abbrev||'')}</span></div>
        <div class="muted">${UI.esc(t.city||'')}</div>
        <div class="card-row" style="margin-top:12px"><span class="muted" style="font-size:11px">Click for details</span><span class="row-actions">
          <button class="btn sm ghost" data-edit="${t.id}">Edit</button>
          <button class="btn sm danger" data-del="${t.id}">Delete</button></span></div></div>`).join('') + `</div>`;
    body.querySelectorAll('[data-detail]').forEach((c) => c.onclick = (e) => {
      if (e.target.dataset.edit || e.target.dataset.del) return;
      showTeamDetail(teams.find((x)=>x.id==c.dataset.detail));
    });
    body.querySelectorAll('[data-edit]').forEach((b) => b.onclick = (e) => { e.stopPropagation(); editTeam(teams.find((x)=>x.id==b.dataset.edit)); });
    body.querySelectorAll('[data-del]').forEach((b) => b.onclick = async () => {
      const t = teams.find((x)=>x.id==b.dataset.del);
      if (await UI.confirm('Delete team', `Delete "${t.name}"?`, {danger:true, okLabel:'Delete'})) {
        await API.del(`/teams/${t.id}`); UI.toast('Team deleted'); renderTeams(body);
      }
    });
  }
  // Feature 6: team detail view — shows the team's attributes plus every
  // season it participates in (with roster size).
  async function showTeamDetail(t) {
    if (!t) return;
    UI.openModal(`<div class="modal-head"><h2>${UI.esc(t.name)} ${t.abbrev?`<span class="tag">${UI.esc(t.abbrev)}</span>`:''}</h2>
      <button class="icon-btn" data-x>×</button></div>
      <div class="modal-body">
        <div class="detail-grid">
          <div><span class="muted">City</span><div>${UI.esc(t.city||'—')}</div></div>
          <div><span class="muted">Abbreviation</span><div>${UI.esc(t.abbrev||'—')}</div></div>
        </div>
        ${t.notes?`<p style="margin-top:10px">${UI.esc(t.notes)}</p>`:''}
        <h3 style="margin-top:16px">Seasons</h3>
        <div id="td-seasons"><p class="muted">Loading…</p></div>
      </div>
      <div class="modal-foot"><button class="btn primary" data-x>Close</button></div>`);
    document.querySelectorAll('#modal [data-x]').forEach((b) => b.onclick = UI.closeModal);
    // Scan leagues -> seasons to find where this team plays.
    try {
      const leagues = await API.leagues();
      const seasonLists = await Promise.all(leagues.map((l) => API.seasons(l.id).catch(()=>[])));
      const seasons = [];
      leagues.forEach((l, i) => seasonLists[i].forEach((s) => seasons.push({ ...s, league_name: l.name })));
      const checks = await Promise.all(seasons.map((s) => API.seasonTeams(s.id).catch(()=>[])));
      const rows = [];
      for (let i = 0; i < seasons.length; i++) {
        if (!checks[i].some((x) => x.id === t.id)) continue;
        const s = seasons[i];
        const roster = await API.roster(s.id, t.id).catch(()=>[]);
        rows.push(`<tr><td>${UI.esc(s.league_name)}</td><td>${UI.esc(s.name)}</td>
          <td>${UI.esc(s.year||'')}</td><td>${roster.length}</td></tr>`);
      }
      const host = document.getElementById('td-seasons');
      if (host) host.innerHTML = rows.length
        ? `<table class="tbl"><thead><tr><th>League</th><th>Season</th><th>Year</th><th>Roster</th></tr></thead><tbody>${rows.join('')}</tbody></table>`
        : '<p class="muted">Not assigned to any season yet.</p>';
    } catch (e) {
      const host = document.getElementById('td-seasons');
      if (host) host.innerHTML = '<p class="muted">Could not load season participation.</p>';
    }
  }

  // A team can only be created once a League and a Season exist, and the
  // creation flow REQUIRES assigning the new team to a League -> Season.
  async function createTeam() {
    const leagues = await API.leagues().catch(()=>[]);
    if (!leagues.length) {
      const go = await UI.confirm('Create a league first',
        'Teams must belong to a league and season. No leagues exist yet — create a league (and a season in it) before adding a team.',
        { okLabel: 'Go to Leagues' });
      if (go) { state.tab = 'leagues'; state.leagueId = null; state.seasonId = null; App.refreshActions(); render(root()); }
      return;
    }
    const leagueOpts = `<option value="">— select league —</option>` +
      leagues.map((l)=>`<option value="${l.id}">${UI.esc(l.name)}</option>`).join('');
    UI.openModal(`<div class="modal-head"><h2>New Team</h2>
      <button class="icon-btn" data-x>×</button></div>
      <div class="modal-body"><form id="nt-form">
        <div class="field"><label>Team Name <span style="color:var(--red)">*</span></label><input name="name" placeholder="e.g. River City Rangers" /></div>
        <div class="grid-2" style="grid-template-columns:1fr 1fr;gap:10px">
          <div class="field"><label>Abbreviation</label><input name="abbrev" placeholder="RCR" /></div>
          <div class="field"><label>City</label><input name="city" /></div>
        </div>
        <div class="field"><label>Accent Color (hex)</label><input name="color" placeholder="#2f7bff" /></div>
        <div class="field"><label>Notes</label><textarea name="notes" rows="2"></textarea></div>
        <h3 style="margin:14px 0 6px">Assign to League &amp; Season <span style="color:var(--red)">*</span></h3>
        <div class="field"><label>League <span style="color:var(--red)">*</span></label><select id="nt-league">${leagueOpts}</select></div>
        <div class="field"><label>Season <span style="color:var(--red)">*</span></label><select id="nt-season" disabled><option value="">— pick a league first —</option></select></div>
        <span class="muted" style="font-size:11px">A team must be assigned to a season. If the league has no seasons yet, create one in the Leagues &amp; Seasons tab first.</span>
      </form></div>
      <div class="modal-foot"><button class="btn ghost" data-cancel>Cancel</button>
        <button class="btn primary" data-ok>Create Team</button></div>`);
    const m = document.getElementById('modal');
    const lSel = m.querySelector('#nt-league');
    const sSel = m.querySelector('#nt-season');
    lSel.onchange = async () => {
      sSel.innerHTML = '<option value="">—</option>'; sSel.disabled = true;
      if (!lSel.value) return;
      const seasons = await API.seasons(Number(lSel.value)).catch(()=>[]);
      if (!seasons.length) {
        sSel.innerHTML = '<option value="">— no seasons in this league —</option>';
        UI.toast('This league has no seasons yet. Create one first.', 'err');
        return;
      }
      sSel.innerHTML = '<option value="">— select season —</option>' +
        seasons.map((s)=>`<option value="${s.id}">${UI.esc(s.name)}${s.year?` (${s.year})`:''}</option>`).join('');
      sSel.disabled = false;
    };
    m.querySelector('[data-x]').onclick = UI.closeModal;
    m.querySelector('[data-cancel]').onclick = UI.closeModal;
    m.querySelector('[data-ok]').onclick = async () => {
      const f = m.querySelector('#nt-form');
      const name = f.name.value.trim();
      let bad = false;
      if (!name) { f.name.style.borderColor = 'var(--red)'; bad = true; }
      if (!lSel.value) { lSel.style.borderColor = 'var(--red)'; bad = true; }
      if (!sSel.value) { sSel.style.borderColor = 'var(--red)'; bad = true; }
      if (bad) { UI.toast('Name, league and season are all required', 'err'); return; }
      const payload = {
        name,
        abbrev: f.abbrev.value.trim() || null,
        city: f.city.value.trim() || null,
        color: f.color.value.trim() || null,
        notes: f.notes.value.trim() || null,
      };
      try {
        const t = await API.post('/teams', payload);
        await API.post(`/seasons/${sSel.value}/teams/${t.id}`);
        UI.toast('Team created & assigned to season');
        UI.closeModal(); render(root());
      } catch (e) { UI.toast(e.message || 'Could not create team', 'err'); }
    };
  }

  async function editTeam(t) {
    const vals = await UI.formModal(t ? 'Edit Team' : 'New Team', [
      {key:'name', label:'Team Name', required:true, placeholder:'e.g. River City Rangers'},
      {key:'abbrev', label:'Abbreviation', placeholder:'RCR'},
      {key:'city', label:'City'},
      {key:'color', label:'Accent Color (hex)', placeholder:'#2f7bff'},
      {key:'notes', label:'Notes', type:'textarea'}], t || {});
    if (!vals) return;
    if (t) { await API.put(`/teams/${t.id}`, vals); UI.toast('Team updated'); }
    else { await API.post('/teams', vals); UI.toast('Team created'); }
    render(root());
  }

  // ---------------- Players ----------------
  async function renderPlayers(body) {
    const players = await API.players();
    if (!players.length) {
      body.innerHTML = UI.empty('🧍', 'No players yet. Each player gets a permanent ID so history follows them across leagues and seasons.',
        `<div class="coming-soon"><button class="btn primary" id="e1">+ New Player</button></div>`);
      body.querySelector('#e1').onclick = () => createPlayer(); return;
    }
    body.innerHTML = `<div class="panel"><div class="panel-body">
      <table class="tbl"><thead><tr><th>ID</th><th>Name</th><th>Pos</th><th>Bats/Throws</th><th></th></tr></thead><tbody>` +
      players.map((p) => `<tr><td><span class="tag mono">${UI.esc(p.public_id||('#'+p.id))}</span></td><td><a class="link" data-detail="${p.id}">${UI.esc(p.full_name)}</a></td>
        <td>${p.primary_position?`<span class="tag">${UI.esc(p.primary_position)}</span>`:'<span class="muted">\u2014</span>'}</td>
        <td class="muted">${UI.esc(p.bats||'-')}/${UI.esc(p.throws||'-')}</td>
        <td class="row-actions">
          <button class="btn sm ghost" data-hist="${p.id}">History</button>
          <button class="btn sm ghost" data-edit="${p.id}">Edit</button>
          <button class="btn sm danger" data-del="${p.id}">Delete</button></td></tr>`).join('') +
      `</tbody></table></div></div>`;
    body.querySelectorAll('[data-detail]').forEach((b) => b.onclick = () => showPlayerDetail(players.find((x)=>x.id==b.dataset.detail)));
    body.querySelectorAll('[data-edit]').forEach((b) => b.onclick = () => editPlayer(players.find((x)=>x.id==b.dataset.edit)));
    body.querySelectorAll('[data-hist]').forEach((b) => b.onclick = () => showHistory(players.find((x)=>x.id==b.dataset.hist)));
    body.querySelectorAll('[data-del]').forEach((b) => b.onclick = async () => {
      const p = players.find((x)=>x.id==b.dataset.del);
      if (await UI.confirm('Delete player', `Delete "${p.full_name}"?`, {danger:true, okLabel:'Delete'})) {
        await API.del(`/players/${p.id}`); UI.toast('Player deleted'); renderPlayers(body);
      }
    });
  }
  // Feature 8: create a new player AND optionally assign them to a team in one
  // step via cascading League -> Season -> Team dropdowns.
  async function createPlayer() {
    const posOpts = `<option value="">— none —</option>` +
      POSITIONS.map((c)=>`<option value="${c}">${c} — ${POS_LABELS[c]}</option>`).join('');
    const leagues = await API.leagues().catch(()=>[]);
    const leagueOpts = `<option value="">— don't assign now —</option>` +
      leagues.map((l)=>`<option value="${l.id}">${UI.esc(l.name)}</option>`).join('');
    UI.openModal(`<div class="modal-head"><h2>New Player</h2>
      <button class="icon-btn" data-x>×</button></div>
      <div class="modal-body"><form id="np-form">
        <div class="field"><label>Player Name <span style="color:var(--red)">*</span></label><input name="player_name" placeholder="e.g. Mike Trout" /></div>
        <div class="field"><label>Primary Position</label><select name="primary_position">${posOpts}</select></div>
        <div class="grid-2" style="grid-template-columns:1fr 1fr;gap:10px">
          <div class="field"><label>Bats</label><select name="bats"><option value=""></option><option value="R">Right</option><option value="L">Left</option><option value="S">Switch</option></select></div>
          <div class="field"><label>Throws</label><select name="throws"><option value=""></option><option value="R">Right</option><option value="L">Left</option></select></div>
        </div>
        <h3 style="margin:14px 0 6px">Assign to Team (optional)</h3>
        <div class="field"><label>League</label><select id="np-league">${leagueOpts}</select></div>
        <div class="field"><label>Season</label><select id="np-season" disabled><option value="">—</option></select></div>
        <div class="field"><label>Team</label><select id="np-team" disabled><option value="">—</option></select></div>
        <div class="field"><label>Jersey #</label><input name="jersey" /></div>
      </form></div>
      <div class="modal-foot"><button class="btn ghost" data-cancel>Cancel</button>
        <button class="btn primary" data-ok>Create Player</button></div>`);
    const m = document.getElementById('modal');
    const lSel = m.querySelector('#np-league');
    const sSel = m.querySelector('#np-season');
    const tSel = m.querySelector('#np-team');
    lSel.onchange = async () => {
      sSel.innerHTML = '<option value="">—</option>'; tSel.innerHTML = '<option value="">—</option>';
      sSel.disabled = true; tSel.disabled = true;
      if (!lSel.value) return;
      const seasons = await API.seasons(Number(lSel.value)).catch(()=>[]);
      sSel.innerHTML = '<option value="">— select season —</option>' +
        seasons.map((s)=>`<option value="${s.id}">${UI.esc(s.name)}${s.year?` (${s.year})`:''}</option>`).join('');
      sSel.disabled = false;
    };
    sSel.onchange = async () => {
      tSel.innerHTML = '<option value="">—</option>'; tSel.disabled = true;
      if (!sSel.value) return;
      const teams = await API.seasonTeams(Number(sSel.value)).catch(()=>[]);
      tSel.innerHTML = '<option value="">— select team —</option>' +
        teams.map((t)=>`<option value="${t.id}">${UI.esc(t.name)}</option>`).join('');
      tSel.disabled = false;
    };
    m.querySelector('[data-x]').onclick = UI.closeModal;
    m.querySelector('[data-cancel]').onclick = UI.closeModal;
    m.querySelector('[data-ok]').onclick = async () => {
      const f = m.querySelector('#np-form');
      const nm = f.player_name.value.trim();
      if (!nm) {
        f.player_name.style.borderColor = 'var(--red)';
        UI.toast('Player name is required', 'err'); return;
      }
      const nparts = nm.split(/\s+/);
      const first = nparts.shift();
      const last = nparts.join(' ');
      const payload = {
        first_name: first, last_name: last,
        primary_position: f.primary_position.value || null,
        bats: f.bats.value || null, throws: f.throws.value || null,
      };
      try {
        const created = await API.post('/players', payload);
        const sid = sSel.value, tid = tSel.value;
        if (sid && tid) {
          await API.post(`/seasons/${sid}/teams/${tid}/roster`, {
            player_id: created.id,
            jersey: f.jersey.value.trim() || null,
            position: payload.primary_position || null,
          });
          UI.toast(`Player created (ID ${created.public_id||('#'+created.id)}) & assigned`);
        } else {
          UI.toast(`Player created (ID ${created.public_id||('#'+created.id)})`);
        }
        UI.closeModal(); render(root());
      } catch (e) { UI.toast(e.message || 'Could not create player', 'err'); }
    };
  }

  async function editPlayer(p) {
    const curName = p ? [p.first_name, p.last_name].filter(Boolean).join(' ') : '';
    const vals = await UI.formModal(p ? 'Edit Player' : 'New Player', [
      {key:'player_name', label:'Player Name', required:true, value:curName, placeholder:'e.g. Mike Trout'},
      {key:'primary_position', label:'Primary Position', type:'select',
        options:[{value:'',label:'\u2014 none \u2014'}].concat(
          POSITIONS.map((c)=>({value:c,label:`${c} \u2014 ${POS_LABELS[c]}`})))},
      {key:'bats', label:'Bats', type:'select', options:[{value:'R',label:'Right'},{value:'L',label:'Left'},{value:'S',label:'Switch'}]},
      {key:'throws', label:'Throws', type:'select', options:[{value:'R',label:'Right'},{value:'L',label:'Left'}]},
      {key:'birthdate', label:'Birthdate', type:'date'},
      {key:'notes', label:'Notes', type:'textarea'}], p || {});
    if (!vals) return;
    const _np = String(vals.player_name || '').trim().split(/\s+/);
    vals.first_name = _np.shift() || '';
    vals.last_name = _np.join(' ');
    delete vals.player_name;
    if (p) { await API.put(`/players/${p.id}`, vals); UI.toast('Player updated'); }
    else { const c = await API.post('/players', vals); UI.toast(`Player created (ID ${c.public_id||('#'+c.id)})`); }
    render(root());
  }
  // Feature 6: full player detail view (attributes + roster history).
  async function showPlayerDetail(p) {
    if (!p) return;
    const hist = await API.playerHistory(p.id).catch(()=>[]);
    const rows = hist.length ? `<table class="tbl"><thead><tr><th>League</th><th>Season</th><th>Team</th><th>#</th><th>Pos</th></tr></thead><tbody>` +
      hist.map((h) => `<tr><td>${UI.esc(h.league_name)}</td><td>${UI.esc(h.season_name)}</td>
        <td>${UI.esc(h.team_name)}</td><td>${UI.esc(h.jersey||'')}</td><td>${UI.esc(h.position||'')}</td></tr>`).join('') +
      `</tbody></table>` : '<p class="muted">No roster history yet.</p>';
    UI.openModal(`<div class="modal-head"><h2>${UI.esc(p.full_name)} <span class="tag mono">${UI.esc(p.public_id||('#'+p.id))}</span></h2>
      <button class="icon-btn" data-x>×</button></div>
      <div class="modal-body">
        <div class="detail-grid">
          <div><span class="muted">Primary position</span><div>${UI.esc(p.primary_position||'—')}</div></div>
          <div><span class="muted">Bats / Throws</span><div>${UI.esc(p.bats||'-')} / ${UI.esc(p.throws||'-')}</div></div>
          <div><span class="muted">Birthdate</span><div>${UI.esc(p.birthdate||'—')}</div></div>
        </div>
        ${p.notes?`<p style="margin-top:10px">${UI.esc(p.notes)}</p>`:''}
        <h3 style="margin-top:16px">Roster History</h3>
        ${rows}
      </div>
      <div class="modal-foot"><button class="btn primary" data-x>Close</button></div>`);
    document.querySelectorAll('#modal [data-x]').forEach((b) => b.onclick = UI.closeModal);
  }

  async function showHistory(p) {
    const hist = await API.playerHistory(p.id);
    const rows = hist.length ? `<table class="tbl"><thead><tr><th>League</th><th>Season</th><th>Team</th><th>#</th><th>Pos</th></tr></thead><tbody>` +
      hist.map((h) => `<tr><td>${UI.esc(h.league_name)}</td><td>${UI.esc(h.season_name)}</td>
        <td>${UI.esc(h.team_name)}</td><td>${UI.esc(h.jersey||'')}</td><td>${UI.esc(h.position||'')}</td></tr>`).join('') +
      `</tbody></table>` : '<p class="muted">No roster history yet.</p>';
    UI.openModal(`<div class="modal-head"><h2>${UI.esc(p.full_name)} <span class="tag mono">${UI.esc(p.public_id||('#'+p.id))}</span></h2>
      <button class="icon-btn" data-x>×</button></div><div class="modal-body">${rows}</div>
      <div class="modal-foot"><button class="btn primary" data-x>Close</button></div>`);
    document.querySelectorAll('#modal [data-x]').forEach((b) => b.onclick = UI.closeModal);
  }

  return { render, actions, onAction, state };
})();
