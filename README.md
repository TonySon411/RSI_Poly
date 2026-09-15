# RSI Ladder Backtest Dashboard

Backtests the `topbot` RSI strategy (see its own README for the live-trading
version) against real Bybit history, across every symbol/timeframe you trade
on Polymarket's 5m/15m/1h/4h Up-or-Down markets — with **no retry ladder**:
every RSI signal is one independent window, win or lose.

## Strategy being tested

For each closed candle:
- Compute Wilder RSI(length).
- If RSI > overbought → predict the **next** window resolves **Down**.
- If RSI < oversold → predict the **next** window resolves **Up**.
- Otherwise, no trade that window.

A window resolves **Down** if its close is below its open, **Up** otherwise.
There is no retry/attempt ladder — a miss is simply counted as a loss, unlike
the original "Lota" strategy this was adapted from.

## Data

Historical candles come straight from Bybit's public `linear` kline endpoint
(`BTCUSDT`, `ETHUSDT`, `SOLUSDT`, `XRPUSDT`, `DOGEUSDT`, `HYPEUSDT`, `BNBUSDT`),
timeframes `5m` / `15m` / `1h` / `4h`, from **2026-01-01** to now. Data is
cached locally as CSV under `data/` so repeat backtests don't re-hit the API.

## Setup

```bash
pip install -r requirements.txt

# one-time bulk download of all symbols/timeframes (re-run any time to top up)
python fetch_data.py
```

## Run the dashboard

```bash
python app.py
```

Open http://localhost:8008. Pick a symbol and timeframe, a date range, RSI
length, and overbought/oversold thresholds, then **Run backtest**. The
dashboard also lazily fetches/extends cached data for whatever symbol and
timeframe you select, so `fetch_data.py` is optional — it just pre-warms the
cache so the first click isn't slow.

## Project layout

- `rsi_backtest/bybit_client.py` — paginated Bybit kline fetcher.
- `rsi_backtest/data_store.py` — local CSV cache, fills gaps from Bybit on demand.
- `rsi_backtest/rsi.py` — Wilder RSI.
- `rsi_backtest/backtest.py` — the no-retry backtest engine.
- `app.py` — Flask server + `/api/meta` and `/api/backtest` endpoints.
- `templates/`, `static/` — the dashboard UI.
- `fetch_data.py` — CLI to bulk-populate the cache.
