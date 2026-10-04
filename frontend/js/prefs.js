// User preferences (client-side, persisted in localStorage).
// Currently governs whether in-popup selectors during live scoring render as
// button "pickers" (default) or classic dropdowns.
const Prefs = (() => {
  const KEY = 'diamond.prefs.v1';
  const DEFAULTS = { usePickers: true };

  function all() {
    try {
      return Object.assign({}, DEFAULTS, JSON.parse(localStorage.getItem(KEY) || '{}'));
    } catch (e) {
      return Object.assign({}, DEFAULTS);
    }
  }
  function get(key) { return all()[key]; }
  function set(key, val) {
    const p = all();
    p[key] = val;
    try { localStorage.setItem(KEY, JSON.stringify(p)); } catch (e) { /* ignore */ }
    return p;
  }
  // Convenience for scorer popups.
  function usePickers() { return get('usePickers') !== false; }

  async function render(root) {
    const p = all();
    root.innerHTML = `
      <div class="panel"><div class="panel-head"><h2>Scoring input style</h2></div>
        <div class="panel-body">
          <p class="muted">Choose how the in-play pop-ups (batted-ball type, contact quality,
          and the error fielder) let you make a selection while scoring. This does not affect
          the main pitcher, catcher, or lineup dropdowns.</p>
          <label class="chk" style="display:flex;gap:10px;align-items:center;margin:10px 0;font-size:15px">
            <input type="checkbox" id="pf-pickers" ${p.usePickers?'checked':''}>
            <span><b>Use button pickers</b> \u2014 tap large buttons instead of opening dropdown lists.
            Turn this off to use classic dropdowns.</span>
          </label>
          <div id="pf-saved" class="muted" style="font-size:12px;height:16px"></div>
        </div></div>`;
    const chk = root.querySelector('#pf-pickers');
    const saved = root.querySelector('#pf-saved');
    chk.onchange = () => {
      set('usePickers', chk.checked);
      saved.textContent = 'Saved \u2713';
      setTimeout(() => { saved.textContent = ''; }, 1600);
    };
  }

  return { get, set, all, usePickers, render };
})();
