const form = document.querySelector("#logForm");
const logsBody = document.querySelector("#logsBody");
const riskBadge = document.querySelector("#riskBadge");
const formStatus = document.querySelector("#formStatus");
const summary = document.querySelector("#summary");
const refreshButton = document.querySelector("#refreshButton");
const LOGS_ENDPOINT = "/health-logs";
const RISK_ENDPOINT = "/health-logs/risk";

const riskClass = {
  "低": "risk-low",
  "中": "risk-mid",
  "高": "risk-high",
};

function today() {
  return new Date().toISOString().slice(0, 10);
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.error || "API 發生錯誤");
  }
  return data;
}

function setRiskBadge(level) {
  riskBadge.className = `risk-badge ${riskClass[level] || "risk-mid"}`;
  riskBadge.textContent = level ? `${level}風險` : "尚無資料";
}

function riskChip(level) {
  const cls = riskClass[level] || "risk-mid";
  return `<span class="chip ${cls}">${level}</span>`;
}

function renderLogs(logs) {
  logsBody.innerHTML = logs
    .map(
      (log) => `
        <tr>
          <td>${log.log_date}</td>
          <td>${log.sleep_hours} 小時</td>
          <td>${log.steps.toLocaleString()}</td>
          <td>${log.mood_score}</td>
          <td>${riskChip(log.risk_level)}</td>
          <td><button class="delete" data-id="${log.id}" type="button">刪除</button></td>
        </tr>
      `
    )
    .join("");
}

function renderSummary(rows) {
  const order = ["低", "中", "高"];
  const byLevel = Object.fromEntries(rows.map((row) => [row.risk_level, row.total]));
  summary.innerHTML = order
    .map((level) => `<span>${level}風險 ${byLevel[level] || 0} 筆</span>`)
    .join("");
}

async function load() {
  const [logs, risk] = await Promise.all([
    api(LOGS_ENDPOINT),
    api(RISK_ENDPOINT),
  ]);
  renderLogs(logs);
  setRiskBadge(risk.risk_level);
  renderSummary(risk.summary);
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const payload = Object.fromEntries(new FormData(form).entries());
  payload.sleep_hours = Number(payload.sleep_hours);
  payload.steps = Number(payload.steps);
  payload.mood_score = Number(payload.mood_score);

  try {
    const saved = await api(LOGS_ENDPOINT, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    formStatus.textContent = `已儲存，判定為${saved.risk_level}風險。`;
    form.reset();
    form.elements.log_date.value = today();
    await load();
  } catch (error) {
    formStatus.textContent = error.message;
  }
});

logsBody.addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-id]");
  if (!button) return;
  await api(`${LOGS_ENDPOINT}/${button.dataset.id}`, { method: "DELETE" });
  await load();
});

refreshButton.addEventListener("click", load);
form.elements.log_date.value = today();
load().catch((error) => {
  formStatus.textContent = error.message;
});
