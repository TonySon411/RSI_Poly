"""Flask dashboard for backtesting the topbot RSI ladder strategy against
locally cached Bybit kline data."""

from __future__ import annotations

import datetime as dt
import sys

# topbot's background loop prints status lines containing non-ASCII characters
# (e.g. "->" as a real arrow); Windows' console defaults to cp1252, which can't
# encode them, crashing that window's trade before orders are even placed.
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from flask import Flask, jsonify, render_template, request

from live_backtest.engine import recording_coverage, run_live_backtest
from paper_engine import store as template_store
from paper_engine.resolver import resolver as pending_resolver
from paper_engine.routes import manager as template_manager
from paper_engine.routes import templates_bp
from rsi_backtest.atr import latest_atr
from rsi_backtest.atr_backtest import run_atr_backtest
from rsi_backtest.backtest import run_backtest
from rsi_backtest.config import SYMBOLS, TIMEFRAMES
from rsi_backtest.data_store import cache_bounds, ensure_data, load_range
from rsi_backtest.thresholds import get_thresholds, load_buckets
from tick_recorder.manager import TIMEFRAMES as TICK_TIMEFRAMES

app = Flask(__name__)
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.register_blueprint(templates_bp)

DATA_START = int(dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc).timestamp() * 1000)


def _now_ms() -> int:
    return int(dt.datetime.now(dt.timezone.utc).timestamp() * 1000)


def _date_to_ms(date_str: str, end_of_day: bool = False) -> int:
    d = dt.datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=dt.timezone.utc)
    if end_of_day:
        d = d + dt.timedelta(days=1) - dt.timedelta(milliseconds=1)
    return int(d.timestamp() * 1000)


def _ms_to_date(ms: int) -> str:
    return dt.datetime.fromtimestamp(ms / 1000, tz=dt.timezone.utc).strftime("%Y-%m-%d")


@app.route("/backtest")
def backtest_page():
    return render_template(
        "backtest.html",
        symbols=SYMBOLS,
        timeframes=list(TIMEFRAMES.keys()),
        default_start=_ms_to_date(DATA_START),
        default_end=_ms_to_date(_now_ms()),
        active_tab="backtest",
    )


@app.route("/api/meta")
def api_meta():
    symbol = request.args.get("symbol", SYMBOLS[0])
    timeframe = request.args.get("timeframe", "5m")

    try:
        ensure_data(symbol, timeframe, DATA_START, _now_ms())
    except Exception as exc:  # network/Bybit hiccup: fall back to whatever is cached
        bounds = cache_bounds(symbol, timeframe)
        return jsonify(
            {
                "symbol": symbol,
                "timeframe": timeframe,
                "count": bounds["count"],
                "range_from": _ms_to_date(bounds["min_ts"]) if bounds["min_ts"] else None,
                "range_to": _ms_to_date(bounds["max_ts"]) if bounds["max_ts"] else None,
                "error": str(exc),
            }
        )

    bounds = cache_bounds(symbol, timeframe)
    return jsonify(
        {
            "symbol": symbol,
            "timeframe": timeframe,
            "count": bounds["count"],
            "range_from": _ms_to_date(bounds["min_ts"]) if bounds["min_ts"] else None,
            "range_to": _ms_to_date(bounds["max_ts"]) if bounds["max_ts"] else None,
        }
    )


@app.route("/api/backtest", methods=["POST"])
def api_backtest():
    payload = request.get_json(force=True)

    symbol = payload["symbol"]
    timeframe = payload["timeframe"]
    rsi_length = int(payload["rsi_length"])
    overbought = float(payload["overbought"])
    oversold = float(payload["oversold"])
    from_ms = _date_to_ms(payload["from_date"])
    to_ms = _date_to_ms(payload["to_date"], end_of_day=True)

    try:
        ensure_data(symbol, timeframe, DATA_START, _now_ms())
    except Exception:
        pass  # use whatever is cached locally

    df = load_range(symbol, timeframe, 0, to_ms)
    result = run_backtest(df, from_ms, to_ms, rsi_length, overbought, oversold)
    result["symbol"] = symbol
    result["timeframe"] = timeframe
    return jsonify(result)


