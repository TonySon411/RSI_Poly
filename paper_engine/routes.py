"""Flask blueprint: Templates tab pages + JSON API."""

from __future__ import annotations

from flask import Blueprint, jsonify, render_template, request

from . import store
from .manager import TemplateManager
from .topbot_bridge import SYMBOLS, TIMEFRAME_LABELS, TIMEFRAMES, config_summary

templates_bp = Blueprint("templates_bp", __name__)
manager = TemplateManager()

VALID_TIMEFRAMES = set(TIMEFRAMES.keys())
VALID_SYMBOLS = set(SYMBOLS)


def _serialize(row: dict) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "symbol": row["symbol"],
        "timeframe": row["timeframe"],
        "rsi_length": row["rsi_length"],
        "overbought": row["overbought"],
        "oversold": row["oversold"],
        "status": row["status"],
        "config_summary": config_summary(row),
        "pnl_sum": round(row["pnl_sum"], 2),
        "markets": row["markets"],
        "wins": row["wins"],
        "losses": row["losses"],
        "win_rate": round(row["win_rate"], 1) if row["win_rate"] is not None else None,
    }


def _parse_template_payload(payload: dict, *, partial: bool) -> dict:
    fields: dict = {}

    def _get(key):
        if key in payload:
            return payload[key]
        if partial:
            return None
        raise KeyError(key)

    if "name" in payload or not partial:
        fields["name"] = str(_get("name") or "Untitled").strip() or "Untitled"
    if "symbol" in payload or not partial:
        symbol = str(_get("symbol")).upper()
        if symbol not in VALID_SYMBOLS:
            raise ValueError(f"invalid symbol: {symbol}")
        fields["symbol"] = symbol
    if "timeframe" in payload or not partial:
        timeframe = str(_get("timeframe"))
        if timeframe not in VALID_TIMEFRAMES:
            raise ValueError(f"invalid timeframe: {timeframe}")
        fields["timeframe"] = timeframe
    if "rsi_length" in payload or not partial:
        fields["rsi_length"] = int(_get("rsi_length"))
    if "overbought" in payload or not partial:
        fields["overbought"] = float(_get("overbought"))
    if "oversold" in payload or not partial:
        fields["oversold"] = float(_get("oversold"))

    return fields


@templates_bp.route("/")
def templates_page():
    return render_template(
        "templates.html",
        symbols=SYMBOLS,
        timeframes=list(TIMEFRAMES.keys()),
        timeframe_labels=TIMEFRAME_LABELS,
        active_tab="templates",
    )


@templates_bp.route("/templates/<template_id>/trades")
def template_trades_page(template_id):
    row = store.get_template(template_id)
    if row is None:
        return "Template not found", 404
    return render_template("template_trades.html", template=row, active_tab="templates")


@templates_bp.route("/api/templates", methods=["GET"])
def api_list_templates():
    return jsonify([_serialize(r) for r in store.list_templates()])


@templates_bp.route("/api/templates", methods=["POST"])
def api_create_template():
    payload = request.get_json(force=True)
    try:
        fields = _parse_template_payload(payload, partial=False)
    except (KeyError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 400

    row = store.create_template(**fields)
    manager.start(row["id"])
    return jsonify(_serialize(store.get_template_with_stats(row["id"]))), 201


@templates_bp.route("/api/templates/<template_id>", methods=["PUT"])
def api_update_template(template_id):
    row = store.get_template(template_id)
    if row is None:
        return jsonify({"error": "not found"}), 404

    payload = request.get_json(force=True)
    try:
        fields = _parse_template_payload(payload, partial=True)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    was_running = row["status"] == "running"
    if was_running:
        manager.stop(template_id)
    store.update_template(template_id, **fields)
    if was_running:
        manager.start(template_id)

    return jsonify(_serialize(store.get_template_with_stats(template_id)))


@templates_bp.route("/api/templates/<template_id>/start", methods=["POST"])
def api_start_template(template_id):
    if store.get_template(template_id) is None:
        return jsonify({"error": "not found"}), 404
    manager.start(template_id)
    return jsonify(_serialize(store.get_template_with_stats(template_id)))


@templates_bp.route("/api/templates/<template_id>/stop", methods=["POST"])
def api_stop_template(template_id):
    if store.get_template(template_id) is None:
        return jsonify({"error": "not found"}), 404
    manager.stop(template_id)
    return jsonify(_serialize(store.get_template_with_stats(template_id)))


@templates_bp.route("/api/templates/<template_id>", methods=["DELETE"])
def api_delete_template(template_id):
    manager.stop(template_id)
    store.delete_template(template_id)
    return jsonify({"ok": True})


@templates_bp.route("/api/templates/<template_id>/trades")
def api_template_trades(template_id):
    row = store.get_template_with_stats(template_id)
    if row is None:
        return jsonify({"error": "not found"}), 404
    return jsonify({"template": _serialize(row), "trades": store.list_trades(template_id)})
