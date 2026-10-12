import json
from io import BytesIO
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

from bossalign import BossAlign
from bossalign.providers import OpenAICompatibleProvider
from bossalign.schema import RuleStatus, TaskContext


class InferenceProvider:
    def parse_feedback(self, feedback, reviewer, context):
        return {
            "directive": "Keep technical parameters in the report.",
            "origin": "ai_inference",
            "confidence": 0.99,
            "applicable_scope": {"task_type": "technical_report"},
            "negative_boundaries": [],
            "deterministic_checks": [],
            "conflict_key": "technical_parameters",
            "effect": "include",
        }

    def review_output(self, task, output, rules):
        return []


class TestProvider(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.tmp_path = Path(self.tempdir.name)

    def test_ai_inference_stays_draft_and_cannot_override_confirmed_instruction(self):
        client = BossAlign(self.tmp_path / "memory.sqlite3")
        explicit = client.ingest(
            "Do not include technical parameters in consumer copy.",
            reviewer="reviewer-a",
            context={
                "applicable_scope": {"task_type": "technical_report"},
                "conflict_key": "technical_parameters",
                "effect": "avoid",
            },
            confirm=True,
        )
        client.provider = InferenceProvider()
        inferred = client.ingest("Some related feedback", reviewer="reviewer-a")

        selection = client.retrieve(TaskContext(task_type="technical_report"))

        self.assertEqual(explicit.status, RuleStatus.CONFIRMED)
        self.assertEqual(inferred.status, RuleStatus.DRAFT)
        self.assertEqual([rule.rule_id for rule in selection.active_rules], [explicit.rule_id])
        self.assertEqual(selection.conflicts, [])


    def test_openai_compatible_provider_uses_chat_completions_contract(self):
        reply = {
            "directive": "Avoid the phrase 'guaranteed zero downtime'.",
            "origin": "explicit_instruction",
            "confidence": 0.9,
            "applicable_scope": {"audience": "consumer"},
            "negative_boundaries": [{"task_type": "incident_report"}],
            "deterministic_checks": ["guaranteed zero downtime"],
            "conflict_key": "downtime_claim",
            "effect": "avoid",
        }
        body = json.dumps({"choices": [{"message": {"content": json.dumps(reply)}}]}).encode()
        provider = OpenAICompatibleProvider(
            "https://provider.invalid/v1",
            "test-model",
            api_key="test-only-key",
        )
        with patch("bossalign.providers.urlopen", return_value=BytesIO(body)) as mocked_urlopen:
            result = provider.parse_feedback("feedback", "reviewer-a", {})

        request = mocked_urlopen.call_args.args[0]
        request_body = json.loads(request.data.decode("utf-8"))
        self.assertEqual(result["directive"], reply["directive"])
        self.assertEqual(request.full_url, "https://provider.invalid/v1/chat/completions")
        self.assertEqual(request.get_header("Authorization"), "Bearer test-only-key")
        self.assertEqual(request_body["model"], "test-model")
