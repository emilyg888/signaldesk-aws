from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ValidationError

from pipeline.safety.policy import SafetyPolicy

log = logging.getLogger(__name__)


class SafetyError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class SafetyDecision:
    allowed: bool
    code: str = "ok"
    message: str = "allowed"


def _flatten_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return " ".join(_flatten_text(v) for v in value.values())
    if isinstance(value, (list, tuple, set)):
        return " ".join(_flatten_text(v) for v in value)
    return str(value)


class RequestSafetyValidator:
    def __init__(self, policy: SafetyPolicy | None = None) -> None:
        self.policy = policy or SafetyPolicy()

    def validate_or_raise(self, payload: Any, *, endpoint: str = "unknown", ticker: str | None = None, correlation_id: str | None = None) -> None:
        decision = self.evaluate(payload)
        if not decision.allowed:
            log.info(
                "safety_reject endpoint=%s ticker=%s correlation_id=%s reason=%s",
                endpoint,
                ticker or "",
                correlation_id or "",
                decision.code,
            )
            raise SafetyError(decision.code, decision.message)

    def evaluate(self, payload: Any) -> SafetyDecision:
        text = _flatten_text(payload).lower()
        compact = re.sub(r"\s+", " ", text)
        if not compact.strip():
            return SafetyDecision(False, "validation_failed", "Request content is empty.")

        for pattern in self.policy.prompt_injection_patterns:
            if pattern.lower() in compact:
                return SafetyDecision(False, "prompt_injection", "Prompt hijacking attempt rejected.")

        for term in self.policy.forbidden_terms:
            if term.lower() in compact:
                return SafetyDecision(False, "content_forbidden", "Request contains forbidden content.")

        if not any(topic.lower() in compact for topic in self.policy.allowed_topics):
            return SafetyDecision(False, "topic_not_allowed", "Request is outside SignalDesk finance workflows.")

        return SafetyDecision(True)


def validate_model_input(model_cls: type[BaseModel], payload: Any, *, safety: RequestSafetyValidator | None = None, endpoint: str = "unknown", correlation_id: str | None = None) -> BaseModel:
    try:
        parsed = model_cls.model_validate(payload)
    except ValidationError as exc:
        raise SafetyError("validation_failed", str(exc)) from exc
    (safety or RequestSafetyValidator()).validate_or_raise(parsed.model_dump(), endpoint=endpoint, correlation_id=correlation_id)
    return parsed


def parse_json_object(raw: str) -> dict[str, Any]:
    cleaned = raw.strip().replace("```json", "").replace("```", "").strip()
    return json.loads(cleaned)


def validate_model_output(model_cls: type[BaseModel], payload: Any) -> dict[str, Any]:
    try:
        return model_cls.model_validate(payload).model_dump()
    except ValidationError as exc:
        raise SafetyError("validation_failed", str(exc)) from exc
