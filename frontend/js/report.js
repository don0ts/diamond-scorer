// Game report: box score + strike-zone heatmap. Report.open(gameId).
const Report = (() => {
  // Strike-zone layout. Core 1..9 is a 3x3 grid (catcher's view, left->right,
  // top->bottom); 11..14 are the four outside "chase" quadrants.
  const CORE = [[1, 2, 3], [4, 5, 6], [7, 8, 9]];

  function heatColor(intensity) {
    // Cool blue (low) -> hot red (high). Alpha scales with density.
    const hue = Math.round(220 - 210 * intensity);
    const a = (0.12 + 0.85 * intensity).toFixed(2);
    return `hsla(${hue}, 82%, 52%, ${a})`;
  }

  function cell(z, zones) {
    const d = zones[String(z)] || { pitches: 0, strike_pct: 0, intensity: 0 };
    const pct = d.pitches ? Math.round(d.strike_pct * 100) : 0;
    return `<div class="hz-cell" style="background:${heatColor(d.intensity)}" ` +
      `title="Zone ${z} \u00b7 ${d.pitches} pitch(es) \u00b7 ${pct}% strikes">` +
      `<span class="hz-n">${d.pitches || ''}</span>` +
      `${d.pitches ? `<span class="hz-p">${pct}%</span>` : ''}</div>`;
  }

  function heatmapHtml(hm) {
    const z = hm.zones;
    const core = CORE.map((row) =>
      `<div class="hz-row">${row.map((n) => cell(n, z)).join('')}</div>`).join('');
    const t = hm.total;
    return `
      <div class="hz-wrap">
        <div class="hz-diagram">
          <div class="hz-corner tl">${cell(11, z)}</div>
          <div class="hz-corner tr">${cell(12, z)}</div>
          <div class="hz-corner bl">${cell(13, z)}</div>
          <div class="hz-corner br">${cell(14, z)}</div>
          <div class="hz-core">${core}</div>
          <div class="hz-plate"></div>
        </div>
        <div class="hz-legend">
          <span class="muted">Pitch density</span>
          <div class="hz-bar"></div>
          <div class="hz-bar-lab"><span>low</span><span>high</span></div>
          <ul class="hz-stats">
            <li><b>${t.pitches}</b> pitches</li>
            <li><b>${Math.round(hm.strike_pct * 100)}%</b> strikes</li>
            <li><b>${Math.round(hm.swing_pct * 100)}%</b> swing</li>
            <li><b>${Math.round(hm.whiff_pct * 100)}%</b> whiff</li>
            ${hm.avg_velo ? `<li><b>${hm.avg_velo}</b> mph avg</li>` : ''}
          </ul>
        </div>
      </div>`;
  }

  const SPRAY = { hit: '#35d07f', out: '#ff5470', other: '#ffc857' };

  function sprayHtml(sp) {
    if (!sp || !sp.total) {
      return '<p class="muted">No batted-ball data for this game. Record plate '
        + 'appearances with contact to build a spray chart.</p>';
    }
    const W = 340, H = 320;
    const hx = 0.5 * W, hy = 0.93 * H;
    const pt = (ang, rad) => {
      const r = ang * Math.PI / 180;
      return [hx + rad * 0.5 * W * Math.sin(r), hy - rad * 0.86 * H * Math.cos(r)];
    };
    const P = (a) => a.map((n)=>n.toFixed(1)).join(',');
    const lf = pt(-45, 1.02), cf = pt(0, 1.06), rf = pt(45, 1.02);
    const b1 = pt(45, .42), b2 = pt(0, .52), b3 = pt(-45, .42);
    const g1 = pt(45, .30), g2 = pt(0, .40), g3 = pt(-45, .30), mound = pt(0, .30);
    let s = `<svg viewBox="0 0 ${W} ${H}" class="spray-svg" preserveAspectRatio="xMidYMid meet">`;
    s += `<defs><radialGradient id="sg" cx="50%" cy="90%" r="95%">`
      + `<stop offset="0%" stop-color="#1c5b34"/><stop offset="100%" stop-color="#0f3d22"/></radialGradient></defs>`;
    s += `<rect x="0" y="0" width="${W}" height="${H}" rx="12" fill="#08131f" stroke="#1e3050"/>`;
    s += `<path d="M${hx},${hy} L${P(lf)} Q${cf[0].toFixed(1)},${(cf[1]-24).toFixed(1)} ${P(rf)} Z" fill="url(#sg)" stroke="#2f7d4c"/>`;
    s += `<polygon points="${hx},${hy} ${P(b1)} ${P(b2)} ${P(b3)}" fill="#7a5230" stroke="#93673d" stroke-width="1.5"/>`;
    s += `<polygon points="${hx},${(hy-6).toFixed(1)} ${P(g1)} ${P(g2)} ${P(g3)}" fill="#1c5b34"/>`;
    s += `<line x1="${hx}" y1="${hy}" x2="${lf[0].toFixed(1)}" y2="${lf[1].toFixed(1)}" stroke="#dfe8f5" stroke-width="1.5" stroke-dasharray="5 4"/>`;
    s += `<line x1="${hx}" y1="${hy}" x2="${rf[0].toFixed(1)}" y2="${rf[1].toFixed(1)}" stroke="#dfe8f5" stroke-width="1.5" stroke-dasharray="5 4"/>`;
    const sq = (p)=>`<rect x="${(p[0]-4).toFixed(1)}" y="${(p[1]-4).toFixed(1)}" width="8" height="8" transform="rotate(45 ${p[0].toFixed(1)} ${p[1].toFixed(1)})" fill="#f4f7fb" stroke="#20303f"/>`;
    s += sq(b1)+sq(b2)+sq(b3);
    s += `<circle cx="${mound[0].toFixed(1)}" cy="${mound[1].toFixed(1)}" r="7" fill="#93673d" stroke="#b07f4c"/>`;
    sp.points.forEach((p) => {
      const col = SPRAY[p.cat] || '#9db';
      const r = p.contact === 'hard' ? 5.5 : (p.contact === 'soft' ? 3.5 : 4.5);
      const loc = p.exact ? '' : ' ~est';
      const tip = `${p.label} \u2014 ${p.batter || ''}${p.bb_type ? ' (' + p.bb_type + ')' : ''}`
        + `${p.detail ? ' ' + p.detail : ''} \u00b7 ${p.half==='T'?'\u25b2':'\u25bc'}${p.inning}${loc}`;
      s += `<circle class="spray-dot" data-cat="${p.cat}" cx="${(p.x*W).toFixed(1)}" cy="${(p.y*H).toFixed(1)}" `
        + `r="${r}" fill="${col}" fill-opacity="${p.exact?0.95:0.6}" stroke="#07101c" stroke-width=".8">`
        + `<title>${UI.esc(tip)}</title></circle>`;
    });
    s += '</svg>';
    return `<div class="spray-wrap">${s}
      <div class="spray-side">
        <ul class="hz-stats">
          <li><b>${sp.total}</b> batted balls</li>
          <li><b>${sp.counts.hit}</b> hits</li>
          <li><b>${sp.counts.out}</b> outs</li>
        </ul>
        <div class="spray-legend">
          <span class="spray-filter" data-cat="hit"><i style="background:${SPRAY.hit}"></i>Hit</span>
          <span class="spray-filter" data-cat="out"><i style="background:${SPRAY.out}"></i>Out</span>
          <span class="spray-filter" data-cat="other"><i style="background:${SPRAY.other}"></i>Other</span>
        </div>
        <p class="muted" style="font-size:11px">Solid dots are exact drop locations you clicked on the field; faded dots are estimated from the fielder and hit value. Click a legend swatch to filter.</p>
      </div></div>`;
  }

  function bindSpray(scope) {
    const filters = (scope || document).querySelectorAll('.spray-filter');
    const active = new Set(['hit','out','other']);
    filters.forEach((f) => f.onclick = () => {
      const cat = f.dataset.cat;
      if (active.has(cat) && active.size === 3) { active.clear(); active.add(cat); }
      else if (active.has(cat)) { active.delete(cat); if (!active.size) ['hit','out','other'].forEach((c)=>active.add(c)); }
      else active.add(cat);
      filters.forEach((x) => x.classList.toggle('off', !active.has(x.dataset.cat)));
      (scope || document).querySelectorAll('.spray-dot').forEach((d) => {
        d.style.display = active.has(d.dataset.cat) ? '' : 'none';
      });
    });
  }

  const BAT_COLS = [['AB','AB'],['R','R'],['H','H'],['2B','2B'],['3B','3B'],['HR','HR'],
    ['RBI','RBI'],['BB','BB'],['SO','SO'],['AVG','AVG'],['OPS','OPS']];
  const PIT_COLS = [['IP','IP'],['BF','BF'],['H','H'],['R','R'],['ER','ER'],['BB','BB'],
    ['SO','SO'],['HR','HR'],['ERA','ERA'],['WHIP','WHIP']];

  function statTable(rows, cols) {
    if (!rows.length) return '<p class="muted">No data.</p>';
    const head = `<th class="lft">Player</th>` + cols.map(([, l]) => `<th>${l}</th>`).join('');
    const body = rows.map((r) => `<tr><td class="lft">${UI.esc(r.name)}</td>` +
      cols.map(([k]) => `<td>${fmt(r[k], k)}</td>`).join('') + '</tr>').join('');
    return `<table class="tbl stat-tbl"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
  }
  const RATE3 = new Set(['AVG','OBP','SLG','OPS','ISO','BABIP','SB%','CS%','FPCT']);
  const RATE2 = new Set(['ERA','WHIP','K9','K/9','BB9','FIP']);
  function fmt(v, key) {
    if (v === undefined || v === null) return '';
    if (RATE3.has(key)) {
      const f = Number(v);
      if (Number.isNaN(f)) return v;
      const s = f.toFixed(3);
      return (f >= 0 && f < 1) ? s.replace(/^0\./, '.') : s;
    }
    if (RATE2.has(key)) {
      const f = Number(v);
      return Number.isNaN(f) ? v : f.toFixed(2);
    }
    if (typeof v === 'number' && !Number.isInteger(v)) return v.toFixed(3).replace(/^0\./, '.');
    return v;
  }

  function sideBlock(side, label) {
    const tn = side.team.name || label;
    return `<div class="rep-side">
      <div class="section-title">${UI.esc(tn)} \u2014 Batting</div>
      ${statTable(side.batting, BAT_COLS)}
      <div class="section-title" style="margin-top:12px">${UI.esc(tn)} \u2014 Pitching</div>
      ${statTable(side.pitching, PIT_COLS)}</div>`;
  }

  async function open(gameId) {
    let rep;
    try {
      rep = await API.get(`/games/${gameId}/report`);
    } catch (e) {
      UI.toast('Could not load report: ' + e.message, 'err');
      return;
    }
    const g = rep.game;
    const hasPitches = rep.heatmap.total.pitches > 0;
    const pitcherOpts = [{ value: '', label: 'All pitchers' }]
      .concat(rep.pitchers.map((p) => ({ value: p.player_id, label: p.name })));
    const pitcherSel = hasPitches && rep.pitchers.length
      ? `<label class="rep-filter">Pitcher
          <select id="rep-pit">${pitcherOpts.map((o) =>
            `<option value="${o.value}">${UI.esc(o.label)}</option>`).join('')}</select></label>`
      : '';
    UI.openModal(`
      <div class="modal-head"><h2>Game Report</h2><button class="icon-btn" data-x>&times;</button></div>
      <div class="modal-body rep-body">
        <div class="rep-title">${UI.esc(g.away_name)} @ ${UI.esc(g.home_name)}
          <span class="muted">${UI.esc(g.game_date || '')}${g.venue ? ' \u00b7 ' + UI.esc(g.venue) : ''}</span></div>
        <div class="rep-heat panel"><div class="panel-head"><h2>Strike-zone heatmap</h2>${pitcherSel}</div>
          <div class="panel-body" id="rep-hm">
            ${hasPitches ? heatmapHtml(rep.heatmap)
              : '<p class="muted">No pitch-by-pitch data for this game. Enable \u201cPitches\u201d in the scorer to build a heatmap.</p>'}
          </div></div>
        <div class="rep-heat panel"><div class="panel-head"><h2>Spray chart</h2></div>
          <div class="panel-body">${sprayHtml(rep.spray)}</div></div>
        <div class="rep-box">${sideBlock(rep.away, g.away_name)}${sideBlock(rep.home, g.home_name)}</div>
      </div>
      <div class="modal-foot">
        <button class="btn ghost" data-export="html">Export Web (HTML)</button>
        <button class="btn ghost" data-export="pdf">Export PDF</button>
        <button class="btn primary" data-cancel>Close</button></div>`);
    const m = document.getElementById('modal');
    m.querySelector('[data-x]').onclick = UI.closeModal;
    m.querySelector('[data-cancel]').onclick = UI.closeModal;
    bindSpray(m);
    m.querySelectorAll('[data-export]').forEach((b) => b.onclick = async () => {
      const ext = b.dataset.export;
      const prev = b.textContent;
      b.disabled = true; b.textContent = ext === 'pdf' ? 'Saving PDF\u2026' : 'Saving\u2026';
      try {
        // Preferred path in the packaged desktop app: native Save-As dialog via
        // the pywebview JS bridge (guarantees a user-chosen, writable location).
        const bridge = window.pywebview && window.pywebview.api && window.pywebview.api.save_report;
        if (bridge) {
          const r = await window.pywebview.api.save_report(gameId, ext);
          if (r && r.ok) {
            UI.toast(`Saved to ${r.path}`, 'ok', 6000);
            if (window.pywebview.api.open_folder) {
              try { await window.pywebview.api.open_folder(r.path); } catch (e) { /* ignore */ }
            }
          } else if (r && r.cancelled) {
            UI.toast('Save cancelled', 'ok');
          } else {
            UI.toast('Export failed: ' + ((r && r.error) || 'unknown error'), 'err');
          }
        } else {
          // Web/browser mode: stream the file straight to the browser as a
          // normal download (no server-side filesystem involved).
          const a = document.createElement('a');
          a.href = `/api/games/${gameId}/export.${ext}`;
          a.download = '';
          document.body.appendChild(a); a.click(); a.remove();
          UI.toast(ext === 'pdf' ? 'Downloading PDF…' : 'Downloading report…', 'ok');
        }
      } catch (e) {
        UI.toast('Export failed: ' + e.message, 'err');
      } finally {
        b.disabled = false; b.textContent = prev;
      }
    });
    const sel = m.querySelector('#rep-pit');
    if (sel) sel.onchange = async () => {
      const q = sel.value ? `?pitcher_id=${sel.value}` : '';
      const hm = await API.get(`/games/${gameId}/heatmap${q}`);
      document.getElementById('rep-hm').innerHTML = hm.total.pitches
        ? heatmapHtml(hm) : '<p class="muted">No pitches for this selection.</p>';
    };
  }

  return { open };
})();
