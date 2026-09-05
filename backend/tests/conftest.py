"""Shared pytest fixtures.

The suite runs against in-memory SQLite so it needs no database server and no
AWS credentials. The LLM is replaced by a stub provider, which keeps tests
deterministic and free: the model's *job* here is to return a schema-shaped
proposal, and we assert on what the rules do with it.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any

import pytest
import pytest_asyncio
from atheria_llm import LLMConfig, LLMInvocationRecord, LLMResponse, PromptRegistry
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.app.models.base import Base
from backend.app.models.case import SourceRecordModel

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def session() -> AsyncGenerator[AsyncSession, None]:
    """A session bound to a fresh in-memory schema per test."""
    engine = create_async_engine(TEST_DB_URL, future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as db_session:
        yield db_session

    await engine.dispose()


class StubProvider:
    """Deterministic stand-in for a real model.

    Returns whatever proposal the test supplies, so rule behaviour can be
    asserted without network calls or spend.
    """

    name = "stub"

    def __init__(self, proposal: dict[str, Any]) -> None:
        self.proposal = proposal
        self.calls: list[tuple[str, LLMConfig]] = []

    def invoke(self, prompt: str, config: LLMConfig) -> LLMResponse:
        self.calls.append((prompt, config))
        return LLMResponse(
            text="",
            structured_output=self.proposal,
            record=LLMInvocationRecord(
                provider=self.name,
                model_id="stub-model-v1",
                prompt_version=config.prompt_version,
                input_tokens=10,
                output_tokens=5,
                stop_reason="tool_use",
            ),
        )


def make_proposal(
    *,
    patient: bool = True,
    reporter: bool = True,
    product: bool = True,
    event: bool = True,
    quotes: dict[str, str] | None = None,
    content_type: str = "ae",
    seriousness: bool = False,
    is_noise: bool = False,
    patient_count: int = 1,
) -> dict[str, Any]:
    """Build a schema-shaped triage proposal for tests."""
    quotes = quotes or {}

    def element(name: str, present: bool) -> dict[str, Any]:
        return {
            "present": present,
            "evidence_quote": quotes.get(name, f"quote for {name}" if present else ""),
        }

    return {
        "identifiable_patient": element("identifiable_patient", patient),
        "identifiable_reporter": element("identifiable_reporter", reporter),
        "suspect_product": element("suspect_product", product),
        "adverse_event": element("adverse_event", event),
        "product_names": ["Atherex 100mg"] if product else [],
        "event_terms": ["severe rash"] if event else [],
        "content_type": content_type,
        "patient_count": patient_count,
        "seriousness_signal": seriousness,
        "is_noise": is_noise,
        "rationale": "stub rationale",
    }


@pytest.fixture
def prompts(tmp_path: Any) -> PromptRegistry:
    """A registry holding a minimal triage prompt.

    Independent of the production YAML so a prompt-wording change does not
    break these tests.
    """
    (tmp_path / "triage_icsr.yaml").write_text(
        "\n".join(
            [
                "name: triage_icsr",
                'version: "1.0"',
                "max_tokens: 500",
                "temperature: 0.0",
                "system_prompt: |",
                "  Report the four ICSR criteria.",
                "user_template: |",
                "  Channel: {channel}",
                "  Source: {source_text}",
                "output_schema:",
                "  type: object",
                "  properties:",
                "    identifiable_patient: {type: object}",
            ]
        ),
        encoding="utf-8",
    )
    return PromptRegistry(tmp_path)


@pytest_asyncio.fixture
async def stored_record(session: AsyncSession) -> SourceRecordModel:
    """A persisted source record ready to be triaged."""
    now = datetime.now(UTC)
    record = SourceRecordModel(
        source_record_id="src_test_0001",
        tenant_id="acme_pharma",
        trace_id="trc_test",
        channel="web_form",
        channel_class="solicited",
        retrieved_at=now,
        awareness_datetime=now,
        raw_text=(
            "Reporter: Dr. Smith, physician. Patient: 54-year-old female. "
            "Product: Atherex 100mg. Event: severe rash after eight days."
        ),
        content_hash="a" * 64,
        status="received",
        manifest_ref="acme_pharma/web_form/raw.txt",
        derived_case_ids=[],
    )
    session.add(record)
    await session.flush()
    return record
