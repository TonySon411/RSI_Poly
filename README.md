# RSI Trading Dashboard

A Flask dashboard with three parts, all served from `python app.py` on
**http://localhost:8008**:

1. **Templates** (home page, `/`) — configure named RSI templates that trade
   **live, in paper mode, against the real Polymarket market**, and watch
   their win rate / PnL accumulate in real time.
2. **Backtest** (`/backtest`) — backtest the same RSI strategy against
   historical Bybit candles, across any symbol/timeframe combination.
3. **Tick recorder** (`recordData.py`, its own separate process, no UI yet)
   — continuously records real Polymarket order-book price ticks via
   WebSocket, for a backtest mode that replays real market prices instead of
   just Bybit candle direction.

This project reuses the existing **`topbot`** project's actual Polymarket
integration (`D:\polymarket\topbot`) read-only via `sys.path` — see
[Prerequisite](#prerequisite) below. `topbot` itself is not modified by
anything here.

## The strategy (shared by all three parts)

For each closed candle: compute Wilder RSI(length). If RSI **> overbought**,
predict/bet **Down**; if RSI **< oversold**, predict/bet **Up**; otherwise
skip. Every signal is an **independent decision** — no retry ladder, a miss
is just a loss (this project always forces `max_attempts=1`, even though
topbot's own default config enables one same-direction retry after a loss).

The Templates tab additionally reuses topbot's real 5-rung paper ladder
(0.50/0.40/0.30/0.20/0.10 at 5/5/10/15/20 shares) and its real Polymarket CLOB
fill simulation; the Backtest tab has no concept of ladder economics — it
just measures directional win rate against historical Bybit candles.

## 1. Templates tab

Create a template (Name, Symbol, Timeframe, RSI length, Overbought,
Oversold) and it immediately starts a background thread that:

- Aligns to that timeframe's window boundaries (5m/15m/1h/4h).
- Each window, reuses topbot's actual `run_window()` unchanged: computes
  RSI off live Bybit candles, and on a signal, places the real 5-rung paper
  ladder against the live Polymarket order book for that exact
  `{symbol}-updown-{timeframe}` market (real market discovery via Gamma,
  real CLOB best-ask fill simulation) — **paper mode only, no credentials,
  no real orders.**
- Retries up to 3 times on a transient network error (timeout/connection
  reset) before logging a real error; non-network errors fail immediately.
- Never silently skips a window — even if a real trade's post-close
  resolution wait runs long, the next window is still always evaluated
  (this project's own fix for a scheduling bug that exists in topbot's own
  `run_forever()`; see `paper_engine/manager.py`).

A separate background thread (`paper_engine/resolver.py`) continuously
re-polls Gamma for any trade that placed a real side but didn't get a
resolution back within topbot's own short post-window wait, so PnL/win-rate
stats stay accurate even when Polymarket is slow to finalize a market.

All templates and their full trade history persist in
`data/templates.db` (SQLite) and resume automatically on restart.

Actions per template: **Stop/Start**, **Trades** (full trade-list page with
live PnL/win-rate summary), **Edit** (config changes restart its thread),
**Delete**.

## 2. Backtest tab

Pick a symbol (BTC/ETH/SOL/XRP/DOGE/HYPE/BNB), timeframe (5m/15m/1h/4h),
date range, RSI length, and overbought/oversold thresholds, then **Run
backtest**. Win rate is measured over fully-decided windows (a window
resolves **Down** if its close is below its open, **Up** otherwise),
excluding a still-open trailing signal at the very end of the loaded data.
Also shows the full trade list (time, RSI, prediction, actual, win/loss).

Historical candles come from Bybit's public `linear` kline endpoint, cached
locally as CSV under `data/{SYMBOL}_{timeframe}.csv`, and lazily
extended/top-warmed on every dashboard request — `fetch_data.py` just
pre-warms the cache so the first click isn't slow.

## 3. Tick recorder (`recordData.py`)

Its own standalone process (`python recordData.py`) — run it alongside
`app.py`, not inside it, so recording keeps running independently of the
dashboard's own lifecycle (and so nothing ever double-records into the same
files). Runs 14 background recorders (7 assets × [5m, 15m]), each with its own
persistent WebSocket connection to Polymarket's CLOB market channel
(`wss://ws-subscriptions-clob.polymarket.com/ws/market`). Every real price
change (not size-only book churn) is recorded with a timestamp; each market
gets its own file at `data/<SYMBOL>/<5m|15m>/<slug>.json`, flushed to disk
every ~5s and patched with its `resolution` once Gamma confirms the
outcome. Ported from the sibling `Up_Down_both` project's recording format
(`tick_recorder/`), reusing this project's own Gamma client instead of a
second parallel implementation.

This data isn't used by the Backtest tab yet — it's accumulating so a future
backtest mode can replay real historical Polymarket prices (real ladder
fills, real settlement) instead of the current Bybit-candle-direction proxy.

## Prerequisite

`paper_engine/topbot_bridge.py` and `tick_recorder/recorder.py` both import
topbot's own modules directly via `sys.path` (see `TOPBOT_SRC` in
`topbot_bridge.py`), so `D:\polymarket\topbot\src` must exist alongside this
project. No install step needed for it — imported read-only, and paper mode
requires no credentials (`.env`/private key) at all.

## Setup

```bash
pip install -r requirements.txt

# one-time bulk download of all symbols/timeframes (re-run any time to top up)
python fetch_data.py
```

## Run

```bash
python app.py          # dashboard on port 8008; resumes any templates left `running`
python recordData.py   # separate process: the 14 tick recorders
```

## Project layout

```
app.py                       Flask server: registers the Templates blueprint,
                              the Backtest routes, and starts the background
                              template manager / pending resolver on startup.
recordData.py                 Standalone tick recorder process (run alongside app.py).
fetch_data.py                 CLI to bulk-populate the Backtest tab's Bybit cache.

rsi_backtest/
  bybit_client.py              Paginated Bybit kline fetcher.
  data_store.py                Local CSV cache, fills gaps from Bybit on demand.
  rsi.py                       Wilder RSI.
  backtest.py                  The no-retry historical backtest engine.

paper_engine/
  topbot_bridge.py              sys.path bridge into topbot; builds a topbot
                                 Config per template row (always paper mode,
                                 max_attempts=1).
  store.py                      SQLite: templates + their trade history.
  manager.py                    One background thread per running template;
                                 window scheduling + transient-error retry.
  resolver.py                   Background thread that keeps re-polling Gamma
                                 for any trade stuck without a resolution.
  routes.py                     Flask blueprint: Templates pages + JSON API.

tick_recorder/
  models.py                     BookTop dataclass.
  clob_ws.py                    Polymarket CLOB "market" websocket client.
  store.py                      JSON-file tick storage (one file per market).
  recorder.py                   Per-(symbol, timeframe) recording loop.
  manager.py                    Spawns one recorder thread per symbol x timeframe.

templates/                     Jinja templates: base.html (shared nav),
                                templates.html, template_trades.html, backtest.html.
static/                        style.css, app.js (backtest), templates.js,
                                template_trades.js.

data/                          Bybit OHLC CSV cache, templates.db, and the
                                tick recorder's data/<SYMBOL>/<5m|15m>/*.json.
```
