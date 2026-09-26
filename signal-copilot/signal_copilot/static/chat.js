"use strict";
const SID = pathParts()[1];
renderChrome({ active: "chat", signalId: SID, crumbs: [[`/signal/${enc(SID)}`, sigLabel(SID)], ["", "Ask the evidence"]] });

async function init() {
  const inv = await loadInvestigation(SID, $("#msg")); if (!inv) return;
  $("#content").hidden = false;
  const qs = ["Which cases had a positive rechallenge?", "What alternative causes were reported?", "How soon after starting the drug did symptoms begin?", "What is the approved dose for children?"];
  $("#suggest").innerHTML = qs.map((q) => `<button type="button">${esc(q)}</button>`).join("");
  api(`/api/investigations/${enc(SID)}/kb`).then((k) => {
    $("#kb").textContent = `Knowledge base: ${k.cases} cases · ${k.summary_vectors} summary vectors · ${k.chunks} evidence chunks`;
  }).catch(() => {});
}
$("#suggest").addEventListener("click", (e) => { if (e.target.tagName === "BUTTON") { $("#chat-q").value = e.target.textContent; $("#chat-form").requestSubmit(); } });
$("#chat-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const q = $("#chat-q").value.trim(); if (!q) return;
  const log = $("#chat-log"); $("#chat-q").value = "";
  log.insertAdjacentHTML("beforeend", `<div class="msg q">${esc(q)}</div><div class="msg a spinner" id="pending">Retrieving evidence</div>`);
  try {
    const r = await api(`/api/investigations/${enc(SID)}/chat`, { method: "POST", body: JSON.stringify({ question: q, actor: reviewer() || "reviewer" }) });
    const g = { grounded: '<span class="badge b-ok">✓ grounded: citations verified</span>', no_evidence: '<span class="badge b-unk">No supporting evidence</span>', unsupported: '<span class="badge b-bad">⚠ unsupported: no verifiable citation, do not rely on this</span>' }[r.grounding];
    $("#pending").outerHTML = `<div class="msg a"><p>${esc(r.answer)}</p>${g}
      ${r.citations.length ? `<ol class="cites">${r.citations.map((c) => `<li><a href="${evidenceHref(SID, c.case_id, c.span)}">${c.case_id}</a> “${esc(c.quote)}”</li>`).join("")}</ol>` : ""}
      ${r.rejected_citations.length ? `<p class="hint">${r.rejected_citations.length} citation(s) stripped by system guardrail: ${esc([...new Set(r.rejected_citations.map((x) => x.reason))].join("; "))}</p>` : ""}
      <p class="hint">Retrieved ${r.retrieval.chunk_ids.length} chunks from ${r.retrieval.cases.length} cases (best relevance ${r.retrieval.best_score}) · ${esc(r.prompt_version)}</p></div>`;
  } catch (err) { $("#pending").outerHTML = `<div class="msg a error" role="alert">${esc(err.message)}</div>`; }
  log.scrollTop = log.scrollHeight;
});
init();
