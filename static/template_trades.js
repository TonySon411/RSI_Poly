const tradesBody = document.getElementById("tradesBody");
const tradesCountEl = document.getElementById("tradesCount");

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

function escapeAttr(s) {
  const div = document.createElement("div");
  div.textContent = s;
  return div.innerHTML.replace(/"/g, "&quot;");
}

function resultCell(t) {
  if (t.error) return `<span class="pnl-neg" title="${escapeAttr(t.error)}">Error ⓘ</span>`;
  if (t.skipped) return '<span class="desc">Skip</span>';
  if (t.won === 1) return '<span class="pnl-pos">Win</span>';
  if (t.won === 0) return '<span class="pnl-neg">Loss</span>';
  return '<span class="desc">Pending</span>';
}

async function load() {
  const resp = await fetch(`/api/templates/${window.TEMPLATE_ID}/trades`);
  const data = await resp.json();
  const t = data.template;

  document.getElementById("pnlSum").textContent = fmtMoney(t.pnl_sum);
  document.getElementById("marketsCount").textContent = t.markets.toLocaleString();
  document.getElementById("winRate").textContent = t.win_rate !== null ? `${t.win_rate.toFixed(1)}%` : "–";
  document.getElementById("wins").textContent = t.wins.toLocaleString();
  document.getElementById("losses").textContent = t.losses.toLocaleString();
  document.getElementById("configSummary").textContent = t.config_summary;

  const trades = data.trades;
  tradesCountEl.textContent = `${trades.length.toLocaleString()} windows, most recent first`;
  tradesBody.innerHTML = "";

  const frag = document.createDocumentFragment();
  trades.forEach((row) => {
    const tr = document.createElement("tr");
    const whenMs = row.window_start ? row.window_start * 1000 : Date.parse(row.ts);
    tr.innerHTML = `
      <td>${formatEt(whenMs)}</td>
      <td>${row.rsi !== null && row.rsi !== undefined ? row.rsi.toFixed(2) : "–"}</td>
      <td>${row.side || "–"}</td>
      <td>${row.filled_shares !== null && row.filled_shares !== undefined ? row.filled_shares : "–"}</td>
      <td>${fmtMoney(row.cost)}</td>
      <td>${row.resolution || "–"}</td>
      <td>${fmtMoney(row.pnl)}</td>
      <td>${resultCell(row)}</td>
    `;
    frag.appendChild(tr);
  });
  tradesBody.appendChild(frag);
}

load();
setInterval(load, 8000);
