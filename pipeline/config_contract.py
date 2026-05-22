from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class ModelSettings:
    bedrock_model_id: str = "amazon.nova-lite-v1:0"
    openai_analysis_model: str = "gpt-4o-mini"
    openai_sentiment_model: str = "gpt-4o-mini"
    openai_content_model: str = "gpt-4o-mini"
    temperature: float = 0.2
    max_tokens: int = 1200


@dataclass(frozen=True)
class PipelineSettings:
    weights: dict[str, float] = field(default_factory=lambda: {"technical": 0.40, "sentiment": 0.35, "macro": 0.25})
    lookback_days: int = 60
    forecast_days: int = 5
    news_max_items: int = 20


@dataclass(frozen=True)
class SafetySettings:
    denied_terms: tuple[str, ...] = ()
    allowed_topics: tuple[str, ...] = ()


@dataclass(frozen=True)
class RuntimeSecrets:
    fred_api_key: str = ""
    newsapi_key: str = ""
    discord_webhook_url: str = ""
    openai_api_key: str = ""


class ConfigProvider(Protocol):
    def model_settings(self) -> ModelSettings: ...
    def pipeline_settings(self) -> PipelineSettings: ...
    def safety_settings(self) -> SafetySettings: ...
    def secrets(self) -> RuntimeSecrets: ...
    def default_watchlist(self) -> list[str]: ...
