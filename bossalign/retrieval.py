"""Pluggable evidence retrieval protocol and safe factual grounding interface."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from .schema import EvidenceType


class RetrievalStatus(str, Enum):
    VERIFIED = "verified"
    UNVERIFIED = "unverified"
    UNKNOWN = "unknown"
    NO_EVIDENCE = "no_evidence"


@dataclass
class EvidenceItem:
    """An atomic piece of grounded evidence with origin and verification metadata."""

    evidence_id: str
    content: str
    evidence_type: str = EvidenceType.DIRECT_EXPLICIT.value
    source: str = "local_evidence"
    verified: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "content": self.content,
            "evidence_type": self.evidence_type,
            "source": self.source,
            "verified": self.verified,
            "metadata": self.metadata,
            "confidence": self.confidence,
        }


@dataclass
class EvidenceQuery:
    """Query parameters for evidence retrieval and factual verification."""

    query: str
    required_evidence_type: Optional[str] = None
    min_confidence: float = 0.5
    tags: List[str] = field(default_factory=list)
    domain: Optional[str] = None
    require_verified: bool = False


@dataclass
class RetrievalResult:
    """Result of an evidence query, maintaining explicit truth boundaries."""

    status: RetrievalStatus
    items: List[EvidenceItem] = field(default_factory=list)
    is_verified: bool = False
    refusal_rationale: Optional[str] = None


class EvidenceRetriever:
    """Pluggable protocol for evidence stores without coupling to specific vector DBs."""

    def retrieve(self, query: EvidenceQuery) -> RetrievalResult:
        raise NotImplementedError

    def verify_claim(self, claim: str, domain: Optional[str] = None) -> Tuple[bool, str, Optional[EvidenceItem]]:
        raise NotImplementedError


class InMemoryEvidenceRetriever(EvidenceRetriever):
    """Deterministic, local in-memory adapter for offline testing and verification.

    Refuses to fabricate facts when supporting evidence is absent.
    """

    def __init__(self, initial_items: Optional[Sequence[EvidenceItem]] = None):
        self._items: List[EvidenceItem] = list(initial_items or [])

    def add_evidence(self, item: EvidenceItem) -> None:
        self._items.append(item)

    def retrieve(self, query: EvidenceQuery) -> RetrievalResult:
        normalized_query = query.query.strip().casefold()
        matches: List[EvidenceItem] = []

        for item in self._items:
            if item.confidence < query.min_confidence:
                continue
            if query.required_evidence_type and item.evidence_type != query.required_evidence_type:
                continue
            if query.domain and item.metadata.get("domain") != query.domain:
                continue
            if query.tags:
                item_tags = set(item.metadata.get("tags") or [])
                if not set(query.tags).issubset(item_tags):
                    continue

            # Deterministic keyword or substring match
            if normalized_query in item.content.casefold() or item.content.casefold() in normalized_query:
                matches.append(item)

        if not matches:
            return RetrievalResult(
                status=RetrievalStatus.UNKNOWN,
                items=[],
                is_verified=False,
                refusal_rationale="No supporting evidence found. Refusing to fabricate ungrounded factual assertions.",
            )

        verified_matches = [m for m in matches if m.verified]
        if query.require_verified and not verified_matches:
            return RetrievalResult(
                status=RetrievalStatus.UNVERIFIED,
                items=matches,
                is_verified=False,
                refusal_rationale="Matching evidence exists but has not been verified by an authoritative source.",
            )

        return RetrievalResult(
            status=RetrievalStatus.VERIFIED if verified_matches else RetrievalStatus.UNVERIFIED,
            items=verified_matches or matches,
            is_verified=bool(verified_matches),
            refusal_rationale=None,
        )

    def verify_claim(self, claim: str, domain: Optional[str] = None) -> Tuple[bool, str, Optional[EvidenceItem]]:
        result = self.retrieve(EvidenceQuery(query=claim, domain=domain, require_verified=True))
        if result.is_verified and result.items:
            return True, "Claim verified against authoritative evidence item '%s'." % result.items[0].evidence_id, result.items[0]
        if result.items:
            return False, "Evidence exists but is not verified as objective fact.", result.items[0]
        return False, "UNKNOWN: No evidence available to substantiate this claim.", None
