# SkyCalm

SkyCalm shows where a European passenger route may feel bumpy. Choose two airports and a UTC departure to see the estimated path on a globe. Move along the timeline to inspect the local category, time and altitude. The first release uses real NOAA weather and a physics-based index.

**For passenger education only. Do not use SkyCalm for navigation, flight planning or safety decisions.**

## Run it on your laptop

Use Node 24, npm and Python 3.12 on macOS or Linux. Run these commands from the repository root.

```sh
(cd web && npm ci && npm run build)
python3 -m services.forecast.local
```

Open **http://127.0.0.1:4173**. Press Ctrl+C in the server terminal to stop. The bundled map, fonts, airport catalog and archived weather work offline after the build. No cloud account is needed.

On phones and tablets, tap **Edit flight** to change the airports or departure time. The sun or moon button in the header switches themes and remembers your choice on this browser.

**Try a replay.** Choose the archived **24 Nov 2026, 12 UTC** weather run, Barcelona (BCN) to Stockholm Arlanda (ARN), and depart on **24 Nov at 18:00 UTC**. Select **Forecast flight** if you change the route. The estimated flight takes 2 h 54 min. Use the timeline or the coloured route to explore the change from smooth to moderate. **Forecast guide** explains the model and its limits.

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

## Architecture and checks

`grid/` contains the Linux/amd64 worker. `services/forecast/` implements the HTTP API shared by the local server and Lambda. The three public GET routes are `/api/airports?q=BCN`, `/api/runs` and `/api/forecast` with `origin`, `destination`, `departure` and `run`. `web/` contains the React app, MapLibre globe and deck.gl route layer.

The Stockholm Terraform configuration defines a private S3 web origin behind CloudFront, a regional HTTP API and arm64 Lambda, S3 weather and replay objects, a DynamoDB latest-run pointer and a manually started Fargate task. The worker can finish a single job in its public subnet and exit. Its security group allows outbound HTTPS. S3 and DynamoDB use regional gateway endpoints. The API role can read weather and the worker role can publish it. Working weather objects expire after seven days. The archived demonstration run has its own prefix. [Application infrastructure](infra/modules/forecast/) · [Bootstrap](infra/bootstrap/)

```sh
source .venv/bin/activate
python -m pip install --require-hashes -r requirements-dev.txt
python -m ruff format --check grid services scripts tests
python -m ruff check grid services scripts tests
python -m pytest -q
python scripts/package_lambda.py
(cd web && npm ci && npm run lint && npm test && npm run build)
(cd web && npx playwright install --only-shell chromium && npm run test:layout)
terraform fmt -check -recursive infra
for directory in infra/bootstrap infra/environments/dev; do
  terraform -chdir="$directory" init -backend=false -input=false -lockfile=readonly
  terraform -chdir="$directory" validate
  terraform -chdir="$directory" test
done
```

These Terraform tests plan against a mocked AWS provider. CI runs them with the same build inputs. The Lambda ZIP normalizes entry dates and uses hash-locked wheels. To build the grid image locally, run `docker build --platform linux/amd64 -f grid/Dockerfile -t skycalm-grid:local .`. The Linux process has a ten-minute deadline.

**Deployment status.** Phase 1 is available locally. An AWS deployment requires a reviewed plan, the expected account in `TF_VAR_account_id`, an authorized temporary identity and the published ECR image digest. Verify the identity with `bash scripts/check_aws.sh`. Bootstrap state starts locally and needs an encrypted backup. The dev root uses a versioned S3 backend and native locking. After approval and deployment, `bash scripts/run_grid.sh gfs-YYYYMMDD-HH` admits one dated task when the cluster is idle. Each run prints its task ARN. The initial local release creates no schedule. The full-project planning model runs with `python3 scripts/estimate_cost.py`.
