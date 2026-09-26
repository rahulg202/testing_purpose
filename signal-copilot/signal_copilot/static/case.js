"use strict";
const [, SID, , CID] = pathParts();
renderChrome({ active: "case", signalId: SID, crumbs: [[`/signal/${enc(SID)}`, sigLabel(SID)], ["", CID]] });
const LABELS = { time_to_onset: "Time to onset (days)", temporal_relationship: "Temporal relationship", dechallenge: "Dechallenge", rechallenge: "Rechallenge" };
let INV = null, CASE = null;

function jumpLink(span, label = "show evidence") {
  return `<a href="?s=${span[0]}&e=${span[1]}" data-s="${span[0]}" data-e="${span[1]}">${label}</a>`;
}
function factItem(label, f) {
  if (f.status === "verified") return `<li><span class="badge b-ai">AI · ✓ verified</span> <b>${esc(label)}:</b> ${esc(f.value)} ${jumpLink(f.span)}</li>`;
  if (f.status === "unverified") return `<li><span class="badge b-bad">AI · ✗ unverified → unknown</span> <b>${esc(label)}:</b> unknown
    <span class="hint">(model claimed “${esc(f.rejected_value)}” with ${f.rejected_quote ? `quote “${esc(f.rejected_quote)}”, which is not in the source` : "no quote"}; rejected by system guardrail)</span></li>`;
  return `<li><span class="badge b-unk">AI · not stated</span> <b>${esc(label)}:</b> unknown <span class="hint">(no evidence to highlight)</span></li>`;
}

async function init() {
  INV = await loadInvestigation(SID, $("#case-detail")); if (!INV) return;
  const idx = INV.cases.findIndex((c) => c.report_id === CID);
  if (idx < 0) { $("#case-detail").innerHTML = `<p class="card error" role="alert">Case ${esc(CID)} is not in this signal.</p>`; return; }
  CASE = INV.cases[idx];
  const prev = INV.cases[idx - 1], next = INV.cases[idx + 1];
  $("#pager").innerHTML = `${prev ? `<a href="${evidenceHref(SID, prev.report_id)}">← ${prev.report_id}</a>` : "<span></span>"}
    <span class="hint">Case ${idx + 1} of ${INV.cases.length}</span>
    ${next ? `<a href="${evidenceHref(SID, next.report_id)}">${next.report_id} →</a>` : "<span></span>"}`;
  render();
  const p = new URLSearchParams(location.search);
  if (p.has("s")) highlight([+p.get("s"), +p.get("e")]);
}