@app.route("/rsi-backtest")
def rsi_backtest_page():
    return render_template(
        "rsi_backtest.html",
        symbols=SYMBOLS,
        timeframes=list(TIMEFRAMES.keys()),
        default_start=_ms_to_date(DATA_START),
        default_end=_ms_to_date(_now_ms()),
        buckets=load_buckets(),
        active_tab="rsi_backtest",
    )


@app.route("/api/rsi-thresholds")
def api_rsi_thresholds():
    symbol = request.args.get("symbol", SYMBOLS[0])
    timeframe = request.args.get("timeframe", "5m")
    try:
        atr_length = int(request.args.get("atr_length", 7))
    except ValueError:
        return jsonify({"error": "invalid atr_length"}), 400

    df = load_range(symbol, timeframe, 0, _now_ms())
    atr_value = latest_atr(df, atr_length)

    if atr_value is None:
        return jsonify({"atr": None, "overbought": None, "oversold": None})

    overbought, oversold = get_thresholds(atr_value)
    return jsonify({"atr": round(atr_value, 4), "overbought": overbought, "oversold": oversold})


@app.route("/api/rsi-backtest", methods=["POST"])
def api_rsi_backtest():
    payload = request.get_json(force=True)

    symbol = payload["symbol"]
    timeframe = payload["timeframe"]
    rsi_length = int(payload["rsi_length"])
    atr_length = int(payload.get("atr_length", 7))
    from_ms = _date_to_ms(payload["from_date"])
    to_ms = _date_to_ms(payload["to_date"], end_of_day=True)

    try:
        ensure_data(symbol, timeframe, DATA_START, _now_ms())
    except Exception:
        pass  # use whatever is cached locally

    df = load_range(symbol, timeframe, 0, to_ms)
    result = run_atr_backtest(df, from_ms, to_ms, rsi_length, atr_length)
    result["symbol"] = symbol
    result["timeframe"] = timeframe
    result["atr_length"] = atr_length
    return jsonify(result)


@app.route("/live-backtest")
def live_backtest_page():
    return render_template(
        "live_backtest.html",
        symbols=SYMBOLS,
        timeframes=TICK_TIMEFRAMES,
        default_start=_ms_to_date(DATA_START),
        default_end=_ms_to_date(_now_ms()),
        active_tab="live_backtest",
    )


@app.route("/api/live-backtest/meta")
def api_live_backtest_meta():
    symbol = request.args.get("symbol", SYMBOLS[0])
    timeframe = request.args.get("timeframe", "5m")

    coverage = recording_coverage(symbol, timeframe)
    return jsonify(
        {
            "symbol": symbol,
            "timeframe": timeframe,
            "count": coverage["count"],
            "resolved_count": coverage["resolved_count"],
            "range_from": (
                dt.datetime.fromtimestamp(coverage["range_from"], tz=dt.timezone.utc).isoformat()
                if coverage["range_from"]
                else None
            ),
            "range_to": (
                dt.datetime.fromtimestamp(coverage["range_to"], tz=dt.timezone.utc).isoformat()
                if coverage["range_to"]
                else None
            ),
        }
    )


@app.route("/api/live-backtest", methods=["POST"])
def api_live_backtest():
    payload = request.get_json(force=True)

    symbol = payload["symbol"]
    timeframe = payload["timeframe"]
    rsi_length = int(payload["rsi_length"])
    overbought = float(payload["overbought"])
    oversold = float(payload["oversold"])
    from_ms = _date_to_ms(payload["from_date"])
    to_ms = _date_to_ms(payload["to_date"], end_of_day=True)

    try:
        ensure_data(symbol, timeframe, DATA_START, _now_ms())
    except Exception:
        pass  # use whatever Bybit candles are cached locally (RSI source only)

    df = load_range(symbol, timeframe, 0, to_ms)
    result = run_live_backtest(df, symbol, timeframe, from_ms, to_ms, rsi_length, overbought, oversold)
    result["symbol"] = symbol
    result["timeframe"] = timeframe
    return jsonify(result)


template_store.init_db()
template_manager.resume_all_running()
pending_resolver.start()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8008, debug=False, threaded=True)
