# Deploying the RSI dashboard with PM2

This is **two separate Flask/Python processes**, run as two PM2 apps:

- `rsi-dashboard` (`python app.py`) — the dashboard itself, plus its
  background template threads and pending-resolution resolver.
- `rsi-recorder` (`python recordData.py`) — the 14 Polymarket tick recorders,
  run independently so they keep recording regardless of the dashboard
  process's own restarts/crashes, and so nothing ever double-records into
  the same files.

PM2 doesn't know Python natively, so we point it directly at the
virtualenv's `python` binary for each and let PM2 treat them like any other
long-running process — restart on crash, log capture, startup-on-boot.

This guide assumes a Linux server (Ubuntu/Debian). Adjust paths for other
distros.

## ⚠️ Single instance only (each app)

Templates, the pending resolver, and the tick recorder are all in-process
singletons (module-level thread registries, one shared SQLite connection).
**Never run either app under PM2 cluster mode or with `instances` > 1** —
an extra `rsi-dashboard` instance would independently resume every template,
double-counting every trade; an extra `rsi-recorder` instance would open a
second duplicate set of 14 Polymarket websocket connections, writing
conflicting data into the same JSON files. `ecosystem.config.js` already
pins `instances: 1` and `exec_mode: "fork"` for both — don't change that,
and never run `python app.py`/`python recordData.py` by hand on the server
at the same time as their PM2-managed copies.

## 1. Prerequisites (on the server)

```bash
sudo apt update
sudo apt install -y python3 python3-venv git

# Node.js + npm (needed for PM2 itself)
curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash -
sudo apt install -y nodejs

# PM2, installed globally
sudo npm install -g pm2
```

Check versions:

```bash
python3 --version   # 3.11+ recommended
pm2 --version
```

## 2. Get the code onto the server

This project imports `topbot`'s real Polymarket integration directly via
`sys.path` (`paper_engine/topbot_bridge.py`) — **`topbot` must exist on the
server too**, either as a sibling directory of this project (the default,
matching local dev: `<parent>/RSI` + `<parent>/topbot`) or anywhere else via
the `TOPBOT_SRC` env var (see step 4). It is never installed or modified —
only read from.

```bash
mkdir -p ~/polymarket && cd ~/polymarket
git clone <your-topbot-repo-url> topbot
git clone <your-rsi-repo-url> RSI
cd RSI
```

(Or `scp -r` your local folders over, excluding `.venv`, `__pycache__`,
`data/`, and `logs/`.)

## 3. Create the virtualenv and install dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
deactivate
```

This must produce `.venv/bin/python` — that's the path PM2 will invoke (see
`ecosystem.config.js`, already included in the repo). `topbot`'s own
dependencies (`httpx`, `pyyaml`, `python-dotenv`) are separate from this
venv; if they aren't already installed for whatever Python topbot itself
runs under, install them too — this project doesn't need topbot's own
`py-clob-client-v2` dependency since paper mode never imports it.

## 4. Configure paths

If `topbot` is **not** a sibling directory of this project (see step 2),
point at it explicitly — add to `.bashrc`/`.profile` or set it directly in
`ecosystem.config.js`'s `env` block:

```bash
export TOPBOT_SRC=/absolute/path/to/topbot/src
```

No `.env` file or credentials are needed for this project itself — paper
mode only ever makes unauthenticated GET requests to Bybit/Gamma/CLOB.

## 5. Warm the Backtest tab's data cache (optional but recommended)

```bash
source .venv/bin/activate
python fetch_data.py    # bulk-downloads all 7 symbols x 4 timeframes from Bybit
deactivate
```

Skippable — the dashboard also fetches/extends this cache on demand — but
doing it once up front means the first Backtest click on the server isn't
slow.

## 6. Start it under PM2

The repo includes `ecosystem.config.js`, defining both apps (`rsi-dashboard`
and `rsi-recorder`) — see the file itself for the full config.

Start both:

```bash
pm2 start ecosystem.config.js
```

Verify:

```bash
pm2 status
pm2 logs rsi-dashboard
pm2 logs rsi-recorder
```

`rsi-dashboard`'s logs should show Flask's startup lines and (once any
templates exist) their window-by-window activity — any templates already
marked `running` in `data/templates.db` resume automatically.
`rsi-recorder`'s logs should show `[tick_recorder] started 14 recorders...`
followed by each market's `recording`/`resolved` lines.

The dashboard listens on port **8008** on all interfaces
(`0.0.0.0:8008`) — open that port in your firewall/security group, or put
an nginx reverse proxy in front of it if you want it on 80/443 with TLS.

## 7. Make it survive reboots

```bash
pm2 save              # snapshot the current process list
pm2 startup           # prints a systemd command — copy/paste and run it once
```

## 8. Day-to-day operations

| Task | Command |
|---|---|
| Tail live logs | `pm2 logs rsi-dashboard` / `pm2 logs rsi-recorder` |
| Check status / uptime / restarts | `pm2 status` |
| Restart dashboard (e.g. after a code change) | `pm2 restart rsi-dashboard` |
| Restart recorder | `pm2 restart rsi-recorder` |
| Restart both | `pm2 restart rsi-dashboard rsi-recorder` |
| Stop | `pm2 stop rsi-dashboard rsi-recorder` |
| Remove from PM2's list | `pm2 delete rsi-dashboard rsi-recorder` |
| Live CPU/memory monitor | `pm2 monit` |

Restarting `rsi-dashboard` does **not** interrupt `rsi-recorder` (they're
independent processes) — recording keeps running across dashboard restarts,
and vice versa. Stopping/restarting `rsi-dashboard` only pauses templates —
every template's config and full trade history stays in `data/templates.db`
and resumes exactly where it left off (any templates that were `running`
restart automatically; ones you'd stopped stay stopped).

## 9. Deploying an update

```bash
cd ~/polymarket/RSI
git pull
source .venv/bin/activate
pip install -r requirements.txt   # only needed if dependencies changed
deactivate
pm2 restart rsi-dashboard rsi-recorder
```

If `topbot` itself was updated too, just `git pull` inside `~/polymarket/topbot`
— no reinstall needed there since it's only read via `sys.path`, never installed.

## Troubleshooting

- **`pm2 logs rsi-dashboard`/`rsi-recorder` shows `[paper_engine] WARNING:
  topbot source not found at ...`** — `topbot` isn't where this project
  expects it. Either clone it as a sibling directory (step 2) or set
  `TOPBOT_SRC` (step 4), then `pm2 restart rsi-dashboard rsi-recorder
  --update-env`.
- **`ModuleNotFoundError: No module named 'websocket'`** — `pip install -r
  requirements.txt` wasn't run inside `.venv`, or you're invoking a different
  Python than `.venv/bin/python`. Check with `.venv/bin/python -c "import
  websocket, flask, pandas, requests"`.
- **Templates show duplicate/doubled trades for the same window** — almost
  certainly running more than one `rsi-dashboard` instance (cluster mode, or
  a second `pm2 start` without stopping the first). Run `pm2 status` and
  make sure exactly one `rsi-dashboard` process exists.
- **Recorded JSON files look corrupted or have inconsistent data** — almost
  certainly two recorders writing to the same files at once: check `pm2
  status` for more than one `rsi-recorder` process, and make sure nobody
  also ran `python recordData.py` by hand on the same server.
- **Backtest tab is slow on first use** — expected if `fetch_data.py` (step
  5) wasn't run; it's lazily fetching the full Bybit history for whatever
  symbol/timeframe you first select.
- **Wrong Python version** — this project targets 3.11+; run `python3
  --version` before creating the venv.
