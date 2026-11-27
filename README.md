# SkyCalm

SkyCalm shows where a European passenger route may feel bumpy. Choose two airports and a UTC departure to see the estimated path on a globe. Move along the timeline to inspect the local category, time and altitude. The first release uses real NOAA weather and a physics-based index.

[Open the live SkyCalm forecast](https://d9w1t8ghthajo.cloudfront.net/)

**For passenger education only. Do not use SkyCalm for navigation, flight planning or safety decisions.**

## Run it on your laptop

Use Node 24, npm and Python 3.12 on macOS or Linux. Run these commands from the repository root.

```sh
(cd web && npm ci && npm run build)
python3 -m services.forecast.local
```

Open **http://127.0.0.1:4173**. Press Ctrl+C in the server terminal to stop. The bundled map, fonts, airport catalog and archived weather work offline after the build. No cloud account is needed.

The home page accepts a flight number and local departure date. **Open replay** plays the recorded Catania–Milan flight. **Search by airports** opens the route planner at `/forecast`. On a phone, tap **Flight details** or swipe its handle up for the timeline. Press Escape to close it with a keyboard. Tap **Explore globe** to pan, zoom or fit the route.

**Map layers** lets you switch daylight shading and 250 hPa cruise winds on or off. Wind lines follow NOAA’s eastward and northward components at the nearest three-hour forecast step. The two reference cycles (21 Nov at 06 UTC and 24 Nov at 12 UTC) include archived wind. New full grid runs carry their own vectors. Older cycles without wind display its availability in the layer menu.

On phones and tablets, tap **Edit flight** to change the airports or departure time. The sun or moon button in the header switches themes and remembers your choice on this browser.

**Try a replay.** Open **Search by airports**, then choose the archived **24 Nov 2026, 12 UTC** weather run, Barcelona (BCN) to Stockholm Arlanda (ARN), and depart on **24 Nov at 18:00 UTC**. Select **Forecast flight** if you change the route. The estimated flight takes 2 h 54 min. Use the timeline or the coloured route to explore the change from smooth to moderate. **Forecast guide** explains the model and its limits.

**Find a recorded flight.** On the homepage choose **Recorded flights**. Search by flight number, callsign, city or airport pair, with an optional local departure date. For example, **AMS to BCN**, **KL1521** and **KLM71Z** all open the Amsterdam–Barcelona flight. The initial catalogue covers six passenger flights on 21 November 2026. The Airports form also shows recordings in the selected direction. Flight-number search opens dated matches before sign-in and still offers AeroDataBox for schedule details. [Search the recordings](https://d9w1t8ghthajo.cloudfront.net/recordings)

Each recording uses observed ADS-B positions and barometric altitudes. The colours show the archived NOAA forecast sampled at their coordinates, times and altitudes. The climb, cruise and descent labels are estimated from the altitude profile. For another airport pair, enter the departure and select **Forecast flight**. If the selected weather run misses that departure, SkyCalm picks the newest archive covering it. Choose **Play forecast route** to follow the estimated path. Dated schedule results use the same weather selection. [Original Catania–Milan replay](https://d9w1t8ghthajo.cloudfront.net/replay)

Each player offers its underlying track as a CSV under the Open Database License. The source manifest lists the archive part, exact byte range and SHA-256 for each aircraft-day, plus the callsign, flight-number reference and UTC interval for each leg. Verify every recording and the search index offline with `python -m scripts.recorded_replay --check`. The following example reimports AZ1704 from its original member and rebuilds the catalogue. [Source manifest](scripts/recorded_sources.json) · [ADSB.lol archive](https://github.com/adsblol/globe_history_2026/releases/tag/v2026.11.21-planes-readsb-prod-0) · [Open Database License 1.0](https://opendatacommons.org/licenses/odbl/1-0/)

```sh
curl -fL --max-time 30 --max-filesize 96750 --range 272510976-272607725 \
  'https://github.com/adsblol/globe_history_2026/releases/download/v2026.11.21-planes-readsb-prod-0/v2026.11.21-planes-readsb-prod-0.tar.ab?trace=4cad5e' \
  -o /tmp/skycalm-az1704.json.gz
python -m scripts.recorded_replay --import-member /tmp/skycalm-az1704.json.gz
```

### Load a current weather run

```sh
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --require-hashes -r grid/requirements.txt
python -m grid.build --run latest
```

Refresh the page and select the live weather source. A single build downloads selected fields for 13 forecast times and writes a complete run to `.local/weather/`. The November replay build read 187 MB. An interrupted build leaves the previous completed grid available. No refresh runs in the background. To rebuild a dated run while NOAA still hosts it, replace `latest` with its ID, for example `gfs-20261124-12`.

## What the forecast measures

- Coverage spans 34–72° N and 25° W–45° E. The airport search includes 646 scheduled-service airports in this box. An exact IATA code outside Europe can be looked up to explain the coverage limit.
- The route follows a great circle sampled about every 25 km. The model assumes 800 km/h, climbs and descends over roughly 150 km at either end, and cruises up to 35,000 ft. The marker represents a point on the estimated route.
- The grid worker reads byte ranges from the NOAA GFS 0.25° product. At cruise it combines vertical wind shear with horizontal wind deformation (Ellrod TI1). Project category boundaries for TI1 × 10⁷ are 2, 6 and 12. Below the pressure grid on climb or descent, the category uses surface CAPE at 500, 1,500 and 2,500 J/kg. These categories have no calibrated likelihood attached. [NOAA GFS](https://registry.opendata.aws/noaa-gfs-bdp-pds/) · [NOAA turbulence-index bulletin](https://www.weather.gov/media/mdl/TPB_430.pdf)
- Temperature, wind and geopotential come from five pressure levels. The API interpolates one-degree serving tiles between forecast steps three hours apart. The 36-hour window starts at the weather run’s issue time. Grey marks missing samples and route sections beyond coverage or forecast time.
- Airport and map data are bundled from OurAirports and Natural Earth. `scripts/prepare_geodata.py` reproduces the snapshots using pinned source revisions and checksums. [Data credits](web/public/maps/credits.txt)

## Weather observations

Open **Map layers** on the globe. **Turbulence advisories** draws SIGMET areas. **Aircraft weather reports** shows where a pilot or aircraft recorded a turbulence intensity. Choose the live weather source for the most recent capture, or a dated replay for the matching archived observations. The layer panel shows when the snapshot was collected.

Try the **21 Nov 2026, 06:00 UTC** replay, **Edinburgh (EDI) → Porto (OPO)**, departing **14:15 UTC**. Enable both layers. Near 14:48 UTC the route passes a light aircraft report. At 16:11 UTC it reaches the Madrid turbulence advisory. Reports are matched within 75 km, 45 minutes and 3,000 ft when a flight level is known. An advisory must cover the selected point, time and known altitude band. The 18:05 UTC archive includes weather reported after departure.

To capture one current eight-hour European weather snapshot or rank routes across the five bundled dates, run these commands from the repository root.

```sh
python3 -m services.observations.collect
python3 -m scripts.find_demo_days
```

The collector reads the Aviation Weather Center on the server. A capped query can include hundreds of automated wind reports, so it also fetches the provider's intensity-filtered reports and deduplicates overlaps. The map displays deidentified weather fields. Reports without a turbulence value remain a separate group in the history query. The optional live-aircraft feed awaits an OpenSky agreement. Weather attribution is NOAA Aviation Weather Center and the issuing meteorological offices, including Météo-France and Fuente: AEMET. [AWC data and coverage](https://aviationweather.gov/data/api/) · [NWS data terms](https://www.weather.gov/disclaimer) · [OpenSky terms](https://opensky-network.org/about/terms-of-use)

Terraform defines an on-demand weather collector, a Glue table with daily partitions, and an Athena workgroup with a 10 MiB scan limit. The optional half-hourly schedule takes an explicit UTC window of up to two hours. Raw snapshots expire after seven days, working history after 30 days and query results after one day. The curated dates stay in the archive. Use the `skycalm-dev-weather` workgroup in Stockholm for [monthly report counts](analytics/monthly_reports.sql) and [dated advisories](analytics/advisories.sql).

## Passenger accounts

With passenger services enabled, open **My flights** or choose **Save route** on a forecast. Sign in with the invited classroom email or Google, confirm a future UTC departure and choose **Save flight**. The **Account** tab manages browser alerts, email fallback, JSON export and deletion. On iPhone, add SkyCalm to the Home Screen and open it there before enabling push. The public forecast and archived weather remain available to visitors.

For a presenter who uses a separate Google account, pass `--login-email` to `scripts/passenger_setup.py`. The invite admits that address. Opted-in email goes to the verified mailbox given by `--classroom-email`. Keep both values in the private environment configuration.

Each passenger can save eight flights. Live grid events reassess departures within 36 hours. A change in peak category or a shift of more than 30 minutes in the first moderate-or-severe section can trigger an alert, with three hours between change alerts per flight. Future 24-hour and 3-hour reminders expire after execution. The authenticated `/demo` page seeds three classroom routes, publishes an archived run and tests delivery. `/health` shows queue counts and the last push accepted for the operator. Both pages require the admin group and scope.

## Run a forecast from the operator panel

From the repository root, use a Python 3.12 virtual environment and start the private panel.

```sh
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --require-hashes -r requirements-dev.txt
python -m services.pipeline.operator
```

Open **http://127.0.0.1:4174/demo**, choose **21 Nov 2026, 06 UTC** and click **Publish replay**. The worker rebuilds all 13 forecast steps from archived GFS weather features, then recalculates the 69 samples on the Edinburgh–Porto route. The progress panel shows elapsed time and the updated route ribbon. **Health** opens the service status. Ctrl+C stops the panel. Local rehearsal works offline after installing the dependencies.

With the pipeline deployed, start the same panel with `python -m services.pipeline.operator --aws --profile coldchain-console --account "$TF_VAR_account_id"`. Set `TF_VAR_account_id` to the approved account first. The server binds to your Mac's loopback address, verifies the AWS identity and signs requests with your CLI session. Terraform supplies a scoped operator policy for an authorized presenter. Actions are recorded locally in `.local/operator-actions.jsonl`. Cognito group access to a hosted panel is planned for Phase 4.

On AWS, an EventBridge `forecast.run.available` event reaches the admission queue. Step Functions takes a DynamoDB lease, waits for one Fargate grid task, verifies its manifest and publishes `forecast.tiles.ready`. Two independent queues deliver this event to the route and audit consumers. Each writes an idempotent result. The worker uses a job-specific prefix for replay output. A completed live job can advance the public forecast after EventBridge accepts its ready event. A fresh forecast request then reads the new run. [Workflow and queues](infra/modules/pipeline/)

- **Check NOAA for a new run** checks up to three recent cycles. A complete, newer cycle starts the same workflow using current GFS data. Scheduled checks are off by default. An optional Terraform `discovery_window` checks every 15 minutes for at most two hours.
- **Health → Send test event** sends one labelled event through the routes queue. Three failed deliveries move it to the routes dead-letter queue. Refresh Health to see the queue depth and its CloudWatch alarm. Each delivery has a 90-second visibility timeout and the alarm evaluates a one-minute metric. Allow extra time for AWS to report the change. The message expires after seven days.
- The classroom forecast is independent of the optional OpenSky traffic feed. Archived weather remains available after the upstream source files expire.

## Architecture and checks

`grid/` contains the Linux/amd64 worker. `services/forecast/` implements the HTTP API shared by the local server and Lambda. The public GET routes are `/api/airports?q=BCN`, `/api/runs`, `/api/forecast` with `origin`, `destination`, `departure` and `run`, and `/api/observations?run=latest`. `web/` contains the React app, MapLibre globe and deck.gl route layer.

The Stockholm Terraform configuration defines a private S3 web origin behind CloudFront, a regional HTTP API and arm64 Lambda, S3 weather and replay objects, a DynamoDB latest-run pointer and a manually started Fargate task. The worker can finish a single job in its public subnet and exit. Its security group allows outbound HTTPS. S3 and DynamoDB use regional gateway endpoints. The API role can read weather and the worker role can publish it. Working weather objects expire after seven days. The archived demonstration run has its own prefix. [Application infrastructure](infra/modules/forecast/) · [Bootstrap](infra/bootstrap/)

```sh
source .venv/bin/activate
python -m pip install --require-hashes -r requirements-dev.txt
python -m ruff format --check grid services scripts tests
python -m ruff check grid services scripts tests
python -m pytest -q
bash scripts/lambda_images.sh build
(cd services/delivery && npm ci --omit=dev --ignore-scripts && npm test)
python3 scripts/check_lambda_images.py
(cd web && npm ci && npm run lint && npm test && npm run build)
(cd web && npx playwright install --only-shell chromium && npm run test:layout)
terraform fmt -check -recursive infra
for directory in infra/bootstrap infra/environments/dev; do
  terraform -chdir="$directory" init -backend=false -input=false -lockfile=readonly
  terraform -chdir="$directory" validate
  terraform -chdir="$directory" test
done
```

These Terraform tests plan against a mocked AWS provider. CI runs them with the same build inputs. Eleven ARM64 functions use the Python target in `services/Dockerfile`. The Web Push sender uses its Node target. The local check invokes both through the AWS runtime emulator with outbound networking disabled. To build the grid image locally, run `docker build --platform linux/amd64 -f grid/Dockerfile -t skycalm-grid:local .`. The Linux process has a ten-minute deadline.

**Deployment status.** The public site serves forecasts, archived replays and Aviation Weather Center observations from Stockholm. In the first Phase 3 cloud rehearsal, a click on **Publish replay** rebuilt all 13 forecast steps and updated the 69-point Edinburgh–Porto route in 62.4 seconds. Scheduled discovery is off. Use **Check NOAA for a new run** to admit a new cycle. An on-demand invocation of the observations Lambda (its name is available from the dev `observations_function` output) with an empty JSON object refreshes the observations. When the current forecast exceeds its 36-hour window, the passenger app opens a dated replay.

For another deployment, set the approved account in `TF_VAR_account_id` and check temporary credentials with `bash scripts/check_aws.sh`. Bootstrap the protected state bucket and private ECR repositories, and keep an encrypted backup of bootstrap state. From a clean release commit, build and check both Lambda images, then run `bash scripts/lambda_images.sh publish` using the approved AWS profile. Pass `-var-file="$PWD/build/lambda-images.tfvars.json"` to the dev plan and pin the separate grid image with `TF_VAR_image_digest`. The dev backend uses S3 native locking. To request a specific complete NOAA cycle, run `bash scripts/run_grid.sh gfs-YYYYMMDD-HH`. It submits the same admission event as discovery and prints the Step Functions execution ARN. Repeating a cycle uses the same execution name. The planning model runs with `python3 scripts/estimate_cost.py`.

## Turbulence model evaluation

Five archived GFS cycles and their aircraft reports can replay the on-demand training pipeline locally. The dataset joins reports with an explicit intensity to the nearest grid point, pressure level and three-hour forecast step. The split uses whole observation days and removes forecast cycles shared across partitions.

```bash
docker build --platform linux/amd64 -f ml/Dockerfile -t skycalm-training:local .
docker build --platform linux/amd64 -f grid/Dockerfile -t skycalm-grid:local .
CHECK_GRID_IMAGE=skycalm-grid:local bash scripts/check_training.sh
```

The script prints the directory containing the Parquet splits, trained artifact, evaluation JSON and presentation report. With `CHECK_GRID_IMAGE` it also saves a `preview` grid. To see the candidate in the local UI, use the printed directory in `python -m services.forecast.local --data <directory>/preview`. Open the November 21 06:00 UTC replay and forecast Edinburgh to Porto at 14:15 UTC. Select a cruise point on the timeline to see its probability and strongest contributing factor. This classroom preview uses a simulated registry approval on your laptop.

In the five-day archive, 28 reports trained the model, 16 selected its iteration and seven tested it. Held-out macro F1 was 0.354 for LightGBM and 0.183 for the physical baseline. All seven held-out reports were light or moderate and east of 12°W. The gate requires five examples of each category in each evaluation region, an improvement in European macro F1 and no regression in moderate or severe recall. Its decision was pending. On 25 November 2026 the project owner manually approved v1 for the classroom demo. The 18:00 UTC grid then loaded v1 from the registry and scored 59 of the 69 samples on Edinburgh–Porto. The other ten used the near-surface CAPE calculation.

### Rehearse the model and route history

Choose **Weather source → Replay · 25 Nov · 18:00 UTC**. Select Edinburgh (EDI) and Porto (OPO), set departure to **26 November at 02:15 UTC** and choose **Forecast flight**. Select a cruise sample to see v1’s probability and feature contribution. This replay preserves the original published tiles. The earlier 21 November replay has the aircraft observation used in the classroom comparison.

Open **Route history** to explore five departures each on three routes. **Post-flight recap** pairs observed turbulence with a particular forecast sample. On the 21 November Edinburgh–Porto flight the pilot reported light turbulence and the nearby forecast sample was moderate. Open **How reports are matched** for the distance, time and altitude bounds. The page reads a small static snapshot. Athena uses the same S3 objects through an explicit Glue table. To regenerate or check the results:

```sh
python -m scripts.route_history --check
# After deploying the catalog, reuse the same check ID to re-read the same Athena execution.
python -m scripts.check_route_history --account "$TF_VAR_account_id" --check-id "$(git rev-parse HEAD)"
```

Set `enable_edge_waf=true` at deployment to attach the optional CloudFront ACL. With it enabled, the public forecast uses CloudFront and an IAM-signed Lambda URL. Direct API Gateway forecast routes then require IAM. The separate passenger API continues to check Cognito tokens. The two WAF rules cost about $7 per month while active, plus request charges. The default is off. [AWS WAF pricing](https://aws.amazon.com/waf/pricing/)

The optional Stockholm SageMaker pipeline uses two network-isolated Processing jobs and one Training job, each capped at five minutes on one `ml.m5.large`. Set `training_image_digest` to the published training image in the grid repository when planning an approved release. Start a single run with `aws sagemaker start-pipeline-execution --pipeline-name skycalm-turbulence --region eu-north-1`. The evaluation selects the registry status. SageMaker approval events publish `model.approved` on the forecast bus. At the start of a new grid job, Fargate pins the most recent approved model. Published runs retain their original forecast. Pressure-level predictions carry their winning-class probability and strongest positive TreeSHAP feature. Climb and descent continue to use the physical fallback below the pressure grid.

The route timeline also includes a two-sentence briefing derived from the sampled categories and data coverage. To prepare one optional Bedrock variation for an archived classroom route, run `python -m scripts.flight_briefing --run gfs-20261121-06 --origin EDI --destination OPO --departure 2026-11-21T14:15:00Z`. The default is local. With separate cloud approval, `--bedrock` allows one Nova Lite request in Stockholm and `--publish` stores the validated selection. Cached public demo briefings expire after seven days. Training artifacts and evaluation metrics stay in the private weather bucket while their registry versions refer to them. Retire the registry version before removing its artifacts. The public API reads the cached selection or uses its template. Only precomputed sentence alternatives are sent to the provider.
