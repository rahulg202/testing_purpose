"""FastAPI app: API + static single-page UI from one process (Req 11.1).

WARNING: no authentication (Assumption A5). Local single-user prototype only;
binds to 127.0.0.1 by default. Do not expose to a network.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import rules
from .llm import BedrockLLM, LLM
from .service import Copilot, Invalid, NotFound
from .store import Store

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
DB_PATH = ROOT.parent / "data" / "copilot.db"


class OverrideIn(BaseModel):
    category: str
    reason: str
    actor: str


class SignoffIn(BaseModel):
    actor: str
    decision: str
    summary_text: str = ""
    reason: str = ""
    final_recommendation: str = ""


class ChatIn(BaseModel):
    question: str
    actor: str = "reviewer"


def create_app(llm: LLM | None = None, store: Store | None = None) -> FastAPI:
    app = FastAPI(title="AI Signal Investigation Copilot")
    cp = Copilot(llm or BedrockLLM(), store or Store(DB_PATH))
    app.state.copilot = cp

    def run(fn, *a, **kw):
        try:
            return fn(*a, **kw)
        except NotFound as e:
            raise HTTPException(404, str(e)) from e
        except Invalid as e:
            raise HTTPException(422, str(e)) from e
        except Exception as e:  # LLM unreachable etc. -> visible error, never silent
            raise HTTPException(502, f"{type(e).__name__}: {e}") from e

    # ---- pages (multi-page UI: each route is its own HTML document)
    def page(name: str):
        return FileResponse(STATIC / f"{name}.html")

    @app.get("/", include_in_schema=False)
    def signals_page():
        return page("signals")

    @app.get("/signal/{signal_id}", include_in_schema=False)
    def overview_page(signal_id: str):
        return page("overview")

    @app.get("/signal/{signal_id}/case/{report_id}", include_in_schema=False)
    def case_page(signal_id: str, report_id: str):
        return page("case")

    @app.get("/signal/{signal_id}/review", include_in_schema=False)
    def review_page(signal_id: str):
        return page("review")

    @app.get("/signal/{signal_id}/chat", include_in_schema=False)
    def chat_page(signal_id: str):
        return page("chat")

    @app.get("/audit", include_in_schema=False)
    def audit_page():
        return page("audit")

    @app.get("/api/signals")
    def signals(all: bool = False):
        return {"evans": {"prr_min": 2.0, "chi2_min": 4.0, "a_min": 3},
                "total_reports": len(cp.reports), "signals": cp.signals(only_flagged=not all)}

    @app.get("/api/rules")
    def rule_sets():
        return {"causality": {"ruleset": rules.CAUSALITY_RULESET, "version": rules.CAUSALITY_VERSION,
                              "categories": rules.CATEGORIES},
                "recommendation": {"ruleset": rules.RECOMMENDATION_RULESET, "version": rules.RECOMMENDATION_VERSION,
                                   "thresholds": rules.REC_THRESHOLDS}}

    @app.post("/api/signals/{signal_id}/investigate")
    def investigate(signal_id: str):
        return run(cp.investigate, signal_id)

    @app.get("/api/investigations/{signal_id}")
    def get_inv(signal_id: str):
        return run(cp.get, signal_id)

    @app.post("/api/investigations/{signal_id}/cases/{report_id}/override")
    def override(signal_id: str, report_id: str, body: OverrideIn):
        return run(cp.override, signal_id, report_id, body.category, body.reason, body.actor)

    @app.delete("/api/investigations/{signal_id}/cases/{report_id}/override")
    def clear_override(signal_id: str, report_id: str, actor: str = "reviewer"):
        return run(cp.clear_override, signal_id, report_id, actor)

    @app.post("/api/investigations/{signal_id}/summary")
    def summary(signal_id: str):
        return run(cp.draft_summary, signal_id)

    @app.post("/api/investigations/{signal_id}/signoff")
    def signoff(signal_id: str, body: SignoffIn):
        return run(cp.signoff, signal_id, body.actor, body.decision, body.summary_text,
                   body.reason, body.final_recommendation)

    @app.post("/api/investigations/{signal_id}/chat")
    def chat(signal_id: str, body: ChatIn):
        return run(cp.chat, signal_id, body.question, body.actor)

    @app.get("/api/investigations/{signal_id}/kb")
    def kb(signal_id: str):
        return run(cp.kb_stats, signal_id)

    @app.get("/api/audit")
    def audit(limit: int = 200):
        return {"events": cp.store.audit_events(limit)}

    @app.get("/api/audit/verify")
    def verify():
        return cp.store.verify_chain()

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app
