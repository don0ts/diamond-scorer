// Thin fetch wrapper around the local FastAPI backend.
const API = (() => {
  async function req(method, path, body) {
    const opts = { method, headers: {} };
    if (body !== undefined) {
      opts.headers['Content-Type'] = 'application/json';
      opts.body = JSON.stringify(body);
    }
    const res = await fetch('/api' + path, opts);
    if (!res.ok) {
      let detail = res.statusText;
      try { const j = await res.json(); detail = j.detail || detail; } catch (e) {}
      throw new Error(detail);
    }
    if (res.status === 204) return null;
    const txt = await res.text();
    return txt ? JSON.parse(txt) : null;
  }
  return {
    get: (p) => req('GET', p),
    post: (p, b) => req('POST', p, b),
    put: (p, b) => req('PUT', p, b),
    patch: (p, b) => req('PATCH', p, b),
    del: (p) => req('DELETE', p),
    // Convenience domain calls
    leagues: () => req('GET', '/leagues'),
    seasons: (leagueId) => req('GET', '/seasons' + (leagueId ? `?league_id=${leagueId}` : '')),
    teams: () => req('GET', '/teams'),
    players: () => req('GET', '/players'),
    playerHistory: (id) => req('GET', `/players/${id}/history`),
    seasonTeams: (sid) => req('GET', `/seasons/${sid}/teams`),
    roster: (sid, tid) => req('GET', `/seasons/${sid}/teams/${tid}/roster`),
  };
})();
