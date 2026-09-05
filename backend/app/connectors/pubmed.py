"""PubMed literature connector — NCBI E-utilities.

Literature monitoring is a standing pharmacovigilance obligation: marketing
authorisation holders must screen published literature for adverse reactions
involving their products. This connector performs that sweep.

Flow (two calls, as E-utilities requires):

1. ``esearch`` — run the query, get back matching PMIDs.
2. ``efetch``  — retrieve those records as XML, from which we take the title
   and abstract.

Only free public endpoints are used, no API key required. Supplying
``ATHERIA_NCBI_API_KEY`` raises the rate limit from 3 to 10 requests/second.
NCBI asks callers to identify themselves via ``tool`` and ``email``, so we do.

Each article becomes one SourceRecord with ``ChannelClass.LITERATURE`` and its
PubMed URL as ``external_url``, so a reviewer can always open the source.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass

import httpx
import structlog
from atheria_contracts.enums import Channel, ChannelClass
from atheria_contracts.source_record import SourceRecord
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential
from ulid import ULID

from .base import ConnectorResult, build_source_record

logger = structlog.get_logger("connector.pubmed")

EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
TOOL_NAME = "atheria-pv"


class _TransientFetchError(Exception):
    """Marker for a retryable E-utilities failure.

    NCBI throttles aggressively and corporate TLS-inspecting proxies drop
    connections intermittently, so transport errors and 5xx/429 responses are
    retried with backoff rather than failing the sweep outright.
    """


@dataclass
class PubMedArticle:
    """A single article retrieved from PubMed."""

    pmid: str
    title: str
    abstract: str
    journal: str | None = None
    published: str | None = None

    @property
    def url(self) -> str:
        return f"https://pubmed.ncbi.nlm.nih.gov/{self.pmid}/"

    def to_source_text(self) -> str:
        """Render as labelled text for triage."""
        parts = [f"Title: {self.title}"]
        if self.journal:
            parts.append(f"Journal: {self.journal}")
        if self.published:
            parts.append(f"Published: {self.published}")
        parts.append(f"PMID: {self.pmid}")
        parts.append("")
        parts.append("Abstract:")
        parts.append(self.abstract or "(no abstract available)")
        return "\n".join(parts)


def _text(node: ET.Element | None) -> str:
    """Collapse an element's full text content, including nested markup."""
    if node is None:
        return ""
    return "".join(node.itertext()).strip()


