# SignalDesk AWS

SignalDesk AWS is the AWS-hosted port of the local-first SignalDesk market
analysis prototype. The port keeps the original product behavior: daily
watchlist analysis, technical and macro signals, news sentiment, AI-generated
market commentary, dashboard views, and first-pass editorial content.

The runtime has moved from macOS launchd, localhost FastAPI, SQLite, and local
config files to AWS serverless services managed by CDK.

## Architecture

| Capability | AWS implementation |
| --- | --- |
| Static dashboard | S3 private bucket served through CloudFront |
| Same-origin API | CloudFront `/api/*` behavior routed to API Gateway |
| Authentication | Cognito private-admin user pool and app client |
| API compute | Python 3.12 ZIP Lambdas behind API Gateway |
| Scheduled pipeline | Lambda container image invoked by EventBridge |
| Manual pipeline runs | API Lambda invokes the pipeline Lambda |
| Storage | Single-table DynamoDB with latest-run, history, watchlist, and run-status items |
| AI runtime | Amazon Bedrock by default, with OpenAI retained for local/provider fallback |
| Secrets | AWS Secrets Manager |
| Settings and safety policy | AWS Systems Manager Parameter Store |
| Observability | CloudWatch logs, API Gateway metrics, Lambda logs, and pipeline DLQ |

More detail is in [architecture.md](/Users/emilygao/LocalDocuments/Projects/signaldesk-aws/architecture.md) and [design/ARCHITECTURE.md](/Users/emilygao/LocalDocuments/Projects/signaldesk-aws/design/ARCHITECTURE.md).

## AWS Stacks

The CDK app in `infrastructure/` deploys four stacks:

| Stack | Purpose |
| --- | --- |
| `SignalDeskCoreStack` | DynamoDB table, Secrets Manager secret, SSM settings, safety denylist, and allowed topics |
| `SignalDeskPipelineStack` | Docker-image Lambda for the market pipeline, EventBridge schedule, SQS DLQ, CloudWatch log group |
| `SignalDeskApiStack` | Cognito user pool, API Gateway REST API, and Lambda handlers for dashboard data, content generation, watchlist, run status, and manual runs |
| `SignalDeskDashboardStack` | S3 dashboard hosting, CloudFront distribution, and `/api/*` origin routing |

## Runtime Flow

1. EventBridge triggers the pipeline Lambda on the configured schedule, or an admin triggers `/api/run`.
2. The pipeline loads settings from SSM and secrets from Secrets Manager.
3. Market, technical, macro, news, and optional social inputs are collected per ticker.
4. Sentiment and narrative generation call the configured AI provider. AWS mode uses Bedrock.
5. Structured inputs and outputs are validated by Pydantic safety schemas.
6. Results are written to DynamoDB as daily history and latest-run records.
7. The dashboard calls same-origin `/api/*` endpoints through CloudFront and API Gateway.

## Safety Model

All Bedrock-bound structured requests pass through:

1. Pydantic request parsing.
2. Finance-topic policy validation.
3. Prompt-hijack and forbidden-content detection.
4. Typed prompt assembly from validated fields only.
5. Bedrock JSON response parsing.
6. Pydantic output validation.
7. One JSON repair attempt before fallback or rejection.

Blocked API requests return structured 400 errors such as `topic_not_allowed`,
`prompt_injection`, `content_forbidden`, or `validation_failed`.

## Local Setup

```bash
make PYTHON=/Users/emilygao/miniconda3/envs/dev/bin/python install
make test
```

Local mode remains available for development. By default it uses the local
providers. Set `SIGNALDESK_RUNTIME=aws` to use AWS-backed config and storage.
The dependency set currently requires Python 3.12; Python 3.14 is not supported
because `pandas-ta` depends on `numba`, which rejects Python 3.14.

## Deploy

```bash
cp .env.example .env
make synth
make deploy
```

`scripts/deploy.sh` installs dependencies, bootstraps CDK, and deploys all
stacks. The deployment expects AWS credentials and a target account/region to be
configured in the shell environment.

After `SignalDeskCoreStack` deploys, seed or update the runtime secret in AWS
Secrets Manager. The generated secret uses this shape:

```json
{
  "fred_api_key": "",
  "newsapi_key": "",
  "discord_webhook_url": "",
  "openai_api_key": ""
}
```

Rotate any local API keys or webhook URLs before copying them into AWS.

## Configuration

`.env.example` documents the main deployment variables:

| Variable | Purpose |
| --- | --- |
| `AWS_REGION` / `CDK_DEFAULT_REGION` | Deployment region |
| `SIGNALDESK_TABLE_NAME` | Local/default DynamoDB table name reference |
| `SIGNALDESK_SECRET_NAME` | Secrets Manager secret name |
| `SIGNALDESK_SETTINGS_PARAM` | SSM settings parameter |
| `SIGNALDESK_SAFETY_DENYLIST_PARAM` | SSM forbidden-term policy parameter |
| `SIGNALDESK_ALLOWED_TOPICS_PARAM` | SSM allowed-topic policy parameter |
| `BEDROCK_MODEL_ID` | Bedrock model used for AWS AI generation |
| `SIGNALDESK_PIPELINE_SCHEDULE_ENABLED` | Enables or disables the EventBridge schedule |

The default Bedrock model is `amazon.nova-lite-v1:0`.

## Project Structure

```text
api/
  handlers/              # Lambda handlers for API Gateway routes
  server.py              # Local FastAPI compatibility server
dashboard/
  index.html             # Static dashboard deployed to S3/CloudFront
infrastructure/
  app.py                 # CDK app entrypoint
  stacks/                # Core, API, pipeline, and dashboard stacks
pipeline/
  runtime.py             # Runtime provider selection
  *_contract.py          # Storage, config, and AI contracts
  providers/             # Local, DynamoDB, AWS config, Bedrock, and OpenAI providers
  safety/                # Finance-only request/output schemas and policy checks
  run_pipeline.py        # Local CLI and Lambda pipeline entrypoint
scripts/
  deploy.sh              # CDK bootstrap and deploy
  destroy.sh             # CDK destroy helper
  seed_watchlist.py      # Watchlist seed helper
tests/
  test_*.py              # Unit, Lambda handler, storage, safety, and SIT tests
```

## API Surface

The AWS API is private-admin only through Cognito authorization.

| Route | Method | Purpose |
| --- | --- | --- |
| `/api/status` | `GET` | Runtime health and latest run time |
| `/api/dashboard` | `GET` | Latest dashboard summary rows |
| `/api/watchlist` | `GET` / `POST` | Read or update tracked tickers |
| `/api/run` | `POST` | Start a manual pipeline run |
| `/api/run/{run_id}` | `GET` | Read pipeline run status |
| `/api/ticker/{ticker}` | `GET` | Latest full ticker analysis |
| `/api/ticker/{ticker}/history` | `GET` | Historical daily score rows |
| `/api/ticker/{ticker}/earnings-story` | `POST` | Generate first-pass earnings copy |
| `/api/ticker/{ticker}/news-draft` | `POST` | Generate first-pass news copy |

## Verification

```bash
make test
```

The test suite covers local API compatibility, Lambda handlers, DynamoDB data
model behavior, safety validation, notifications, storage, technical indicators,
and SIT coverage.
