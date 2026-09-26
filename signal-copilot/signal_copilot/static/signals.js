"use strict";
renderChrome({ active: "signals" });
const params = new URLSearchParams(location.search);
$("#show-all").checked = params.get("all") === "1";

async function loadSignals() {
  const d = await api(`/api/signals?all=${$("#show-all").checked}`);
  const sel = $("#drug-filter"), cur = sel.value || params.get("drug") || "";
  const drugs = [...new Set(d.signals.map((s) => s.drug))].sort();
  sel.innerHTML = `<option value="">All drugs</option>` + drugs.map((x) => `<option ${x === cur ? "selected" : ""}>${esc(x)}</option>`).join("");
  const rows = d.signals.filter((s) => !sel.value || s.drug === sel.value);
  $("#signals-meta").textContent = `(${d.total_reports} reports, ${rows.length} shown)`;
  $("#signals-table tbody").innerHTML = rows.map((s) => `
    <tr>
      <td>${esc(s.drug)}</td><td>${esc(s.event)}</td><td>${s.a}</td><td><b>${s.prr.toFixed(2)}</b></td>
      <td>${s.ror.toFixed(2)} (${s.ror_lo.toFixed(2)}–${s.ror_hi.toFixed(2)})</td><td>${s.chi2.toFixed(1)}</td>
      <td>${s.is_signal ? '<span class="badge b-bad">⚑ Signal</span>' : '<span class="badge b-unk">Not flagged</span>'}</td>
      <td>${esc(s.investigation_status.replace("_", " "))}</td>
      <td class="row">
        <button type="button" data-t="${esc(s.signal_id)}" aria-expanded="false" aria-controls="t-${esc(s.signal_id)}">2×2</button>
        ${s.investigation_status === "not_started"
          ? `<button type="button" class="${s.is_signal ? "primary" : ""}" data-inv="${esc(s.signal_id)}">Investigate</button>`
          : `<a class="button primary" href="/signal/${enc(s.signal_id)}">Open</a>`}
      </td>
    </tr>
    <tr hidden id="t-${esc(s.signal_id)}"><td colspan="9">
      <table class="two-by-two" style="width:auto"><caption>2×2 contingency table</caption>
        <tr><th></th><th scope="col">${esc(s.event)}</th><th scope="col">Other events</th></tr>
        <tr><th scope="row">${esc(s.drug)}</th><td>a = ${s.a}</td><td>b = ${s.b}</td></tr>
        <tr><th scope="row">Other drugs</th><td>c = ${s.c}</td><td>d = ${s.d}</td></tr>
      </table></td></tr>`).join("");
}

$("#signals-table").addEventListener("click", async (e) => {
  const t = e.target.closest("button"); if (!t) return;
  if (t.dataset.t) { const row = document.getElementById("t-" + t.dataset.t); row.hidden = !row.hidden; t.setAttribute("aria-expanded", String(!row.hidden)); }
  if (t.dataset.inv) {
    const id = t.dataset.inv;
    document.querySelectorAll("[data-inv]").forEach((b) => (b.disabled = true));
    $("#run-status").innerHTML = `<p class="card spinner">Investigating ${esc(sigLabel(id))}: the AI is reading every narrative in parallel, guardrails are verifying each quote, rules are assigning causality</p>`;
    try { await api(`/api/signals/${enc(id)}/investigate`, { method: "POST" }); location.href = `/signal/${enc(id)}`; }
    catch (err) { $("#run-status").innerHTML = `<p class="card error" role="alert">Investigation failed: ${esc(err.message)}</p>`; document.querySelectorAll("[data-inv]").forEach((b) => (b.disabled = false)); }
  }
});
$("#show-all").addEventListener("change", loadSignals);
$("#drug-filter").addEventListener("change", () => { if ($("#drug-filter").value) $("#show-all").checked = true; loadSignals(); });
loadSignals().catch((e) => { $("#signals-meta").textContent = "Failed to load: " + e.message; });
