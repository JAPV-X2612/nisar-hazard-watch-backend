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
| `EARTHDATA_TOKEN` | unset | Reported as configured or not (blank counts as missing); never logged or returned |
| `MODAL_TOKEN_ID`, `MODAL_TOKEN_SECRET` | unset | Both are needed to count as configured; never logged or returned |

## API

| Endpoint | Purpose |
|---|---|
| `GET /api/v1/health` | Dependency report: database (critical), NASA CMR, Modal and Earthdata credentials. `200` when ok or degraded, `503` when a critical dependency is down |
| `GET /api/v1/health/live` | Liveness only; never touches a dependency (used by the Railway health check) |

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
  services/     use cases: HealthService, ScenePlanner (and scene_selection)
  ports/        interfaces the services depend on (DependencyProbe, SarCatalog)
  adapters/     implementations: db/, nasa/ (CMR health), asf/ (scene catalog), credentials/
  models/       camelCase DTOs (CamelModel), problem details, health
  constants/    routes, headers, reason codes, enums: no magic strings
  config/       settings (pydantic-settings)
  exceptions/   AppError and subclasses
  utils/        logging, request context, database url, timing, geometry (areas of interest)
migrations/     Alembic (async), baseline revision 0001
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

## Testing

```bash
uv run pytest                                      # unit tests, no network, 80 % coverage gate
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/nisar_hazard_watch \
  uv run pytest -m integration                     # needs a real PostgreSQL
uv run pytest -m live                              # calls the real NASA CMR and ASF catalog
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
