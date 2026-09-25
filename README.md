# RSI Trading Dashboard

A Flask dashboard with four tabs, served from `python app.py` on
**http://localhost:8008**, plus a separate standalone recorder process:

1. **Templates** (home page, `/`) — configure named RSI templates that trade
   **live, in paper mode, against the real Polymarket market**, and watch
   their win rate / PnL accumulate in real time.
2. **Backtest** (`/backtest`) — backtest the RSI strategy against historical
   Bybit candles, across any symbol/timeframe combination, with manually-set
   overbought/oversold thresholds.
3. **ATR Backtest** (`/rsi-backtest`) — same historical backtest, but the
   overbought/oversold thresholds aren't fixed: each candle picks its own
   thresholds from *that candle's own ATR* (volatility), via a bucket table
   in `rsi_backtest/config.json`.
4. **Live Backtest** (`/live-backtest`) — replays the *actually recorded*
   Polymarket order-book prices (from the tick recorder, see below) to
   simulate the real 5-rung paper ladder fill-by-fill, instead of just
   guessing win/loss from Bybit candle direction.
5. **Tick recorder** (`recordData.py`, its own separate process, no UI yet)
   — continuously records real Polymarket order-book price ticks via
   WebSocket, which the Live Backtest tab replays.

This project reuses the existing **`topbot`** project's actual Polymarket
integration (`D:\polymarket\topbot`) read-only via `sys.path` — see
[Prerequisite](#prerequisite) below. `topbot` itself is not modified by
anything here.

## The strategy (shared by Templates, Backtest, and ATR Backtest)

For each closed candle: compute Wilder RSI(length). If RSI **> overbought**,
predict/bet **Down**; if RSI **< oversold**, predict/bet **Up**; otherwise
skip. Every signal is an **independent decision** — no retry ladder, a miss
is just a loss (this project always forces `max_attempts=1`, even though
topbot's own default config enables one same-direction retry after a loss).

The Templates tab additionally reuses topbot's real 5-rung paper ladder
(0.50/0.40/0.30/0.20/0.10 at 5/5/10/15/20 shares) and its real Polymarket CLOB
fill simulation; the Backtest/ATR Backtest tabs have no concept of ladder
economics — they just measure directional win rate against historical Bybit
candles. The Live Backtest tab is the exception: it *does* replay the real
ladder against real recorded order-book prices (see below).

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
extended/top-warmed on every dashboard request — `fetch_data.py`/
`fetch_historical_data.py` just pre-warm the cache so the first click isn't
slow (see [Setup](#setup)).

## 3. ATR Backtest tab

Same next-window prediction as the Backtest tab, except the
overbought/oversold thresholds are not typed in manually — each candle
computes its own ATR(length) and looks up the matching bucket in
`rsi_backtest/config.json`:

```json
{
  "atr_buckets": [
    { "min_atr": 0.0, "max_atr": 3.0,  "overbought": 84, "oversold": 17 },
    { "min_atr": 3.0, "max_atr": 4.25, "overbought": 83, "oversold": 24 },
    ...
  ]
}
```

A calmer, low-ATR market uses a narrower (closer-to-50) band; a more
volatile, high-ATR market needs a much more extreme band to fire at a
similar rate. A bucket can also be one-sided (`overbought: 99` or
`oversold: 1` effectively disables that side for that ATR range, since RSI
essentially never reaches those values) — useful when only one direction is
actually profitable in a given volatility regime. Buckets don't need to
cover the whole ATR range either; an ATR value matching no bucket is simply
skipped (no trade), which lets you deliberately exclude a regime rather than
force a mediocre threshold onto it.

This table is tuned to a specific symbol/RSI-length/ATR-length combination
(currently ETH, RSI(7), ATR(7) — see the tab's default inputs); it's raw
dollar ATR, not normalized to price, so it doesn't automatically generalize
to other symbols or lengths without re-tuning.

## 4. Live Backtest tab

Uses the same RSI(length)/overbought/oversold decision as the other tabs,
but instead of guessing win/loss from Bybit candle direction, it replays the
**actually recorded** Polymarket order-book prices for that exact market
(from the tick recorder) to simulate the real 5-rung paper ladder
(0.50/0.40/0.30/0.20/0.10) fill-by-fill, then settles using the market's
real recorded resolution. Coverage is limited to whatever the tick recorder
has captured so far — signals with no recording, or whose market hasn't
resolved yet, are shown separately rather than silently dropped.

## 5. Tick recorder (`recordData.py`)

Its own standalone process (`python recordData.py`) — run it alongside
`app.py`, not inside it, so recording keeps running independently of the
dashboard's own lifecycle (and so nothing ever double-records into the same
files). Runs 14 background recorders (7 assets × [5m, 15m]), each with its
own persistent WebSocket connection to Polymarket's CLOB market channel
(`wss://ws-subscriptions-clob.polymarket.com/ws/market`). Every real price
change (not size-only book churn) is recorded with a timestamp; each market
gets its own file at `data/<SYMBOL>/<5m|15m>/<slug>.json`, flushed to disk
every ~5s and patched with its `resolution` once Gamma confirms the
outcome. Ported from the sibling `Up_Down_both` project's recording format
(`tick_recorder/`), reusing this project's own Gamma client instead of a
second parallel implementation.

Use `clearRecordedData.py` to wipe recorded data for one or more symbols
without touching anything else (Bybit CSV cache, `templates.db`, etc.) — see
[Data maintenance](#data-maintenance).

## Prerequisite

`paper_engine/topbot_bridge.py` and `tick_recorder/recorder.py` both import
topbot's own modules directly via `sys.path` (see `TOPBOT_SRC` in
`topbot_bridge.py`), so `D:\polymarket\topbot\src` must exist alongside this
project. No install step needed for it — imported read-only, and paper mode
requires no credentials (`.env`/private key) at all.

## Setup

```bash
pip install -r requirements.txt

# one-time bulk download of all symbols/timeframes from 2026-01-01 onward
# (re-run any time to top up)
python fetch_data.py

# optional: backfill 5m/15m history further back, from 2023-01-01 to
# 2026-01-01 (only fetches what's missing, safe to re-run)
python fetch_historical_data.py
```

## Run

```bash
python app.py          # dashboard on port 8008; resumes any templates left `running`
python recordData.py   # separate process: the 14 tick recorders
```

## Data maintenance

```bash
python clearRecordedData.py                 # all symbols, asks to confirm
python clearRecordedData.py BTC ETH          # only these symbols
python clearRecordedData.py BTC --timeframe 5m
python clearRecordedData.py --all --yes      # skip the confirmation prompt
```

Deletes recorded tick JSON files (`data/<SYMBOL>/<5m|15m>/*.json`) only —
never the Bybit CSV cache or `templates.db`. Useful after a tick-recorder
fix, to avoid mixing old/incomplete recordings with clean ones in the Live
Backtest tab's coverage stats.

## Project layout

```
app.py                       Flask server: registers the Templates blueprint,
                              the Backtest/ATR Backtest/Live Backtest routes,
                              and starts the background template manager /
                              pending resolver on startup.
recordData.py                 Standalone tick recorder process (run alongside app.py).
clearRecordedData.py          CLI to delete recorded tick data per symbol/timeframe.
fetch_data.py                  CLI to bulk-populate the Bybit cache from 2026-01-01.
fetch_historical_data.py       CLI to backfill 5m/15m Bybit history back to 2023-01-01.
ecosystem.config.js           PM2 config: rsi-dashboard (app.py) + rsi-recorder (recordData.py).

rsi_backtest/
  bybit_client.py               Paginated Bybit kline fetcher, with retry on
                                 transient network errors.
  data_store.py                 Local CSV cache, fills gaps from Bybit on demand.
  rsi.py                        Wilder RSI.
  atr.py                        Wilder ATR (+ latest_atr for a live preview).
  thresholds.py                 ATR value -> (overbought, oversold) bucket lookup.
  config.json                   The ATR bucket table thresholds.py reads.
  backtest.py                    The no-retry historical backtest engine (fixed OB/OS).
  atr_backtest.py                Same engine, but OB/OS come from each candle's own ATR.

live_backtest/
  engine.py                      Replays recorded tick data to simulate real ladder
                                  fills against real recorded resolutions.

paper_engine/
  topbot_bridge.py               sys.path bridge into topbot; builds a topbot
                                  Config per template row (always paper mode,
                                  max_attempts=1).
  store.py                       SQLite: templates + their trade history.
  manager.py                     One background thread per running template;
                                  window scheduling + transient-error retry.
  resolver.py                    Background thread that keeps re-polling Gamma
                                  for any trade stuck without a resolution.
  routes.py                      Flask blueprint: Templates pages + JSON API.

tick_recorder/
  models.py                      BookTop dataclass.
  clob_ws.py                      Polymarket CLOB "market" websocket client.
  store.py                        JSON-file tick storage (one file per market).
  recorder.py                     Per-(symbol, timeframe) recording loop.
  manager.py                      Spawns one recorder thread per symbol x timeframe.

templates/                     Jinja templates: base.html (shared nav),
                                templates.html, template_trades.html,
                                backtest.html, rsi_backtest.html, live_backtest.html.
static/                        style.css, app.js (backtest), rsi_backtest.js,
                                live_backtest.js, templates.js, template_trades.js.

data/                          Bybit OHLC CSV cache, templates.db, and the
                                tick recorder's data/<SYMBOL>/<5m|15m>/*.json.
```
