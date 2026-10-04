# Diamond Scorer

An MLB-grade baseball scoring, statistics and analytics desktop application.

- **Backend:** Python + FastAPI + SQLite (single local database file)
- **Frontend:** modern dark-blue single-page UI (HTML/CSS/JS, no build step)
- **Desktop shell:** native window via `pywebview`; binds to `127.0.0.1` only
- **Packaging:** single Windows `.exe` via PyInstaller (`build_windows_exe.bat`)

## Run (development)

```bash
pip install -r requirements.txt
python main.py
```

If `pywebview` is installed it opens a native window. In a headless environment
it falls back to printing a local URL you can open in a browser.

## Build the Windows executable

**64-bit Windows (default):**

```bat
build_windows_exe.bat
```

**32-bit Windows (also runs on 64-bit):**

```bat
build_windows_exe_32bit.bat
```

PyInstaller always produces an `.exe` that matches the architecture of the
Python interpreter used to build it, so the 32-bit script must be run with a
32-bit (x86) build of Python. Just double-click `build_windows_exe_32bit.bat`:
it automatically locates a 32-bit interpreter (preferring the `py -3-32`
launcher), refuses to continue if only a 64-bit Python is found, and keeps the
window open at the end so you can read the result. See the comments at the top
of the script for how to install 32-bit Python. A 32-bit executable is the most
broadly compatible: it runs on **both** 32-bit and 64-bit Windows. The app code
itself is pure Python and architecture-independent, and all dependencies ship
32-bit (`win32`) wheels.

For the native window, the app prefers the modern WebView2 renderer and
automatically falls back to the built-in MSHTML (Internet Explorer) engine on
older machines that lack the WebView2 runtime, so no extra runtime install is
required on legacy 32-bit systems.

The app is fully offline and never exposes a network service.

## Run as a web app (browser mode)

Diamond Scorer is already a web application internally (FastAPI backend + a
single-page frontend). The desktop build simply wraps that in a native window.
To use it in an ordinary browser instead -- for local use or a self-hosted
deployment -- run the web entry point:

```bash
pip install -r requirements.txt
python run_web.py                 # serves http://127.0.0.1:8000
```

macOS / Linux users can instead run `./run_web.sh`, which creates a local
virtualenv, installs dependencies, and starts the server. Override the address
with environment variables:

```bash
PORT=9000 python run_web.py       # choose a port
NO_BROWSER=1 python run_web.py    # do not auto-open the browser
```

### Deployment notes & security

- **Localhost by default.** `run_web.py` binds to `127.0.0.1`, so it is only
  reachable from the same machine and is **not** exposed on your network.
- **No built-in authentication.** The app has no login or access control --
  anyone who can reach the bound address has full read/write access to all
  data. Do **not** bind it to a public interface (`0.0.0.0` or a LAN IP)
  directly.
- **For remote / multi-user access**, place it behind a reverse proxy
  (nginx, Caddy, Traefik) that terminates TLS and enforces authentication, and
  keep the app itself bound to localhost. Example (nginx):

  ```nginx
  location / {
      auth_basic "Diamond Scorer";
      auth_basic_user_file /etc/nginx/.htpasswd;
      proxy_pass http://127.0.0.1:8000;
  }
  ```

- **Data lives in a single SQLite file** under `data/`. Back it up (or use the
  in-app *Export Session* button) before upgrades. For production you can run
  under a process manager (systemd, supervisor) with multiple uvicorn/gunicorn
  workers only if you move to a server-grade database; SQLite is best for
  single-writer local use.

## Host it online (create a repo and deploy)

The repository is ready to publish as-is. Create a Git repo and push it:

```bash
git init
git add .
git commit -m "Diamond Scorer"
git branch -M main
git remote add origin <your-repo-url>
git push -u origin main
```

A `.gitignore` already excludes the local database, exports and build
artefacts, so no user data is committed.

### Option A - Docker (works anywhere)

```bash
docker build -t diamond-scorer .
docker run -d --name diamond-scorer \
  -p 8000:8000 \
  -v diamond_data:/data \
  -e DIAMONDSCORER_AUTH=admin:change-me \
  diamond-scorer
```

