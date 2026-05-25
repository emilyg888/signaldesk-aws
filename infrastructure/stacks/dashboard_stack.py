from __future__ import annotations

from pathlib import Path

from aws_cdk import CfnOutput, Duration, RemovalPolicy, Stack, aws_apigateway as apigw, aws_cloudfront as cloudfront, aws_cloudfront_origins as origins, aws_cognito as cognito, aws_s3 as s3, aws_s3_deployment as s3deploy
from constructs import Construct


class SignalDeskDashboardStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, *, api: apigw.RestApi, user_pool: cognito.IUserPool, user_pool_client: cognito.IUserPoolClient, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        project_root = Path(__file__).resolve().parents[2]
        bucket = s3.Bucket(self, "DashboardBucket", block_public_access=s3.BlockPublicAccess.BLOCK_ALL, encryption=s3.BucketEncryption.S3_MANAGED, enforce_ssl=True, removal_policy=RemovalPolicy.RETAIN)
        api_domain = f"{api.rest_api_id}.execute-api.{self.region}.amazonaws.com"
        distribution = cloudfront.Distribution(
            self,
            "DashboardDistribution",
            default_behavior=cloudfront.BehaviorOptions(origin=origins.S3BucketOrigin.with_origin_access_control(bucket), viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS),
            additional_behaviors={
                "api/*": cloudfront.BehaviorOptions(
                    origin=origins.HttpOrigin(api_domain, origin_path=f"/{api.deployment_stage.stage_name}"),
                    allowed_methods=cloudfront.AllowedMethods.ALLOW_ALL,
                    cached_methods=cloudfront.CachedMethods.CACHE_GET_HEAD_OPTIONS,
                    cache_policy=cloudfront.CachePolicy.CACHING_DISABLED,
                    origin_request_policy=cloudfront.OriginRequestPolicy.ALL_VIEWER_EXCEPT_HOST_HEADER,
                    viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                )
            },
            default_root_object="index.html",
            error_responses=[cloudfront.ErrorResponse(http_status=403, response_http_status=200, response_page_path="/index.html", ttl=Duration.minutes(5))],
        )
        s3deploy.BucketDeployment(self, "DashboardDeploy", sources=[s3deploy.Source.asset(str(project_root / "dashboard"))], destination_bucket=bucket, distribution=distribution)
        CfnOutput(self, "DashboardUrl", value=f"https://{distribution.distribution_domain_name}")
        CfnOutput(self, "CognitoUserPoolId", value=user_pool.user_pool_id)
        CfnOutput(self, "CognitoClientId", value=user_pool_client.user_pool_client_id)
