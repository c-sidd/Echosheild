# EchoSheild Backend

FastAPI application layer for the EchoSheild 3D Ocean Data Visualization Platform.

## Architecture

```
                    ECHOSHIELD
                         |
              +----------+----------+
              |                     |
           FastAPI               THREDDS
       (application API)    (scientific serving)
              |                     |
   +-----+----+----+         OPeNDAP / WMS / HTTP
   |     |    |     |
  Argo Glider Model Text
   |     |    |     |
   argopy xarray/netCDF4  csv
```

* **FastAPI** — application API, validation, response shaping (`/api/v1/...`)
* **THREDDS** — scientific data serving (OPeNDAP/WMS); never reimplemented here
* **xarray + netCDF4/h5netcdf/pydap** — lazy NetCDF access (local *and* remote)
* **argopy** — Argo ingestion (ERDDAP/GDAC)
* **pydantic-settings** — all environment-specific configuration

## Quick start

```bash
cd backend
uv sync                                  # install locked dependencies
uv run uvicorn app.main:app --reload     # http://localhost:8000/docs
```

Generate a labelled synthetic sample dataset:

```bash
uv run --project backend python scripts/download_sample_data.py
# -> data/sample_netcdf/synthetic_ocean.nc  (SYNTHETIC - not real INCOIS data)
```

Full stack with THREDDS:

```bash
docker compose -f infra/docker-compose.yml up -d --build
```

## API

Interactive schema: `/docs` (Swagger) · `/redoc` · `/openapi.json`.
Frontend integration contract: [`docs/api-contract.md`](../docs/api-contract.md). overview (`/api/v1`)

| Endpoint | Purpose |
|---|---|
| `GET /health` | Liveness: status, service, version, environment, optional-dependency availability (`xarray`/`netCDF4`/`argopy`/…), THREDDS-configured flag |
| `GET /health/ready` | Readiness checks (data dir, registry, THREDDS/ERDDAP connectivity probes) |
| `GET /model/datasets` | Registered datasets (local files, ISO 19115 discoveries, THREDDS) |
| `GET /model/{id}/metadata` | Dimensions, variables, coordinates, time/depth ranges |
| `GET /model/{id}/variables` | Variable discovery |
| `GET /model/{id}/times` | Time axis (ISO-8601) |
| `GET /model/{id}/depths` | Depth levels in meters |
| `GET /model/{id}/slice?variable&time_index&depth&west&east&south&north` | 2-D grid slice (auto-downsampled to `MAX_GRID_POINTS`, NaN → null) |
| `GET /model/{id}/profile?variable&latitude&longitude&time_index` | Vertical profile at nearest grid point |
| `GET /model/{id}/point?variables=a,b&latitude&longitude&time_index&depth` | Nearest-grid point sample |
| `GET /model/{id}/currents?time_index&depth&bbox…` | (u, v) vector field + max speed |
| `GET /model/{id}/services` | OPeNDAP / WMS / WCS / ERDDAP URLs for direct frontend use |
| `GET /argo/floats?lon_min&lon_max&lat_min&lat_max` | Argo float search (Indian Ocean default) |
| `GET /argo/{wmo}` · `GET /argo/{wmo}/profile?cycle=n` | Float detail / single profile |
| `GET /glider/status` · `/glider/missions` | Explicit `not_configured` until a source exists |
| `GET /gliders` · `/gliders/{glider_id}` | Collection-style aliases of the glider API |

Errors are mapped consistently: unknown dataset/variable/cycle → **404**,
invalid parameters → **422**, upstream scientific service failure → **503**.

The versioned prefix is configurable via `API_V1_PREFIX`; with the default
`/api/v1`, the paths above resolve to `/api/v1/health`,
`/api/v1/model/datasets`, etc.

## Dataset registration & security

API requests reference **registered dataset IDs only** — there is no arbitrary
file or URL access. Sources discovered at startup:

1. Local NetCDF under `NETCDF_DATA_ROOT` (IDs prefixed `local_`)
2. ISO 19115 metadata records (`*iso19115*.xml`) under `DATA_ROOT`
   — the included INCOIS ERDDAP records register real products such as
   `incois_argo_sst_weekly` with griddap/OPeNDAP + WMS endpoints
3. Optional THREDDS catalog entries when `THREDDS_CATALOG_URL` is set

Remote datasets open lazily via xarray (`engine=pydap`) — no bulk downloads.
Paths are validated against path traversal; service URLs must be http(s).

## Configuration

