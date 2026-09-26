"use strict";
const SID = pathParts()[1];
renderChrome({ active: "review", signalId: SID, crumbs: [[`/signal/${enc(SID)}`, sigLabel(SID)], ["", "Summary & sign-off"]] });
let INV = null;

async function init() { INV = await loadInvestigation(SID, $("#msg")); if (INV) { $("#content").hidden = false; render(); } }

function render() {
  const v = INV, sm = v.summary, so = v.signoff, done = v.status === "completed", r = v.recommendation;
  $("#rec").innerHTML = `<span class="badge b-rule">Rule ${esc(r.ruleset)} v${esc(r.version)} · ${esc(r.rule_id)}</span> <b>${esc(r.recommendation)}</b>
    <span class="hint">(${CATS.map((c) => `${c} ${r.inputs.distribution[c]}`).join(", ")}; ${v.cases.filter((c) => c.override).length} human override(s))</span>`;
  $("#btn-summary").hidden = done;
  $("#btn-summary").textContent = sm ? "Re-draft summary with AI" : "Draft summary with AI";
  $("#summary-box").innerHTML = sm ? `<p><span class="badge b-ai">${esc(sm.label)}</span> <span class="hint">${esc(sm.model_id)} · ${esc(sm.prompt_version)}</span></p>
    <p>Cited cases: ${sm.citations.valid.map((id) => `<a href="${evidenceHref(SID, id)}">${id}</a>`).join(" ") || "none"}</p>
    <p>${sm.citations.invalid.length ? `<span class="badge b-bad">✗ Not in this signal (flagged by guardrail): ${esc(sm.citations.invalid.join(", "))}</span>` : '<span class="badge b-ok">✓ all cited case IDs exist in this signal</span>'}</p>`
    : `<p class="hint">No summary yet. The AI drafts it from the structured facts, statistics and the rule-computed recommendation; it cannot change the recommendation.</p>`;
  $("#signoff-form").hidden = done || !sm;
  if (sm && !done && $("#summary-text").dataset.v !== sm.text) { $("#summary-text").value = sm.text; $("#summary-text").dataset.v = sm.text; }
  $("#signoff-name").value ||= reviewer();
  $("#signoff-box").innerHTML = so ? `<div class="card"><p><span class="badge b-human">✎ Signed off</span> by <b>${esc(so.actor)}</b> at ${esc(so.ts)}</p>
    <p>Decision: <b>${esc(so.decision)}</b> → <b>${esc(so.final_recommendation)}</b>${so.reason ? ` (reason: ${esc(so.reason)})` : ""}</p>
    <p class="hint">Rule recommendation was: ${esc(so.rule_recommendation)}. Summary ${sm?.edited ? "edited by reviewer" : "accepted as drafted"}. Audit hash <code>${esc(so.audit_hash.slice(0, 16))}…</code></p>
    <h3>Final summary</h3><p>${esc(sm?.final_text || "")}</p></div>` : "";
}

$("#btn-summary").addEventListener("click", async (e) => {
  const b = e.target; b.disabled = true; b.textContent = "Drafting…";
  try { INV = await api(`/api/investigations/${enc(SID)}/summary`, { method: "POST" }); render(); announce("Summary drafted"); }
  catch (err) { $("#summary-box").innerHTML = `<p class="error" role="alert">${esc(err.message)}</p>`; }
  b.disabled = false;
});
document.querySelectorAll('input[name="decision"]').forEach((r) => r.addEventListener("change", () => {
  $("#rec-override-fields").hidden = document.querySelector('input[name="decision"]:checked').value !== "override";
}));
$("#signoff-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const actor = $("#signoff-name").value.trim(); setReviewer(actor);
  try {
    INV = await api(`/api/investigations/${enc(SID)}/signoff`, { method: "POST", body: JSON.stringify({
      actor, decision: document.querySelector('input[name="decision"]:checked').value, summary_text: $("#summary-text").value,
      reason: $("#final-reason").value, final_recommendation: $("#final-rec").value }) });
    $("#signoff-error").textContent = ""; render(); announce("Investigation signed off");
  } catch (err) { $("#signoff-error").textContent = err.message; }
});
init();
