"use strict";
const SID = pathParts()[1];
renderChrome({ active: "overview", signalId: SID, crumbs: [[`/signal/${enc(SID)}`, sigLabel(SID)]] });
let INV = null;

async function init() {
  try { INV = await api(`/api/investigations/${enc(SID)}`); render(); }
  catch (e) {
    if (e.status !== 404) { $("#inv-progress").innerHTML = `<p class="card error" role="alert">${esc(e.message)}</p>`; return; }
    $("#inv-h").textContent = `Investigation: ${sigLabel(SID)}`;
    $("#inv-progress").innerHTML = `<div class="card"><p>Not investigated yet.</p><button type="button" class="primary" id="btn-run">Run investigation</button></div>`;
    $("#btn-run").addEventListener("click", run);
  }
}

async function run() {
  $("#inv-actions").innerHTML = "";
  $("#inv-progress").innerHTML = `<p class="card spinner">The AI is reading every case narrative in parallel (temperature 0, fixed output schema), guardrails are verifying each quote, rules are assigning causality</p>`;
  try { INV = await api(`/api/signals/${enc(SID)}/investigate`, { method: "POST" }); render(); announce("Investigation complete"); }
  catch (e) { $("#inv-progress").innerHTML = `<p class="card error" role="alert">Investigation failed: ${esc(e.message)}</p>`; }
}

function render() {
  const v = INV, m = v.metrics, done = v.status === "completed";
  $("#inv-h").innerHTML = `Investigation: ${esc(v.stats.drug)} + ${esc(v.stats.event)} <small>${done ? "✔ signed off" : "in review"}</small>`;
  $("#inv-actions").innerHTML = done ? "" : `<button type="button" id="btn-rerun">Re-run (replays from cache)</button>`;
  $("#btn-rerun")?.addEventListener("click", run);
  $("#inv-progress").innerHTML = v.stats.is_signal ? "" : `<p class="card"><span class="badge b-unk">Not a statistical signal</span> This pair does not meet the Evans criteria. This is an ad-hoc investigation; the same rules apply.</p>`;
  $("#content").hidden = false;
  const metric = (val, label) => `<div class="metric"><b>${val}</b><span>${label}</span></div>`;
  $("#metrics").innerHTML = [
    metric(m.cases_processed, "cases processed"), metric(`${m.ai_seconds}s`, "AI processing time"),
    metric(m.llm_calls, "new LLM calls"), metric(m.cache_hits, "cache replays"),
    metric(m.quotes_verified, "quotes verified"), metric(m.quotes_rejected, "claims rejected by guardrail"),
    metric(m.extraction_failures, "extraction failures"),
    metric(`~${Math.round(m.manual_minutes_saved_estimate / 6) / 10} h`, `manual time saved (assumes ${m.minutes_per_case_assumption} min/case)`),
  ].join("");
  const r = v.recommendation, i = r.inputs;
  $("#recommendation").innerHTML = `
    <h3>Recommendation <span class="badge b-rule">Rule ${esc(r.ruleset)} v${esc(r.version)} · ${esc(r.rule_id)}</span></h3>
    <p class="big">${esc(r.recommendation)}</p>
    <p>Causality distribution (incl. human overrides): ${CATS.map((c) => `${c}: ${i.distribution[c]}`).join(" · ")}</p>
    <p class="hint">Inputs: PRR ${i.prr}, signal=${i.is_signal}, supportive share ${i.supportive_share}, unlikely share ${i.unlikely_share}, unassessable share ${i.unassessable_share}.
    Thresholds: supportive ≥ ${r.thresholds.min_supportive_share}, unlikely ≥ ${r.thresholds.min_unlikely_share}, unassessable ≤ ${r.thresholds.max_unassessable_share}. Computed by a deterministic rule, never by the AI.</p>
    ${done ? `<p><span class="badge b-human">✎ Signed off by ${esc(v.signoff.actor)}</span> Final: <b>${esc(v.signoff.final_recommendation)}</b></p>`
      : `<a class="button primary" href="/signal/${enc(SID)}/review">Go to summary & sign-off →</a>`}`;
  renderCases();
}

const fv = (f) => (f == null ? "—" : f.status === "unverified" ? "unverified" : (f.value ?? "unknown"));
function renderCases() {
  const flt = $("#case-filter").value;
  const rows = INV.cases.filter((c) => !flt || (flt === "issues" ? (c.error || c.guardrail.quotes_rejected) : flt === "override" ? c.override : c.effective_category === flt));
  $("#cases-table tbody").innerHTML = rows.map((c) => {
    const f = c.facts || {};
    const onset = f.time_to_onset ? (f.time_to_onset.value != null ? `${f.time_to_onset.value}d` : fv(f.time_to_onset)) : "—";
    return `<tr>
      <td><a href="${evidenceHref(SID, c.report_id)}">${c.report_id}</a></td><td>${c.age}${c.sex}${c.serious ? " · serious" : ""}</td>
      <td>${esc(onset)}</td><td>${esc(fv(f.dechallenge))}</td><td>${esc(fv(f.rechallenge))}</td>
      <td>${f.alternative_causes ? f.alternative_causes.length : "—"}</td>
      <td>${badge.guard(c)}</td><td>${badge.rule(c)}</td></tr>`;
  }).join("") || `<tr><td colspan="8">No cases match this filter.</td></tr>`;
}
$("#case-filter").addEventListener("change", renderCases);
init();
