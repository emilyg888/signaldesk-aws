# Create signaldesk-aws Sibling Project

## Summary

Create a new sibling project at /Users/emilygao/LocalDocuments/Projects/signaldesk-aws as a clean AWS port of the local-first SignalDesk app. Do not mutate the existing signaldesk project. Use signaldesk as the product/code source and aws-genai-airlab as the CDK/IaC reference.

The new project will target:

- S3 + CloudFront for the static dashboard
- CloudFront `/api/*` routing to API Gateway
- Cognito private-admin access
- Lightweight ZIP Lambdas for API handlers
- Lambda container image for the scheduled pipeline
- DynamoDB single-table storage
- Bedrock runtime adapter with strict Pydantic validation and request safety gates
- Secrets Manager + SSM for runtime configuration

## Project Creation

Create /Users/emilygao/LocalDocuments/Projects/signaldesk-aws.

Copy only safe source assets from signaldesk:

- dashboard/
- pipeline/ logic modules, excluding local secrets/config implementation details
- api/ as reference, then replace FastAPI server runtime with Lambda handlers
- tests/, README.md, pytest.ini, requirements.txt
- design/ as historical reference

Do not copy:

- .git/, .venv/, .pytest_cache/, `__pycache__/`
- logs/, data/db/, pipeline/config.py
- local launchd scheduler files except as archived reference
- generated cdk.out/ from AirLab

Initialize a new git repo for signaldesk-aws after the safe copy.

## Target Structure

```text
signaldesk-aws/
├── api/
│ └── handlers/
│ ├── dashboard.py
│ ├── ticker_detail.py
│ ├── watchlist.py
│ ├── manual_run.py
│ └── run_status.py
├── dashboard/
├── infrastructure/
│ ├── app.py
│ ├── cdk.json
│ ├── requirements.txt
│ └── stacks/
│ ├── core_stack.py
│ ├── api_stack.py
│ ├── dashboard_stack.py
│ └── pipeline_stack.py
├── pipeline/
│ ├── run_pipeline.py
│ ├── storage_contract.py
│ ├── config_contract.py
│ ├── ai_client_contract.py
│ ├── safety/
│ │ ├── schemas.py
│ │ ├── policy.py
│ │ └── validator.py
│ └── providers/
│ ├── local_storage.py
│ ├── dynamodb_storage.py
│ ├── local_config.py
│ ├── aws_config.py
│ ├── openai_client.py
│ └── bedrock_client.py
├── scripts/
├── tests/
├── Dockerfile.pipeline
├── Makefile
└── README.md
```

## Core Implementation

Refactor around runtime contracts first:

- StorageProvider: save_run, get_latest_run, get_all_latest, get_history, load_watchlist, save_watchlist, run status methods.
- ConfigProvider: model IDs, weights, lookback, forecast days, external API keys, webhook config, safety policy config.
- AIClient: sentiment scoring, analysis generation, earnings story, news draft.

Keep local dev mode working with SQLite + optional OpenAI/local config.
Add AWS mode with DynamoDB + Bedrock + Secrets Manager/SSM.
Use Lambda-safe logging to stdout with correlation IDs and no filesystem log writes.

## Safety And Validation

Add Pydantic schemas for every structured Bedrock input and output:

- sentiment request/response
- analysis request/response
- earnings story request/response
- news draft request/response
- manual generation request payloads
- stored DynamoDB analysis payloads

Enforce a Finance-Only Strict policy before any Bedrock call:

Reject off-topic prompts unrelated to market analysis, ticker analysis, macro context, earnings, or SignalDesk dashboard workflows.
Reject prompt hijacking attempts, including instructions to ignore policy, reveal prompts, bypass validators, exfiltrate secrets, or change model/system behavior.
Reject forbidden words/content using a configurable denylist loaded from SSM, with strict defaults committed as safe non-secret config.
Reject requests for credentials, API keys, webhook URLs, private system instructions, hidden chain-of-thought, malware, evasion, harassment, sexual content, or illegal financial manipulation.

Apply validation pipeline:

- API/body Pydantic parse
- topic and forbidden-content policy check
- Bedrock prompt construction from validated fields only
- Bedrock response JSON parse
- Pydantic output validation
- repair prompt once if invalid
- reject and audit if still invalid
- persist only validated payloads

Return structured 400 errors for blocked requests:

- topic_not_allowed
- prompt_injection
- content_forbidden
- validation_failed

Write policy decisions to structured logs with correlation ID, endpoint, ticker/run ID, reason code, and no raw secrets.

## DynamoDB Model

Use a single DynamoDB table for the MVP:

| Entity | PK | SK | Purpose |
|---|---|---|---|
| Daily run | TICKER#AAPL | RUN#2026-05-22 | Full ticker analysis payload |
| Latest run pointer | LATEST | TICKER#AAPL | Fast dashboard overview |
| Watchlist | CONFIG | WATCHLIST | Editable ticker list |
| Pipeline status | PIPELINE | RUN#<run_id> | Manual/scheduled execution state |
| Macro snapshot | MACRO | RUN#2026-05-22 | Optional shared macro context |

