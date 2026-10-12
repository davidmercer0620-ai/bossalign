"""Feedback and review providers.

The built-in provider is deterministic and deliberately conservative. It is
useful offline and in tests, but it does not claim to understand arbitrary
natural language. OpenAI-compatible services can be selected explicitly.
"""

import json
import os
import re
from typing import Any, Dict, List, Mapping, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class FeedbackProvider(Protocol):
    semantic_review_enabled: bool

    def parse_feedback(self, feedback: str, reviewer: str, context: Mapping[str, Any]) -> Dict[str, Any]:
        ...

    def review_output(self, task: Mapping[str, Any], output: str, rules: List[Mapping[str, Any]]) -> List[Dict[str, Any]]:
        ...


class DeterministicProvider:
    """Offline, rule-based proposal parser; never promotes rules by itself."""

    semantic_review_enabled = False
    data_local = True
    _hypothesis = re.compile(r"\b(maybe|perhaps|might|could consider|i wonder)\b|也许|可能|要不要|是不是", re.I)
    _preference = re.compile(r"\b(i prefer|prefer|usually|tend to)\b|我更喜欢|我偏好|通常希望|一般希望", re.I)
    _instruction = re.compile(
        r"\b(must|always|never|do not|don't|avoid|keep|include|remove|use)\b|必须|务必|禁止|不要|别|避免|保留|加入|删除|请",
        re.I,
    )
    _negative = re.compile(r"\b(avoid|never|do not|don't|remove|exclude)\b|不要|别|禁止|避免|删除|剔除", re.I)
    _quotes = re.compile(r"'([^']{1,100})'|\"([^\"]{1,100})\"|[“‘「『]([^”’」』]{1,100})[”’」』]")

    def parse_feedback(self, feedback: str, reviewer: str, context: Mapping[str, Any]) -> Dict[str, Any]:
        text = feedback.strip()
        if not text:
            raise ValueError("Feedback cannot be empty")

        if self._hypothesis.search(text):
            origin, confidence = "hypothesis", 0.35
        elif self._preference.search(text):
            origin, confidence = "user_preference", 0.72
        elif self._instruction.search(text):
            origin, confidence = "explicit_instruction", 0.82
        else:
            # This is a parser uncertainty, not a claim that the user said it.
            origin, confidence = "hypothesis", 0.25

        scope = context.get("applicable_scope")
        if not isinstance(scope, Mapping):
            scope_keys = (
                "project", "task_type", "topic", "audience", "objective", "task_id",
                "interaction_context", "tags",
            )
            scope = {key: context[key] for key in scope_keys if context.get(key) not in (None, "", [])}
        else:
            scope = dict(scope)

        # Phrase checks are explicit caller configuration. Do not mistake a
        # quoted example, exception, or counter-example for a violation term.
        checks = context.get("deterministic_checks", [])
        if checks is None:
            checks = []

        effect = context.get("effect")
        if not effect:
            effect = "avoid" if self._negative.search(text) else "include" if self._instruction.search(text) else ""

        quoted = next((next((part for part in m.groups() if part), "").strip() for m in self._quotes.finditer(text)), "")
        conflict_key = context.get("conflict_key") or re.sub(r"\W+", "_", quoted.casefold()).strip("_")
        boundaries = context.get("negative_boundaries", [])
        if not isinstance(boundaries, list):
            boundaries = []

        return {
            "directive": str(context.get("directive") or text),
            "origin": str(context.get("origin") or origin),
            "confidence": float(context.get("confidence", confidence)),
            "applicable_scope": dict(scope),
            "negative_boundaries": boundaries,
            "deterministic_checks": [str(item) for item in checks if str(item).strip()],
            "conflict_key": str(conflict_key or ""),
            "effect": str(effect or ""),
            "communicative_intent": str(context.get("communicative_intent") or "unspecified"),
            "rule_candidate": context.get("rule_candidate", True),
            "valid_from": context.get("valid_from"),
            "valid_until": context.get("valid_until"),
            "assumptions": ["Offline parser; inferred scope is limited to structured context supplied by the caller."],
        }

    def review_output(self, task: Mapping[str, Any], output: str, rules: List[Mapping[str, Any]]) -> List[Dict[str, Any]]:
        # Semantic review is intentionally absent in offline mode.
        return []


