// Initialize Game / Scoring wizard.
// One screen to create-or-pick a League → Season → Teams → Rosters → Game,
// then jump straight into the live Scorer. Anything missing can be created
// inline here without leaving the screen.
const Setup = (() => {
  const S = { leagueId: null, seasonId: null, awayId: null, homeId: null };
  const POSITIONS = ['P','C','1B','2B','3B','SS','LF','CF','RF','DH','UT'];
  const POS_LABELS = {P:'Pitcher',C:'Catcher','1B':'First Base','2B':'Second Base',
    '3B':'Third Base',SS:'Shortstop',LF:'Left Field',CF:'Center Field',
    RF:'Right Field',DH:'Designated Hitter',UT:'Utility'};
  const root = () => document.getElementById('view-root');

  async function render(r) {
    r = r || root();
    document.getElementById('view-title').textContent = 'Initialize Game / Scoring';
    document.querySelectorAll('.nav-item').forEach((n) =>
      n.classList.toggle('active', n.dataset.view === 'setup'));

    const leagues = await API.leagues();
    const seasons = S.leagueId ? await API.seasons(S.leagueId) : [];
    if (S.seasonId && !seasons.some((s) => s.id === S.seasonId)) S.seasonId = null;
    const teams = S.seasonId ? await API.seasonTeams(S.seasonId) : [];
    const ids = teams.map((t) => t.id);
    if (S.awayId && !ids.includes(S.awayId)) S.awayId = null;
    if (S.homeId && !ids.includes(S.homeId)) S.homeId = null;
    const awayRoster = S.awayId ? await API.roster(S.seasonId, S.awayId) : [];
    const homeRoster = S.homeId ? await API.roster(S.seasonId, S.homeId) : [];

    r.innerHTML = `
      <div class="panel" style="margin-bottom:16px"><div class="panel-body">
        <p class="muted">Create or pick each piece below, then press <b>Start Scoring</b>.
          Anything missing — a league, season, team, or player — can be created right
          here without leaving this screen.</p></div></div>
      <div id="wz">
        ${leagueSection(leagues)}
        ${seasonSection(seasons)}
        ${teamsSection(teams)}
        ${rosterSection(teams, awayRoster, homeRoster)}
        ${gameSection(awayRoster, homeRoster)}
      </div>`;
    bind(r, leagues, seasons, teams);
  }

  // ---------------------------------------------------------------- sections
  function step(n, title, bodyHtml, ready) {
    return `<div class="panel setup-step ${ready ? '' : 'is-locked'}" style="margin-bottom:14px">
      <div class="panel-head"><h2><span class="step-num">${n}</span> ${title}</h2></div>
      <div class="panel-body">${bodyHtml}</div></div>`;
  }

  function selOpts(list, sel, labeler) {
    return '<option value="">— select —</option>' + list.map((x) =>
      `<option value="${x.id}" ${x.id===sel?'selected':''}>${UI.esc(labeler(x))}</option>`).join('');
  }

  function leagueSection(leagues) {
    const body = `<div class="setup-row">
      <select id="wz-league">${selOpts(leagues, S.leagueId, (l)=>l.name)}</select>
      <button class="btn sm" id="wz-new-league">+ New League</button></div>`;
    return step(1, 'League', body, true);
  }

  function seasonSection(seasons) {
    if (!S.leagueId) return step(2, 'Season', '<p class="muted">Pick a league first.</p>', false);
    const body = `<div class="setup-row">
      <select id="wz-season">${selOpts(seasons, S.seasonId, (s)=>s.name + (s.year?` (${s.year})`:''))}</select>
      <button class="btn sm" id="wz-new-season">+ New Season</button></div>`;
    return step(2, 'Season', body, true);
  }

  function teamsSection(teams) {
    if (!S.seasonId) return step(3, 'Teams', '<p class="muted">Pick a season first.</p>', false);
    const body = `<div class="setup-grid2">
        <label class="fld">Away team
          <select id="wz-away">${selOpts(teams, S.awayId, (t)=>t.name)}</select></label>
        <label class="fld">Home team
          <select id="wz-home">${selOpts(teams, S.homeId, (t)=>t.name)}</select></label>
      </div>
      <div class="setup-row" style="margin-top:10px">
        <button class="btn sm" id="wz-add-team">+ Add existing team to season</button>
        <button class="btn sm" id="wz-new-team">+ Create new team</button></div>`;
    return step(3, 'Teams', body, true);
  }

  function rosterCard(side, team, roster) {
    if (!team) return `<div class="roster-col"><h3 class="muted">${side==='away'?'Away':'Home'} — not selected</h3></div>`;
    const rows = roster.length ? roster.map((p) =>
      `<tr><td>${UI.esc(p.jersey||'')}</td><td>${UI.esc(p.full_name)}</td>
        <td><span class="tag">${UI.esc(p.position||'')}</span></td></tr>`).join('')
      : '<tr><td colspan="3" class="muted">No players yet.</td></tr>';
    return `<div class="roster-col">
      <div class="card-row"><h3>${UI.esc(team.name)}</h3>
        <span class="muted">${roster.length} player(s)</span></div>
      <table class="tbl"><thead><tr><th>#</th><th>Player</th><th>Pos</th></tr></thead>
        <tbody>${rows}</tbody></table>
      <div class="setup-row" style="margin-top:8px">
        <button class="btn sm" data-add-existing="${side}">+ Existing</button>
        <button class="btn sm" data-add-new="${side}">+ New player</button></div></div>`;
  }

  function rosterSection(teams, aR, hR) {
    if (!S.awayId && !S.homeId)
      return step(4, 'Rosters', '<p class="muted">Pick the two teams first.</p>', false);
    const away = teams.find((t) => t.id === S.awayId);
    const home = teams.find((t) => t.id === S.homeId);
    const body = `<div class="setup-grid2">${rosterCard('away', away, aR)}${rosterCard('home', home, hR)}</div>`;
    return step(4, 'Rosters', body, true);
  }

  function gameSection(aR, hR) {
    const ready = S.awayId && S.homeId && S.awayId !== S.homeId && aR.length && hR.length;
    const hint = !S.awayId || !S.homeId ? 'Select both teams above.'
      : S.awayId === S.homeId ? 'Away and home teams must differ.'
      : (!aR.length || !hR.length) ? 'Add at least one player to each roster.'
      : 'Ready to score.';
    const body = `<div class="setup-grid2">
        <label class="fld">Date <input id="wz-date" type="date" /></label>
        <label class="fld">Venue <input id="wz-venue" placeholder="Ballpark" /></label>
        <label class="fld">Regulation innings <input id="wz-inn" type="number" value="9" /></label>
      </div>
      <div class="setup-row" style="margin-top:12px;align-items:center">
        <button class="btn primary" id="wz-start" ${ready?'':'disabled'}>▶ Start Scoring</button>
        <span class="muted">${UI.esc(hint)}</span></div>`;
    return step(5, 'Game & Start', body, true);
  }

  // ------------------------------------------------------------------- bind
  function bind(r, leagues, seasons, teams) {
    const $ = (id) => r.querySelector(id);
    const rerender = () => render(r);

    if ($('#wz-league')) $('#wz-league').onchange = (e) => {
      S.leagueId = Number(e.target.value) || null; S.seasonId = null;
      S.awayId = null; S.homeId = null; rerender();
    };
    if ($('#wz-new-league')) $('#wz-new-league').onclick = async () => {
      const v = await UI.formModal('New League', [
        {key:'name', label:'League Name', required:true, placeholder:'e.g. Pacific Coast League'},
        {key:'abbrev', label:'Abbreviation', placeholder:'PCL'},
        {key:'level', label:'Level', type:'select', options:['MLB','AAA','AA','A','College','Independent','Amateur']}]);
      if (!v) return;
      const l = await API.post('/leagues', v); S.leagueId = l.id; S.seasonId = null;
      UI.toast('League created'); rerender();
    };

    if ($('#wz-season')) $('#wz-season').onchange = (e) => {
      S.seasonId = Number(e.target.value) || null; S.awayId = null; S.homeId = null; rerender();
    };
    if ($('#wz-new-season')) $('#wz-new-season').onclick = async () => {
      const v = await UI.formModal('New Season', [
        {key:'name', label:'Season Name', required:true, placeholder:'e.g. 2026 Regular Season'},
        {key:'year', label:'Year', type:'number', placeholder:'2026'}]);
      if (!v) return;
      v.league_id = S.leagueId;
      const s = await API.post('/seasons', v); S.seasonId = s.id;
      UI.toast('Season created'); rerender();
    };

    if ($('#wz-away')) $('#wz-away').onchange = (e) => { S.awayId = Number(e.target.value) || null; rerender(); };
    if ($('#wz-home')) $('#wz-home').onchange = (e) => { S.homeId = Number(e.target.value) || null; rerender(); };

    if ($('#wz-add-team')) $('#wz-add-team').onclick = async () => {
      const all = await API.teams();
      const inSeason = teams.map((t) => t.id);
      const avail = all.filter((t) => !inSeason.includes(t.id));
      if (!avail.length) { UI.toast('No other teams exist. Use “Create new team”.', 'err'); return; }
      const v = await UI.formModal('Add Team to Season', [
        {key:'team_id', label:'Team', type:'select', required:true,
          options: avail.map((t) => ({value:t.id, label:t.name}))}]);
      if (!v) return;
      await API.post(`/seasons/${S.seasonId}/teams/${v.team_id}`);
      if (!S.awayId) S.awayId = Number(v.team_id); else if (!S.homeId) S.homeId = Number(v.team_id);
      UI.toast('Team added'); rerender();
    };
    if ($('#wz-new-team')) $('#wz-new-team').onclick = async () => {
      const v = await UI.formModal('New Team', [
        {key:'name', label:'Team Name', required:true, placeholder:'e.g. River City Rangers'},
        {key:'abbrev', label:'Abbreviation', placeholder:'RCR'},
        {key:'city', label:'City'}]);
      if (!v) return;
      const t = await API.post('/teams', v);
      await API.post(`/seasons/${S.seasonId}/teams/${t.id}`);
      if (!S.awayId) S.awayId = t.id; else if (!S.homeId) S.homeId = t.id;
      UI.toast('Team created & added'); rerender();
    };

    r.querySelectorAll('[data-add-existing]').forEach((b) => b.onclick =
      () => addExisting(b.dataset.addExisting, rerender));
    r.querySelectorAll('[data-add-new]').forEach((b) => b.onclick =
      () => addNew(b.dataset.addNew, rerender));

    if ($('#wz-start')) $('#wz-start').onclick = async () => {
      const body = {
        season_id: S.seasonId,
        away_team_id: S.awayId,
        home_team_id: S.homeId,
        game_date: ($('#wz-date').value || '').trim() || null,
        venue: ($('#wz-venue').value || '').trim() || null,
        regulation_innings: Number($('#wz-inn').value) || 9,
      };
      const g = await API.post('/games', body);
      UI.toast('Game created — opening scorer');
      Scorer.open(g.id);
    };
  }

  async function teamId(side) { return side === 'away' ? S.awayId : S.homeId; }

  async function addExisting(side, done) {
    const tid = await teamId(side);
    const all = await API.players();
    if (!all.length) { UI.toast('No players exist yet. Use “+ New player”.', 'err'); return; }
    const onRoster = (await API.roster(S.seasonId, tid)).map((p) => p.player_id);
    // One team per player per season: also exclude anyone on another team.
    const assigned = await API.get(`/seasons/${S.seasonId}/assignments`).catch(() => []);
    const elsewhere = new Set(assigned.filter((a) => a.team_id !== tid).map((a) => a.player_id));
    const avail = all.filter((p) => !onRoster.includes(p.id) && !elsewhere.has(p.id));
    if (!avail.length) { UI.toast('No eligible players — the rest are already on a team this season.', 'err'); return; }
    const v = await UI.formModal('Add Existing Player', [
      {key:'player_id', label:'Player', type:'select', required:true,
        options: avail.map((p) => ({value:p.id,
          label: (p.public_id?`[${p.public_id}] `:'') + p.full_name + (p.primary_position?` (${p.primary_position})`:'')}))},
      {key:'jersey', label:'Jersey #'},
      {key:'position', label:'Position', type:'select', options: POSITIONS}]);
    if (!v) return;
    if (!v.position) {
      const chosen = avail.find((p) => String(p.id) === String(v.player_id));
      if (chosen && chosen.primary_position) v.position = chosen.primary_position;
    }
    try {
      await API.post(`/seasons/${S.seasonId}/teams/${tid}/roster`, v);
      UI.toast('Player added'); done();
    } catch (e) { UI.toast(e.message || 'Could not add player', 'err'); }
  }

  async function addNew(side, done) {
    const tid = await teamId(side);
    const v = await UI.formModal('Create New Player', [
      {key:'first_name', label:'First Name', required:true},
      {key:'last_name', label:'Last Name', required:true},
      {key:'primary_position', label:'Primary Position', type:'select',
        options: POSITIONS.map((c) => ({value:c, label:`${c} — ${POS_LABELS[c]}`}))},
      {key:'bats', label:'Bats', type:'select',
        options:[{value:'R',label:'Right'},{value:'L',label:'Left'},{value:'S',label:'Switch'}]},
      {key:'throws', label:'Throws', type:'select',
        options:[{value:'R',label:'Right'},{value:'L',label:'Left'}]},
      {key:'jersey', label:'Jersey #'}]);
    if (!v) return;
    const jersey = v.jersey; delete v.jersey;
    const p = await API.post('/players', v);
    await API.post(`/seasons/${S.seasonId}/teams/${tid}/roster`,
      {player_id: p.id, jersey: jersey || null, position: v.primary_position || null});
    UI.toast(`Player created (ID ${p.public_id || ('#'+p.id)}) & added`); done();
  }

  return { render, state: S };
})();
