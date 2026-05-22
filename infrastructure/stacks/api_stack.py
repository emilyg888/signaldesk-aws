from __future__ import annotations

import os
from pathlib import Path

from aws_cdk import CfnOutput, Duration, RemovalPolicy, Stack, aws_apigateway as apigw, aws_cognito as cognito, aws_dynamodb as dynamodb, aws_iam as iam, aws_lambda as lambda_, aws_logs as logs, aws_secretsmanager as secretsmanager, aws_ssm as ssm
from constructs import Construct

_ASSET_EXCLUDE = [".git", ".git/*", ".venv", ".venv/*", "cdk.out", "cdk.out/*", "logs", "logs/*", "data/db", "data/db/*", "data/cache", "data/cache/*", "pipeline/config.py", ".env", ".env.*", "**/__pycache__", "**/*.pyc"]


class SignalDeskApiStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, *, table: dynamodb.ITable, secret: secretsmanager.ISecret, settings_param: ssm.IStringParameter, denylist_param: ssm.IStringParameter, allowed_topics_param: ssm.IStringParameter, pipeline_function: lambda_.IFunction, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        project_root = Path(__file__).resolve().parents[2]
        self.user_pool = cognito.UserPool(self, "AdminUserPool", self_sign_up_enabled=False, sign_in_aliases=cognito.SignInAliases(email=True), removal_policy=RemovalPolicy.RETAIN)
        self.user_pool_client = self.user_pool.add_client("DashboardClient", auth_flows=cognito.AuthFlow(user_password=True, user_srp=True))
        authorizer = apigw.CognitoUserPoolsAuthorizer(self, "Authorizer", cognito_user_pools=[self.user_pool])
        self.api = apigw.RestApi(self, "SignalDeskApi", rest_api_name="SignalDesk API", deploy_options=apigw.StageOptions(stage_name="prod", metrics_enabled=True, logging_level=apigw.MethodLoggingLevel.INFO))

        env = {
            "SIGNALDESK_RUNTIME": "aws",
            "SIGNALDESK_TABLE_NAME": table.table_name,
            "SIGNALDESK_SECRET_NAME": secret.secret_name,
            "SIGNALDESK_SETTINGS_PARAM": settings_param.parameter_name,
            "SIGNALDESK_SAFETY_DENYLIST_PARAM": denylist_param.parameter_name,
            "SIGNALDESK_ALLOWED_TOPICS_PARAM": allowed_topics_param.parameter_name,
            "SIGNALDESK_PIPELINE_FUNCTION_NAME": pipeline_function.function_name,
            "BEDROCK_MODEL_ID": os.getenv("BEDROCK_MODEL_ID", "amazon.nova-lite-v1:0"),
        }

        def fn(name: str, handler: str, bedrock: bool = False) -> lambda_.Function:
            function = lambda_.Function(self, name, runtime=lambda_.Runtime.PYTHON_3_12, handler=handler, code=lambda_.Code.from_asset(str(project_root), exclude=_ASSET_EXCLUDE), timeout=Duration.seconds(30), memory_size=512, environment=env)
            table.grant_read_write_data(function)
            secret.grant_read(function)
            for param in (settings_param, denylist_param, allowed_topics_param):
                param.grant_read(function)
            if bedrock:
                function.add_to_role_policy(iam.PolicyStatement(actions=["bedrock:InvokeModel", "bedrock:Converse"], resources=["*"]))
            logs.LogGroup(self, f"{name}LogGroup", log_group_name=f"/aws/lambda/{function.function_name}", retention=logs.RetentionDays.ONE_WEEK, removal_policy=RemovalPolicy.DESTROY)
            return function

        status_fn = fn("StatusHandler", "api.handlers.status.handler")
        dashboard_fn = fn("DashboardHandler", "api.handlers.dashboard.handler")
        detail_fn = fn("TickerDetailHandler", "api.handlers.ticker_detail.detail_handler")
        history_fn = fn("TickerHistoryHandler", "api.handlers.ticker_detail.history_handler")
        get_watchlist_fn = fn("GetWatchlistHandler", "api.handlers.watchlist.get_handler")
        update_watchlist_fn = fn("UpdateWatchlistHandler", "api.handlers.watchlist.update_handler")
        manual_run_fn = fn("ManualRunHandler", "api.handlers.manual_run.handler")
        run_status_fn = fn("RunStatusHandler", "api.handlers.run_status.handler")
        earnings_fn = fn("EarningsStoryHandler", "api.handlers.content.earnings_story_handler", bedrock=True)
        news_fn = fn("NewsDraftHandler", "api.handlers.content.news_draft_handler", bedrock=True)
        pipeline_function.grant_invoke(manual_run_fn)

        auth = {"authorizer": authorizer, "authorization_type": apigw.AuthorizationType.COGNITO}
        api_root = self.api.root.add_resource("api")
        api_root.add_resource("status").add_method("GET", apigw.LambdaIntegration(status_fn), **auth)
        api_root.add_resource("dashboard").add_method("GET", apigw.LambdaIntegration(dashboard_fn), **auth)
        watchlist = api_root.add_resource("watchlist")
        watchlist.add_method("GET", apigw.LambdaIntegration(get_watchlist_fn), **auth)
        watchlist.add_method("POST", apigw.LambdaIntegration(update_watchlist_fn), **auth)
        run = api_root.add_resource("run")
        run.add_method("POST", apigw.LambdaIntegration(manual_run_fn), **auth)
        run.add_resource("{run_id}").add_method("GET", apigw.LambdaIntegration(run_status_fn), **auth)
        ticker = api_root.add_resource("ticker").add_resource("{ticker}")
        ticker.add_method("GET", apigw.LambdaIntegration(detail_fn), **auth)
        ticker.add_resource("history").add_method("GET", apigw.LambdaIntegration(history_fn), **auth)
        ticker.add_resource("earnings-story").add_method("POST", apigw.LambdaIntegration(earnings_fn), **auth)
        ticker.add_resource("news-draft").add_method("POST", apigw.LambdaIntegration(news_fn), **auth)

        CfnOutput(self, "ApiUrl", value=self.api.url)
        CfnOutput(self, "UserPoolId", value=self.user_pool.user_pool_id)
        CfnOutput(self, "UserPoolClientId", value=self.user_pool_client.user_pool_client_id)
