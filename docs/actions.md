# Team actions

## Phase 0

| Status | Owner | Action or result |
| --- | --- | --- |
| Done | Alan | Selected the SkyCalm repository and descriptive feature branches. Approved publishing Phase 0 to GitHub on 24 November 2026. |
| Done | Project | Checked the AWS account identity, Free plan, regional service listings, relevant quotas and Nova Lite availability using read-only calls. The owner has private billing evidence. |
| Approved | Team | Approved Stockholm, NOAA GFS, the temporary-IP grid task, the cost envelope and the demo sequence on 24 November 2026. Phase 1 starts locally. |

Review the [architecture](architecture.md), [cost comparison](costs.md) and [walkthrough](demo.md).

The initial AWS deployment has a separate resource, cost and Terraform plan review.

## Upcoming dependencies

No setup is needed for these during Phase 0. Open a concrete request at the start of the relevant phase.

| Phase | What may require someone from the team |
| --- | --- |
| 1 | Review bootstrap, deployment identity, account allowlist, monthly budget notifications, exact Terraform plan and bounded initial smoke test. Authorize AWS writes only after reviewing that inventory. |
| 2 | Obtain OpenSky written permission covering the live product and classroom display. Only then provision client credentials via a private channel. If the terms cannot be met, decide whether to omit this optional layer. Confirm archive rights before redistributing any source. |
| 3 | Confirm the demo operator's scoped IAM access and the timed rehearsal window. |
| 4 | Configure the exact Google/Cognito redirect, review third-party privacy/residency terms, verify SES sender/sandbox recipients, and install/enable push on the demo phone. Secret values go to approved runtime storage. |
| 5 | Approve a bounded ML extraction and job budget. Recheck model access and quotas. Request an owner action only if a necessary permission or quota actually fails. |
| 6 | Review account-wide GuardDuty scope/trial behavior before activation, WAF configuration and three classroom rehearsals. A custom domain is optional. |
