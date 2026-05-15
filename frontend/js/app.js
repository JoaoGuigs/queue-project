/** Queue Activity Report — dashboard frontend */

const STORAGE_KEY = "queue-report-settings";

/** @type {import('chart.js').Chart | null} */
let dayChart = null;

const $ = (sel) => document.querySelector(sel);

/**
 * Base URL for API calls (no trailing slash).
 * Port 8000: local uvicorn — routes at /reports (no /api).
 * Other ports (e.g. 8081 + Apache): same origin with /api proxy prefix.
 */
function getApiBase() {
  const origin = window.location.origin.replace(/\/$/, "");
  if (window.location.port === "8000") {
    return origin;
  }
  return `${origin}/api`;
}

function getIsoWeek(d = new Date()) {
  const date = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
  const day = date.getUTCDay() || 7;
  date.setUTCDate(date.getUTCDate() + 4 - day);
  const yearStart = new Date(Date.UTC(date.getUTCFullYear(), 0, 1));
  return Math.ceil(((date - yearStart) / 86400000 + 1) / 7);
}

function loadSettings() {
  try {
    return JSON.parse(sessionStorage.getItem(STORAGE_KEY) || "{}");
  } catch {
    return {};
  }
}

function saveSettings() {
  const data = { apiKey: $("#api-key").value };
  sessionStorage.setItem(STORAGE_KEY, JSON.stringify(data));
  showAlert("Chave salva nesta sessão.", "success");
}

function initSettings() {
  const saved = loadSettings();
  $("#api-key").value = saved.apiKey || "";

  const now = new Date();
  $("#year").value = now.getFullYear();
  $("#week").value = getIsoWeek(now);
  $("#month").value = String(now.getMonth() + 1);
}

function parseListInput(value) {
  if (!value?.trim()) return null;
  const items = value
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
  return items.length ? items : null;
}

function buildRequestBody() {
  const periodType = document.querySelector('input[name="period_type"]:checked').value;
  const body = {
    period_type: periodType,
    year: Number($("#year").value),
  };

  if (periodType === "weekly") {
    body.week = Number($("#week").value);
  } else {
    body.month = Number($("#month").value);
  }

  const queues = parseListInput($("#queues").value);
  const agents = parseListInput($("#agents").value);
  if (queues) body.queues = queues;
  if (agents) body.agents = agents;

  return body;
}

function formatDate(iso) {
  return new Date(iso + "T12:00:00").toLocaleDateString("pt-BR", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

function formatDuration(seconds) {
  const s = Math.round(Number(seconds) || 0);
  const m = Math.floor(s / 60);
  const r = s % 60;
  return `${m}:${String(r).padStart(2, "0")}`;
}

function formatNumber(n) {
  return new Intl.NumberFormat("pt-BR").format(n);
}

function showAlert(message, type = "error") {
  const el = $("#alert");
  el.textContent = message;
  el.className = `alert ${type}`;
  el.classList.remove("hidden");
}

function hideAlert() {
  $("#alert").classList.add("hidden");
}

function setLoading(loading) {
  const btn = $("#submit-btn");
  btn.disabled = loading;
  btn.querySelector(".btn-label").textContent = loading ? "Gerando…" : "Gerar relatório";
  btn.querySelector(".spinner").classList.toggle("hidden", !loading);
}

function togglePeriodFields() {
  const isWeekly = document.querySelector('input[name="period_type"]:checked').value === "weekly";
  $(".field-week").classList.toggle("hidden", !isWeekly);
  $(".field-month").classList.toggle("hidden", isWeekly);
  $("#week").required = isWeekly;
}

async function fetchReport(body) {
  const saved = loadSettings();
  const apiBase = getApiBase();
  const apiKey = $("#api-key").value || saved.apiKey;

  if (!apiKey) {
    throw new Error("Informe a chave API em Autenticação e clique em Salvar na sessão.");
  }

  const res = await fetch(`${apiBase}/reports/queue-activity`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-API-Key": apiKey,
    },
    body: JSON.stringify(body),
  });

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const err = await res.json();
      detail = err.detail ?? (Array.isArray(err.detail) ? JSON.stringify(err.detail) : detail);
    } catch {
      /* ignore */
    }
    throw new Error(typeof detail === "string" ? detail : `Erro ${res.status}`);
  }

  return res.json();
}

function renderKpis(summary) {
  const items = [
    { label: "Total de chamadas", value: summary.total_calls, cls: "accent" },
    { label: "Atendidas", value: summary.answered, cls: "success" },
    { label: "Abandonadas", value: summary.abandoned, cls: "danger" },
    { label: "Transferidas", value: summary.transferred },
    { label: "Encaminhadas", value: summary.forwarded },
    { label: "Talk médio", value: formatDuration(summary.avg_talk_time_sec), raw: true },
    { label: "Duração média", value: formatDuration(summary.avg_duration_sec), raw: true },
    {
      label: "CDR sem QUEUEMON",
      value: summary.cdr_linkedids_not_in_queuemon,
      cls: summary.cdr_linkedids_not_in_queuemon > 0 ? "danger" : "",
    },
  ];

  $("#kpi-grid").innerHTML = items
    .map(
      (k) => `
    <article class="kpi-card ${k.cls || ""}">
      <div class="label">${k.label}</div>
      <div class="value">${k.raw ? k.value : formatNumber(k.value)}</div>
    </article>`
    )
    .join("");
}