Dashboard overview must query PK = LATEST, not scan historical runs.

## AWS Runtime

### API

Replace FastAPI server with Lambda handlers matching existing /api/_ response shapes.
Add POST /api/run as async only:

- create run_id
- write status STARTED
- invoke pipeline Lambda asynchronously or start Step Functions later
- return { "run_id": "...", "status": "STARTED" }

Add GET /api/run/{run_id} for polling run status.

### Dashboard

Deploy static assets to S3.
CloudFront origin 1: S3 dashboard.
CloudFront origin 2: API Gateway.
Route /api/_ through CloudFront to preserve same-origin frontend fetches.

### Pipeline

Package scheduled pipeline as a Lambda container image because pandas/yfinance dependencies are heavy.
Use EventBridge Scheduler, initially disabled until manual smoke tests pass.
Add DLQ, timeout, memory, CloudWatch logs, and per-ticker status updates.

### Bedrock

Implement a runtime adapter based on AirLab’s BedrockClient.
Never pass raw user text directly into a prompt without policy validation and typed prompt assembly.
Use Bedrock Guardrails if available in the target account; keep app-level Pydantic/policy validation mandatory regardless.

### Security

Cognito private-admin access for dashboard/API.
Secrets in Secrets Manager; settings and safety denylist in SSM.
Rotate any exposed-looking local API keys/webhooks before seeding AWS secrets.
CDK asset excludes must block .env, .venv, logs, local DBs, caches, cdk.out, and secret config files.

## CDK/IaC

Pattern the IaC after aws-genai-airlab/infrastructure:

- SignalDeskCoreStack
- DynamoDB table
- Secrets Manager secret placeholders/references
- SSM settings, including safety denylist and allowed-topic config
- shared IAM/log retention conventions
- SignalDeskApiStack
- API Gateway
- API Lambda functions
- Cognito authorizer
- permissions for DynamoDB, SSM, Secrets Manager, Bedrock where needed
- SignalDeskDashboardStack
- S3 bucket
- CloudFront distribution
- OAC
- `/api/*` behavior to API Gateway
- SignalDeskPipelineStack
- ECR/container Lambda or CDK Docker image asset
- EventBridge schedule
- DLQ
- alarms/log groups
- async invoke permissions

Add SignalDeskObservabilityStack later, not in the first scaffold, unless deployment smoke tests show immediate need.

## Implementation Sequence

1. Create the sibling project with safe copied source and no secrets.
2. Refactor local runtime contracts while preserving local tests.
3. Add Pydantic schemas and the Finance-Only Strict safety validator.
4. Add DynamoDB, Bedrock, Secrets Manager, and SSM providers.
5. Add Lambda handlers and async manual-run flow.
6. Add CDK stacks and deployment scripts.
7. Add Dockerfile for pipeline Lambda container.
8. Update dashboard fetch/auth behavior while keeping same-origin /api/_.

Deploy in order:

1. Core stack
2. Seed secrets/settings/watchlist/safety policy
3. Pipeline stack with schedule disabled
4. Manual pipeline invoke
5. API stack
6. Dashboard stack
7. Enable schedule after successful smoke test

## Test Plan

### Local

- Existing unit tests remain green against local providers.
- New contract tests run against fake/local providers.
- Safety tests cover off-topic requests, prompt hijacking, forbidden terms, secrets extraction attempts, invalid Bedrock JSON, and repair failure.
- Bedrock adapter tests mock bedrock-runtime.converse.
- DynamoDB provider tests validate exact PK/SK writes and latest-pointer behavior.

### Lambda/API

- Handler tests for dashboard, ticker detail, history, watchlist, manual run, and run status.
- Async /api/run test confirms no synchronous pipeline execution.
- Blocked generation requests return structured 400 errors.

### CDK

- `cdk synth`
- assert asset excludes prevent secrets/local artifacts in bundles.

### AWS Smoke

- Manual invoke pipeline Lambda.
- Verify LATEST rows in DynamoDB.
- Verify unauthenticated API requests fail.
- Verify authenticated dashboard loads via CloudFront and /api/_ works same-origin.
- Verify prompt-hijack/off-topic requests are rejected before Bedrock invocation.
- Verify DLQ/alarm/log groups exist.

## Assumptions

- signaldesk-aws does not currently exist, so creation can proceed as a new sibling directory.
- The existing signaldesk project remains untouched except for read-only reference.
- First deployment is dev/private-admin, not production/public.
- Finance-Only Strict is the default safety policy.
- Bedrock is the AWS default; OpenAI remains optional only for local/dev parity.
- Pipeline Lambda container image is the MVP packaging choice.
