from __future__ import annotations

import json
import os

from aws_cdk import CfnOutput, RemovalPolicy, Stack, aws_dynamodb as dynamodb, aws_secretsmanager as secretsmanager, aws_ssm as ssm
from constructs import Construct

from pipeline.safety.policy import DEFAULT_ALLOWED_TOPICS, DEFAULT_FORBIDDEN_TERMS


class SignalDeskCoreStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.table = dynamodb.Table(
            self,
            "SignalDeskTable",
            partition_key=dynamodb.Attribute(name="PK", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="SK", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            point_in_time_recovery=True,
            removal_policy=RemovalPolicy.RETAIN,
        )

        self.secret = secretsmanager.Secret(
            self,
            "SignalDeskRuntimeSecrets",
            secret_name=os.getenv("SIGNALDESK_SECRET_NAME", "/signaldesk/dev/secrets"),
            description="SignalDesk external API keys and webhook URLs. Seed values after deploy; do not commit secrets.",
            generate_secret_string=secretsmanager.SecretStringGenerator(
                secret_string_template=json.dumps({"fred_api_key": "", "newsapi_key": "", "x_bearer_token": "", "discord_webhook_url": "", "openai_api_key": ""}),
                generate_string_key="placeholder",
            ),
        )

        self.settings_param = ssm.StringParameter(
            self,
            "SettingsParam",
            parameter_name=os.getenv("SIGNALDESK_SETTINGS_PARAM", "/signaldesk/dev/settings"),
            string_value=json.dumps({
                "model": {"bedrock_model_id": os.getenv("BEDROCK_MODEL_ID", "amazon.nova-lite-v1:0"), "temperature": 0.2, "max_tokens": 1200},
                "pipeline": {"weights": {"technical": 0.40, "sentiment": 0.35, "macro": 0.25}, "lookback_days": 60, "forecast_days": 5, "news_max_items": 20},
                "default_watchlist": ["AAPL", "NVDA", "TSLA", "BTC-USD", "EURUSD=X"],
            }),
        )
        self.denylist_param = ssm.StringParameter(self, "SafetyDenylistParam", parameter_name=os.getenv("SIGNALDESK_SAFETY_DENYLIST_PARAM", "/signaldesk/dev/safety/denylist"), string_value=json.dumps(list(DEFAULT_FORBIDDEN_TERMS)))
        self.allowed_topics_param = ssm.StringParameter(self, "AllowedTopicsParam", parameter_name=os.getenv("SIGNALDESK_ALLOWED_TOPICS_PARAM", "/signaldesk/dev/safety/allowed-topics"), string_value=json.dumps(list(DEFAULT_ALLOWED_TOPICS)))

        CfnOutput(self, "TableName", value=self.table.table_name)
        CfnOutput(self, "SecretName", value=self.secret.secret_name)
        CfnOutput(self, "SettingsParamName", value=self.settings_param.parameter_name)
