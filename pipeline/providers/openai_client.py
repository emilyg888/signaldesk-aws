from __future__ import annotations

import json
import logging
from typing import Any

from openai import OpenAI

from pipeline.ai_client_contract import AIClient
from pipeline.config_contract import ModelSettings, RuntimeSecrets
from pipeline.safety.policy import SafetyPolicy
from pipeline.safety.schemas import AnalysisRequest, AnalysisResponse, EarningsStoryRequest, EarningsStoryResponse, NewsDraftRequest, NewsDraftResponse, SentimentRequest, SentimentResponse
from pipeline.safety.validator import RequestSafetyValidator, parse_json_object, validate_model_input, validate_model_output
from pipeline.providers.bedrock_client import _fallback_analysis, _fallback_earnings_story, _fallback_news_draft

log = logging.getLogger(__name__)


class OpenAIClient(AIClient):
    """Optional local/dev AI provider with the same validation gates as Bedrock."""

    def __init__(self, *, model_settings: ModelSettings | None = None, secrets: RuntimeSecrets | None = None, policy: SafetyPolicy | None = None) -> None:
        self.model_settings = model_settings or ModelSettings()
        self.secrets = secrets or RuntimeSecrets()
        self.safety = RequestSafetyValidator(policy or SafetyPolicy())
        self._client = OpenAI(api_key=self.secrets.openai_api_key) if self.secrets.openai_api_key else None

    def score_sentiment_batch(self, *, ticker: str, source_name: str, texts: list[str]) -> dict[str, Any]:
        request = validate_model_input(SentimentRequest, {"ticker": ticker, "source_name": source_name, "texts": texts}, safety=self.safety, endpoint="sentiment")
        return self._invoke_json("sentiment", request.model_dump(), SentimentResponse, {"score": 50, "label": "Neutral", "key_themes": []}, self.model_settings.openai_sentiment_model)

    def generate_analysis(self, *, ticker: str, price_data: dict[str, Any], technicals: dict[str, Any], sentiment: dict[str, Any], macro: dict[str, Any]) -> dict[str, Any]:
        request = validate_model_input(AnalysisRequest, {"ticker": ticker, "price_data": price_data, "technicals": technicals, "sentiment": sentiment, "macro": macro}, safety=self.safety, endpoint="analysis")
        return self._invoke_json("analysis", request.model_dump(), AnalysisResponse, _fallback_analysis(ticker, technicals, sentiment), self.model_settings.openai_analysis_model)

    def generate_earnings_story(self, *, ticker: str, run_data: dict[str, Any]) -> dict[str, Any]:
        request = validate_model_input(EarningsStoryRequest, {"ticker": ticker, "run_data": run_data}, safety=self.safety, endpoint="earnings_story")
        return self._invoke_json("earnings_story", request.model_dump(), EarningsStoryResponse, _fallback_earnings_story(ticker, run_data), self.model_settings.openai_content_model)

    def generate_news_draft(self, *, ticker: str, run_data: dict[str, Any]) -> dict[str, Any]:
        request = validate_model_input(NewsDraftRequest, {"ticker": ticker, "run_data": run_data}, safety=self.safety, endpoint="news_draft")
        return self._invoke_json("news_draft", request.model_dump(), NewsDraftResponse, _fallback_news_draft(ticker, run_data), self.model_settings.openai_content_model)

    def _invoke_json(self, task: str, payload: dict[str, Any], schema, fallback: dict[str, Any], model: str) -> dict[str, Any]:
        if self._client is None:
            return fallback
        prompt = json.dumps({"task": task, "payload": payload, "format": "Return JSON only."}, default=str)
        try:
            resp = self._client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=self.model_settings.temperature,
                max_tokens=self.model_settings.max_tokens,
            )
            return validate_model_output(schema, parse_json_object(resp.choices[0].message.content or "{}"))
        except Exception as exc:
            log.warning("openai_generation_fallback task=%s error=%s", task, exc)
            return fallback
