# Issues Pending Review

## Summary

| ID | Severity | Area | Issue | Recommended action | Status |
|---|---|---|---|---|---|
| ISSUE-001 | Medium | Config | Default `python3` on this machine is Python 3.14.4, but the dependency set requires Python 3.12 because `pandas-ta` pulls `numba`, which rejects Python 3.14. | Use the documented Python 3.12 conda interpreter for local setup, or add a project-level Python version manager file and Makefile guard. | Pending review |
| ISSUE-002 | Medium | Operations | EventBridge schedule is disabled by default and should remain disabled until manual AWS smoke tests pass. | Manually invoke the deployed pipeline, inspect DynamoDB and CloudWatch, then enable `SIGNALDESK_PIPELINE_SCHEDULE_ENABLED=true` only after validation. | Pending review |
| ISSUE-003 | Medium | Operations | SQS DLQ exists for the pipeline Lambda, but alarm/notification wiring is not yet documented as implemented. | Add CloudWatch alarms for DLQ depth, Lambda errors, and API 5xx before production use. | Pending review |
| ISSUE-004 | Medium | Product | Subscriber-facing personalization and distribution channels beyond dashboard/Discord are extension points, not complete workflows. | Define email/SMS/WhatsApp/mobile delivery requirements and editorial approval states before public rollout. | Pending review |
| ISSUE-005 | Low | Framework | FastAPI `on_event` deprecation warnings remain in the local compatibility server. | Migrate `api/server.py` startup handling to lifespan events when touching the local server. | Pending review |
| ISSUE-006 | Low | Dependencies | `pandas-ta` emits a pandas Copy-on-Write deprecation warning under pandas 3. | Track upstream compatibility or pin a compatible pandas/pandas-ta combination if the warning becomes noisy in CI. | Pending review |

## SIT Results

| Command | Result | Notes |
|---|---|---|
| `make test` before venv creation | Failed | `.venv/bin/python` did not exist. |
| `make install` with default `python3` | Failed | Created a Python 3.14 venv; dependency install failed because `numba` supports Python `<3.14`. |
| `make PYTHON=/Users/emilygao/miniconda3/envs/dev/bin/python install` | Passed | Created `.venv` with Python 3.12.12 and installed project plus CDK dependencies. |
| `make test` | Passed | `173 passed, 3 warnings` on Python 3.12.12. Warnings: FastAPI `on_event` deprecation twice and `pandas-ta` pandas Copy-on-Write deprecation. |

## Archived Code Review

| Original path | Archived path | Reason | Review needed? |
|---|---|---|---|
| None | None | No redundant files met the two-signal threshold for safe archival. | No |

## Detailed Issues

### ISSUE-001 — Python 3.12 Runtime Required

- Severity: Medium
- Area: Config
- Evidence: `make install` with default `python3` used Python 3.14.4 and failed while installing `numba` for `pandas-ta`; `make PYTHON=/Users/emilygao/miniconda3/envs/dev/bin/python install` succeeded with Python 3.12.12.
- Impact: New developers or CI runners using Python 3.14 will fail before tests run.
- Recommended action: Add a project-level Python version manager file such as `.python-version`, document the supported interpreter, and optionally add a Makefile preflight check.
- Status: Pending review

### ISSUE-002 — Scheduled Pipeline Still Needs AWS Smoke Validation

- Severity: Medium
- Area: Operations
- Evidence: `SIGNALDESK_PIPELINE_SCHEDULE_ENABLED=false` is the default deployment setting.
- Impact: The schedule should not be enabled until the deployed AWS resources, secrets, model access, and data writes are verified.
- Recommended action: Run a manual pipeline invocation after deploy, inspect CloudWatch logs and DynamoDB records, then enable the schedule.
- Status: Pending review

### ISSUE-003 — DLQ Alarm Wiring Not Yet Captured

- Severity: Medium
- Area: Operations
- Evidence: `SignalDeskPipelineStack` creates an SQS DLQ, but no CloudWatch alarms were found in the CDK stacks.
- Impact: Pipeline failures can land in the DLQ without a proactive alert.
- Recommended action: Add alarms for DLQ visible messages, Lambda errors, API Gateway 5xx, and pipeline age/staleness.
- Status: Pending review

### ISSUE-004 — Subscriber Distribution Is An Extension Point

- Severity: Medium
- Area: Product
- Evidence: Current implementation supports dashboard workflows and Discord webhook notification, while email, SMS, WhatsApp, and mobile push remain documented product targets.
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

### ISSUE-006 — pandas-ta Copy-on-Write Warning

- Severity: Low
- Area: Dependencies
- Evidence: SIT reports a `Pandas4Warning` from `pandas_ta`.
- Impact: No test failure today, but dependency churn could affect CI noise or future compatibility.
- Recommended action: Monitor upstream compatibility and pin versions if needed.
- Status: Pending review