def _parse_articles(xml_text: str) -> list[PubMedArticle]:
    """Parse an efetch PubmedArticleSet into articles."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        logger.error("pubmed_xml_parse_failed", error=str(exc))
        return []

    articles: list[PubMedArticle] = []
    for entry in root.findall(".//PubmedArticle"):
        pmid = _text(entry.find(".//PMID"))
        if not pmid:
            continue
        title = _text(entry.find(".//ArticleTitle"))

        # Abstracts may be split into labelled sections (BACKGROUND, METHODS...).
        chunks: list[str] = []
        for abstract_part in entry.findall(".//Abstract/AbstractText"):
            label = abstract_part.get("Label")
            body = _text(abstract_part)
            if not body:
                continue
            chunks.append(f"{label}: {body}" if label else body)

        journal = _text(entry.find(".//Journal/Title")) or None
        year = _text(entry.find(".//JournalIssue/PubDate/Year"))
        medline = _text(entry.find(".//JournalIssue/PubDate/MedlineDate"))

        articles.append(
            PubMedArticle(
                pmid=pmid,
                title=title,
                abstract="\n\n".join(chunks),
                journal=journal,
                published=year or medline or None,
            )
        )
    return articles


class PubMedConnector:
    """Fetches literature from PubMed and emits SourceRecords."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        tool_email: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._api_key = api_key
        self._tool_email = tool_email
        self._timeout = timeout

    def _common_params(self) -> dict[str, str]:
        params = {"tool": TOOL_NAME}
        if self._tool_email:
            params["email"] = self._tool_email
        if self._api_key:
            params["api_key"] = self._api_key
        return params

    @retry(
        retry=retry_if_exception_type(_TransientFetchError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        reraise=True,
    )
    def _get(self, endpoint: str, params: dict[str, str]) -> httpx.Response:
        """GET an E-utilities endpoint, retrying transient failures."""
        try:
            response = httpx.get(f"{EUTILS_BASE}/{endpoint}", params=params, timeout=self._timeout)
        except httpx.HTTPError as exc:
            # Transport-level failure (connection reset, timeout, DNS).
            raise _TransientFetchError(f"{type(exc).__name__}: {exc}") from exc

        if response.status_code == 429 or response.status_code >= 500:
            raise _TransientFetchError(f"HTTP {response.status_code}")
        if response.status_code >= 400:
            raise RuntimeError(f"PubMed {endpoint} returned HTTP {response.status_code}")
        return response

    def search(self, query: str, *, max_results: int = 5) -> list[str]:
        """Run esearch and return matching PMIDs."""
        params = {
            **self._common_params(),
            "db": "pubmed",
            "term": query,
            "retmax": str(max_results),
            "retmode": "json",
            "sort": "date",
        }
        try:
            response = self._get("esearch.fcgi", params)
        except _TransientFetchError as exc:
            raise RuntimeError(
                f"PubMed search failed after 3 attempts: {exc}. "
                "Check network egress to eutils.ncbi.nlm.nih.gov."
            ) from exc

        payload = response.json()
        pmids: list[str] = payload.get("esearchresult", {}).get("idlist", [])
        logger.info("pubmed_search_complete", query=query, hits=len(pmids))
        return pmids

    def fetch(self, pmids: list[str]) -> list[PubMedArticle]:
        """Run efetch for the given PMIDs and parse the results."""
        if not pmids:
            return []
        params = {
            **self._common_params(),
            "db": "pubmed",
            "id": ",".join(pmids),
            "retmode": "xml",
        }
        try:
            response = self._get("efetch.fcgi", params)
        except _TransientFetchError as exc:
            raise RuntimeError(f"PubMed fetch failed after 3 attempts: {exc}") from exc

        articles = _parse_articles(response.text)
        logger.info("pubmed_fetch_complete", requested=len(pmids), parsed=len(articles))
        return articles

    def sweep(
        self,
        *,
        tenant_id: str,
        query: str,
        max_results: int = 5,
        trace_id: str | None = None,
        known_content_hashes: set[str] | None = None,
    ) -> ConnectorResult:
        """Search, fetch, and convert to SourceRecords.

        Args:
            known_content_hashes: Hashes already in the store. Matching
                articles are skipped so a repeated sweep does not create
                duplicate work items.
        """
        sweep_id = str(ULID())
        pmids = self.search(query, max_results=max_results)
        articles = self.fetch(pmids)

        seen = known_content_hashes or set()
        records: list[SourceRecord] = []
        duplicates = 0

        for article in articles:
            record = build_source_record(
                tenant_id=tenant_id,
                channel=Channel.LITERATURE_PUBMED,
                channel_class=ChannelClass.LITERATURE,
                raw_text=article.to_source_text(),
                raw_language="en",
                trace_id=trace_id,
                external_id=article.pmid,
                external_url=article.url,
                sweep_id=sweep_id,
            )
            if record.content_hash in seen:
                duplicates += 1
                continue
            seen.add(record.content_hash)
            records.append(record)

        summary = (
            f"PubMed sweep '{query}': {len(pmids)} hits, {len(articles)} fetched, "
            f"{len(records)} new, {duplicates} duplicate(s) skipped."
        )
        logger.info(
            "pubmed_sweep_complete",
            query=query,
            new_records=len(records),
            duplicates_skipped=duplicates,
            sweep_id=sweep_id,
        )
        return ConnectorResult(records=records, duplicates_skipped=duplicates, summary=summary)
