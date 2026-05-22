from __future__ import annotations

import json
import os
from pathlib import Path

from pipeline.config_contract import ConfigProvider, ModelSettings, PipelineSettings, RuntimeSecrets, SafetySettings
from pipeline.safety.policy import DEFAULT_ALLOWED_TOPICS, DEFAULT_FORBIDDEN_TERMS


class LocalConfigProvider(ConfigProvider):
    def model_settings(self) -> ModelSettings:
        return ModelSettings(
            bedrock_model_id=os.getenv("BEDROCK_MODEL_ID", "amazon.nova-lite-v1:0"),
            openai_analysis_model=os.getenv("OPENAI_ANALYSIS_MODEL", "gpt-4o-mini"),
            openai_sentiment_model=os.getenv("OPENAI_SENTIMENT_MODEL", "gpt-4o-mini"),
            openai_content_model=os.getenv("OPENAI_CONTENT_MODEL", "gpt-4o-mini"),
            temperature=float(os.getenv("SIGNALDESK_TEMPERATURE", "0.2")),
            max_tokens=int(os.getenv("SIGNALDESK_MAX_TOKENS", "1200")),
        )

    def pipeline_settings(self) -> PipelineSettings:
        return PipelineSettings()

    def safety_settings(self) -> SafetySettings:
        denied = tuple(filter(None, (item.strip() for item in os.getenv("SIGNALDESK_DENIED_TERMS", "").split(","))))
        allowed = tuple(filter(None, (item.strip() for item in os.getenv("SIGNALDESK_ALLOWED_TOPICS", "").split(","))))
        return SafetySettings(denied_terms=denied or DEFAULT_FORBIDDEN_TERMS, allowed_topics=allowed or DEFAULT_ALLOWED_TOPICS)

    def secrets(self) -> RuntimeSecrets:
        return RuntimeSecrets(
            fred_api_key=os.getenv("FRED_API_KEY", ""),
            newsapi_key=os.getenv("NEWSAPI_KEY", ""),
            discord_webhook_url=os.getenv("DISCORD_WEBHOOK_URL", ""),
            openai_api_key=os.getenv("OPENAI_API_KEY", ""),
        )

    def default_watchlist(self) -> list[str]:
        watchlist_file = Path(os.getenv("SIGNALDESK_WATCHLIST_FILE", "data/watchlist.json"))
        if watchlist_file.exists():
            return json.loads(watchlist_file.read_text())
        return ["AAPL", "NVDA", "TSLA", "BTC-USD", "EURUSD=X"]
