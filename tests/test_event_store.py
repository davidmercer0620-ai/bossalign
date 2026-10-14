"""Tests for SQLite Event Store, evidence provenance, and audit tracking."""

import tempfile
import unittest
from pathlib import Path

from bossalign import BossAlign, FeedbackEvent, MemoryStore
from bossalign.schema import ContentType, EvidenceLevel, EvidenceType


class TestEventStore(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.db_path = Path(self.tempdir.name) / "events.sqlite3"

    def tearDown(self):
        MemoryStore.close_all()

    def test_feedback_event_persistence_and_separation_of_times(self):
        store = MemoryStore(self.db_path)
        event = FeedbackEvent(
            event_id="evt_001",
            timestamp="2026-01-01T10:00:00Z",  # occurrence time
            reviewer="actor_A",
            evidence_level=EvidenceLevel.L1_DIRECT_QUOTE,
            topic_context="context_alpha",
            raw_content="Never use absolute claims in summary copy.",
            extracted_intent="Avoid absolute claims.",
            derived_rule_id="rule_001",
            recorded_at="2026-01-01T10:05:00Z",  # recorded time
            preference_owner="subject_1",
            evidence_type=EvidenceType.DIRECT_EXPLICIT.value,
            content_type=ContentType.PREFERENCE.value,
        )
        store.save_event(event)

        loaded = store.get_event("evt_001")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.event_id, "evt_001")
        self.assertEqual(loaded.timestamp, "2026-01-01T10:00:00Z")
        self.assertEqual(loaded.recorded_at, "2026-01-01T10:05:00Z")
        self.assertEqual(loaded.preference_owner, "subject_1")
        self.assertEqual(loaded.reviewer, "actor_A")

    def test_event_linking_and_evidence_chain_tracing(self):
        with BossAlign(self.db_path) as client:
            # 1. Root event: original conversation note
            root_event = FeedbackEvent(
                event_id="evt_root",
                timestamp="2026-01-01T09:00:00Z",
                reviewer="actor_A",
                evidence_level=EvidenceLevel.L3_TRANSFERRED_NOTE,
                topic_context="meeting_notes",
                raw_content="Subject mentioned preferring concise output.",
                extracted_intent="Keep summaries concise.",
                preference_owner="subject_1",
            )
            client.store.save_event(root_event)

            # 2. Child event that links to root
            child_event = FeedbackEvent(
                event_id="evt_child",
                timestamp="2026-01-01T09:30:00Z",
                reviewer="actor_B",
                evidence_level=EvidenceLevel.L1_DIRECT_QUOTE,
                topic_context="review_session",
                raw_content="Confirmed: limit summary to 3 bullets.",
                extracted_intent="Summary limit 3 bullets.",
                derived_rule_id="rule_chain_1",
                parent_event_id="evt_root",
                preference_owner="subject_1",
            )
            client.store.save_event(child_event)

            # Create rule referencing child
            rule = client.ingest(
                "Limit summary to 3 bullets.",
                reviewer="actor_B",
                preference_owner="subject_1",
                context={"applicable_scope": {"task_type": "summary"}},
            )
            # Link rule to child event
            client.update_rule(rule.rule_id, source_event_ids=["evt_child"])

            chain = client.get_evidence_chain(rule.rule_id)
            chain_ids = [e.event_id for e in chain]
            self.assertIn("evt_child", chain_ids)
            self.assertIn("evt_root", chain_ids)

    def test_event_revocation_creates_audit_log(self):
        store = MemoryStore(self.db_path)
        event = FeedbackEvent(
            event_id="evt_revoke_me",
            timestamp="2026-01-01T12:00:00Z",
            reviewer="actor_A",
            evidence_level=EvidenceLevel.L1_DIRECT_QUOTE,
            topic_context="session_1",
            raw_content="Temporary requirement.",
            extracted_intent="Temporary.",
            preference_owner="subject_1",
        )
        store.save_event(event)

        success = store.revoke_event("evt_revoke_me", revoked_by="auditor_X", reason="Superseded by direct decision")
        self.assertTrue(success)

        updated_event = store.get_event("evt_revoke_me")
        self.assertEqual(updated_event.status, "revoked")

        # Check audit log record
        with store._lock:
            cur = store._connection.execute(
                "SELECT * FROM event_audit_log WHERE event_id = ?", ("evt_revoke_me",)
            )
            audit_rows = cur.fetchall()
            self.assertEqual(len(audit_rows), 1)
            self.assertEqual(audit_rows[0]["action"], "revoke")
            self.assertEqual(audit_rows[0]["actor"], "auditor_X")
            self.assertIn("Superseded", audit_rows[0]["reason"])

    def test_schema_migration_preserves_existing_data(self):
        # Create a database with V1 schema manually
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        conn.executescript(
            """
            CREATE TABLE feedback_events (
                event_id TEXT PRIMARY KEY,
                reviewer TEXT NOT NULL,
                created_at TEXT NOT NULL,
                data_json TEXT NOT NULL
            );
            CREATE TABLE rules (
                rule_id TEXT PRIMARY KEY,
                reviewer TEXT NOT NULL,
                project TEXT,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                version INTEGER NOT NULL,
                data_json TEXT NOT NULL
            );
            CREATE TABLE rule_versions (
                rule_id TEXT NOT NULL,
                version INTEGER NOT NULL,
                changed_at TEXT NOT NULL,
                snapshot_json TEXT NOT NULL,
                PRIMARY KEY (rule_id, version)
            );
            """
        )
        conn.execute(
            "INSERT INTO feedback_events(event_id, reviewer, created_at, data_json) VALUES (?, ?, ?, ?)",
            ("evt_v1", "reviewer_old", "2025-01-01", '{"event_id": "evt_v1", "timestamp": "2025-01-01", "reviewer": "reviewer_old", "evidence_level": "L1_DIRECT_QUOTE", "topic_context": "", "raw_content": "old", "extracted_intent": "old"}'),
        )
        conn.commit()
        conn.close()

        # Opening with MemoryStore triggers automatic V2 migrations
        store = MemoryStore(self.db_path)
        v1_evt = store.get_event("evt_v1")
        self.assertIsNotNone(v1_evt)
        self.assertEqual(v1_evt.event_id, "evt_v1")

        # Verify schema_migrations table records migration
        with store._lock:
            cur = store._connection.execute("SELECT version, description FROM schema_migrations WHERE version = 2")
            row = cur.fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row["version"], 2)
