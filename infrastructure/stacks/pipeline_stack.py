from __future__ import annotations

import os
from pathlib import Path

from aws_cdk import CfnOutput, Duration, RemovalPolicy, Stack, aws_dynamodb as dynamodb, aws_events as events, aws_events_targets as targets, aws_iam as iam, aws_lambda as lambda_, aws_logs as logs, aws_sqs as sqs, aws_secretsmanager as secretsmanager, aws_ssm as ssm
from constructs import Construct

_ASSET_EXCLUDE = [
    ".git",
    ".git/*",
    ".venv",
    ".venv/*",
    "cdk.out",
    "cdk.out/*",
    "infrastructure/cdk.out",
    "infrastructure/cdk.out/*",
    "logs",
    "logs/*",
    "data/db",
    "data/db/*",
    "data/cache",
    "data/cache/*",
    ".env",
    ".env.*",
    "**/__pycache__",
    "**/*.pyc",
]


class SignalDeskPipelineStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, *, table: dynamodb.ITable, secret: secretsmanager.ISecret, settings_param: ssm.IStringParameter, denylist_param: ssm.IStringParameter, allowed_topics_param: ssm.IStringParameter, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        project_root = Path(__file__).resolve().parents[2]
        dlq = sqs.Queue(self, "PipelineDlq", retention_period=Duration.days(14))
        self.pipeline_function = lambda_.DockerImageFunction(
            self,
            "PipelineFunction",
            code=lambda_.DockerImageCode.from_image_asset(str(project_root), file="Dockerfile.pipeline", exclude=_ASSET_EXCLUDE),
            architecture=lambda_.Architecture.ARM_64,
            timeout=Duration.minutes(15),
            memory_size=2048,
            dead_letter_queue=dlq,
            environment={
                "SIGNALDESK_RUNTIME": "aws",
                "SIGNALDESK_TABLE_NAME": table.table_name,
                "SIGNALDESK_SECRET_NAME": secret.secret_name,
                "SIGNALDESK_SETTINGS_PARAM": settings_param.parameter_name,
                "SIGNALDESK_SAFETY_DENYLIST_PARAM": denylist_param.parameter_name,
                "SIGNALDESK_ALLOWED_TOPICS_PARAM": allowed_topics_param.parameter_name,
                "BEDROCK_MODEL_ID": os.getenv("BEDROCK_MODEL_ID", "amazon.nova-lite-v1:0"),
            },
        )
        table.grant_read_write_data(self.pipeline_function)
        secret.grant_read(self.pipeline_function)
        for param in (settings_param, denylist_param, allowed_topics_param):
            param.grant_read(self.pipeline_function)
        self.pipeline_function.add_to_role_policy(iam.PolicyStatement(actions=["bedrock:InvokeModel", "bedrock:Converse"], resources=["*"]))
        logs.LogGroup(self, "PipelineLogGroup", log_group_name=f"/aws/lambda/{self.pipeline_function.function_name}", retention=logs.RetentionDays.ONE_WEEK, removal_policy=RemovalPolicy.DESTROY)

        rule = events.Rule(
            self,
            "PipelineSchedule",
            schedule=events.Schedule.cron(minute="0", hour="20"),
            enabled=os.getenv("SIGNALDESK_PIPELINE_SCHEDULE_ENABLED", "false").lower() == "true",
        )
        rule.add_target(targets.LambdaFunction(self.pipeline_function, event=events.RuleTargetInput.from_object({"source": "eventbridge-schedule"})))
        CfnOutput(self, "PipelineFunctionName", value=self.pipeline_function.function_name)
        CfnOutput(self, "PipelineDlqUrl", value=dlq.queue_url)
