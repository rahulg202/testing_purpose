"use strict";
// Shared helpers for every page. All decisions come from the API; pages only render them.
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const CATS = ["Certain", "Probable", "Possible", "Unlikely", "Unassessable"];
const enc = encodeURIComponent;

async function api(path, opts = {}) {
  const r = await fetch(path, { headers: { "content-type": "application/json" }, ...opts });
  const body = await r.json().catch(() => ({}));
  if (!r.ok) { const e = new Error(body.detail || `HTTP ${r.status}`); e.status = r.status; throw e; }
  return body;
}
function announce(msg) { const el = $("#sr-status"); if (el) el.textContent = msg; }
function pathParts() { return location.pathname.split("/").filter(Boolean).map(decodeURIComponent); }
function sigLabel(id) { return id.replace("__", " + "); }
function reviewer() { return localStorage.reviewer || ""; }
function setReviewer(n) { if (n) localStorage.reviewer = n; }

// Shared header + breadcrumbs + page tabs for one signal
function renderChrome({ active, signalId, crumbs = [] }) {
  const nav = [["/", "Signals", "signals"], ["/audit", "Audit trail", "audit"]];
  $("#chrome").innerHTML = `
    <a class="skip" href="#main">Skip to content</a>
    <header class="top">
      <div><a href="/" class="brand"><h1>AI Signal Investigation Copilot</h1></a>
        <p class="tag">Statistics detect · AI extracts (verified) · Rules decide · Humans approve</p></div>
      <nav aria-label="Main" class="top-right">
        ${nav.map(([h, t, k]) => `<a href="${h}" ${k === active ? 'aria-current="page"' : ""}>${t}</a>`).join("")}
        <span class="warn" role="note">Local prototype · synthetic data · no authentication</span>
      </nav>
    </header>
    <div class="subbar">
      <nav aria-label="Breadcrumb"><ol class="crumbs"><li><a href="/">Signals</a></li>${crumbs.map(([h, t], i) =>
        `<li>${i === crumbs.length - 1 ? `<span aria-current="page">${esc(t)}</span>` : `<a href="${h}">${esc(t)}</a>`}</li>`).join("")}</ol></nav>
      ${signalId ? `<nav aria-label="Investigation sections" class="tabs">
        <a href="/signal/${enc(signalId)}" ${active === "overview" ? 'aria-current="page"' : ""}>Overview & cases</a>
        <a href="/signal/${enc(signalId)}/review" ${active === "review" ? 'aria-current="page"' : ""}>Summary & sign-off</a>
        <a href="/signal/${enc(signalId)}/chat" ${active === "chat" ? 'aria-current="page"' : ""}>Ask the evidence</a>
      </nav>` : ""}
    </div>`;
}

const badge = {
  rule: (c) => c.override ? `<span class="badge b-human">✎ Human: ${esc(c.effective_category)}</span>` : `<span class="badge b-rule">⚙ ${esc(c.effective_category)}</span>`,
  guard: (c) => {
    if (c.error) return `<span class="badge b-bad">✖ failed</span>`;
    const g = c.guardrail;
    return g.quotes_rejected ? `<span class="badge b-bad">⚠ ${g.quotes_verified}✓ ${g.quotes_rejected}✗</span>` : `<span class="badge b-ok">✓ ${g.quotes_verified}</span>`;
  },
};

// Evidence link: goes to the case page, which highlights by stored char offsets
function evidenceHref(signalId, caseId, span) {
  return `/signal/${enc(signalId)}/case/${enc(caseId)}` + (span ? `?s=${span[0]}&e=${span[1]}` : "");
}

// Loads the investigation or shows a "not started" message with a Run button
async function loadInvestigation(signalId, box) {
  try { return await api(`/api/investigations/${enc(signalId)}`); }
  catch (e) {
    if (e.status !== 404) { box.innerHTML = `<p class="card error" role="alert">${esc(e.message)}</p>`; return null; }
    box.innerHTML = `<div class="card"><p>This investigation has not been run yet.</p>
      <a class="button primary" href="/signal/${enc(signalId)}">Go to overview to run it</a></div>`;
    return null;
  }
}
