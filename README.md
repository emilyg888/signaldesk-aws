# SignalDesk AWS

## Overview

SignalDesk AWS is a serverless AWS port of the SignalDesk market analysis
prototype. It runs a watchlist pipeline, computes technical and macro signals,
collects recent news, produces AI-assisted analysis, and serves a private admin
dashboard.

## Architecture Summary

| Capability | Implementation |
| --- | --- |
| Dashboard | S3 private bucket served by CloudFront |
| Same-origin API | CloudFront `/api/*` behavior routed to API Gateway |
| Authentication | Cognito private-admin user pool and app client |
| API compute | Python 3.12 Lambda handlers |
| Pipeline compute | Docker-image Lambda invoked manually or by EventBridge |
| Storage | Single-table DynamoDB |
| AI runtime | Amazon Bedrock in AWS mode; OpenAI remains available for local/provider fallback |
| Secrets | AWS Secrets Manager |
| Settings and safety policy | SSM Parameter Store |
| Observability | CloudWatch logs, API Gateway metrics, pipeline status rows, and SQS DLQ |

Full design details are in [design/architecture.md](/Users/emilygao/LocalDocuments/Projects/signaldesk-aws/design/architecture.md).

## Repository Structure

```text
api/              Lambda handlers and local FastAPI compatibility server
dashboard/        Static dashboard deployed to S3/CloudFront
design/           Architecture, implementation notes, and pending review issues
infrastructure/   CDK app and stack definitions
pipeline/         Market pipeline, providers, contracts, safety schemas, and storage
scripts/          Deploy, destroy, and watchlist seed helpers
tests/            Unit, handler, storage, safety, and SIT tests
```

## Setup

Use Python 3.12 for local development and tests:

```bash
make PYTHON=/Users/emilygao/miniconda3/envs/dev/bin/python install
```

Copy the sample environment file when deploying:

```bash
cp .env.example .env
```

Do not commit `.env`, deployment outputs, generated CDK output, or secret-bearing
files. The ignore rules cover these paths.

## Run And Deploy

```bash
make synth
make deploy
```

After deployment, repeat the manual AWS setup steps:

1. Create a Cognito admin user.
2. Seed `/signaldesk/dev/secrets` in Secrets Manager.
3. Seed the DynamoDB watchlist with `scripts/seed_watchlist.py`.
4. Invoke the pipeline once and verify dashboard/API data.

Destroy helpers are available:

```bash
make destroy
```

Some resources may be retained by AWS/CDK removal policies; clean them up
manually only when you intentionally want to remove stored data and bootstrap
assets.

## Test / SIT

```bash
make test
make synth
```

The test suite covers local API compatibility, Lambda handlers, DynamoDB model
behavior, storage, safety validation, technical indicators, notifications, and
SIT-level smoke coverage.

## Configuration

`.env.example` documents deployment variables:

| Variable | Purpose |
| --- | --- |
| `AWS_REGION` / `CDK_DEFAULT_REGION` | Deployment region |
| `SIGNALDESK_TABLE_NAME` | Local/default DynamoDB table reference |
| `SIGNALDESK_SECRET_NAME` | Secrets Manager secret name |
| `SIGNALDESK_SETTINGS_PARAM` | SSM settings parameter |
| `SIGNALDESK_SAFETY_DENYLIST_PARAM` | SSM forbidden-term policy parameter |
| `SIGNALDESK_ALLOWED_TOPICS_PARAM` | SSM allowed-topic policy parameter |
| `BEDROCK_MODEL_ID` | Bedrock model used for AWS AI generation |
| `X_BEARER_TOKEN` | Optional local X API token |
| `SIGNALDESK_PIPELINE_SCHEDULE_ENABLED` | Enables or disables the EventBridge schedule |

Secrets are stored in Secrets Manager with this shape:

```json
{
  "fred_api_key": "",
  "newsapi_key": "",
  "x_bearer_token": "",
  "discord_webhook_url": "",
  "openai_api_key": ""
}
```

## Documentation

- Architecture: [design/architecture.md](/Users/emilygao/LocalDocuments/Projects/signaldesk-aws/design/architecture.md)
- Pending review issues: [design/issues-pending-review.md](/Users/emilygao/LocalDocuments/Projects/signaldesk-aws/design/issues-pending-review.md)
- AWS porting plan: [design/plan_aws-porting.md](/Users/emilygao/LocalDocuments/Projects/signaldesk-aws/design/plan_aws-porting.md)

## Current Status

The AWS implementation has been deployed and smoke-tested. The latest local
housekeeping pass keeps the worktree free of tracked secrets, records remaining
operational issues in `design/issues-pending-review.md`, and treats
`design/architecture.md` as the canonical architecture document.
