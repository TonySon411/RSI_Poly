const templatesBody = document.getElementById("templatesBody");
const emptyState = document.getElementById("emptyState");
const newTemplateBtn = document.getElementById("newTemplateBtn");
const modalOverlay = document.getElementById("modalOverlay");
const modalTitle = document.getElementById("modalTitle");
const modalCancel = document.getElementById("modalCancel");
const modalSave = document.getElementById("modalSave");
const modalError = document.getElementById("modalError");

const nameEl = document.getElementById("tplName");
const symbolEl = document.getElementById("tplSymbol");
const timeframeEl = document.getElementById("tplTimeframe");
const rsiLengthEl = document.getElementById("tplRsiLength");
const overboughtEl = document.getElementById("tplOverbought");
const oversoldEl = document.getElementById("tplOversold");

let editingId = null;
let templatesCache = [];

function fmtMoney(v) {
  const sign = v < 0 ? "-" : "";
  return `${sign}$${Math.abs(v).toFixed(2)}`;
}

function renderTemplates(templates) {
  templatesCache = templates;
  templatesBody.innerHTML = "";
  emptyState.hidden = templates.length > 0;

  const frag = document.createDocumentFragment();
  templates.forEach((t) => {
    const tr = document.createElement("tr");

    const statusHtml =
      t.status === "running"
        ? '<span class="status-pill status-running">Active (paper)</span>'
        : '<span class="status-pill status-stopped">Stopped</span>';

    const resultHtml =
      t.markets > 0
        ? `<span class="${t.pnl_sum < 0 ? "pnl-neg" : "pnl-pos"}">${fmtMoney(t.pnl_sum)}</span>
           · ${t.markets.toLocaleString()} markets · ${t.win_rate.toFixed(0)}% win`
        : "–";

    const toggleBtn =
      t.status === "running"
        ? `<button class="btn-pill btn-danger" data-action="stop" data-id="${t.id}">Stop</button>`
        : `<button class="btn-pill btn-go" data-action="start" data-id="${t.id}">Start</button>`;

    tr.innerHTML = `
      <td>${escapeHtml(t.name)}</td>
      <td class="config-cell">${escapeHtml(t.config_summary)}</td>
      <td>${statusHtml}</td>
      <td>${resultHtml}</td>
      <td class="actions-cell">
        ${toggleBtn}
        <a class="btn-pill" href="/templates/${t.id}/trades">Trades</a>
        <button class="btn-pill" data-action="edit" data-id="${t.id}">Edit</button>
        <button class="btn-pill btn-danger" data-action="delete" data-id="${t.id}">Delete</button>
      </td>
    `;
    frag.appendChild(tr);
  });
  templatesBody.appendChild(frag);
}

function escapeHtml(s) {
  const div = document.createElement("div");
  div.textContent = s;
  return div.innerHTML;
}

async function fetchTemplates() {
  try {
    const resp = await fetch("/api/templates");
    const data = await resp.json();
    renderTemplates(data);
  } catch (err) {
    templatesBody.innerHTML = `<tr><td colspan="5" class="meta-error">Failed to load templates: ${err}</td></tr>`;
  }
}

function openModal(mode, template) {
  modalError.textContent = "";
  editingId = mode === "edit" ? template.id : null;
  modalTitle.textContent = mode === "edit" ? "Edit template" : "New template";
  modalSave.textContent = mode === "edit" ? "Save changes" : "Save & start";

  if (mode === "edit") {
    nameEl.value = template.name;
    symbolEl.value = template.symbol;
    timeframeEl.value = template.timeframe;
    rsiLengthEl.value = template.rsi_length;
    overboughtEl.value = template.overbought;
    oversoldEl.value = template.oversold;
  } else {
    nameEl.value = "";
    symbolEl.value = "ETH";
    timeframeEl.value = "5m";
    rsiLengthEl.value = 7;
    overboughtEl.value = 86;
    oversoldEl.value = 16;
  }
  modalOverlay.hidden = false;
}

function closeModal() {
  modalOverlay.hidden = true;
  editingId = null;
}

async function saveModal() {
  const body = {
    name: nameEl.value.trim() || `${symbolEl.value} ${timeframeEl.value}`,
    symbol: symbolEl.value,
    timeframe: timeframeEl.value,
    rsi_length: Number(rsiLengthEl.value),
    overbought: Number(overboughtEl.value),
    oversold: Number(oversoldEl.value),
  };

  modalSave.disabled = true;
  try {
    const url = editingId ? `/api/templates/${editingId}` : "/api/templates";
    const method = editingId ? "PUT" : "POST";
    const resp = await fetch(url, {
      method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.error || "save failed");
    closeModal();
    fetchTemplates();
  } catch (err) {
    modalError.textContent = `${err}`;
  } finally {
    modalSave.disabled = false;
  }
}

async function handleAction(action, id) {
  if (action === "edit") {
    const t = templatesCache.find((x) => x.id === id);
    if (t) openModal("edit", t);
    return;
  }
  if (action === "delete") {
    if (!confirm("Delete this template? Its trade history will be removed too.")) return;
    await fetch(`/api/templates/${id}`, { method: "DELETE" });
    fetchTemplates();
    return;
  }
  if (action === "stop" || action === "start") {
    await fetch(`/api/templates/${id}/${action}`, { method: "POST" });
    fetchTemplates();
  }
}

templatesBody.addEventListener("click", (e) => {
  const btn = e.target.closest("[data-action]");
  if (!btn) return;
  handleAction(btn.dataset.action, btn.dataset.id);
});

newTemplateBtn.addEventListener("click", () => openModal("create"));
modalCancel.addEventListener("click", closeModal);
modalSave.addEventListener("click", saveModal);
modalOverlay.addEventListener("click", (e) => {
  if (e.target === modalOverlay) closeModal();
});

fetchTemplates();
setInterval(fetchTemplates, 8000);