function renderChart(byDay) {
  const ctx = $("#chart-by-day").getContext("2d");
  const labels = byDay.map((d) => formatDate(d.date));
  const answered = byDay.map((d) => d.answered);
  const abandoned = byDay.map((d) => d.abandoned);

  if (dayChart) dayChart.destroy();

  dayChart = new Chart(ctx, {
    type: "bar",
    data: {
      labels,
      datasets: [
        {
          label: "Atendidas",
          data: answered,
          backgroundColor: "rgba(16, 185, 129, 0.75)",
          borderRadius: 4,
        },
        {
          label: "Abandonadas",
          data: abandoned,
          backgroundColor: "rgba(239, 68, 68, 0.75)",
          borderRadius: 4,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { position: "bottom" },
      },
      scales: {
        x: { stacked: true, grid: { display: false } },
        y: { stacked: true, beginAtZero: true, ticks: { precision: 0 } },
      },
    },
  });
}

function renderSummaryExtra(summary) {
  $("#answer-rate-value").textContent = `${summary.answer_rate_pct.toFixed(1)}%`;
  $("#summary-extra").innerHTML = `
    <li><span>Transferidas</span><strong>${formatNumber(summary.transferred)}</strong></li>
    <li><span>Encaminhadas</span><strong>${formatNumber(summary.forwarded)}</strong></li>
    <li><span>Talk médio</span><strong>${formatDuration(summary.avg_talk_time_sec)}</strong></li>
    <li><span>Duração média</span><strong>${formatDuration(summary.avg_duration_sec)}</strong></li>
    <li><span>CDR órfãos</span><strong>${formatNumber(summary.cdr_linkedids_not_in_queuemon)}</strong></li>
  `;
}

function renderTable(tbody, rows, emptyMsg) {
  if (!rows.length) {
    tbody.innerHTML = `<tr><td colspan="10" class="empty-table">${emptyMsg}</td></tr>`;
    return;
  }
  tbody.innerHTML = rows;
}

function renderQueues(byQueue) {
  const rows = byQueue.map(
    (q) => `
    <tr>
      <td>${escapeHtml(q.queue)}</td>
      <td class="num">${formatNumber(q.total_calls)}</td>
      <td class="num">${formatNumber(q.answered)}</td>
      <td class="num">${formatNumber(q.abandoned)}</td>
      <td class="num">${formatDuration(q.avg_talk_time_sec)}</td>
    </tr>`
  );
  renderTable($("#table-queues tbody"), rows, "Nenhuma fila no período.");
}

function renderAgents(byAgent) {
  const rows = byAgent.map(
    (a) => `
    <tr>
      <td class="num">${escapeHtml(a.agent_id)}</td>
      <td>${escapeHtml(a.agent_name || "—")}</td>
      <td class="num">${formatNumber(a.answered)}</td>
      <td class="num">${formatDuration(a.avg_talk_time_sec)}</td>
    </tr>`
  );
  renderTable($("#table-agents tbody"), rows, "Nenhum agente no período.");
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

function renderReport(data) {
  const periodLabel =
    data.period_type === "weekly"
      ? `Semana · ${formatDate(data.period_start)} — ${formatDate(data.period_end)}`
      : `Mês · ${formatDate(data.period_start)} — ${formatDate(data.period_end)}`;

  $("#period-subtitle").textContent = periodLabel;
  $("#generated-at").textContent = data.generated_at
    ? `Gerado: ${new Date(data.generated_at).toLocaleString("pt-BR")}`
    : "";

  const cacheBadge = $("#cache-badge");
  cacheBadge.classList.toggle("hidden", !data.cached);
  cacheBadge.textContent = data.cached ? "Resposta em cache (10s)" : "";

  renderKpis(data.summary);
  renderSummaryExtra(data.summary);
  renderChart(data.by_day);
  renderQueues(data.by_queue);
  renderAgents(data.by_agent);

  $("#empty-state").classList.add("hidden");
  $("#report").classList.remove("hidden");
}

async function onSubmit(e) {
  e.preventDefault();
  hideAlert();
  setLoading(true);

  try {
    const body = buildRequestBody();
    const data = await fetchReport(body);
    renderReport(data);
  } catch (err) {
    showAlert(err.message || "Falha ao gerar relatório.");
    console.error(err);
  } finally {
    setLoading(false);
  }
}

function init() {
  initSettings();
  togglePeriodFields();

  document.querySelectorAll('input[name="period_type"]').forEach((el) => {
    el.addEventListener("change", togglePeriodFields);
  });

  $("#report-form").addEventListener("submit", onSubmit);
  $("#save-settings").addEventListener("click", saveSettings);
}

document.addEventListener("DOMContentLoaded", init);