class OpenAICompatibleProvider:
    """Small adapter for providers exposing the OpenAI Chat Completions API."""

    semantic_review_enabled = True
    data_local = False

    def __init__(self, base_url: str, model: str, api_key: str, timeout: float = 30.0):
        if not base_url.strip() or not model.strip() or not api_key:
            raise ValueError("base_url, model, and api_key are required")
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._api_key = api_key
        self.timeout = timeout

    def _endpoint(self) -> str:
        if self.base_url.endswith("/chat/completions"):
            return self.base_url
        if self.base_url.endswith("/v1"):
            return self.base_url + "/chat/completions"
        return self.base_url + "/v1/chat/completions"

    def _request_json(self, system: str, payload: Mapping[str, Any]) -> Dict[str, Any]:
        body = json.dumps(
            {
                "model": self.model,
                "temperature": 0,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                ],
            },
            ensure_ascii=False,
        ).encode("utf-8")
        request = Request(
            self._endpoint(),
            data=body,
            headers={
                "Authorization": "Bearer " + self._api_key,
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                response_data = json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            raise RuntimeError("OpenAI-compatible request failed (HTTP %s)." % error.code) from None
        except (URLError, TimeoutError) as error:
            raise RuntimeError("OpenAI-compatible request failed: %s" % type(error).__name__) from None
        try:
            content = response_data["choices"][0]["message"]["content"]
            if not isinstance(content, str):
                raise TypeError("message content is not text")
            content = content.strip()
            if content.startswith("```"):
                content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content, flags=re.I)
            result = json.loads(content)
        except (KeyError, IndexError, TypeError, ValueError) as error:
            raise ValueError("Provider response did not contain valid JSON output: %s" % type(error).__name__) from None
        if not isinstance(result, dict):
            raise ValueError("Provider JSON response must be an object")
        return result

    def parse_feedback(self, feedback: str, reviewer: str, context: Mapping[str, Any]) -> Dict[str, Any]:
        return self._request_json(
            "Convert feedback into a proposed rule. Return only JSON with keys: directive, origin "
            "(explicit_instruction, user_preference, ai_inference, or hypothesis), confidence (0..1), "
            "applicable_scope (object), negative_boundaries (array of condition objects), deterministic_checks "
            "(array of exact phrases only when the feedback explicitly prohibits them), conflict_key, effect, "
            "communicative_intent, rule_candidate (false for expression or advice-seeking with no preference), "
            "valid_from, valid_until, assumptions. Distinguish direct expression, reported speech, and inference; "
            "do not treat third-party reports or inferred preferences as confirmed facts. Do not invent the preference owner. "
            "Do not infer a lasting rule from emotional expression or a request for advice. Do not invent confirmation. "
            "The caller will always store this proposal as draft.",
            {"feedback": feedback, "reviewer": reviewer, "context": dict(context)},
        )

    def review_output(self, task: Mapping[str, Any], output: str, rules: List[Mapping[str, Any]]) -> List[Dict[str, Any]]:
        result = self._request_json(
            "Review the output only against supplied rules and task context. Return JSON with key findings, "
            "an array of objects containing rule_id, severity (low/medium/high), evidence (verbatim substring "
            "from output), suggestion, and confidence (0..1). If evidence is absent, do not invent a violation. "
            "These are model findings, not user approval.",
            {"task": dict(task), "output": output, "rules": rules},
        )
        findings = result.get("findings", [])
        return findings if isinstance(findings, list) else []


def provider_from_env() -> FeedbackProvider:
    """Load a real provider only when explicitly configured by environment."""
    provider_name = os.environ.get("BOSSALIGN_PROVIDER", "offline").strip().lower()
    if provider_name in ("offline", "deterministic", "test"):
        return DeterministicProvider()
    if provider_name in ("openai", "openai-compatible"):
        api_key = os.environ.get("BOSSALIGN_API_KEY", "")
        if not api_key:
            raise ValueError("BOSSALIGN_API_KEY is required when BOSSALIGN_PROVIDER=openai")
        return OpenAICompatibleProvider(
            os.environ.get("BOSSALIGN_BASE_URL", "https://api.openai.com/v1"),
            os.environ.get("BOSSALIGN_MODEL", "gpt-4o-mini"),
            api_key,
        )
    raise ValueError("Unsupported BOSSALIGN_PROVIDER: %s" % provider_name)


# Clear name for applications which want to make the offline/test nature explicit.
TestProvider = DeterministicProvider
