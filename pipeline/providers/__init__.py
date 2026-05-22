from pipeline.providers.local_config import LocalConfigProvider
from pipeline.providers.local_storage import LocalStorageProvider

__all__ = [
    "LocalConfigProvider",
    "LocalStorageProvider",
    "AWSConfigProvider",
    "DynamoDBStorageProvider",
    "BedrockClient",
    "OpenAIClient",
]


def __getattr__(name):
    if name == "AWSConfigProvider":
        from pipeline.providers.aws_config import AWSConfigProvider
        return AWSConfigProvider
    if name == "DynamoDBStorageProvider":
        from pipeline.providers.dynamodb_storage import DynamoDBStorageProvider
        return DynamoDBStorageProvider
    if name == "BedrockClient":
        from pipeline.providers.bedrock_client import BedrockClient
        return BedrockClient
    if name == "OpenAIClient":
        from pipeline.providers.openai_client import OpenAIClient
        return OpenAIClient
    raise AttributeError(name)
