# NISAR Hazard Watch — Backend

FastAPI backend for **NISAR Hazard Watch**, the NASA Space Apps 2026 project that reads NISAR radar to show surface change after earthquakes, fires, floods and forest loss. The backend plans each exploration from the public ASF catalog, orchestrates the ML workers on Modal and serves the results to the frontend. This repository currently holds the **foundation**: the app factory, configuration, one error shape, structured logs, the health endpoints, Alembic, Docker, CI and the Railway deployment. The exploration API comes next.

## Quickstart

```bash
uv sync                                  # Python 3.13 + locked dependencies
cp .env.example .env
docker compose up -d db                  # PostgreSQL 17 on localhost:5432
uv run alembic upgrade head
uv run uvicorn nisar_hazard_watch.main:app --reload
curl localhost:8000/api/v1/health
```

Or run everything in containers with `docker compose up --build` (applies the migrations, then serves on `:8000`). Interactive docs live at `/docs`.

## Configuration

Environment variables (see `.env.example`). The app fails at start-up on a malformed value instead of running misconfigured: origins, timeouts and the log level are validated, and `ENVIRONMENT=production` refuses to start without an explicit `DATABASE_URL`. `DATABASE_URL` accepts the plain `postgresql://` form that Railway provides and adds the asyncpg driver itself.

| Variable | Default | Meaning |
|---|---|---|
| `ENVIRONMENT` | `local` | `local`, `test` or `production` |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` or `CRITICAL` (any case); JSON logs on stdout |
| `DATABASE_URL` | local Postgres | SQLAlchemy URL of the application database (required in production, never printed) |
| `CORS_ALLOWED_ORIGINS` | `http://localhost:5173` | Comma-separated list or JSON array of origins such as `https://app.example.com` (scheme and host, no path, no trailing slash, at least one) |
| `CMR_HEALTH_URL` | NASA CMR health | Endpoint probed by `/api/v1/health` |
| `CMR_HEALTH_TIMEOUT_SECONDS` | `5` | Per-phase HTTP timeout of the CMR probe (> 0) |
| `DATABASE_HEALTH_TIMEOUT_SECONDS` | `3` | Total deadline of the database probe (> 0) |
| `HEALTH_PROBE_TIMEOUT_SECONDS` | `10` | Total deadline of any probe; a slower one is reported as down (> 0) |
| `ML_GATEWAY_URL` | `https://ch0comilo--nisar-hazard-watch-ml-dev.us-east.modal.run` | Modal gateway that runs the analysis of a scene plan |
| `RUNNER` | `gateway` | `gateway`, or `inProcess` (synthetic results labelled as demo; refused in production) |
| `MAX_ACTIVE_EXPLORATIONS` | `5` | Explorations running at once; more get `503 QUEUE_FULL` |
| `EXPLORATION_DEADLINE_SECONDS` | `55` | After this a running exploration is answered `partial` with `TIMEOUT_PARTIAL` |
| `EXPLORATION_CACHE_TTL_SECONDS` | `86400` | A finished exploration with the same lens, area and scenes is reused for this long |
| `RATE_LIMIT_PER_MINUTE` | `20` | Requests per client (left-most `X-Forwarded-For`, else socket peer) to the exploration and coverage endpoints |
| `ETA_PRIOR_SECONDS` | `60` | ETA until three comparable runs exist; then the p80 of the last 50 |
| `ASF_TIMEOUT_SECONDS`, `GATEWAY_TIMEOUT_SECONDS` | `30`, `20` | HTTP timeouts towards the ASF catalog and the ML gateway (> 0) |
| `PRECOMPUTED_CASES_PATH` | unset | JSON list of precomputed cases offered when the catalog is down |
| `EARTHDATA_TOKEN` | unset | Reported as configured or not (blank counts as missing); never logged or returned |
| `MODAL_TOKEN_ID`, `MODAL_TOKEN_SECRET` | unset | Both are needed to count as configured; never logged or returned |

## API

| Endpoint | Purpose |
|---|---|
| `GET /api/v1/health` | Dependency report: database (critical), NASA CMR, Modal and Earthdata credentials. `200` when ok or degraded, `503` when a critical dependency is down |
| `GET /api/v1/health/live` | Liveness only; never touches a dependency (used by the Railway health check) |
| `POST /api/v1/explorations` | Start an exploration `{lens, geometry, source?, opticalEvidence?}` (`geometry` is a GeoJSON Point, Polygon or MultiPolygon). `202` while it runs, `200` when the answer is final (cache hit, or no data) |
| `GET /api/v1/explorations/{id}` | Status, stage, per-stage seconds, `etaSeconds` and `etaRemainingSeconds`, progress, the scene plan and, when done, the result with its layers, limitations and `scientificStatus` |
| `DELETE /api/v1/explorations/{id}` | Cancel a running exploration |
| `GET /api/v1/explorations/{id}/layers/{layerId}` | `307` redirect to the layer image on the ML gateway |
| `GET /api/v1/lenses` | The supported lenses and how many dates they need |
| `GET /api/v1/coverage?lon=&lat=` | The scene plan for a point without running anything |

Every response carries `X-Request-ID` (a safe incoming value is kept, otherwise one is generated), including unexpected 500s, which also keep their CORS headers. Errors are `application/problem+json` (server-side details are never echoed, and the headers of an `HTTPException` such as `Allow` or `Retry-After` are preserved):

