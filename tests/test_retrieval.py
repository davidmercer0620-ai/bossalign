"""Tests for pluggable EvidenceRetriever and safe factual verification."""

import unittest

from bossalign import (
    EvidenceItem,
    EvidenceQuery,
    EvidenceType,
    InMemoryEvidenceRetriever,
    RetrievalStatus,
)


class TestRetrieval(unittest.TestCase):
    def test_verified_evidence_retrieval(self):
        retriever = InMemoryEvidenceRetriever([
            EvidenceItem(
                evidence_id="ev_001",
                content="System maximum supported concurrent connections is 10000.",
                evidence_type=EvidenceType.VERIFIED_FACT.value,
                source="benchmark_run_2026",
                verified=True,
                metadata={"domain": "performance"},
            ),
            EvidenceItem(
                evidence_id="ev_002",
                content="Someone suggested that memory usage might be 2GB.",
                evidence_type=EvidenceType.THIRD_PARTY_REPORT.value,
                source="meeting_chat",
                verified=False,
                metadata={"domain": "performance"},
            ),
        ])

        # Query requiring verified evidence
        query = EvidenceQuery(query="concurrent connections", require_verified=True, domain="performance")
        result = retriever.retrieve(query)
        self.assertEqual(result.status, RetrievalStatus.VERIFIED)
        self.assertTrue(result.is_verified)
        self.assertEqual(len(result.items), 1)
        self.assertEqual(result.items[0].evidence_id, "ev_001")

        # Verify claim
        verified, explanation, item = retriever.verify_claim("concurrent connections", domain="performance")
        self.assertTrue(verified)
        self.assertIn("authoritative evidence", explanation)
        self.assertEqual(item.evidence_id, "ev_001")

    def test_unverified_claim_returns_unverified_status(self):
        retriever = InMemoryEvidenceRetriever([
            EvidenceItem(
                evidence_id="ev_unverified",
                content="Tentative claim without lab proof.",
                evidence_type=EvidenceType.AI_INFERENCE.value,
                verified=False,
            )
        ])

        query = EvidenceQuery(query="Tentative claim", require_verified=True)
        result = retriever.retrieve(query)
        self.assertEqual(result.status, RetrievalStatus.UNVERIFIED)
        self.assertFalse(result.is_verified)
        self.assertIn("not been verified", result.refusal_rationale)

    def test_absent_evidence_returns_unknown_and_refuses_to_fabricate(self):
        retriever = InMemoryEvidenceRetriever([])

        query = EvidenceQuery(query="Fabricated metric that does not exist in store")
        result = retriever.retrieve(query)

        self.assertEqual(result.status, RetrievalStatus.UNKNOWN)
        self.assertEqual(len(result.items), 0)
        self.assertFalse(result.is_verified)
        self.assertIn("Refusing to fabricate", result.refusal_rationale)

        verified, explanation, item = retriever.verify_claim("Nonexistent fact")
        self.assertFalse(verified)
        self.assertIn("UNKNOWN", explanation)
        self.assertIsNone(item)