All configuration flows through `app/core/config.py` (`pydantic-settings`) and
`.env.example`. Key groups: application/CORS, THREDDS/OPeNDAP/WMS/WCS/ERDDAP
URLs, Argo source/dataset, data roots and caches, request timeout, and
response-size limits (`MAX_DATA_POINTS`, `MAX_PROFILE_POINTS`,
`MAX_GRID_POINTS`). Inside docker compose, services communicate via names
(`http://thredds:8080/thredds`), never localhost.

## Reliability

* `app/core/reliability/retry.py` — exponential backoff; retries timeouts,
  transport errors and transient HTTP codes (408/425/429/5xx), never permanent 4xx
* `app/core/reliability/circuit_breaker.py` — opens after repeated upstream
  failures, half-open probe after a reset period
* Filesystem cache (`data/argo_cache/`, TTL, deterministic keys,
  size-aware pruning) designed to be replaceable by Redis later

## Tests & quality gates

```bash
cd backend
uv run pytest            # 69 tests (external services mocked)
uv run ruff check .
uv run ruff format --check .
uv run mypy app          # strict mode
uv sync                  # dependency resolution from uv.lock
```

Tests run fully offline: synthetic NetCDF fixtures, mocked argopy/httpx.

## Known limitations

* WCS is advertised only if an external WCS-capable service is configured;
  stock THREDDS 5.x exposes OPeNDAP/WMS/HTTPServer (catalog reflects this).
* ERDDAP tabledap records (e.g. `Indian_ARGO_Floats`) are listed but not
  openable through the gridded model API.
* Argo endpoints require internet access to the configured ERDDAP/GDAC.

---

## Development log

### Session 2026-08-21/22 — full backend implementation

**Built from scratch (all green: 64 tests, ruff, strict mypy):**

* Complete app skeleton: `core/config.py` (pydantic-settings), structured
  logging (`core/logging.py`), retry w/ exponential backoff + circuit breaker
  (`core/reliability/`), response schemas (`models/schemas.py`), app factory
  (`main.py`), health/readiness routes.
* Ingestion layer: `netcdf_parser.py` (lazy xarray open, slice/profile/point/
  currents extraction, NaN→null, downsampling caps),
  `iso19115_parser.py` (**auto-registers the 6 INCOIS ERDDAP ISO 19115 XML
  records in `/data` as remote datasets**, handles both old gmd- and new
  cit-style linkage XML), `thredds_client.py` (catalog parse + service URLs +
  circuit breaker), `argo_client.py` (argopy wrapper, mock seam,
  `_create_fetcher`), `text_parser.py` (CSV/TSV).
* Services: filesystem TTL cache, dataset registry (local + ISO19115 +
  optional THREDDS discovery), model service, NullGliderClient (explicit
  `not_configured`).
* API routes under `/api/v1`: model datasets/metadata/slice/profile/point/
  currents/services, Argo floats/profiles/search, glider status/missions.
* Infra: multi-stage Dockerfile (uv, non-root), `infra/docker-compose.yml`
  (backend + unidata/thredds-docker:5.6, service-name URLs), THREDDS
  catalog/config in `thredds/`, `.env.example`, sample-data generator script.
* Tests: 8 offline test modules (mocked argopy/httpx, synthetic NetCDF via
  `app/testing_utils.py`).

**Bugs found & fixed (relevant if you extend this code):**

* erddapy pinned `<3` — v3 broke argopy 1.4.0 imports (`_quote_string_constraints`).
* pydantic-settings force-decodes list env vars as JSON → use
  `Annotated[list[str], NoDecode]` pattern (see CORS_ORIGINS) if you add more.
* FastAPI exception handlers can't be registered with tuple keys — loop instead.
* Pydantic models silently drop unknown kwargs (e.g. `max_speed=` vs
  `max_speed_ms=` field name mismatch caused silent None).
* Docker venv shebangs must match final path — builder sets
  `UV_PROJECT_ENVIRONMENT=/app/.venv` up-front.
* Argo cycle counts = `nunique(CYCLE_NUMBER)`, not row counts.

**Verified:** local serving, container health (7 datasets registered inside
Docker), readiness degradation when THREDDS absent.

**NOT VERIFIED (needs network / future work):**

1. THREDDS container runtime — image pull blocked by Docker Hub CDN EOF
   errors from this machine (affects all images). Retry
   `docker compose -f infra/docker-compose.yml up -d --build` on a working network.
2. Live INCOIS ERDDAP reads & real Argo floats — mocked in tests.
3. Glider ingestion — no public source exists yet; client interface ready.

**Suggested next steps:** wire real ERDDAP tabledap reading for
`Indian_ARGO_Floats`; optional Redis cache backend; frontend consumption of
`/model/{id}/slice|currents|services`; revisit WCS if an external service
becomes available.
