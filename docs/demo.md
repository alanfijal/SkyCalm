# Classroom walkthrough

**Goal: 9 minutes 35 seconds, with 25 seconds to spare.** The presenter uses an archived weather run on the same forecast code path as the live app. Keep the run time, replay label and observation times visible. The table is a rehearsal plan. The Phase 0 evidence at the end is available today.

| Clock | On screen and what to do | What the audience should see |
| --- | --- | --- |
| 00:00–00:30 | Open the passenger app on the projector. Point to the Europe globe, latest run time and education disclaimer. | What a passenger can learn about a route and how old the forecast is. |
| 00:30–02:10 | Choose the rough-route fixture by airport pair and departure UTC. Press **Forecast**, scrub the timeline and tap a coloured section. Point to the time, altitude and reason. | The marker moves with the timeline. Baseline intensity has a label. Calibrated likelihood and the short briefing appear only when verified in Phase 5. |
| 02:10–02:55 | Toggle the archived SIGMET and available pilot reports for the same time. Separately switch to current traffic if the provider permits classroom display. Point to each timestamp. | A model forecast, an area warning and an observation have different meanings. An empty or sparse layer has a visible explanation. |
| 02:55–04:05 | Sign in with Google. Open **My flights**, save the selected departure and show notification opt-in on the already installed phone PWA. | The new watch belongs to this user. The projected browser shows the saved trip without revealing account details. |
| 04:05–06:35 | As the demo operator, open **Demo → Publish archived run**, choose the verified successor and click once. Watch progress, then switch to the Step Functions graph and the bounded ECS task. Show the route update and phone notification. | Use the same run ID across execution, ready event and inbox. If the phone is late, open the inbox, show the delivery status and use the short clip of a verified receipt. |
| 06:35–07:55 | Open **How we score**, point to baseline vs. held-out model evaluation and regional support. Show the registry version used by this run. Tap the feature explanation. | Explain what the model improved, or why the baseline still serves. The class and confidence belong to the displayed version. |
| 07:55–08:55 | Use the prepared local security check on the protected flights route. Show status only for missing token, missing scope and authorized access, then the CloudFront WAF rate rule. | Demonstrate measured 401, 403 and 200 behavior and the boundaries of WAF coverage. Keep tokens and email addresses off the projector. |
| 08:55–09:35 | Open route statistics or the saved Athena result, show sample count and period, then return to the architecture diagram. | Explain the separation between the current forecast, archived reports and the user's watch. |

Start the pipeline timer on the first click. If it runs beyond the 2:30 stage slot, show the evaluation chart while it finishes and return to the phone at receipt. Log the actual button-to-phone interval even when the presentation overlaps those steps.

## Phase increments and evidence

| Phase | Increment to rehearse | Passing evidence |
| --- | --- | --- |
| 0 · plan | Walk through the architecture and compare the two networks. | Local plan screenshot and short clip, reproducible price table and team sign-off. |
| 1 · baseline | Steps 1–2. Select airports, scrub one real current run, then pin that same run in replay. Try an outside-box airport and a departure beyond 36 hours. | A deployed route with dated data, realistic missing-coverage states and screenshot/clip. |
| 2 · sources | Steps 2–3. Toggle real SIGMETs and reports. Save a route/day evidence manifest. Query counts by month/intensity. | 3–5 evidence-backed candidate days and 2–3 verified routes. Record coverage gaps and permission status for traffic. |
| 3 · pipeline | Step 5 through updated tiles. Trigger a real replay from the IAM-protected operator view, follow the execution, then induce one controlled failure in a dedicated demo message. | Record trigger → ready and route update in under 180 s, a DLQ receipt and alarm. A cached cruise-band input is acceptable if the production grid code runs. |
| 4 · watches | Steps 4, 5 and 7. Seed three watches, demonstrate push on the actual phone, reminders, scoped responses and export/delete with a disposable identity. | Measure trigger → phone receipt under 180 s. Record provider acceptance and visible device receipt separately. Verify cleanup removes schedules. |
| 5 · model | Step 6 and the step 2 briefing. Open real evaluation and registry evidence. | Persist the dataset split, model version, metrics, approval outcome, segment explanation and briefing fallback example. |
| 6 · hardening | All eight steps in the planned order. Show WAF, route statistics and a post-flight comparison. | Three successful deployed rehearsals under 10 minutes each, with per-step screenshots and clips of 30 seconds or less. |

## Choosing the demonstration flights

In Phase 2, search the collected archive and any permitted historical sources for **3–5 dates** with valid weather, an overlapping significant-weather advisory or an explicit intensity report. Choose **2–3 routes** including a lower-index contrast. Penalize missing forecast leads. Rank a rough route by time/altitude overlap with observed evidence and a demonstrable change between two issued runs for the same departure. Absence of reports alone cannot establish smooth conditions.

Record each airport pair, departure UTC, both provider run IDs, lead coverage, source URL/licence, observation IDs/validity and evidence confidence in this guide. Pin the source data, tiles, inputs and checksums in the nonpersonal replay prefix. Use a demo clock for watched departures/reminders so a historical date remains reproducible. Keep the event clock, historical observation time and real operator audit time distinct. Demo-labelled events and a separate replay namespace prevent accidental real-user notifications.

## Presenter preflight

1. Open the app, the execution graph, ECS task list, Model Registry and WAF in separate tabs. Check the deployed commit and curated replay manifest. Confirm projected views omit identities and credentials.
2. On the admin health page, check latest ready run, source timestamps, OpenSky permission/token health if enabled, queue depth and DLQs, model version and last notification status.
3. Reset only the demo account and its schedules. Seed three watches for the chosen routes/departures. Verify the PWA is installed, push permission granted, the notification centre accessible, and at least one verified SES fallback recipient if used.
4. Run the eight steps three times. Record date, commit, fixture/run IDs, full duration, trigger-to-ready, trigger-to-device, delivery mode and failures. For each step store a screenshot and a clip of at most 30 seconds under `docs/demo-assets/`. Record timings only after observing them.
5. If a feed fails, use the labelled archive. If the pipeline stalls, open the last real execution and its recording. If the model fails its promotion threshold, show the measured result and which scorer served. A synthetic change is allowed only through the normal event path and with **Test event** on screen.
6. End the demo window, disable live polling and run admission, verify no grid tasks or ML jobs remain active, and check queued retries. Keep the archive and Terraform state until reviewed cleanup.

## Available now

- [Phase 0 architecture screenshot](demo-assets/phase-0-architecture.png) and [local planning walkthrough](demo-assets/phase-0-walkthrough.webm).
- [Editable architecture](architecture.md) and [reproducible cost comparison](costs.md).
- Product deployment, historical route selection, phone delivery, timings and classroom rehearsals are pending their phase gates.
