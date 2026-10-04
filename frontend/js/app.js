// App shell: view routing + top-bar action wiring.
const App = (() => {
  const TITLES = { setup: 'Initialize Game / Scoring', games: 'Games', statistics: 'Statistics', utilities: 'Utilities', visualization: 'Visualization', preferences: 'Preferences' };
  let current = 'games';

  function refreshActions() {
    const host = document.getElementById('topbar-actions');
    host.innerHTML = current === 'utilities' ? Utilities.actions() : '';
    host.querySelectorAll('[data-act]').forEach((b) => b.onclick = () => Utilities.onAction(b.dataset.act));
  }

  function placeholder(view, blurb, phase) {
    return UI.empty('🚧', blurb,
      `<div class="coming-soon"><span class="tag">Arriving in ${phase}</span></div>`);
  }

  async function show(view) {
    current = view;
    document.getElementById('view-title').textContent = TITLES[view];
    document.querySelectorAll('.nav-item').forEach((n) => n.classList.toggle('active', n.dataset.view === view));
    const root = document.getElementById('view-root');
    refreshActions();
    if (view === 'utilities') { await Utilities.render(root); refreshActions(); return; }
    if (view === 'setup') { await Setup.render(root); return; }
    if (view === 'games') { await Games.render(root); return; }
    if (view === 'statistics') { await Statistics.render(root); return; }
    if (view === 'visualization') { await Visualization.render(root); return; }
    if (view === 'preferences') { await Prefs.render(root); return; }
  }

  function init() {
    document.querySelectorAll('.nav-item').forEach((n) => n.onclick = () => show(n.dataset.view));
    // Feature 11: hide / show the sidebar.
    const app = document.getElementById('app');
    const tog = document.getElementById('sidebar-toggle');
    if (localStorage.getItem('ds_sidebar_hidden') === '1') app.classList.add('sidebar-hidden');
    if (tog) tog.onclick = () => {
      const hidden = app.classList.toggle('sidebar-hidden');
      localStorage.setItem('ds_sidebar_hidden', hidden ? '1' : '0');
    };
    show('utilities'); // start on the first working module
  }

  document.addEventListener('DOMContentLoaded', init);
  return { show, refreshActions };
})();
