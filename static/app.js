const symbolEl = document.getElementById("symbol");
const timeframeEl = document.getElementById("timeframe");
const fromDateEl = document.getElementById("fromDate");
const toDateEl = document.getElementById("toDate");
const candleCountEl = document.getElementById("candleCount");
const candleRangeEl = document.getElementById("candleRange");
const metaErrorEl = document.getElementById("metaError");
const runBtn = document.getElementById("runBacktest");
const useFullRangeBtn = document.getElementById("useFullRange");
const summaryPanel = document.getElementById("summaryPanel");
const tradesPanel = document.getElementById("tradesPanel");
const tradesBody = document.getElementById("tradesBody");
const tradesCountEl = document.getElementById("tradesCount");
const errorPanel = document.getElementById("errorPanel");

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

let lastMeta = null;

async function refreshMeta() {
  metaErrorEl.textContent = "";
  candleCountEl.textContent = "loading…";
  candleRangeEl.textContent = "loading…";

  const params = new URLSearchParams({
    symbol: symbolEl.value,
    timeframe: timeframeEl.value,
  });

  try {
    const resp = await fetch(`/api/meta?${params}`);
    const data = await resp.json();
    lastMeta = data;

    candleCountEl.textContent = data.count.toLocaleString();
    candleRangeEl.textContent =
      data.range_from && data.range_to ? `${data.range_from} – ${data.range_to}` : "no data cached yet";

    if (data.error) {
      metaErrorEl.textContent = `(fetch warning: ${data.error})`;
    }

    applyDateBounds(data.range_from, data.range_to);
  } catch (err) {
    candleCountEl.textContent = "–";
    candleRangeEl.textContent = "–";
    metaErrorEl.textContent = `(failed to reach server: ${err})`;
  }
}

function applyDateBounds(rangeFrom, rangeTo) {
  for (const el of [fromDateEl, toDateEl]) {
    if (rangeFrom && rangeTo) {
      el.min = rangeFrom;
      el.max = rangeTo;
      // clamp any out-of-range value (e.g. left over from a previous symbol) into bounds
      if (el.value && el.value < rangeFrom) el.value = rangeFrom;
      if (el.value && el.value > rangeTo) el.value = rangeTo;
    } else {
      el.removeAttribute("min");
      el.removeAttribute("max");
    }
  }
}

function useFullRange() {
  if (lastMeta && lastMeta.range_from && lastMeta.range_to) {
    fromDateEl.value = lastMeta.range_from;
    toDateEl.value = lastMeta.range_to;
  }
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
    const resp = await fetch("/api/backtest", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await resp.json();

    if (!resp.ok) {
      throw new Error(data.error || "backtest failed");
    }

    document.getElementById("winRate").textContent = `${data.win_rate.toFixed(2)}%`;
    document.getElementById("totalSignals").textContent = data.total_signals.toLocaleString();
    document.getElementById("wins").textContent = data.wins.toLocaleString();
    document.getElementById("losses").textContent = data.losses.toLocaleString();
    document.getElementById("incomplete").textContent = data.incomplete.toLocaleString();

    summaryPanel.hidden = false;
    renderTrades(data.trades || []);
  } catch (err) {
    errorPanel.textContent = `Backtest failed: ${err}`;
    errorPanel.hidden = false;
    summaryPanel.hidden = true;
    tradesPanel.hidden = true;
  } finally {
    runBtn.disabled = false;
    runBtn.textContent = "Run backtest";
  }
}

function renderTrades(trades) {
  tradesBody.innerHTML = "";

  if (trades.length === 0) {
    tradesPanel.hidden = true;
    return;
  }

  // newest first
  const ordered = [...trades].sort((a, b) => b.ts - a.ts);
  tradesCountEl.textContent = `${trades.length.toLocaleString()} trades, most recent first`;

  const frag = document.createDocumentFragment();
  ordered.forEach((t, idx) => {
    const tr = document.createElement("tr");
    tr.className = t.win ? "row-win" : "row-loss";
    tr.innerHTML = `
      <td>${trades.length - idx}</td>
      <td>${formatEt(t.ts)}</td>
      <td>${t.rsi.toFixed(2)}</td>
      <td>${t.prediction}</td>
      <td>${t.actual}</td>
      <td class="result-cell">${t.win ? "Win" : "Loss"}</td>
    `;
    frag.appendChild(tr);
  });
  tradesBody.appendChild(frag);
  tradesPanel.hidden = false;
}

symbolEl.addEventListener("change", refreshMeta);
timeframeEl.addEventListener("change", refreshMeta);
useFullRangeBtn.addEventListener("click", useFullRange);
runBtn.addEventListener("click", runBacktest);

refreshMeta();
