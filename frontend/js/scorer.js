// Live Game Scorer view. Entry: Scorer.open(gameId).
const Scorer = (() => {
  let S = {};
  const root = () => document.getElementById('view-root');
  const POS = ['P','C','1B','2B','3B','SS','LF','CF','RF','DH'];
  // Scoring position number (1..9) -> defensive code, for error attribution.
  const POS_NUM = {1:'P',2:'C',3:'1B',4:'2B',5:'3B',6:'SS',7:'LF',8:'CF',9:'RF'};
  const BATT_GROUPS = {
    Hits: ['1B','2B','3B','HR'],
    Outs: ['K','KL','GO','FO','LO','POP','FOUL','SF','SAC','DP','TP'],
    'On Base': ['BB','IBB','HBP','ROE','FC','D3K','CI'],
  };
  const INHERENT_OUTS = {K:1,KL:1,GO:1,FO:1,LO:1,POP:1,FOUL:1,SF:1,SAC:1,DP:1,TP:1};

  // Parse an "HH:MM:SS" (or "H:MM:SS") string into total seconds; also accepts
  // bare "MM:SS" and a plain number of minutes. Returns null if unparseable.
  function hmsToSeconds(str) {
    const s = String(str).trim();
    if (!s) return null;
    if (/^\d+$/.test(s)) return Number(s) * 60; // legacy: plain minutes
    const parts = s.split(':').map((x) => x.trim());
    if (parts.some((x) => x === '' || !/^\d+$/.test(x))) return null;
    let h = 0, m = 0, sec = 0;
    if (parts.length === 3) [h, m, sec] = parts.map(Number);
    else if (parts.length === 2) [m, sec] = parts.map(Number);
    else return null;
    if (m > 59 || sec > 59) return null;
    return h * 3600 + m * 60 + sec;
  }

  async function open(gameId) {
    S = { gameId, pitcher: null, catcher: null, pitches: [] };
    await reload();
    document.getElementById('view-title').textContent = 'Scorer';
    document.querySelectorAll('.nav-item').forEach((n) => n.classList.remove('active'));
    render();
  }

  async function reload() {
    S.game = await API.get(`/games/${S.gameId}`);
    S.pitchTracking = !!S.game.pitch_tracking;
    if (!Array.isArray(S.pitches)) S.pitches = [];
    S.lineups = await API.get(`/games/${S.gameId}/lineups`);
    S.ls = await API.get(`/games/${S.gameId}/state`);
    S.events = await API.get(`/games/${S.gameId}/events`);
    if (!S.cat) S.cat = await API.get('/games/catalogue');
  }

  function battingSide() { return S.ls.state.half === 'T' ? 'away' : 'home'; }
  function fieldingSide() { return S.ls.state.half === 'T' ? 'home' : 'away'; }

  function lineupReady() {
    return (S.lineups.away || []).length >= 1 && (S.lineups.home || []).length >= 1;
  }

  function currentBatter() {
    const side = battingSide();
    const lu = S.lineups[side] || [];
    if (!lu.length) return null;
    // Bat out of order: an explicit override wins until it is consumed/cleared.
    if (S.batOverride) {
      const ov = lu.find((x) => String(x.player_id) === String(S.batOverride));
      if (ov) return ov;
      S.batOverride = null;
    }
    const paCount = S.events.filter((e) => e.kind === 'PA' && e.half === S.ls.state.half).length;
    // NB: half only distinguishes T/B; across innings the order continues.
    const paThisSide = S.events.filter((e) => e.kind === 'PA' &&
      ((side === 'away' && e.half === 'T') || (side === 'home' && e.half === 'B'))).length;
    const order = lu.slice().sort((a, b) => a.batting_order - b.batting_order);
    return order[paThisSide % order.length];
  }

  function defaultBattery() {
    const lu = S.lineups[fieldingSide()] || [];
    const ids = lu.map((x) => x.player_id);
    const p = lu.find((x) => x.position === 'P');
    const cc = lu.find((x) => x.position === 'C');
    // Reset battery when the fielding side changed (current pick no longer on field).
    if (!S.pitcher || !ids.includes(S.pitcher)) S.pitcher = p ? p.player_id : (ids[0] || null);
    if (!S.catcher || !ids.includes(S.catcher)) S.catcher = cc ? cc.player_id : (ids[0] || null);
  }

  // ------------------------------------------------------------------ render
  function render() {
    S._names = null;
    defaultBattery();
    const g = S.game;
    root().innerHTML = `
      <div class="scorer">
        ${headerHtml(g)}
        ${lineScoreHtml()}
        ${!lineupReady() ? lineupSetupHtml() : liveHtml()}
      </div>`;
    bindHeader();
    if (!lineupReady()) bindLineupSetup(); else bindLive();
  }

  function headerHtml(g) {
    const s = S.ls.state;
    const arrow = s.half === 'T' ? '▲' : '▼';
    const statusTag = { setup:'Setup', in_progress:'Live', paused:'Paused', final:'Final', forfeited:'Forfeited' }[g.status] || g.status;
    return `
      <div class="sc-head panel">
        <div class="sc-teams">
          <div class="sc-team"><span class="sc-tn">${UI.esc(g.away_name)}</span>
            <span class="sc-score">${s.score.away}</span></div>
          <div class="sc-mid">
            <span class="sc-inn">${arrow} ${s.inning}</span>
            <span class="sc-outs">${'●'.repeat(s.outs)}${'○'.repeat(Math.max(0,2-s.outs))} ${s.outs} out</span>
            <span class="tag">${statusTag}</span>
          </div>
          <div class="sc-team"><span class="sc-score">${s.score.home}</span>
            <span class="sc-tn">${UI.esc(g.home_name)}</span></div>
        </div>
        <div class="sc-actions">
          <button class="btn ghost sm" id="sc-back">‹ Games</button>
          <button class="btn ghost sm" id="sc-info">Info</button>
          <button class="btn ghost sm" id="sc-lineups">Lineups</button>
          <button class="btn ghost sm" id="sc-subs">Subs</button>
          <button class="btn ghost sm" id="sc-multisubs">Multiple Subs</button>
          <button class="btn ghost sm" id="sc-pt" title="Toggle pitch-by-pitch tracking">Pitches: ${S.pitchTracking?'On':'Off'}</button>
          ${g.status==='in_progress' ? '<button class="btn ghost sm" id="sc-pause">Pause</button>' : ''}
          ${g.status==='paused' ? '<button class="btn primary sm" id="sc-resume">Resume</button>' : ''}
          ${['final','forfeited'].includes(g.status) ? '' : '<button class="btn sm" id="sc-end" style="border-color:#63263a;color:var(--red)">End Game</button>'}
        </div>
      </div>`;
  }

  function lineScoreHtml() {
    const ls = S.ls; const g = S.game;
    const th = ls.innings.map((i) => `<th>${i}</th>`).join('');
    const cells = (arr) => arr.map((v) => `<td>${v || 0}</td>`).join('');
    const row = (name, arr, t) => `<tr><td class="sc-ls-team">${UI.esc(name)}</td>${cells(arr)}
      <td class="sc-ls-tot">${t.R}</td><td>${t.H}</td><td>${t.E}</td></tr>`;
    return `<div class="panel" style="margin:14px 0"><div class="panel-body" style="overflow:auto">
      <table class="tbl sc-ls"><thead><tr><th></th>${th}<th>R</th><th>H</th><th>E</th></tr></thead>
      <tbody>${row(g.away_abbrev||g.away_name, ls.away, ls.totals.away)}
      ${row(g.home_abbrev||g.home_name, ls.home, ls.totals.home)}</tbody></table>
    </div></div>`;
  }

  function bindHeader() {
    const $ = (id) => document.getElementById(id);
    $('sc-back').onclick = () => App.show('games');
    $('sc-info').onclick = editInfo;
    $('sc-lineups').onclick = () => { S.forceLineup = true; renderLineupEditor(); };
    if ($('sc-subs')) $('sc-subs').onclick = manageSubs;
    if ($('sc-multisubs')) $('sc-multisubs').onclick = manageMultiSubs;
    if ($('sc-pt')) $('sc-pt').onclick = togglePitchTracking;
    if ($('sc-pause')) $('sc-pause').onclick = () => setStatus('paused');
    if ($('sc-resume')) $('sc-resume').onclick = () => setStatus('in_progress');
    if ($('sc-end')) $('sc-end').onclick = endGame;
  }

  async function setStatus(status) {
    S.game = await API.patch(`/games/${S.gameId}/state`, { status });
    render();
  }

  async function togglePitchTracking() {
    const next = S.pitchTracking ? 0 : 1;
    S.game = await API.patch(`/games/${S.gameId}/state`, { pitch_tracking: next });
    S.pitchTracking = !!next;
    if (!S.pitchTracking) S.pitches = [];
    render();
    UI.toast(`Pitch tracking ${S.pitchTracking ? 'enabled' : 'disabled'}`);
  }

  // ------------------------------------------------------------- name lookup
  function nameMap() {
    const m = {};
    ['away','home'].forEach((s) => (S.lineups[s]||[]).forEach((x) => m[x.player_id] = x.full_name));
    S.events.forEach((e) => { if (e.batter_id) m[e.batter_id]=e.batter_name; if (e.runner_id) m[e.runner_id]=e.runner_name; });
    return m;
  }
  function nameOf(id) { if (!id) return ''; return (S._names ||= nameMap())[id] || `#${id}`; }

  // --------------------------------------------------------- lineup setup/edit
  function lineupSetupHtml() {
    return `<div class="panel"><div class="panel-head"><h2>Set Lineups</h2></div>
      <div class="panel-body"><p class="muted">Add each team's batting order and defensive positions to begin scoring. Assign one <b>P</b> (pitcher) and one <b>C</b> (catcher) per side so battery attribution works.</p>
      <div id="lu-editor"></div></div></div>`;
  }
  function bindLineupSetup() { renderLineupEditor(); }

  async function renderLineupEditor() {
    S._names = null;
    const host = document.getElementById('lu-editor') || (() => {
      root().querySelector('.scorer').insertAdjacentHTML('beforeend',
        `<div class="panel" style="margin-top:14px"><div class="panel-head"><h2>Edit Lineups</h2>
         <button class="btn ghost sm" id="lu-close">Close</button></div><div class="panel-body"><div id="lu-editor"></div></div></div>`);
      document.getElementById('lu-close').onclick = () => { S.forceLineup=false; render(); };
      return document.getElementById('lu-editor');
    })();
    const [awayR, homeR] = await Promise.all([
      API.roster(S.game.season_id, S.game.away_team_id).catch(()=>[]),
      API.roster(S.game.season_id, S.game.home_team_id).catch(()=>[]),
    ]);
    S._pool = { away: rosterPool(awayR), home: rosterPool(homeR) };
    S._draft = S._draft || { away: draftFrom(S.lineups.away), home: draftFrom(S.lineups.home) };
    host.innerHTML = `<div class="grid-2" style="grid-template-columns:1fr 1fr">
      ${sideEditor('away', S.game.away_name)}${sideEditor('home', S.game.home_name)}</div>
      <div style="margin-top:16px;text-align:right"><button class="btn primary" id="lu-save">Save Lineups</button></div>`;
    ['away','home'].forEach(bindSideEditor);
    document.getElementById('lu-save').onclick = saveLineups;
  }
  function rosterPool(roster) {
    // Only players actually rostered for this team in this season are eligible
    // for the lineup -- avoids the redundant "every player in the database"
    // list and keeps each team's choices to its own roster.
    return (roster || [])
      .map((r) => ({ player_id: r.id, full_name: r.full_name, position: r.position }))
      .sort((a, b) => a.full_name.localeCompare(b.full_name));
  }
  function draftFrom(lu) {
    const arr = (lu||[]).slice().sort((a,b)=>a.batting_order-b.batting_order)
      .map((x)=>({player_id:x.player_id, position:x.position}));
    while (arr.length < 9) arr.push({player_id:'', position:''});
    return arr;
  }
  function sideEditor(side, name) {
    const pool = S._pool[side]; const draft = S._draft[side];
    const opts = (sel) => pool.map((p)=>`<option value="${p.player_id}" ${p.player_id==sel?'selected':''}>${UI.esc(p.full_name)}</option>`).join('');
    const posOpts = (sel) => POS.map((p)=>`<option ${p==sel?'selected':''}>${p}</option>`).join('');
    const rows = draft.map((d,i)=>`<tr><td>${i+1}</td>
      <td><select data-side="${side}" data-i="${i}" data-f="player_id" style="width:100%"><option value=""></option>${opts(d.player_id)}</select></td>
      <td><select data-side="${side}" data-i="${i}" data-f="position"><option value=""></option>${posOpts(d.position)}</select></td></tr>`).join('');
    return `<div><div class="section-title">${UI.esc(name)}</div>
      <table class="tbl"><thead><tr><th>#</th><th>Batter</th><th>Pos</th></tr></thead><tbody>${rows}</tbody></table>
      <div style="margin-top:8px;display:flex;gap:8px">
        <button class="btn ghost sm" data-add="${side}">+ Add slot</button>
        <button class="btn ghost sm" data-remove-slot="${side}" ${draft.length<=1?'disabled':''}>− Remove slot</button>
      </div></div>`;
  }
  function bindSideEditor(side) {
    document.querySelectorAll(`select[data-side="${side}"]`).forEach((sel)=> sel.onchange = () => {
      S._draft[side][+sel.dataset.i][sel.dataset.f] = sel.value;
    });
    const add = document.querySelector(`[data-add="${side}"]`);
    if (add) add.onclick = () => { S._draft[side].push({player_id:'',position:''}); renderLineupEditor(); };
    const rm = document.querySelector(`[data-remove-slot="${side}"]`);
    if (rm) rm.onclick = () => {
      if (S._draft[side].length <= 1) return;
      S._draft[side].pop(); // drop the last batting slot
      renderLineupEditor();
    };
  }
  async function saveLineups() {
    const MANDATORY = ['P','C','1B','2B','3B','SS','LF','CF','RF'];
    // Validate the nine defensive positions per side that has any players.
    const problems = [];
    for (const side of ['away','home']) {
      const entries = (S._draft[side]||[]).filter((d)=>d.player_id);
      if (!entries.length) continue;
      const label = side === 'away' ? (S.game.away_abbrev||S.game.away_name||'Away')
                                    : (S.game.home_abbrev||S.game.home_name||'Home');
      const positions = entries.map((d)=>d.position).filter(Boolean);
      const missing = MANDATORY.filter((p)=>!positions.includes(p));
      const dups = positions.filter((p,i)=> p!=='DH' && positions.indexOf(p)!==i);
      if (missing.length) problems.push(`${label}: missing ${missing.join(', ')}`);
      if (dups.length) problems.push(`${label}: duplicate ${[...new Set(dups)].join(', ')}`);
    }
    if (problems.length) {
      const ok = await UI.confirm('Incomplete defensive lineup',
        `Fielding issues \u2014 ${problems.join('; ')}. All nine positions (P, C, 1B, 2B, 3B, SS, LF, CF, RF) should be assigned exactly once for correct battery and fielding stats. Save anyway?`);
      if (!ok) return;
    }
    for (const side of ['away','home']) {
      const entries = S._draft[side].filter((d)=>d.player_id)
        .map((d,idx)=>({batting_order: idx+1, player_id:Number(d.player_id), position:d.position||null}));
      if (entries.length) await API.post(`/games/${S.gameId}/lineups`, { side, entries });
    }
    S._draft = null; S.forceLineup = false; UI.toast('Lineups saved');
    await reload(); render();
  }

  // ------------------------------------------------------------- live scoring
  function shortName(full) {
    if (!full) return '';
    const parts = full.trim().split(/\s+/);
    return parts.length > 1 ? parts[parts.length - 1] : parts[0];
  }

  function liveHtml() {
    const b = currentBatter();
    const g = S.game;
    const fld = S.lineups[fieldingSide()] || [];
    const battOpts = (sel) => fld.map((x) => `<option value="${x.player_id}" ${x.player_id==sel?'selected':''}>${UI.esc(x.full_name)}${x.position?` (${x.position})`:''}</option>`).join('');
    const done = ['final','forfeited'].includes(g.status);
    const battName = battingSide()==='away' ? (g.away_abbrev||g.away_name) : (g.home_abbrev||g.home_name);
    const batLu = (S.lineups[battingSide()] || []).slice().sort((a,b)=>a.batting_order-b.batting_order);
    const batOpts = batLu.map((x) => `<option value="${x.player_id}" ${b&&x.player_id==b.player_id?'selected':''}>#${x.batting_order} ${UI.esc(x.full_name)}</option>`).join('');
    return `<div class="grid-2 sc-live" style="grid-template-columns:1.15fr 0.85fr;gap:16px">
      <div class="panel"><div class="panel-body">
        ${diamondHtml()}
        <div class="sc-battery">
          <label>Pitcher <select id="sc-pit">${battOpts(S.pitcher)}</select></label>
          <label>Catcher <select id="sc-cat">${battOpts(S.catcher)}</select></label>
        </div>
        <div class="sc-batter">
          <span class="muted">Now batting &middot; ${UI.esc(battName)}</span>
          <div class="sc-batter-name">${b?`#${b.batting_order} ${UI.esc(b.full_name)}`:'\u2014'}</div>
          ${done?'':`<label class="sc-bat-override muted" style="display:block;margin-top:6px;font-size:12px">Batting out of order? <select id="sc-batover" style="margin-left:4px">${batOpts}</select>${S.batOverride?' <button type="button" class="btn ghost sm" id="sc-batover-clr">reset</button>':''}</label>`}
        </div>
        ${(S.pitchTracking && !done) ? pitchPanelHtml() : ''}
        ${done?'<p class="muted">Game is final. Use Undo to correct the last plays if needed.</p>':resultButtonsHtml()}
      </div></div>
      <div class="panel"><div class="panel-head"><h2>Play-by-play</h2>
        <button class="btn ghost sm" id="sc-undo" ${S.events.length?'':'disabled'}>\u21b6 Undo</button></div>
        <div class="panel-body">
          ${done?'':baserunHtml()}
          <div class="sc-log">${playLogHtml()}</div>
        </div></div>
    </div>`;
  }

  function diamondHtml() {
    const bs = S.ls.state.bases;
    const base = (n, cls) => `<div class="base ${cls} ${bs[n]?'occ':''}" title="${UI.esc(nameOf(bs[n]))}"><span>${bs[n]?UI.esc(shortName(nameOf(bs[n]))):''}</span></div>`;
    return `<div class="diamond">${base('2','b2')}${base('3','b3')}${base('1','b1')}
      <div class="base home"><span>H</span></div></div>`;
  }

  function resultButtonsHtml() {
    const cat = S.cat.batting;
    const grp = (title, codes) => `<div class="sc-bgroup"><div class="sc-blabel">${title}</div>
      <div class="sc-btns">${codes.map((c)=>`<button class="btn res" data-res="${c}" title="${UI.esc(cat[c]?cat[c].label:c)}">${c}</button>`).join('')}</div></div>`;
    return `<div class="sc-results">${Object.entries(BATT_GROUPS).map(([t,c])=>grp(t,c)).join('')}</div>`;
  }

  // ------------------------------------------------------- pitch-by-pitch
  function pitchCount() {
    let balls = 0, strikes = 0;
    S.pitches.forEach((p) => {
      if (p.result === 'B') balls++;
      else if (p.result === 'CS' || p.result === 'SS') strikes = Math.min(strikes + 1, 3);
      else if (p.result === 'F') strikes = strikes < 2 ? strikes + 1 : strikes;
    });
    return { balls, strikes };
  }

  function pitchPanelHtml() {
    const c = pitchCount();
    const pr = S.cat.pitch_results;
    const seq = S.pitches.map((p, i) => {
      const lab = (pr[p.result] || {}).label || p.result;
      const bits = [p.pitch_type, p.velocity ? `${p.velocity}` : '', `z${p.zone||'-'}`].filter(Boolean).join(' ');
      return `<span class="pz-chip pz-r-${p.result}" title="${UI.esc(lab + (bits?' \u00b7 '+bits:''))}">${i+1}. ${UI.esc(p.result)}</span>`;
    }).join('');
    return `<div class="sc-pitch">
      <div class="sc-pitch-head">
        <span class="sc-blabel">Pitch sequence</span>
        <span class="pz-count">${c.balls}\u2013${c.strikes}</span>
        <span class="pz-n muted">${S.pitches.length} pitch${S.pitches.length===1?'':'es'}</span>
        <span class="sc-pitch-btns">
          <button class="btn primary sm" id="pz-add">+ Pitch</button>
          <button class="btn ghost sm" id="pz-undo" ${S.pitches.length?'':'disabled'}>\u21b6</button>
          <button class="btn ghost sm" id="pz-clear" ${S.pitches.length?'':'disabled'}>Clear</button>
        </span>
      </div>
      <div class="pz-seq">${seq || '<span class="muted">No pitches logged for this at-bat yet.</span>'}</div>
    </div>`;
  }

  function addPitch() {
    if (!S.pitchTracking) return;
    const pt = S.cat.pitch_types, pr = S.cat.pitch_results;
    const zoneBtn = (z) => `<button type="button" class="pz-z" data-zone="${z}">${z}</button>`;
    const core = [1,2,3,4,5,6,7,8,9].map(zoneBtn).join('');
    const typeOpts = Object.entries(pt).map(([k,v]) => `<option value="${k}">${UI.esc(v.label)}</option>`).join('');
    const outcomes = Object.entries(pr).map(([k,v]) => `<button type="button" class="btn res pz-out" data-out="${k}" title="${UI.esc(v.label)}">${k}</button>`).join('');
    UI.openModal(`
      <div class="modal-head"><h2>Add pitch</h2><button class="icon-btn" data-x>&times;</button></div>
      <div class="modal-body">
        <div class="field"><label>Location (click the zone)</label>
          <div class="pz-grid">
            <div class="pz-chase">${zoneBtn(11)}${zoneBtn(12)}</div>
            <div class="pz-core">${core}</div>
            <div class="pz-chase">${zoneBtn(13)}${zoneBtn(14)}</div>
          </div>
        </div>
        <div class="grid-2" style="grid-template-columns:1fr 1fr;gap:10px">
          <div class="field"><label>Pitch type</label><select id="pz-type"><option value=""></option>${typeOpts}</select></div>
          <div class="field"><label>Velocity (mph)</label><input id="pz-velo" type="number" min="0" step="0.1" placeholder="e.g. 92"></div>
        </div>
        <div class="field"><label>Outcome (click to log the pitch)</label><div class="sc-btns">${outcomes}</div></div>
        <p class="muted" id="pz-hint">Pick a zone and (optionally) type/velocity, then tap an outcome.</p>
      </div>`);
    const m = document.getElementById('modal');
    let zone = null;
    m.querySelectorAll('.pz-z').forEach((b) => b.onclick = () => {
      zone = Number(b.dataset.zone);
      m.querySelectorAll('.pz-z').forEach((x) => x.classList.remove('sel'));
      b.classList.add('sel');
    });
    const close = () => UI.closeModal();
    m.querySelector('[data-x]').onclick = close;
    m.querySelectorAll('.pz-out').forEach((b) => b.onclick = () => {
      const veloRaw = m.querySelector('#pz-velo').value;
      S.pitches.push({
        pitch_num: S.pitches.length + 1,
        zone: zone,
        velocity: veloRaw === '' ? null : Number(veloRaw),
        pitch_type: m.querySelector('#pz-type').value || null,
        result: b.dataset.out,
      });
      close();
      render();
    });
  }

  function baserunHtml() {
    const codes = ['SB','CS','PO','POCS','WP','PB','BK','ADV','OUT'];
    const cat = S.cat.baserunning;
    return `<div class="sc-baserun"><div class="sc-blabel">Baserunning / battery</div>
      <div class="sc-btns">${codes.map((c)=>`<button class="btn ghost sm br" data-br="${c}" title="${UI.esc(cat[c]?cat[c].label:c)}">${c}</button>`).join('')}</div></div>`;
  }

  function playLogHtml() {
    if (!S.events.length) return UI.empty('\u26be', 'No plays yet. Record the first batter\u2019s result.');
    return S.events.slice().reverse().map((e) => {
      const tag = e.half==='T'?'\u25b2':'\u25bc';
      return `<div class="logrow"><span class="logi">${tag}${e.inning}</span>
        <span class="logd">${UI.esc(e.description||describe(e))}</span></div>`;
    }).join('');
  }

  function describe(e) {
    if (e.kind === 'BR') {
      const lab = (S.cat.baserunning[e.result]||{}).label || e.result;
      return `${e.runner_name||''} ${lab}`.trim();
    }
    const lab = (S.cat.batting[e.result]||{}).label || e.result;
    return `${e.batter_name||''} \u2014 ${lab}`.trim();
  }

  function bindLive() {
    const $ = (id) => document.getElementById(id);
    if (S.forceLineup) renderLineupEditor();
    const pit = $('sc-pit'), cat = $('sc-cat');
    if (pit) pit.onchange = () => { S.pitcher = Number(pit.value); };
    if (cat) cat.onchange = () => { S.catcher = Number(cat.value); };
    const bov = $('sc-batover');
    if (bov) bov.onchange = () => { S.batOverride = Number(bov.value); render(); };
    if ($('sc-batover-clr')) $('sc-batover-clr').onclick = () => { S.batOverride = null; render(); };
    if ($('sc-undo')) $('sc-undo').onclick = undo;
    if ($('pz-add')) $('pz-add').onclick = addPitch;
    if ($('pz-undo')) $('pz-undo').onclick = () => { S.pitches.pop(); render(); };
    if ($('pz-clear')) $('pz-clear').onclick = () => { S.pitches = []; render(); };
    document.querySelectorAll('[data-res]').forEach((bx) => bx.onclick = () => recordPA(bx.dataset.res));
    document.querySelectorAll('[data-br]').forEach((bx) => bx.onclick = () => recordBR(bx.dataset.br));
  }

  async function undo() {
    if (!(await UI.confirm('Undo last play', 'Remove the most recent play from the log?'))) return;
    await API.post(`/games/${S.gameId}/undo`);
    await reload(); render(); UI.toast('Play undone');
  }

  // A clickable half-field diagram. Returns SVG markup; the caller wires up
  // click handling to capture a normalised (x,y) drop location.
  function fieldPickerSvg() {
    const S0 = 320, H = 300;
    const hx = 0.5 * S0, hy = 0.93 * H;
    const pt = (ang, rad) => {
      const r = ang * Math.PI / 180;
      return [hx + rad * 0.5 * S0 * Math.sin(r), hy - rad * 0.86 * H * Math.cos(r)];
    };
    const lf = pt(-45, 1.02), cf = pt(0, 1.06), rf = pt(45, 1.02);
    const b1 = pt(45, .42), b2 = pt(0, .52), b3 = pt(-45, .42);
    const mound = pt(0, .30);
    const P = (a) => a.map((n)=>n.toFixed(1)).join(',');
    let s = `<svg id="fp-svg" viewBox="0 0 ${S0} ${H}" class="fieldpick-svg" preserveAspectRatio="xMidYMid meet">`;
    // grass fan
    s += `<defs><radialGradient id="fpg" cx="50%" cy="90%" r="95%">`
      + `<stop offset="0%" stop-color="#1c5b34"/><stop offset="100%" stop-color="#0f3d22"/></radialGradient></defs>`;
    s += `<rect x="0" y="0" width="${S0}" height="${H}" rx="12" fill="#08131f"/>`;
    s += `<path d="M${hx},${hy} L${P(lf)} Q${cf[0].toFixed(1)},${(cf[1]-24).toFixed(1)} ${P(rf)} Z" fill="url(#fpg)" stroke="#1e3050"/>`;
    // outfield arc
    s += `<path d="M${P(lf)} Q${cf[0].toFixed(1)},${(cf[1]-24).toFixed(1)} ${P(rf)}" fill="none" stroke="#2f7d4c" stroke-width="2"/>`;
    // infield dirt
    s += `<polygon points="${hx},${hy} ${P(b1)} ${P(b2)} ${P(b3)}" fill="#7a5230" stroke="#93673d" stroke-width="1.5"/>`;
    // infield grass (smaller diamond)
    const g1=pt(45,.30),g2=pt(0,.40),g3=pt(-45,.30);
    s += `<polygon points="${hx},${(hy-6).toFixed(1)} ${P(g1)} ${P(g2)} ${P(g3)}" fill="#1c5b34"/>`;
    // foul lines
    s += `<line x1="${hx}" y1="${hy}" x2="${lf[0].toFixed(1)}" y2="${lf[1].toFixed(1)}" stroke="#dfe8f5" stroke-width="1.5" stroke-dasharray="5 4"/>`;
    s += `<line x1="${hx}" y1="${hy}" x2="${rf[0].toFixed(1)}" y2="${rf[1].toFixed(1)}" stroke="#dfe8f5" stroke-width="1.5" stroke-dasharray="5 4"/>`;
    // bases + mound + plate
    const sq = (p,c)=>`<rect x="${(p[0]-4).toFixed(1)}" y="${(p[1]-4).toFixed(1)}" width="8" height="8" transform="rotate(45 ${p[0].toFixed(1)} ${p[1].toFixed(1)})" fill="${c}" stroke="#20303f"/>`;
    s += sq(b1,'#f4f7fb')+sq(b2,'#f4f7fb')+sq(b3,'#f4f7fb');
    s += `<circle cx="${mound[0].toFixed(1)}" cy="${mound[1].toFixed(1)}" r="7" fill="#93673d" stroke="#b07f4c"/>`;
    s += `<polygon points="${(hx-5).toFixed(1)},${(hy-3).toFixed(1)} ${(hx+5).toFixed(1)},${(hy-3).toFixed(1)} ${(hx+5).toFixed(1)},${(hy+2).toFixed(1)} ${hx},${(hy+7).toFixed(1)} ${(hx-5).toFixed(1)},${(hy+2).toFixed(1)}" fill="#f4f7fb" stroke="#20303f"/>`;
    // position labels (help the scorer aim the drop)
    const labels = {LF:pt(-30,.80),CF:pt(0,.88),RF:pt(30,.80),SS:pt(-18,.46),'2B':pt(18,.46),'3B':pt(-34,.34),'1B':pt(34,.34)};
    Object.entries(labels).forEach(([k,p])=>{ s += `<text x="${p[0].toFixed(1)}" y="${p[1].toFixed(1)}" fill="rgba(220,232,245,.45)" font-size="9" text-anchor="middle">${k}</text>`; });
    s += `<circle id="fp-marker" cx="0" cy="0" r="6" fill="#ffd34d" stroke="#111c30" stroke-width="1.5" style="display:none"/>`;
    s += '</svg>';
    return s;
  }

  // ------------------------------------------------------------ record a PA
  const BB_TYPES = [['GB','Ground ball'],['LD','Line drive'],['FB','Fly ball'],['PU','Pop up']];
  const CONTACT = [['soft','Soft'],['avg','Average'],['hard','Hard']];

  // Render either a button "picker" (default) or a classic dropdown for a
  // single-choice field, honouring the user's Preferences setting. In both
  // cases a real (possibly hidden) <select id> is emitted so downstream code
  // can keep reading `.value`.
  function pickerField(id, options, sel) {
    const opts = `<option value=""></option>` + options.map(([v,l]) =>
      `<option value="${v}" ${String(v)===String(sel)?'selected':''}>${UI.esc(l)}</option>`).join('');
    const usePickers = (typeof Prefs !== 'undefined') && Prefs.usePickers();
    if (!usePickers) {
      return `<select id="${id}">${opts}</select>`;
    }
    const btns = options.map(([v,l]) =>
      `<button type="button" class="btn sm pk-btn ${String(v)===String(sel)?'primary':'ghost'}" data-for="${id}" data-val="${v}">${UI.esc(l)}</button>`).join('');
    return `<div class="pk-group" style="display:flex;flex-wrap:wrap;gap:6px">${btns}
      <select id="${id}" class="pk-hidden" style="display:none">${opts}</select></div>`;
  }

  function bindPickers(m) {    m.querySelectorAll('.pk-btn').forEach((b) => b.onclick = () => {
      const sel = m.querySelector('#' + b.dataset.for);
      if (!sel) return;
      const val = b.dataset.val;
      sel.value = (sel.value === val) ? '' : val;   // click again to clear
      m.querySelectorAll(`.pk-btn[data-for="${b.dataset.for}"]`).forEach((x) => {
        const on = x.dataset.val === sel.value && sel.value !== '';
        x.classList.toggle('primary', on);
        x.classList.toggle('ghost', !on);
      });
      sel.dispatchEvent(new Event('change'));
    });
  }

  // Multi-select fielder-notation picker: a row of 1-9 buttons (number + pos
  // code) synced with a free-text input. Clicking a button appends '-N' to the
  // raw text; typing digits highlights the matching buttons in the order they
  // appear. A Clear button empties the field.
  function fielderPicker(id, initial) {
    const usePickers = (typeof Prefs !== 'undefined') && Prefs.usePickers();
    const val = initial || '';
    if (!usePickers) {
      return `<input id="${id}" value="${UI.esc(val)}" placeholder="e.g. 6-4-3, F8, 5-3">`;
    }
    const btns = [1,2,3,4,5,6,7,8,9].map((n) =>
      `<button type="button" class="btn sm ghost fp-btn" data-fp="${id}" data-num="${n}">`
      + `${n}<span style="opacity:.6;font-size:.8em">&nbsp;${POS_NUM[n]}</span></button>`).join('');
    return `<div class="fp-wrap" data-fpwrap="${id}">
      <div class="fp-btns" style="display:flex;flex-wrap:wrap;gap:6px;margin-bottom:6px">${btns}
        <button type="button" class="btn sm ghost fp-clear" data-fp="${id}">Clear</button></div>
      <input id="${id}" class="fp-input" value="${UI.esc(val)}" placeholder="e.g. 6-4-3, F8, 5-3"></div>`;
  }

  function bindFielderPicker(m, id) {
    const input = m.querySelector('#' + id);
    if (!input) return;
    const wrap = m.querySelector(`[data-fpwrap="${id}"]`);
    if (!wrap) return; // plain input mode (pickers disabled)
    const btns = wrap.querySelectorAll('.fp-btn');
    const refresh = () => {
      // Highlight buttons whose digit appears in the typed value, in order.
      const digits = (input.value.match(/[1-9]/g) || []);
      const present = new Set(digits);
      btns.forEach((b) => {
        const on = present.has(b.dataset.num);
        b.classList.toggle('primary', on);
        b.classList.toggle('ghost', !on);
      });
    };
    btns.forEach((b) => b.onclick = () => {
      const raw = input.value.trim();
      input.value = raw ? `${raw}-${b.dataset.num}` : b.dataset.num;
      input.dispatchEvent(new Event('input'));
      input.focus();
    });
    const clr = wrap.querySelector('.fp-clear');
    if (clr) clr.onclick = () => { input.value = ''; input.dispatchEvent(new Event('input')); input.focus(); };
    input.addEventListener('input', refresh);
    refresh();
  }

  function destSelect(cls, from, sel) {
    let opts;
    if (from === 0) opts = [['OUT','Out'],['1','1B'],['2','2B'],['3','3B'],['H','Home']];
    else if (from === 1) opts = [['1','Hold 1B'],['2','2B'],['3','3B'],['H','Home'],['OUT','Out']];
    else if (from === 2) opts = [['2','Hold 2B'],['3','3B'],['H','Home'],['OUT','Out']];
    else opts = [['3','Hold 3B'],['H','Home'],['OUT','Out']];
    const o = opts.map(([v,l]) => `<option value="${v}" ${v===String(sel)?'selected':''}>${l}</option>`).join('');
    return `<select class="${cls}" data-from="${from}">${o}</select>`;
  }

  async function recordPA(code) {
    const g = S.game;
    if (['final','forfeited'].includes(g.status)) return;
    const b = currentBatter();
    if (!b) { UI.toast('Set a batting lineup first', 'err'); return; }
    const info = S.cat.batting[code];
    const bs = S.ls.state.bases;
    const occupied = ['3','2','1'].filter((n) => bs[n]);
    const batterDest = code==='HR' ? 'H' : (info.bases>=1 && info.bases<=3 ? String(info.bases) : (info.bases===4?'H':'OUT'));
    const fielders = S.lineups[fieldingSide()] || [];
    const fldOpts = (sel) => fielders.map((x)=>`<option value="${x.player_id}" ${x.player_id==sel?'selected':''}>${UI.esc(x.full_name)}${x.position?` (${x.position})`:''}</option>`).join('');
    // Auto-fill batted-ball type from the out kind: GO->GB, FO->FB, LO->LD, POP->PU.
    const BB_AUTO = { GO:'GB', FO:'FB', LO:'LD', POP:'PU' };
    const defBB = BB_AUTO[code] || '';
    const bbSel = (v) => BB_TYPES.map(([val,l])=>`<option value="${val}" ${val===defBB?'selected':''}>${l}</option>`).join('');
    const battedFields = info.batted ? `
      <div class="field"><label>Where did the ball land? (click the field)</label>
        <div class="fieldpick">${fieldPickerSvg()}</div>
        <span class="muted" id="rz-loc" style="font-size:11px">Click the field to mark the drop location (optional but recommended for the spray chart).</span>
      </div>
      <div class="grid-2" style="grid-template-columns:1fr 1fr;gap:10px">
        <div class="field"><label>Batted-ball type</label>${pickerField('rz-bb', BB_TYPES, defBB)}</div>
        <div class="field"><label>Contact quality</label>${pickerField('rz-ct', CONTACT, '')}</div>
      </div>
      <div class="field"><label>Fielder(s) / notation</label>${fielderPicker('rz-fld','')}</div>` : '';
    const runnerRows = occupied.map((n)=>`<div class="field"><label>Runner on ${n} &middot; ${UI.esc(nameOf(bs[n]))}</label>${destSelect('rz-run', Number(n), n)}</div>`).join('');
    UI.openModal(`
      <div class="modal-head"><h2>${UI.esc(info.label)} &middot; ${UI.esc(b.full_name)}</h2>
        <button class="icon-btn" data-x>&times;</button></div>
      <div class="modal-body">
        ${battedFields}
        <div class="field"><label>Batter advances to</label>${destSelect('rz-bat', 0, batterDest)}</div>
        ${runnerRows}
        <label class="chk" style="display:flex;gap:8px;align-items:center;margin:6px 0"><input type="checkbox" id="rz-err" ${(info.cat==='roe'||code==='CI')?'checked':''}> Error(s) charged on the play</label>
        <div class="field" id="rz-err-wrap" style="display:none"><label>Error(s) charged to fielder(s) &middot; select one or more</label>
          <select id="rz-err-on" multiple size="4" style="min-height:96px">${fldOpts('')}</select>
          <span class="muted" style="font-size:11px">Ctrl/Cmd-click to charge multiple fielders on the same play. Runners' extra bases from the error are set above in "advances to".</span></div>
        <div class="field"><label>RBI</label><input type="number" id="rz-rbi" min="0" value="0"></div>
        <div class="rz-preview" id="rz-prev"></div>
      </div>
      <div class="modal-foot"><button class="btn ghost" data-cancel>Cancel</button>
        <button class="btn primary" data-ok>Record Play</button></div>`);
    const m = document.getElementById('modal');
    bindPickers(m);
    bindFielderPicker(m, 'rz-fld');
    const rbiInput = m.querySelector('#rz-rbi');
    rbiInput.oninput = () => { rbiInput.dataset.touched = '1'; };

    // --- clickable field drop location ---
    let hit = { x: null, y: null };
    const svg = m.querySelector('#fp-svg');
    if (svg) {
      const marker = m.querySelector('#fp-marker');
      svg.addEventListener('click', (ev) => {
        const r = svg.getBoundingClientRect();
        const vx = (ev.clientX - r.left) / r.width;
        const vy = (ev.clientY - r.top) / r.height;
        hit = { x: Math.max(0, Math.min(1, vx)), y: Math.max(0, Math.min(1, vy)) };
        marker.setAttribute('cx', (hit.x * 320).toFixed(1));
        marker.setAttribute('cy', (hit.y * 300).toFixed(1));
        marker.style.display = '';
        const loc = m.querySelector('#rz-loc');
        if (loc) loc.textContent = `Drop location set (${(hit.x*100).toFixed(0)}%, ${(hit.y*100).toFixed(0)}%). Click again to move it.`;
      });
    }

    // --- error fielder picker (default from notation position) ---
    const errChk = m.querySelector('#rz-err');
    const errWrap = m.querySelector('#rz-err-wrap');
    const errSel = m.querySelector('#rz-err-on');
    function defaultErrFielder() {
      const fld = (m.querySelector('#rz-fld')||{}).value || '';
      const d = String(fld).replace(/[^1-9]/g, '')[0];
      if (d) {
        const posCode = POS_NUM[Number(d)];
        const match = fielders.find((x)=>x.position===posCode);
        if (match) return match.player_id;
      }
      return '';
    }
    function syncErr() {
      if (!errWrap) return;
      errWrap.style.display = errChk.checked ? '' : 'none';
      if (errChk.checked && errSel && !errSel.selectedOptions.length) {
        const def = defaultErrFielder();
        if (def) { const o = errSel.querySelector(`option[value="${def}"]`); if (o) o.selected = true; }
      }
    }
    if (errChk) errChk.onchange = () => { syncErr(); compute(); };
    // Catcher's interference is, by rule, an error on the defending catcher.
    if (code === 'CI' && errSel && S.catcher) {
      const o = errSel.querySelector(`option[value="${S.catcher}"]`);
      if (o) o.selected = true;
    }
    const fldInput = m.querySelector('#rz-fld');
    if (fldInput) fldInput.oninput = () => { if (errChk.checked && errSel && !errSel.selectedOptions.length) { const d=defaultErrFielder(); if (d){ const o=errSel.querySelector(`option[value="${d}"]`); if(o) o.selected=true; } } };

    function compute() {
      const newBases = { '1':null, '2':null, '3':null };
      let runs = 0, outsAdded = 0;
      const batDest = m.querySelector('.rz-bat').value;
      if (batDest === 'H') runs++; else if (batDest !== 'OUT') newBases[batDest] = b.player_id;
      m.querySelectorAll('.rz-run').forEach((sel) => {
        const from = sel.dataset.from; const pid = bs[from];
        const d = sel.value;
        if (d === 'H') runs++;
        else if (d === 'OUT') outsAdded++;
        else newBases[d] = pid;
      });
      const inherent = INHERENT_OUTS[code] || 0;
      const outs = inherent + outsAdded;
      const err = m.querySelector('#rz-err').checked;
      if (!rbiInput.dataset.touched) rbiInput.value = err ? 0 : runs;
      const baseTxt = ['1','2','3'].map((n)=> newBases[n] ? `${n}B:${shortName(nameOf(newBases[n]))}` : '').filter(Boolean).join('  ') || 'bases empty';
      m.querySelector('#rz-prev').innerHTML = `<b>Runs</b> +${runs} &nbsp; <b>Outs</b> +${outs} &nbsp; <b>After</b> ${UI.esc(baseTxt)}`;
      return { newBases, runs, outs, err };
    }
    m.querySelectorAll('.rz-bat,.rz-run').forEach((el)=> el.onchange = compute);
    syncErr(); compute();

    const close = () => UI.closeModal();
    m.querySelector('[data-x]').onclick = close;
    m.querySelector('[data-cancel]').onclick = close;
    m.querySelector('[data-ok]').onclick = async () => {
      const r = compute();
      let errorOn = null;
      let errorsJson = null;
      if (r.err && errSel && errSel.selectedOptions.length) {
        errorsJson = Array.from(errSel.selectedOptions).map((o)=>Number(o.value)).filter(Boolean);
        errorOn = errorsJson[0] || null;
      }
      const pitchBuf = (S.pitchTracking && S.pitches.length) ? S.pitches.slice() : null;
      const pitchNote = pitchBuf ? ` (${pitchBuf.length} pitch${pitchBuf.length>1?'es':''})` : '';
      const payload = {
        inning: S.ls.state.inning, half: S.ls.state.half, kind: 'PA',
        batter_id: b.player_id, pitcher_id: S.pitcher, catcher_id: S.catcher,
        result: code,
        bb_type: info.batted ? (m.querySelector('#rz-bb')||{}).value || null : null,
        contact: info.batted ? (m.querySelector('#rz-ct')||{}).value || null : null,
        detail: info.batted ? (m.querySelector('#rz-fld')||{}).value || null : null,
        is_error: r.err ? 1 : 0,
        error_on: errorOn,
        errors_json: errorsJson,
        hit_x: (info.batted && hit.x !== null) ? Number(hit.x.toFixed(4)) : null,
        hit_y: (info.batted && hit.y !== null) ? Number(hit.y.toFixed(4)) : null,
        rbi: Number(rbiInput.value)||0,
        outs_recorded: r.outs, runs_scored: r.runs,
        advances: r.newBases,
        pitches: pitchBuf,
        description: `${b.full_name} \u2014 ${info.label}` + (r.runs?`, ${r.runs} run${r.runs>1?'s':''}`:'') + (r.err?', E':'') + pitchNote,
      };
      close();
      S.pitches = [];
      S.batOverride = null;
      await API.post(`/games/${S.gameId}/events`, payload);
      await reload(); render();
    };
  }

  // ------------------------------------------------- substitutions / position
  async function manageSubs() {
    const [awayR, homeR] = await Promise.all([
      API.roster(S.game.season_id, S.game.away_team_id).catch(()=>[]),
      API.roster(S.game.season_id, S.game.home_team_id).catch(()=>[]),
    ]);
    const rosters = { away: awayR, home: homeR };
    const activeIds = (side) => new Set((S.lineups[side]||[]).map((x)=>x.player_id));
    const slotOpts = ['away','home'].map((side) => {
      const label = side==='away' ? (S.game.away_name) : (S.game.home_name);
      const rows = (S.lineups[side]||[]).slice().sort((a,b)=>a.batting_order-b.batting_order)
        .map((x)=>`<option value="${x.id}" data-side="${side}" data-pos="${x.position||''}" data-pid="${x.player_id}">`
          + `#${x.batting_order} ${UI.esc(x.full_name)}${x.position?` (${x.position})`:''}</option>`).join('');
      return `<optgroup label="${UI.esc(label)}">${rows}</optgroup>`;
    }).join('');
    const posOpts = (sel) => POS.map((p)=>`<option ${p===sel?'selected':''}>${p}</option>`).join('');
    UI.openModal(`
      <div class="modal-head"><h2>Substitutions &amp; position changes</h2><button class="icon-btn" data-x>&times;</button></div>
      <div class="modal-body">
        <div class="field"><label>Lineup slot to change</label><select id="sub-slot">${slotOpts}</select></div>
        <div class="field"><label>Player in this slot</label><select id="sub-player"></select>
          <span class="muted" style="font-size:11px">Keep the same player to make a defensive position change, or pick a bench player to substitute.</span></div>
        <div class="field"><label>Position</label><select id="sub-pos">${posOpts('')}</select></div>
      </div>
      <div class="modal-foot"><button class="btn ghost" data-cancel>Cancel</button>
        <button class="btn primary" data-ok>Apply change</button></div>`);
    const m = document.getElementById('modal');
    const slotSel = m.querySelector('#sub-slot');
    const playerSel = m.querySelector('#sub-player');
    const posSel = m.querySelector('#sub-pos');
    function refresh() {
      const opt = slotSel.selectedOptions[0];
      if (!opt) return;
      const side = opt.dataset.side;
      const curPid = Number(opt.dataset.pid);
      const curName = opt.textContent.replace(/^#\d+\s*/, '').replace(/\s*\(.*\)$/, '');
      const active = activeIds(side);
      const bench = (rosters[side]||[]).filter((r)=>!active.has(r.id))
        .sort((a,b)=>a.full_name.localeCompare(b.full_name));
      let html = `<option value="${curPid}">Keep ${UI.esc(curName)} (position change)</option>`;
      html += bench.map((r)=>`<option value="${r.id}">${UI.esc(r.full_name)} \u2014 sub in</option>`).join('');
      playerSel.innerHTML = html;
      // default position to the slot's current position
      const pos = opt.dataset.pos || '';
      Array.from(posSel.options).forEach((o)=>{ o.selected = o.value===pos; });
    }
    slotSel.onchange = refresh; refresh();
    const close = () => UI.closeModal();
    m.querySelector('[data-x]').onclick = close;
    m.querySelector('[data-cancel]').onclick = close;
    m.querySelector('[data-ok]').onclick = async () => {
      const lineup_id = Number(slotSel.value);
      const player_id = Number(playerSel.value);
      const position = posSel.value || null;
      try {
        await API.post(`/games/${S.gameId}/sub`, { lineup_id, player_id, position });
      } catch (e) { UI.toast('Substitution failed: ' + e.message, 'err'); return; }
      close();
      // Keep the current battery selection valid after a pitcher/catcher change.
      S.pitcher = null; S.catcher = null;
      await reload(); render(); UI.toast('Lineup change applied');
    };
  }

  // --------------------------------------- batch substitutions / positions
  async function manageMultiSubs() {
    const [awayR, homeR] = await Promise.all([
      API.roster(S.game.season_id, S.game.away_team_id).catch(()=>[]),
      API.roster(S.game.season_id, S.game.home_team_id).catch(()=>[]),
    ]);
    const rosters = { away: awayR, home: homeR };
    const activeIds = (side) => new Set((S.lineups[side]||[]).map((x)=>x.player_id));
    let side = (S.lineups.home && S.lineups.home.length) ? fieldingSide() : 'away';
    const posOpts = (sel) => POS.map((p)=>`<option ${p===sel?'selected':''}>${p}</option>`).join('');
    function sideTable() {
      const lu = (S.lineups[side]||[]).slice().sort((a,b)=>a.batting_order-b.batting_order);
      const active = activeIds(side);
      const bench = (rosters[side]||[]).filter((r)=>!active.has(r.id))
        .sort((a,b)=>a.full_name.localeCompare(b.full_name));
      const benchOpts = bench.map((r)=>`<option value="${r.id}">${UI.esc(r.full_name)} \u2014 sub in</option>`).join('');
      const rows = lu.map((x)=>`<tr>
        <td>${x.batting_order}</td>
        <td><select class="ms-player" data-lineup="${x.id}" data-cur="${x.player_id}">
          <option value="${x.player_id}">${UI.esc(x.full_name)} (keep)</option>${benchOpts}</select></td>
        <td><select class="ms-pos" data-cur="${x.position||''}">${posOpts(x.position||'')}</select></td>
      </tr>`).join('');
      return `<table class="tbl" style="width:100%"><thead><tr><th>#</th><th>Player</th><th>Pos</th></tr></thead><tbody>${rows}</tbody></table>`;
    }
    const sideBtns = ['away','home'].map((sd)=>{
      const label = sd==='away'?(S.game.away_abbrev||S.game.away_name):(S.game.home_abbrev||S.game.home_name);
      return `<button type="button" class="btn sm ms-side ${sd===side?'primary':'ghost'}" data-side="${sd}">${UI.esc(label)}</button>`;
    }).join(' ');
    UI.openModal(`
      <div class="modal-head"><h2>Multiple substitutions &amp; position changes</h2><button class="icon-btn" data-x>&times;</button></div>
      <div class="modal-body">
        <div class="field"><label>Team</label><div id="ms-sides">${sideBtns}</div></div>
        <div id="ms-body">${sideTable()}</div>
        <span class="muted" style="font-size:11px">Change any number of slots at once. Bench players are restricted to the same team's roster. Keeping a player only changes their position.</span>
      </div>
      <div class="modal-foot"><button class="btn ghost" data-cancel>Cancel</button>
        <button class="btn primary" data-ok>Apply all changes</button></div>`);
    const m = document.getElementById('modal');
    function rebind() {
      m.querySelectorAll('.ms-side').forEach((b)=> b.onclick = () => {
        side = b.dataset.side;
        m.querySelector('#ms-body').innerHTML = sideTable();
        m.querySelectorAll('.ms-side').forEach((x)=>{ x.classList.toggle('primary', x.dataset.side===side); x.classList.toggle('ghost', x.dataset.side!==side); });
      });
    }
    rebind();
    const close = () => UI.closeModal();
    m.querySelector('[data-x]').onclick = close;
    m.querySelector('[data-cancel]').onclick = close;
    m.querySelector('[data-ok]').onclick = async () => {
      const changes = [];
      m.querySelectorAll('#ms-body tr').forEach((tr)=>{
        const ps = tr.querySelector('.ms-player'); const pos = tr.querySelector('.ms-pos');
        if (!ps) return;
        const lineup_id = Number(ps.dataset.lineup);
        const player_id = Number(ps.value);
        const position = pos.value || null;
        const changed = player_id !== Number(ps.dataset.cur) || position !== (pos.dataset.cur||null);
        if (changed) changes.push({ lineup_id, player_id, position });
      });
      if (!changes.length) { UI.toast('No changes to apply'); close(); return; }
      let n = 0;
      for (const ch of changes) {
        try { await API.post(`/games/${S.gameId}/sub`, ch); n++; }
        catch (e) { UI.toast('A change failed: ' + e.message, 'err'); }
      }
      close();
      S.pitcher = null; S.catcher = null;
      await reload(); render();
      UI.toast(`${n} lineup change${n===1?'':'s'} applied`);
    };
  }

  // ------------------------------------------------- baserunning / battery
  async function recordBR(code) {
    const g = S.game;
    if (['final','forfeited'].includes(g.status)) return;
    const bs = S.ls.state.bases;
    const occupied = ['3','2','1'].filter((n) => bs[n]);
    if (!occupied.length && code !== 'BK') { UI.toast('No runners on base', 'err'); return; }
    const info = S.cat.baserunning[code];
    const upMap = { '1':'2', '2':'3', '3':'H' };
    const defKind = { SB:'up', CS:'OUT', PO:'OUT', POCS:'OUT', WP:'up', PB:'up', ADV:'up', OUT:'OUT', BK:'up' }[code];
    const rows = occupied.map((n) => {
      const def = defKind==='OUT' ? 'OUT' : (defKind==='up' ? upMap[n] : n);
      return `<div class="field"><label>Runner on ${n} &middot; ${UI.esc(nameOf(bs[n]))}</label>${destSelect('rz-run', Number(n), def)}</div>`;
    }).join('');
    const fielders = S.lineups[fieldingSide()] || [];
    const fldOpts = fielders.map((x)=>`<option value="${x.player_id}">${UI.esc(x.full_name)}${x.position?` (${x.position})`:''}</option>`).join('');
    // Position-play notation applies to caught-stealing / pickoff plays.
    const showNotation = ['CS','POCS','PO'].includes(code);
    const notationField = showNotation ? `
      <div class="field"><label>Fielding notation (optional)</label>
        ${fielderPicker('rz-note','')}
        <span class="muted" style="font-size:11px">Credits assists to the throwers and the putout to the tagger.</span></div>` : '';
    const errField = `
      <label class="chk" style="display:flex;gap:8px;align-items:center;margin:6px 0"><input type="checkbox" id="rz-err"> Error(s) on the play (e.g. errant pickoff throw)</label>
      <div class="field" id="rz-err-wrap" style="display:none"><label>Error(s) charged to fielder(s) &middot; select one or more</label>
        <select id="rz-err-on" multiple size="4" style="min-height:96px">${fldOpts}</select>
        <span class="muted" style="font-size:11px">Ctrl/Cmd-click to charge multiple fielders. Set runners' extra bases above.</span></div>`;
    UI.openModal(`
      <div class="modal-head"><h2>${UI.esc(info.label)}</h2><button class="icon-btn" data-x>&times;</button></div>
      <div class="modal-body">${rows || '<p class="muted">Balk with no runners on base \u2014 will be logged with no base change.</p>'}
        ${notationField}
        ${errField}
        <div class="rz-preview" id="rz-prev"></div></div>
      <div class="modal-foot"><button class="btn ghost" data-cancel>Cancel</button>
        <button class="btn primary" data-ok>Record</button></div>`);
    const m = document.getElementById('modal');
    bindFielderPicker(m, 'rz-note');
    function compute() {
      const newBases = { '1':null, '2':null, '3':null };
      let runs = 0, outsAdded = 0, runnerId = null, outRunner = null, advRunner = null;
      m.querySelectorAll('.rz-run').forEach((sel) => {
        const from = sel.dataset.from; const pid = bs[from]; const d = sel.value;
        if (d === 'H') { runs++; advRunner = pid; }
        else if (d === 'OUT') { outsAdded++; outRunner = pid; }
        else { newBases[d] = pid; if (d !== from) advRunner = pid; }
      });
      runnerId = outRunner || advRunner || (occupied.length ? bs[occupied[0]] : null);
      m.querySelector('#rz-prev').innerHTML = `<b>Runs</b> +${runs} &nbsp; <b>Outs</b> +${outsAdded}`;
      return { newBases, runs, outsAdded, runnerId };
    }
    m.querySelectorAll('.rz-run').forEach((el)=> el.onchange = compute);
    compute();
    const errChk = m.querySelector('#rz-err');
    const errWrap = m.querySelector('#rz-err-wrap');
    const errSel = m.querySelector('#rz-err-on');
    if (errChk) errChk.onchange = () => { errWrap.style.display = errChk.checked ? '' : 'none'; };
    const close = () => UI.closeModal();
    m.querySelector('[data-x]').onclick = close;
    m.querySelector('[data-cancel]').onclick = close;
    m.querySelector('[data-ok]').onclick = async () => {
      const r = compute();
      let credited = null, charged = null;
      if (['CS','POCS'].includes(code)) credited = S.catcher;
      else if (code === 'PO') credited = S.pitcher;
      else if (code === 'WP' || code === 'BK') charged = S.pitcher;
      else if (code === 'PB') charged = S.catcher;
      let errorsJson = null, errorOn = null, isErr = 0;
      if (errChk && errChk.checked && errSel && errSel.selectedOptions.length) {
        errorsJson = Array.from(errSel.selectedOptions).map((o)=>Number(o.value)).filter(Boolean);
        errorOn = errorsJson[0] || null;
        isErr = 1;
      }
      const noteEl = m.querySelector('#rz-note');
      const detail = noteEl && noteEl.value.trim() ? noteEl.value.trim() : null;
      const payload = {
        inning: S.ls.state.inning, half: S.ls.state.half, kind: 'BR',
        pitcher_id: S.pitcher, catcher_id: S.catcher, runner_id: r.runnerId,
        result: code, credited_to: credited, charged_to: charged,
        detail,
        is_error: isErr, error_on: errorOn, errors_json: errorsJson,
        outs_recorded: r.outsAdded, runs_scored: r.runs,
        advances: r.newBases,
        description: `${r.runnerId?shortName(nameOf(r.runnerId)):''} ${info.label}`.trim()
          + (detail?` ${detail}`:'') + (isErr?', E':''),
      };
      close();
      await API.post(`/games/${S.gameId}/events`, payload);
      await reload(); render();
    };
  }

  // --------------------------------------------------------------- game info
  async function editInfo() {
    const g = S.game;
    const fields = [
      { key:'game_date', label:'Date', type:'date', half:true },
      { key:'venue', label:'Venue', type:'text', half:true },
      { key:'scheduled_start', label:'Scheduled start', type:'time', half:true },
      { key:'actual_start', label:'Actual first pitch', type:'time', half:true },
      { key:'weather', label:'Weather', type:'text', half:true },
      { key:'temperature', label:'Temperature', type:'text', half:true },
      { key:'wind', label:'Wind', type:'text', half:true },
      { key:'attendance', label:'Attendance', type:'number', half:true },
      { key:'ump_home', label:'HP umpire', type:'text', half:true },
      { key:'ump_first', label:'1B umpire', type:'text', half:true },
      { key:'ump_second', label:'2B umpire', type:'text', half:true },
      { key:'ump_third', label:'3B umpire', type:'text', half:true },
      { key:'scorer', label:'Official scorer', type:'text', half:true },
      { key:'regulation_innings', label:'Regulation innings', type:'number', half:true },
      { key:'notes', label:'Notes', type:'textarea' },
    ];
    const vals = await UI.formModal('Game information', fields, g);
    if (!vals) return;
    const body = { season_id:g.season_id, away_team_id:g.away_team_id, home_team_id:g.home_team_id, ...vals };
    S.game = await API.put(`/games/${S.gameId}`, body);
    render(); UI.toast('Game info saved');
  }

  // --------------------------------------------------------- end game / wrap
  function pitcherOptions() {
    const list = [];
    ['away','home'].forEach((s)=> (S.lineups[s]||[]).forEach((x)=> list.push({ value:x.player_id, label:`${x.full_name} (${s==='away'?S.game.away_abbrev||'A':S.game.home_abbrev||'H'})` })));
    return list;
  }
  async function endGame() {
    const st = S.ls.state;
    const teams = [{ value:S.game.away_team_id, label:S.game.away_name }, { value:S.game.home_team_id, label:S.game.home_name }];
    const pitchers = pitcherOptions();
    const fields = [
      { key:'status', label:'Final status', type:'select', required:true, options:[{value:'final',label:'Final'},{value:'forfeited',label:'Forfeited'}], value:'final' },
      { key:'end_reason', label:'End reason', type:'select', options:['Regulation','Walk-off','Called (weather)','Called (darkness)','Mercy / knockout rule','Time limit','Forfeit'] },
      { key:'forfeit_team_id', label:'Forfeiting team (if forfeit)', type:'select', options:teams },
      { key:'win_pitcher_id', label:'Winning pitcher', type:'select', options:pitchers },
      { key:'loss_pitcher_id', label:'Losing pitcher', type:'select', options:pitchers },
      { key:'save_pitcher_id', label:'Save', type:'select', options:pitchers },
      { key:'duration', label:'Duration (HH:MM:SS)', type:'duration', half:true },
      { key:'delay', label:'Delay (HH:MM:SS)', type:'duration', half:true },
    ];
    const vals = await UI.formModal('Wrap up game', fields, { status:'final' });
    if (!vals) return;
    const body = {};
    Object.entries(vals).forEach(([k,v]) => {
      if (v === null || v === '') return;
      if (k === 'duration' || k === 'delay') {
        const sec = hmsToSeconds(v);
        if (sec === null) { UI.toast(`${k==='duration'?'Duration':'Delay'} must be HH:MM:SS`, 'err'); return; }
        body[`${k}_sec`] = sec;
        body[`${k}_min`] = Math.round(sec / 60);
        return;
      }
      body[k] = k.endsWith('_id') ? Number(v) : v;
    });
    S.game = await API.patch(`/games/${S.gameId}/state`, body);
    await reload(); render(); UI.toast('Game wrapped up');
  }

  return { open };
})();
