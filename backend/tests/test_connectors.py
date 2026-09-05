"""Tests for intake connectors — hashing, Day 0, and PubMed parsing."""

from __future__ import annotations

import httpx
import pytest
from atheria_contracts.enums import Channel, ChannelClass, SourceStatus

from backend.app.connectors.base import compute_content_hash, normalise_text
from backend.app.connectors.pubmed import PubMedConnector, _parse_articles
from backend.app.connectors.web_form import WebFormSubmission, ingest_web_form

SAMPLE_EFETCH_XML = """<?xml version="1.0"?>
<PubmedArticleSet>
  <PubmedArticle>
    <MedlineCitation>
      <PMID Version="1">40123456</PMID>
      <Article>
        <Journal>
          <Title>Journal of Hepatology</Title>
          <JournalIssue><PubDate><Year>2026</Year></PubDate></JournalIssue>
        </Journal>
        <ArticleTitle>Severe hepatotoxicity associated with Atherex therapy.</ArticleTitle>
        <Abstract>
          <AbstractText Label="BACKGROUND">Atherex is widely used.</AbstractText>
          <AbstractText Label="CASE">A 72-year-old woman developed jaundice.</AbstractText>
        </Abstract>
      </Article>
    </MedlineCitation>
  </PubmedArticle>
</PubmedArticleSet>
"""


class TestNormalisationAndHashing:
    def test_normalise_collapses_line_endings_and_trailing_space(self) -> None:
        assert normalise_text("a  \r\nb\r\n") == "a\nb"

    def test_cosmetically_different_text_hashes_identically(self) -> None:
        """Dedup must not be defeated by line endings or trailing whitespace."""
        assert compute_content_hash("Hello\r\nworld  ") == compute_content_hash("Hello\nworld")

    def test_different_text_hashes_differently(self) -> None:
        assert compute_content_hash("Atherex") != compute_content_hash("Cardiozol")

    def test_hash_is_sha256_hex(self) -> None:
        assert len(compute_content_hash("x")) == 64


class TestWebFormConnector:
    def test_builds_solicited_source_record(self) -> None:
        record = ingest_web_form(
            tenant_id="acme_pharma",
            submission=WebFormSubmission(narrative="A rash appeared."),
        )
        assert record.channel is Channel.WEB_FORM
        assert record.channel_class is ChannelClass.SOLICITED
        assert record.status is SourceStatus.RECEIVED
        assert record.tenant_id == "acme_pharma"
        assert len(record.content_hash) == 64

    def test_day_zero_is_set_at_intake(self) -> None:
        record = ingest_web_form(tenant_id="t", submission=WebFormSubmission(narrative="x"))
        # Day 0 is the regulatory clock start and must always be populated.
        assert record.awareness_datetime is not None
        assert record.retrieved_at is not None

    def test_populated_fields_are_labelled_in_source_text(self) -> None:
        submission = WebFormSubmission(
            narrative="She developed a rash.",
            reporter_name="Dr. Smith",
            product_name="Atherex 100mg",
            patient_age="54",
        )
        text = submission.to_source_text()
        assert "Reporter name: Dr. Smith" in text
        assert "Product: Atherex 100mg" in text
        assert "Patient age: 54" in text
        assert text.strip().endswith("She developed a rash.")

    def test_empty_fields_are_omitted_not_written_as_unknown(self) -> None:
        """A blank field must not read as a positive assertion of absence."""
        text = WebFormSubmission(narrative="Only a narrative.").to_source_text()
        assert "Reporter name" not in text
        assert "unknown" not in text.lower()


class TestPubMedParsing:
    def test_parses_pmid_title_and_sectioned_abstract(self) -> None:
        articles = _parse_articles(SAMPLE_EFETCH_XML)
        assert len(articles) == 1
        article = articles[0]
        assert article.pmid == "40123456"
        assert "hepatotoxicity" in article.title.lower()
        assert "BACKGROUND: Atherex is widely used." in article.abstract
        assert "CASE: A 72-year-old woman developed jaundice." in article.abstract
        assert article.journal == "Journal of Hepatology"
        assert article.published == "2026"

    def test_article_url_points_at_pubmed(self) -> None:
        article = _parse_articles(SAMPLE_EFETCH_XML)[0]
        assert article.url == "https://pubmed.ncbi.nlm.nih.gov/40123456/"

    def test_source_text_includes_title_and_abstract(self) -> None:
        text = _parse_articles(SAMPLE_EFETCH_XML)[0].to_source_text()
        assert "Title:" in text
        assert "PMID: 40123456" in text
        assert "Abstract:" in text

    def test_malformed_xml_returns_empty_rather_than_raising(self) -> None:
        assert _parse_articles("<not-xml") == []


class TestPubMedRetry:
    """Transient network failures must be retried, not fail the sweep.

    The development network sits behind a TLS-inspecting proxy that drops
    connections intermittently, which was observed to fail a live sweep.
    """

    def test_transient_transport_error_is_retried_then_succeeds(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls = {"n": 0}

        def flaky_get(url: str, **kwargs: object) -> httpx.Response:
            calls["n"] += 1
            if calls["n"] < 3:
                raise httpx.ConnectError("connection reset")
            return httpx.Response(
                200,
                json={"esearchresult": {"idlist": ["123"]}},
                request=httpx.Request("GET", url),
            )

        monkeypatch.setattr(httpx, "get", flaky_get)
        connector = PubMedConnector()
        # Wait is exponential; patch sleep so the test stays fast.
        monkeypatch.setattr("time.sleep", lambda _: None)

        assert connector.search("query") == ["123"]
        assert calls["n"] == 3

    def test_persistent_failure_raises_actionable_runtime_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def always_fail(url: str, **kwargs: object) -> httpx.Response:
            raise httpx.ConnectError("blocked")

        monkeypatch.setattr(httpx, "get", always_fail)
        monkeypatch.setattr("time.sleep", lambda _: None)
        connector = PubMedConnector()

        with pytest.raises(RuntimeError, match="after 3 attempts"):
            connector.search("query")

    def test_client_error_is_not_retried(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A 400 is our fault, not transient — fail immediately."""
        calls = {"n": 0}

        def bad_request(url: str, **kwargs: object) -> httpx.Response:
            calls["n"] += 1
            return httpx.Response(400, request=httpx.Request("GET", url))

        monkeypatch.setattr(httpx, "get", bad_request)
        connector = PubMedConnector()

        with pytest.raises(RuntimeError, match="HTTP 400"):
            connector.search("query")
        assert calls["n"] == 1
