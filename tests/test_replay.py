"""Tests for ReplayEngine chronological verification and regression safety."""

import tempfile
import unittest
from pathlib import Path

from bossalign import MemoryStore, ReplayEngine, ReplayStep


class TestReplayEngine(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.db = Path(self.tempdir.name) / "replay.sqlite3"

    def tearDown(self):
        MemoryStore.close_all()

    def test_chronological_replay_validates_revocation_and_regression_safety(self):
        steps = [
            # 1. Ingest initial preference
            ReplayStep(
                step_id="step_1",
                action="ingest",
                payload={
                    "feedback": "Never use the word 'guaranteed' in customer documentation.",
                    "reviewer": "actor_A",
                    "alias": "rule_guaranteed",
                    "confirm": True,
                    "context": {
                        "applicable_scope": {"project": "proj_alpha", "audience": "customer"},
                        "deterministic_checks": ["guaranteed"],
                    },
                },
                expected={"status": "confirmed"},
            ),
            # 2. Evaluate task: rule must be active
            ReplayStep(
                step_id="step_2",
                action="evaluate_task",
                payload={"task": {"project": "proj_alpha", "audience": "customer"}},
                expected={"expected_effective_aliases": ["rule_guaranteed"]},
            ),
            # 3. Check output: must find violation
            ReplayStep(
                step_id="step_3",
                action="check_output",
                payload={
                    "task": {"project": "proj_alpha", "audience": "customer"},
                    "output": "We offer guaranteed uptime for all clients.",
                },
                expected={"status": "violations_found", "violations_count": 1},
            ),
            # 4. Revoke the rule
            ReplayStep(
                step_id="step_4",
                action="revoke",
                payload={"alias": "rule_guaranteed", "revoked_by": "actor_A", "reason": "Relaxed policy"},
                expected={"status": "revoked"},
            ),
            # 5. Evaluate task again: revoked rule MUST NOT be effective
            ReplayStep(
                step_id="step_5",
                action="evaluate_task",
                payload={
                    "task": {"project": "proj_alpha", "audience": "customer"},
                    "must_not_include_aliases": ["rule_guaranteed"],
                },
            ),
        ]

        engine = ReplayEngine(str(self.db))
        report = engine.run(steps)

        self.assertTrue(report.passed, report.summary)
        self.assertEqual(report.total_steps, 5)
        self.assertEqual(report.passed_steps, 5)
        self.assertEqual(len(report.regressions), 0)
