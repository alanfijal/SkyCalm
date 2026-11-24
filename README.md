# SkyCalm

SkyCalm is a passenger guide to the parts of a European flight where the air may feel bumpy. The planned app combines a weather forecast, an estimated route and reports from aircraft. Every forecast will show the time of its weather run.

**For passenger education only. Do not use SkyCalm for navigation, flight planning or safety decisions.**

This is an ESADE Cloud Solutions project. The team reviews each phase before the next one begins. Phase 0 covers the design and demo plan. The first passenger-facing release is the Phase 1 route forecast.

## Run the Phase 0 checks

The cost estimate runs on Python 3.10 or later with the standard library. Use Python 3.12 for the project checks.

```sh
python3 scripts/estimate_cost.py
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --require-hashes -r requirements-dev.txt
python -m ruff format --check scripts tests
python -m ruff check scripts tests
python -m pytest -q
```

## Repository

| Path | Purpose |
| --- | --- |
| `web/` | Passenger PWA, globe and timeline |
| `services/` | One directory per Lambda as each handler is introduced |
| `grid/` | Fargate image, GRIB selection and baseline scoring |
| `ml/` | Dataset preparation, model training and evaluation |
| `infra/bootstrap/` | Remote state and tightly scoped deployment roles |
| `infra/modules/`, `infra/environments/dev/` | Reusable Terraform organized by service, composed in one active environment |
| `scripts/`, `tests/`, `.github/workflows/` | Cost model, checks and CI |

Use descriptive feature branches and commit one logical change at a time. Phase 0 can be reviewed entirely on a laptop. Cloud deployment commands and a reviewed Terraform plan arrive with the first deployable slice.
