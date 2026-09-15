const symbolEl = document.getElementById("symbol");
const timeframeEl = document.getElementById("timeframe");
const fromDateEl = document.getElementById("fromDate");
const toDateEl = document.getElementById("toDate");
const candleCountEl = document.getElementById("candleCount");
const candleRangeEl = document.getElementById("candleRange");
const resolvedCountEl = document.getElementById("resolvedCount");
const metaErrorEl = document.getElementById("metaError");
const runBtn = document.getElementById("runBacktest");
const useFullRangeBtn = document.getElementById("useFullRange");
const summaryPanel = document.getElementById("summaryPanel");
const tradesPanel = document.getElementById("tradesPanel");
const tradesBody = document.getElementById("tradesBody");
const tradesCountEl = document.getElementById("tradesCount");
const errorPanel = document.getElementById("errorPanel");

let lastMeta = null;

function isoToDateStr(iso) {
  return iso ? iso.slice(0, 10) : null;
}

function formatEt(ts) {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/New_York",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).formatToParts(new Date(ts));
  const p = Object.fromEntries(parts.map((x) => [x.type, x.value]));
  return `${p.year}-${p.month}-${p.day} ${p.hour}:${p.minute}`;
}

function fmtMoney(v) {
  if (v === null || v === undefined) return "–";
  const sign = v < 0 ? "-" : "";
  return `${sign}$${Math.abs(v).toFixed(2)}`;
}

async function refreshMeta() {
  metaErrorEl.textContent = "";
  candleCountEl.textContent = "loading…";
  candleRangeEl.textContent = "loading…";
  resolvedCountEl.textContent = "loading…";

  const params = new URLSearchParams({ symbol: symbolEl.value, timeframe: timeframeEl.value });

  try {
    const resp = await fetch(`/api/live-backtest/meta?${params}`);
    const data = await resp.json();
    lastMeta = data;

    candleCountEl.textContent = data.count.toLocaleString();
    resolvedCountEl.textContent = data.resolved_count.toLocaleString();
    candleRangeEl.textContent =
      data.range_from && data.range_to
        ? `${isoToDateStr(data.range_from)} – ${isoToDateStr(data.range_to)}`
        : "no recordings yet";

    applyDateBounds(isoToDateStr(data.range_from), isoToDateStr(data.range_to));
  } catch (err) {
    candleCountEl.textContent = "–";
    candleRangeEl.textContent = "–";
    resolvedCountEl.textContent = "–";
    metaErrorEl.textContent = `(failed to reach server: ${err})`;
  }
}

function applyDateBounds(rangeFrom, rangeTo) {
  for (const el of [fromDateEl, toDateEl]) {
    if (rangeFrom && rangeTo) {
      el.min = rangeFrom;
      el.max = rangeTo;
    } else {
      el.removeAttribute("min");
      el.removeAttribute("max");
    }
  }
}

function useFullRange() {
  if (lastMeta && lastMeta.range_from && lastMeta.range_to) {
    fromDateEl.value = isoToDateStr(lastMeta.range_from);
    toDateEl.value = isoToDateStr(lastMeta.range_to);
  }
}

function renderTrades(trades) {
  tradesBody.innerHTML = "";
  if (trades.length === 0) {
    tradesPanel.hidden = true;
    return;
  }
  const ordered = [...trades].sort((a, b) => b.ts - a.ts);
  tradesCountEl.textContent = `${trades.length.toLocaleString()} decided trades, most recent first`;

  const frag = document.createDocumentFragment();
  ordered.forEach((t) => {
    const tr = document.createElement("tr");
    tr.className = t.won ? "row-win" : "row-loss";
    tr.innerHTML = `
      <td>${formatEt(t.window_start * 1000)}</td>
      <td>${t.rsi.toFixed(2)}</td>
      <td>${t.side}</td>
      <td>${t.filled_shares}</td>
      <td>${fmtMoney(t.cost)}</td>
      <td>${t.resolution}</td>
      <td>${fmtMoney(t.pnl)}</td>
      <td class="result-cell">${t.won ? "Win" : "Loss"}</td>
    `;
    frag.appendChild(tr);
  });
  tradesBody.appendChild(frag);
  tradesPanel.hidden = false;
}

async function runBacktest() {
  errorPanel.hidden = true;
  runBtn.disabled = true;
  runBtn.textContent = "Running…";

  const body = {
    symbol: symbolEl.value,
    timeframe: timeframeEl.value,
    from_date: fromDateEl.value,
    to_date: toDateEl.value,
    rsi_length: document.getElementById("rsiLength").value,
    overbought: document.getElementById("overbought").value,
    oversold: document.getElementById("oversold").value,
  };

  try {
    const resp = await fetch("/api/live-backtest", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.error || "live backtest failed");

    document.getElementById("winRate").textContent = `${data.win_rate.toFixed(2)}%`;
    document.getElementById("pnlSum").textContent = fmtMoney(data.pnl_sum);
    document.getElementById("wins").textContent = data.wins.toLocaleString();
    document.getElementById("losses").textContent = data.losses.toLocaleString();
    document.getElementById("pending").textContent = data.pending.toLocaleString();
    document.getElementById("noRecording").textContent = data.no_recording.toLocaleString();

    summaryPanel.hidden = false;
    renderTrades(data.trades || []);
  } catch (err) {
    errorPanel.textContent = `Live backtest failed: ${err}`;
    errorPanel.hidden = false;
    summaryPanel.hidden = true;
    tradesPanel.hidden = true;
  } finally {
    runBtn.disabled = false;
    runBtn.textContent = "Run live backtest";
  }
}

symbolEl.addEventListener("change", refreshMeta);
timeframeEl.addEventListener("change", refreshMeta);
useFullRangeBtn.addEventListener("click", useFullRange);
runBtn.addEventListener("click", runBacktest);

refreshMeta();