function render() {
  const c = CASE, f = c.facts, done = INV.status === "completed";
  let facts;
  if (!f) facts = `<p class="error" role="alert">Extraction failed: ${esc(c.error)}. Nothing from the AI was accepted for this case.</p>`;
  else facts = `<ul class="facts">${Object.keys(LABELS).map((k) => factItem(LABELS[k], f[k])).join("")}
    ${f.alternative_causes.map((a) => `<li><span class="badge b-ai">AI · ✓ verified</span> <b>Alternative cause:</b> ${esc(a.cause)} ${jumpLink(a.span)}</li>`).join("")}
    ${(f.excluded_causes || []).map((a) => `<li><span class="badge b-ai">AI · ✓ verified</span>${a.reclassified_by ? ' <span class="badge b-rule">⚙ reclassified by negation guardrail</span>' : ""} <b>Ruled out:</b> ${esc(a.cause)} ${jumpLink(a.span)}</li>`).join("")}
    ${f.rejected_alternative_causes.map((a) => `<li><span class="badge b-bad">AI · ✗ unverified, dropped</span> <b>Cause:</b> ${esc(a.cause)}</li>`).join("")}
    ${(f.malformed_items || []).length ? `<li><span class="badge b-bad">AI · ✗ malformed, dropped</span> ${f.malformed_items.length} empty list item(s) removed by schema guardrail</li>` : ""}
    ${f.data_gaps.length ? `<li><span class="badge b-ai">AI</span> <b>Data gaps:</b> ${esc(f.data_gaps.join("; "))}</li>` : ""}</ul>`;

  $("#case-detail").innerHTML = `
    <div class="split">
      <section class="card" aria-labelledby="facts-h">
        <h2 id="facts-h">${esc(c.report_id)} <small>${c.age}${c.sex} · ${c.serious ? "serious" : "non-serious"} · ${esc(c.country)} · received ${esc(c.received_date)}${c.from_cache ? " · replayed from cache" : ""}</small></h2>
        <h3>Extracted facts</h3>${facts}
        <h3>Causality</h3>
        <p><span class="badge b-rule">⚙ Rule ${esc(c.rule.ruleset)} v${esc(c.rule.version)} · ${esc(c.rule.rule_id)}</span> <b>${esc(c.rule.category)}</b><br><span class="hint">${esc(c.rule.explanation)}</span></p>
        ${c.override ? `<p><span class="badge b-human">✎ Human override</span> <b>${esc(c.override.category)}</b> by ${esc(c.override.actor)}: “${esc(c.override.reason)}”
          ${done ? "" : '<button type="button" id="btn-clear-ov">Revert to rule</button>'}</p>` : ""}
      </section>
      <section class="card" aria-labelledby="narr-h">
        <h3 id="narr-h">Source narrative</h3>
        <div class="narrative" id="narrative" tabindex="0" aria-labelledby="narr-h">${esc(c.narrative)}</div>
        <p class="hint">Evidence is highlighted by the character offsets stored when the guardrail verified the quote.</p>
        ${done ? `<p class="hint">Investigation is signed off; overrides are locked.</p>` : `
        <form id="ov-form" class="stack" aria-labelledby="ov-h">
          <h3 id="ov-h">Override causality</h3>
          <label for="ov-cat">Category</label>
          <select id="ov-cat" style="width:auto">${CATS.map((k) => `<option ${k === c.effective_category ? "selected" : ""}>${k}</option>`).join("")}</select>
          <label for="ov-reason">Reason (required)</label><input id="ov-reason" type="text" required>
          <label for="ov-actor">Reviewer name (required)</label><input id="ov-actor" type="text" required value="${esc(reviewer())}">
          <button type="submit" class="primary">Apply override & recompute recommendation</button>
          <p class="error" id="ov-err" role="alert"></p><p id="ov-ok" role="status"></p>
        </form>`}
      </section>
    </div>`;
  $("#ov-form")?.addEventListener("submit", doOverride);
  $("#btn-clear-ov")?.addEventListener("click", async () => {
    INV = await api(`/api/investigations/${enc(SID)}/cases/${enc(CID)}/override?actor=${enc(reviewer() || "reviewer")}`, { method: "DELETE" });
    CASE = INV.cases.find((x) => x.report_id === CID); render();
  });
}

// Highlight by stored character offsets, never by re-searching text (Req 4a.1)
function highlight([s, e]) {
  const t = CASE.narrative;
  if (!(s >= 0 && e > s && e <= t.length)) return;
  $("#narrative").innerHTML = `${esc(t.slice(0, s))}<mark id="ev" tabindex="-1" aria-label="Evidence from case ${esc(CID)}, characters ${s} to ${e}">${esc(t.slice(s, e))}</mark>${esc(t.slice(e))}`;
  const mk = $("#ev"); mk.scrollIntoView({ block: "center", behavior: "smooth" }); mk.focus({ preventScroll: true });
  announce(`Showing evidence from case ${CID}: ${t.slice(s, e)}`);
}
$("#case-detail").addEventListener("click", (e) => {
  const a = e.target.closest("a[data-s]"); if (!a) return;
  e.preventDefault(); history.replaceState(null, "", a.getAttribute("href")); highlight([+a.dataset.s, +a.dataset.e]);
});

async function doOverride(ev) {
  ev.preventDefault();
  const actor = $("#ov-actor").value.trim(); setReviewer(actor);
  try {
    INV = await api(`/api/investigations/${enc(SID)}/cases/${enc(CID)}/override`, {
      method: "POST", body: JSON.stringify({ category: $("#ov-cat").value, reason: $("#ov-reason").value, actor }) });
    CASE = INV.cases.find((x) => x.report_id === CID); render();
    $("#ov-ok").textContent = `Override saved. Signal recommendation is now: ${INV.recommendation.recommendation}`;
    announce($("#ov-ok").textContent);
  } catch (e) { $("#ov-err").textContent = e.message; }
}
init();
