#!/usr/bin/env python3
from __future__ import annotations

import os
from pathlib import Path

import aws_cdk as cdk
from dotenv import load_dotenv

from stacks.api_stack import SignalDeskApiStack
from stacks.core_stack import SignalDeskCoreStack
from stacks.dashboard_stack import SignalDeskDashboardStack
from stacks.pipeline_stack import SignalDeskPipelineStack

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

app = cdk.App()
env = cdk.Environment(account=os.getenv("CDK_DEFAULT_ACCOUNT"), region=os.getenv("CDK_DEFAULT_REGION", os.getenv("AWS_REGION", "us-east-1")))

core = SignalDeskCoreStack(app, "SignalDeskCoreStack", env=env, description="SignalDesk shared state, secrets, and settings.")
pipeline = SignalDeskPipelineStack(app, "SignalDeskPipelineStack", env=env, table=core.table, secret=core.secret, settings_param=core.settings_param, denylist_param=core.denylist_param, allowed_topics_param=core.allowed_topics_param, description="SignalDesk scheduled pipeline runtime.")
api = SignalDeskApiStack(app, "SignalDeskApiStack", env=env, table=core.table, secret=core.secret, settings_param=core.settings_param, denylist_param=core.denylist_param, allowed_topics_param=core.allowed_topics_param, pipeline_function=pipeline.pipeline_function, description="SignalDesk private admin API.")
SignalDeskDashboardStack(app, "SignalDeskDashboardStack", env=env, api=api.api, user_pool=api.user_pool, user_pool_client=api.user_pool_client, description="SignalDesk CloudFront dashboard and same-origin API routing.")

app.synth()
