from __future__ import annotations

import os

from pipeline.config_contract import ConfigProvider
from pipeline.safety.policy import SafetyPolicy
from pipeline.providers.local_config import LocalConfigProvider
from pipeline.providers.local_storage import LocalStorageProvider


def runtime_mode() -> str:
    return os.getenv("SIGNALDESK_RUNTIME", "local").lower()


def get_config_provider() -> ConfigProvider:
    if runtime_mode() == "aws":
        from pipeline.providers.aws_config import AWSConfigProvider
        return AWSConfigProvider()
    return LocalConfigProvider()


def get_storage_provider():
    if runtime_mode() == "aws":
        from pipeline.providers.dynamodb_storage import DynamoDBStorageProvider
        return DynamoDBStorageProvider()
    return LocalStorageProvider()


def get_ai_client(config: ConfigProvider | None = None):
    config = config or get_config_provider()
    safety = config.safety_settings()
    policy = SafetyPolicy.from_settings(allowed_topics=safety.allowed_topics, denied_terms=safety.denied_terms)
    if runtime_mode() == "aws" or os.getenv("SIGNALDESK_AI_PROVIDER", "openai").lower() == "bedrock":
        from pipeline.providers.bedrock_client import BedrockClient
        return BedrockClient(model_settings=config.model_settings(), policy=policy)
    from pipeline.providers.openai_client import OpenAIClient
    return OpenAIClient(model_settings=config.model_settings(), secrets=config.secrets(), policy=policy)