```json
{ "type": "about:blank", "title": "Not Found", "status": 404, "detail": "Not Found",
  "reasonCode": "NOT_FOUND", "requestId": "bd343cf307d144609d84178020e7ffd2" }
```

Payload fields are camelCase.

## Project layout

```
src/nisar_hazard_watch/
  api/          app factory, composition root, middlewares (request id, unexpected errors), error handlers, routes/<resource>/
  services/     use cases: HealthService, ScenePlanner (and scene_selection), ExplorationService, EtaEstimator, lens_catalog
  ports/        interfaces the services depend on (DependencyProbe, SarCatalog, AnalysisRunner, JobRepository, PrecomputedCases)
  adapters/     implementations: db/ (jobs), nasa/ (CMR health), asf/ (scene catalog), runners/ (ML gateway, in-process), cases/, credentials/
  models/       camelCase DTOs (CamelModel), problem details, health
  constants/    routes, headers, reason codes, enums: no magic strings
  config/       settings (pydantic-settings)
  exceptions/   AppError and subclasses
  utils/        logging, request context, database url, timing, geometry (areas of interest)
migrations/     Alembic (async): 0001 baseline, 0002 explorations
tests/          unit/ (mirrors src), integration/ (Postgres), live/ (NASA)
```

### Adding an endpoint group

1. Add the path and reason codes to `constants/`.
2. Create `api/routes/<resource>/routes.py` exporting a `router`.
3. Append `(router, "/<resource>")` to `ROUTERS` in `api/routes/router.py`.
4. Put logic in `services/`, depend on a `ports/` interface and implement it in `adapters/`.
5. Write DTOs as `CamelModel` subclasses and the tests mirroring the source path.

## Scene planning (SAR core)

`ScenePlanner` turns an area of interest and "now" into the exact scenes to read. The area comes from `aoi_from_point` (the 10.24 km square in the local UTM zone) or `aoi_from_geojson` (a drawn polygon: closed ring, up to 100 vertices, repaired with `buffer(0)`, split at ±180°, measured on the ellipsoid and capped by native pixels: about 110 km² is the ideal, 400 km² the hard limit). `AsfCatalog` queries the public ASF SearchAPI once for the last five months without maturity or configuration filters (maturity is read from the product URL) and fails loudly instead of returning a truncated list. The planner keeps one scene per acquisition (VALIDATED over PROVISIONAL over BETA over urgent response, then CRID and version), picks one series, the ML service's key `track_direction_frame_bandwidthCode_mode` (a frame can mix 2005 and 4005 bandwidth codes or DHDH and QPDH modes, which have incompatible grids; full coverage, dual-pol, most dates, newest) and walks back from the newest scene in steps of about 30 days (± 6) up to five images. Fewer than four usable dates is an `insufficientHistory` plan, no scene at all is `noCoverage`, and `maturityMixed` tells the UI when the series mixes maturities.

## Exploration flow

`POST /api/v1/explorations` validates the area (`INVALID_GEOMETRY`, `AREA_TOO_LARGE`), refuses `source: "S"` (`SOURCE_NOT_AVAILABLE`: S-band will arrive as a precomputed layer), plans the scenes with `ScenePlanner`, and answers from the cache when the same lens, area and granules finished in the last day. Otherwise it checks capacity (`QUEUE_FULL`), hands the plan to the runner and stores the job. The default runner posts it to the Modal gateway of `NISAR-Modeling`, which reads the planned windows (up to 10.24 km at 10 m), runs the lens and serves the layers; polling `GET /explorations/{id}` refreshes the job from the gateway. Failures are explicit: no scenes is a final `noData` answer with `NO_COVERAGE` or `INSUFFICIENT_HISTORY`; a catalog outage is `502 UPSTREAM_CATALOG_ERROR` (and names a precomputed case when one matches); an exploration past the deadline is `partial` with `TIMEOUT_PARTIAL`. Every result carries `limitations[]`, `scientificStatus: "diagnostic"` and `isDemo`; an area wider than the analysed window says so in `limitations` and `quality.windowTruncated`. Measured on 2026-11-12 (Qadirabad, five scenes, 1024 × 1024 cells): about 35 s of analysis plus rendering once warm, 47 s from a cold start.

## Testing

```bash
uv run pytest                                      # unit tests, no network, 80 % coverage gate
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/nisar_hazard_watch \
  uv run pytest -m integration                     # needs a real PostgreSQL
uv run pytest -m live                              # real NASA CMR and ASF catalog, and one exploration on the ML gateway
```

## Quality

```bash
uv run ruff check && uv run ruff format --check && uv run pyright
uv run pre-commit install
```

## CI

`.github/workflows/ci.yml` runs on every pull request and on pushes to `main`: **Checks (lint, types, tests)** (ruff, pyright, pytest with coverage against a PostgreSQL service) and **Docker build**.

## Deployment

Railway builds the `Dockerfile`, runs `alembic upgrade head` before each deploy (`railway.toml`) and health-checks `/api/v1/health/live`. Variables: `DATABASE_URL` (reference of the Postgres service), `CORS_ALLOWED_ORIGINS`, `ENVIRONMENT=production`, `LOG_LEVEL`. **`main` is production**: change it only through reviewed pull requests with green CI.

## License

Apache-2.0.
