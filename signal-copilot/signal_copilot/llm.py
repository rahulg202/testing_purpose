"""Bedrock access + Level 1 prompt guardrails (versioned prompts).

All generation is temperature 0 with forced tool-use (structured output).
"""

from __future__ import annotations

import json
import threading
from typing import Protocol

from . import AWS_REGION, EMBED_MODEL_ID, MODEL_ID

# ---------------------------------------------------------------- prompts ---
# Level 1 guardrails. Necessary, not sufficient: every output is still checked
# by the deterministic Level 2 guardrails in guardrails.py.

EXTRACT_PROMPT_VERSION = "extract_v1.4.0"  # 1.4.0: no placeholder checklist items (1.3.0: confounder checklist)
EXTRACT_SYSTEM = """You are a pharmacovigilance fact-extraction assistant.
Read ONE adverse event case narrative and record facts using the record_facts tool.

Rules you must follow:
1. Report facts only. NEVER assign causality, relatedness, or any recommendation.
2. Every non-unknown fact MUST include a quote copied VERBATIM (exact words) from the narrative.
3. If the narrative does not explicitly state a fact, return "unknown" (or null days). Do not infer.
4. time_to_onset.days: number of days from drug start to event onset, only if stated (with its quote).
   If not stated, days MUST be null. Never use 0 as a placeholder.
   Lists (alternative_causes, excluded_causes) must be empty [] when there is nothing to report;
   never include items with null or empty cause/quote.
5. temporal_relationship (its quote must be the sentence that states the timing):
   "plausible" if the event started after drug start in a stated timeframe,
   "implausible" if it clearly started before the drug, otherwise "unknown".
6. dechallenge: "positive" = event improved after drug stopped; "negative" = did not improve after stop;
   "not_done" = drug explicitly continued; otherwise "unknown". Same scheme for rechallenge (drug restarted).
7. alternative_causes: go through the narrative SENTENCE BY SENTENCE and list EVERY other explanation that is
   PRESENT in the patient, one item per explanation, each with its own verbatim quote. Categories to check:
   (a) any other medication the patient was taking, (b) alcohol or substance use, (c) gallstones or other
   structural findings, (d) a prior episode or history of the same condition, (e) abnormal lab values that can
   cause the event, (f) other diseases. Never list the suspect drug itself. A physician's opinion is not a cause.
   The checklist is for YOUR review only: output an item ONLY when the narrative actually mentions it.
   Never output placeholder items such as "no other medication"; if nothing is mentioned, return [].
   A cause that was tested for and found negative, denied, or absent is NOT an alternative cause:
   put it in excluded_causes instead. Empty list if none.
8. excluded_causes: explanations the narrative explicitly rules out (negative serology, denied alcohol, no other drugs).
9. data_gaps: short phrases for important information that is missing."""

_q = {"type": "string", "description": "Verbatim quote from the narrative"}
EXTRACT_SCHEMA = {
    "type": "object",
    "properties": {
        "time_to_onset": {"type": "object", "properties": {"days": {"type": ["integer", "null"]}, "quote": _q}, "required": ["days"]},
        "temporal_relationship": {"type": "object", "properties": {"value": {"type": "string", "enum": ["plausible", "implausible", "unknown"]}, "quote": _q}, "required": ["value"]},
        "dechallenge": {"type": "object", "properties": {"value": {"type": "string", "enum": ["positive", "negative", "not_done", "unknown"]}, "quote": _q}, "required": ["value"]},
        "rechallenge": {"type": "object", "properties": {"value": {"type": "string", "enum": ["positive", "negative", "not_done", "unknown"]}, "quote": _q}, "required": ["value"]},
        "alternative_causes": {"type": "array", "items": {"type": "object", "properties": {"cause": {"type": "string"}, "quote": _q}, "required": ["cause", "quote"]}},
        "excluded_causes": {"type": "array", "items": {"type": "object", "properties": {"cause": {"type": "string"}, "quote": _q}, "required": ["cause", "quote"]}},
        "data_gaps": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["time_to_onset", "temporal_relationship", "dechallenge", "rechallenge", "alternative_causes", "excluded_causes", "data_gaps"],
}

SUMMARY_PROMPT_VERSION = "summary_v1.0.0"
SUMMARY_SYSTEM = """You draft pharmacovigilance signal investigation summaries.
Use ONLY the structured data provided (statistics, verified facts, rule-computed causality and recommendation).
Rules:
1. Do not change, question or re-decide the recommendation or any causality category; restate them as given.
2. Cite supporting cases by their exact report IDs (format R-00000). Only cite IDs present in the data.
3. Do not add clinical facts that are not in the data. Be concise: 150-250 words, plain prose, no headings."""
SUMMARY_SCHEMA = {"type": "object", "properties": {"summary": {"type": "string"}}, "required": ["summary"]}

CHAT_PROMPT_VERSION = "chat_v1.1.0"
CHAT_SYSTEM = """You are a read-only assistant helping a medical reviewer explore ONE safety signal.
Rules:
1. Answer ONLY from the CONTEXT provided. Do not use general medical knowledge.
2. If the context does not answer the question, set no_evidence=true and say you cannot find supporting evidence.
3. Every claim must be supported by a citation: the report ID and a quote copied VERBATIM from a NARRATIVE line
   (lines starting with [R-xxxxx]). CASE SUMMARY lines are for orientation only and must never be quoted.
4. Never assign causality, never change or suggest changing the recommendation. You are an assistant, not a decision-maker.
5. Be concise."""
CHAT_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "no_evidence": {"type": "boolean"},
        "citations": {"type": "array", "items": {"type": "object", "properties": {
            "case_id": {"type": "string"}, "quote": {"type": "string"}}, "required": ["case_id", "quote"]}},
    },
    "required": ["answer", "no_evidence", "citations"],
}


class LLM(Protocol):
    model_id: str

    def structured(self, system: str, user: str, tool: str, schema: dict, max_tokens: int = 1500) -> dict: ...
    def embed(self, text: str) -> list[float]: ...


class BedrockLLM:
    model_id = MODEL_ID

    def __init__(self) -> None:
        self._local = threading.local()

    @property
    def _client(self):
        if not hasattr(self._local, "c"):
            import boto3
            from botocore.config import Config
            self._local.c = boto3.client("bedrock-runtime", region_name=AWS_REGION,
                                         config=Config(retries={"max_attempts": 4, "mode": "adaptive"},
                                                       read_timeout=60, connect_timeout=10))
        return self._local.c

    def structured(self, system: str, user: str, tool: str, schema: dict, max_tokens: int = 1500) -> dict:
        resp = self._client.converse(
            modelId=self.model_id,
            system=[{"text": system}],
            messages=[{"role": "user", "content": [{"text": user}]}],
            inferenceConfig={"maxTokens": max_tokens, "temperature": 0.0},
            toolConfig={"tools": [{"toolSpec": {"name": tool, "description": f"Return the {tool} result.",
                                                "inputSchema": {"json": schema}}}],
                        "toolChoice": {"tool": {"name": tool}}},
        )
        for block in resp["output"]["message"]["content"]:
            if "toolUse" in block:
                return block["toolUse"].get("input") or {}
        raise ValueError("model did not return the forced tool output")

    def embed(self, text: str) -> list[float]:
        r = self._client.invoke_model(modelId=EMBED_MODEL_ID, body=json.dumps(
            {"inputText": text[:8000], "dimensions": 512, "normalize": True}))
        return json.loads(r["body"].read())["embedding"]
