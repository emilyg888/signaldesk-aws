from __future__ import annotations

import json
import os
from functools import cached_property
from typing import Any

import boto3

from pipeline.config_contract import ConfigProvider, ModelSettings, PipelineSettings, RuntimeSecrets, SafetySettings
from pipeline.safety.policy import DEFAULT_ALLOWED_TOPICS, DEFAULT_FORBIDDEN_TERMS


class AWSConfigProvider(ConfigProvider):
    def __init__(self, region_name: str | None = None) -> None:
        self.region_name = region_name or os.getenv("AWS_REGION", "us-east-1")
        self.settings_param = os.getenv("SIGNALDESK_SETTINGS_PARAM", "/signaldesk/dev/settings")
        self.secret_name = os.getenv("SIGNALDESK_SECRET_NAME", "/signaldesk/dev/secrets")
        self.denylist_param = os.getenv("SIGNALDESK_SAFETY_DENYLIST_PARAM", "/signaldesk/dev/safety/denylist")
        self.allowed_topics_param = os.getenv("SIGNALDESK_ALLOWED_TOPICS_PARAM", "/signaldesk/dev/safety/allowed-topics")

    @cached_property
    def _ssm(self):
        return boto3.client("ssm", region_name=self.region_name)

    @cached_property
    def _secrets(self):
        return boto3.client("secretsmanager", region_name=self.region_name)

    @cached_property
    def _settings(self) -> dict[str, Any]:
        try:
            raw = self._ssm.get_parameter(Name=self.settings_param)["Parameter"]["Value"]
            return json.loads(raw)
        except Exception:
            return {}

    @cached_property
    def _secret_payload(self) -> dict[str, Any]:
        try:
            raw = self._secrets.get_secret_value(SecretId=self.secret_name).get("SecretString", "{}")
            return json.loads(raw)
        except Exception:
            return {}

    def _string_list_param(self, name: str, fallback: tuple[str, ...]) -> tuple[str, ...]:
        try:
            raw = self._ssm.get_parameter(Name=name)["Parameter"]["Value"]
            if raw.strip().startswith("["):
                return tuple(json.loads(raw))
            return tuple(item.strip() for item in raw.split(",") if item.strip())
        except Exception:
            return fallback

    def model_settings(self) -> ModelSettings:
        model = self._settings.get("model", {})
        return ModelSettings(
            bedrock_model_id=os.getenv("BEDROCK_MODEL_ID") or model.get("bedrock_model_id", "amazon.nova-lite-v1:0"),
            temperature=float(model.get("temperature", 0.2)),
            max_tokens=int(model.get("max_tokens", 1200)),
        )

    def pipeline_settings(self) -> PipelineSettings:
        settings = self._settings.get("pipeline", {})
        return PipelineSettings(
            weights=settings.get("weights", {"technical": 0.40, "sentiment": 0.35, "macro": 0.25}),
            lookback_days=int(settings.get("lookback_days", 60)),
            forecast_days=int(settings.get("forecast_days", 5)),
            news_max_items=int(settings.get("news_max_items", 20)),
        )

    def safety_settings(self) -> SafetySettings:
        return SafetySettings(
            denied_terms=self._string_list_param(self.denylist_param, DEFAULT_FORBIDDEN_TERMS),
            allowed_topics=self._string_list_param(self.allowed_topics_param, DEFAULT_ALLOWED_TOPICS),
        )

    def secrets(self) -> RuntimeSecrets:
        payload = self._secret_payload
        return RuntimeSecrets(
            fred_api_key=payload.get("fred_api_key", ""),
            newsapi_key=payload.get("newsapi_key", ""),
            discord_webhook_url=payload.get("discord_webhook_url", ""),
            openai_api_key=payload.get("openai_api_key", ""),
        )

    def default_watchlist(self) -> list[str]:
        return list(self._settings.get("default_watchlist", ["AAPL", "NVDA", "TSLA", "BTC-USD", "EURUSD=X"]))
