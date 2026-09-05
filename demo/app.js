"use strict";

const byId = (id) => document.getElementById(id);

function renderTrace(evidence, requestId) {
  const spans = evidence.spans.filter((span) => span.attributes["request.id"] === requestId);
  const origin = Math.min(...spans.map((span) => span.start_ms));
  const end = Math.max(...spans.map((span) => span.start_ms + span.duration_ms));
  const total = Math.max(1, end - origin);
  const rows = spans.map((span) => {
    const row = document.createElement("tr");
    const name = document.createElement("td");
    name.textContent = span.name;
    const time = document.createElement("td");
    time.textContent = `${span.duration_ms.toFixed(2)} ms`;
    const timeline = document.createElement("td");
    const track = document.createElement("div");
    track.className = "track";
    track.setAttribute("aria-hidden", "true");
    const bar = document.createElement("div");
    bar.className = `bar${span.status === "ERROR" ? " error" : ""}`;
    bar.style.left = `${100 * (span.start_ms - origin) / total}%`;
    bar.style.width = `${100 * span.duration_ms / total}%`;
    track.append(bar);
    timeline.append(track);
    row.append(name, time, timeline);
    return row;
  });
  byId("spans").replaceChildren(...rows);
  byId("request-label").textContent = `request_id: ${requestId}`;
  document.querySelectorAll("#trace-selector button").forEach((button) => {
    button.setAttribute("aria-pressed", String(button.dataset.requestId === requestId));
  });
}

async function main() {
  const response = await fetch("evidence.json");
  if (!response.ok) throw new Error("Evidência indisponível");
  const evidence = await response.json();
  if (evidence.data_kind !== "synthetic" || evidence.blocked_connections !== 2) {
    throw new Error("Formato de evidência inválido");
  }
  const metrics = [
    ["Conexões realmente bloqueadas", evidence.blocked_connections],
    ["Unidades no saldo final", evidence.final_stock],
    ["Vendas confirmadas", evidence.persisted_sales],
    ["Movimentações de saída", evidence.sale_stock_movements],
  ];
  byId("summary").replaceChildren(...metrics.map(([label, value]) => {
    const row = document.createElement("div");
    row.className = "proof-row";
    const title = document.createElement("span");
    title.textContent = label;
    const number = document.createElement("strong");
    number.textContent = String(value);
    row.append(title, number);
    return row;
  }));
  byId("database").textContent = `PostgreSQL ${evidence.postgres_version}`;
  if (/^https:\/\/github\.com\/jhonwictordev\/stockflow-api\/actions\/runs\/\d+$/.test(evidence.run_url)) {
    byId("run-link").href = evidence.run_url;
    byId("run-link").hidden = false;
  }
  byId("provenance").textContent = `Execução: ${new Date(evidence.generated_at).toLocaleDateString("pt-BR")} · commit ${evidence.commit.slice(0, 7)}`;
  for (const result of evidence.responses) {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = `${result.request_id.endsWith("a") ? "Compra A" : "Compra B"} · HTTP ${result.status_code}`;
    button.dataset.requestId = result.request_id;
    button.addEventListener("click", () => renderTrace(evidence, result.request_id));
    byId("trace-selector").append(button);
  }
  renderTrace(evidence, evidence.responses.find((result) => result.status_code === 201).request_id);
}

main().catch(() => {
  byId("summary").textContent = "Não foi possível carregar as evidências. Recarregue a página ou consulte a execução no repositório.";
  byId("summary").className = "error-message";
});
