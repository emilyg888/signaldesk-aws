# Issues Pending Review

## Summary

| ID | Severity | Area | Issue | Recommended action | Status |
|---|---|---|---|---|---|
| ISSUE-001 | High | Security | A local ignored deployment output file contained a live-looking OpenAI API key. The file is ignored and not tracked, but the key should be treated as exposed on the local machine. | Revoke/rotate the OpenAI API key in the OpenAI dashboard and avoid storing secret-bearing deployment output in project folders. | Pending review |
| ISSUE-002 | Medium | Operations | EventBridge schedule is disabled by default and should remain disabled until manual AWS smoke tests pass after each fresh deployment. | Manually invoke the deployed pipeline, inspect DynamoDB and CloudWatch, then enable `SIGNALDESK_PIPELINE_SCHEDULE_ENABLED=true` only after validation. | Pending review |
| ISSUE-003 | Medium | Operations | SQS DLQ exists for the pipeline Lambda, but alarm/notification wiring is not yet implemented in CDK. | Add CloudWatch alarms for DLQ depth, Lambda errors, API 5xx, and stale pipeline runs before production use. | Pending review |
| ISSUE-004 | Medium | Product | Subscriber-facing personalization and distribution channels beyond dashboard/Discord are extension points, not complete workflows. | Define email/SMS/WhatsApp/mobile delivery requirements and editorial approval states before public rollout. | Pending review |
| ISSUE-005 | Low | Framework | FastAPI `on_event` deprecation warnings remain in the local compatibility server. | Migrate `api/server.py` startup handling to lifespan events when touching the local server. | Pending review |
| ISSUE-006 | Low | Infrastructure | CDK synth warns that Node.js `v25.9.0` is not a tested CDK runtime. | Use an officially supported Node.js version for CDK, preferably Node 22 or 24. | Pending review |
| ISSUE-007 | Low | Infrastructure | CDK synth warns that `aws_dynamodb.TableOptions#pointInTimeRecovery` is deprecated. | Replace with `pointInTimeRecoverySpecification` before the next major CDK upgrade. | Pending review |

## SIT Results

| Command | Result | Notes |
|---|---|---|
| `make test` | Passed | `173 passed, 2 warnings` on Python 3.12.12. Warnings are FastAPI `on_event` deprecation warnings. |
| `make synth` | Passed | CDK synthesized all stacks. Warnings: Node.js `v25.9.0` is not tested by CDK, and DynamoDB `pointInTimeRecovery` API is deprecated. |

## Archived Code Review

| Original path | Archived path | Reason | Review needed? |
|---|---|---|---|
| None | None | No redundant code met the two-signal threshold for safe archival. | No |

## Detailed Issues

### ISSUE-001 — Local Deployment Output Contained An API Key

- Severity: High
- Area: Security
- Evidence: Secret scanning found an OpenAI-looking API key value in local file `design/Outputs_aws_deployment`. The file is ignored by `.gitignore` and was not staged or committed.
- Impact: The key should be considered exposed on the local machine and any local backups of this project folder.
- Recommended action: Revoke/rotate the key in the OpenAI dashboard. Keep deployment outputs outside the repo, or ensure they are redacted before saving.
- Status: Pending review

### ISSUE-002 — Scheduled Pipeline Needs Smoke Validation Before Enablement

- Severity: Medium
- Area: Operations
- Evidence: `SIGNALDESK_PIPELINE_SCHEDULE_ENABLED=false` is the default deployment setting.
- Impact: The schedule should not be enabled until deployed AWS resources, secrets, model access, and data writes are verified.
- Recommended action: Run a manual pipeline invocation after deploy, inspect CloudWatch logs and DynamoDB records, then enable the schedule.
- Status: Pending review

### ISSUE-003 — DLQ Alarm Wiring Not Yet Captured

- Severity: Medium
- Area: Operations
- Evidence: `SignalDeskPipelineStack` creates an SQS DLQ, but no CloudWatch alarms were found in the CDK stacks.
- Impact: Pipeline failures can land in the DLQ without proactive notification.
- Recommended action: Add alarms for DLQ visible messages, Lambda errors, API Gateway 5xx, and pipeline age/staleness.
- Status: Pending review

### ISSUE-004 — Subscriber Distribution Is An Extension Point

- Severity: Medium
- Area: Product
- Evidence: Current implementation supports dashboard workflows and Discord webhook notification, while email, SMS, WhatsApp, and mobile push remain product targets.
- Impact: News/media subscriber delivery requires additional product and integration work before launch.
- Recommended action: Define channel-specific approval thresholds, payload formats, opt-out handling, and provider integrations.
- Status: Pending review

### ISSUE-005 — FastAPI Startup Deprecation Warning

- Severity: Low
- Area: Code
- Evidence: SIT reports FastAPI `on_event` deprecation warnings from `api/server.py`.
- Impact: No runtime failure today, but future FastAPI versions may remove the older startup hook style.
- Recommended action: Migrate local server startup to lifespan events.
- Status: Pending review

### ISSUE-006 — CDK Node Runtime Warning

- Severity: Low
- Area: Infrastructure
- Evidence: `make synth` warns that CDK has not been tested with Node.js `v25.9.0`.
- Impact: No synth failure today, but unsupported Node versions can create hard-to-debug CDK/runtime issues.
- Recommended action: Use Node.js 22 or 24 for CDK commands.
- Status: Pending review

### ISSUE-007 — Deprecated DynamoDB PITR CDK Property

- Severity: Low
- Area: Infrastructure
- Evidence: `make synth` warns that `aws_dynamodb.TableOptions#pointInTimeRecovery` is deprecated.
- Impact: The property will be removed in a future major CDK release.
- Recommended action: Replace it with `pointInTimeRecoverySpecification`.
- Status: Pending review
