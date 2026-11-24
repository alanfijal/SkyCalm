# Team actions

## Phase 0

| Status | Owner | Action or result |
| --- | --- | --- |
| Done | Alan | Selected the SkyCalm Desktop repository and a `feature/` branch. Keep these commits local. |
| Done | Project | Checked the AWS account identity, Free plan, regional service listings, relevant quotas and Nova Lite availability using read-only calls. The owner has private billing evidence. |
| Open | Team | Review the architecture, network choice, cost envelope and demo sequence. Approve or amend the Phase 0 plan before implementation. |

Review the [architecture](architecture.md), [cost comparison](costs.md) and [walkthrough](demo.md).

```text
🙋 ACTION NEEDED FROM YOU
What:        Approve the Phase 0 design to start local Phase 1 work.
Why:         This selects the source, region and grid network for the first implementation.
Blocking:    yes – I am waiting
Time:        About 5 minutes.
Steps:
  1. Open the architecture, network cost comparison and walkthrough linked above.
  2. Review Stockholm, NOAA GFS and a temporary-IP task with zero inbound rules.
  3. Reply in the project chat. AWS deployment has its own exact-plan approval later.
Send back:   “Approve Phase 0 and start Phase 1 locally” or the change you want.
Check:       The decision appears here and work starts on a new feature branch.
```

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