The database persists in the `diamond_data` volume at `/data/baseball.db`.
Open `http://<host>:8000`. Put it behind a TLS-terminating reverse proxy for
public use.

### Option B - Render / Railway / Fly.io / Heroku (PaaS)

- **Render:** this repo ships a `render.yaml` blueprint. In Render choose
  *New + > Blueprint* and point it at your repo. It provisions a web service
  with a 1 GB persistent disk mounted at `/var/data` (where the DB lives) and
  a `/health` check. Set `DIAMONDSCORER_AUTH` in the dashboard.
- **Railway / Heroku-style:** the `Procfile` runs the app with gunicorn +
  a uvicorn worker on the platform-provided `$PORT`. Add a persistent volume
  and point `BASEBALL_DB` at it; otherwise data is lost on redeploy.
- `runtime.txt` pins Python 3.12.

### Option C - Plain VPS (systemd + nginx)

```bash
pip install -r requirements.txt
BASEBALL_DB=/srv/diamond/baseball.db \
  gunicorn backend.server:app -k uvicorn.workers.UvicornWorker \
  -b 127.0.0.1:8000 --workers 1 --timeout 120
```

Then reverse-proxy it with nginx (see the example below) and manage it with a
`systemd` unit so it restarts on boot.

### Configuration (environment variables)

| Variable | Purpose | Default |
|----------|---------|---------|
| `BASEBALL_DB` | Path to the SQLite database file (point at a persistent disk) | `data/baseball.db` |
| `PORT` | Port the server listens on | `8000` |
| `HOST` | Bind address for `run_web.py` | `127.0.0.1` |
| `DIAMONDSCORER_AUTH` | `user:password` to require HTTP Basic auth on every route (except `/health`). Unset = no login | *(off)* |
| `NO_BROWSER` | Set to `1` to stop `run_web.py` auto-opening a browser | *(off)* |

### Security -- read before going public

- **No login by default.** Anyone who can reach the URL has full read/write
  access to all data. Before exposing it on the internet, **either** set
  `DIAMONDSCORER_AUTH=user:password` **or** enforce auth at your reverse proxy
  (and always serve over HTTPS).
- **SQLite is single-writer**, so run **one** worker. For many concurrent
  writers migrate to a server-grade database; SQLite is ideal for small clubs
  and single-scorer use.
- Example nginx reverse proxy with TLS + extra auth:

  ```nginx
  location / {
      auth_basic "Diamond Scorer";
      auth_basic_user_file /etc/nginx/.htpasswd;
      proxy_pass http://127.0.0.1:8000;
      proxy_set_header Host $host;
      proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
  }
  ```

## Portable backup: Export / Import Session

The **Utilities** screen has **Export Session** and **Import Session** buttons.
Export writes a single `.zip` containing every league, season, team, player,
roster and game, which you can archive or move to another machine. Import loads
such a `.zip` -- note that importing **replaces all current data**, so export
first if you want to keep the existing contents.

## Roadmap

| Phase | Scope | Status |
|-------|-------|--------|
| 1 | Foundation: data model, Utilities CRUD (Leagues/Seasons/Teams/Players + rosters), persistent player IDs, dark-blue UI shell | Done |
| 2 | Live game scorer: full play-by-play, baserunning, catcher attribution, game info, wrap-up, save/load, forfeits/knockouts | Planned |
| 3 | Pitch-by-pitch mode: 9-zone strike grid, velocity, pitch type | Planned |
| 4 | Statistics engine: Basic/Advanced/Detailed, standings, streaks, game-by-game, presets | Planned |
| 5 | Visualization: field spray chart + strike-zone heatmap with % overlays | Planned |
| 6 | Reports (PDF + Web) and portable League/Season/Game export-import | Planned |
| 7 | Windows packaging | Scaffolded |

## Data model

```
League 1--* Season 1--* (season_teams) *--1 Team
Season + Team 1--* Roster *--1 Player   (Player has a stable global ID)
```

Players and Teams are global entities, so a player's identity and history
persist across every league and season.
