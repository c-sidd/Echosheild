# EchoSheild Backend

FastAPI application layer for the EchoSheild 3D Ocean Data Visualization Platform.

## Problem-statement status (audit 2026-08-22)

SIH PS: web-based interactive 3D ocean visualization integrating model outputs
and in-situ observations. Current completion vs its requirements:

| Requirement | Status | Notes |
| --- | --- | --- |
| 3D volumetric rendering (slices/isosurfaces/animation) | backend-ready, no UI | `slice`, `times`, `currents` APIs live **and value-verified against the real INCOIS NetCDF product**; WebGL layer not started (`frontend/` is empty scaffolding) |
| Instrument overlay (Argo/Glider/CTD/BGC) | partial | Argo complete (remote + local-cache provider, profile drill-down); glider pluggable stub; CTD/BGC not started |
| Multi-format ingestion (NetCDF + text, modular) | done | xarray/pydap, CSV/TSV, ISO 19115 auto-discovery, canonical variable-mapping layer; **real 280 MB INCOIS ARGO Monthly VAM product registered & verified** |
| Colorbar/variable/opacity/exaggeration controls | backend-ready, no UI | units, ranges, `max_speed_ms`, downsampling strides exposed for the UI |
| Scalable web architecture (REST/OPeNDAP, deployable) | done* | FastAPI + THREDDS client + docker compose (config validated); *THREDDS container runtime not exercised here (registry pulls blocked by environment egress) |
| Extensible plugin design | partial | `GliderClient` seam, `ARGO_PROVIDER` factory, canonical layer; needs a second concrete plugin |
| Open standards (CF, WMS/WCS) | partial | CF coordinate/variable resolution implemented; WMS advertised from metadata (unverified live — upstream unreachable from this machine); WCS never falsely advertised |

Overall ≈ 55%: backend/data layer ~95% (tested, live-verified against real
data), presentation layer 0%. Next milestone: frontend bootstrap +
first slice-rendering loop against `incois_argo_mnt_VAM`.

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
| `GET /model/{id}/depths` | Vertical levels in native units (`metadata.vertical_kind`: depth meters / pressure dbar) |
| `GET /model/{id}/slice?variable&time_index&depth&west&east&south&north` | 2-D grid slice (auto-downsampled to `MAX_GRID_POINTS`, NaN → null) |
| `GET /model/{id}/profile?variable&latitude&longitude&time_index` | Vertical profile at nearest grid point |
| `GET /model/{id}/point?variables=a,b&latitude&longitude&time_index&depth` | Nearest-grid point sample |
| `GET /model/{id}/currents?time_index&depth&bbox…` | (u, v) vector field + max speed; `{"available": false, "reason": …}` when absent |
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

1. Local NetCDF under `NETCDF_DATA_ROOT`, `ARGO_CACHE_DIR` and
   `GLIDER_CACHE_DIR` (IDs prefixed `local_`; cache-dir collisions get
   deterministic `local_<dirname>_<stem>` IDs). When an ISO 19115 sidecar
   record matches a file — exact stem, or ERDDAP-style download names with
   hash suffixes (`incois_argo_mnt_VAM_<hash>.nc` ↔
   `incois_argo_mnt_VAM_iso19115.xml`) — the ISO product identifier becomes
   the stable dataset ID and the record enriches title/provider/license/
   bounds/services. **The real 280 MB INCOIS ARGO Monthly VAM product is
   registered this way as `incois_argo_mnt_VAM`.**
2. ISO 19115 metadata records (`*iso19115*.xml`) under `DATA_ROOT`
   — the included INCOIS ERDDAP records register real products such as
   `incois_argo_sst_weekly` with griddap/OPeNDAP + WMS endpoints, and
   provider/license provenance
3. Optional THREDDS catalog entries when `THREDDS_CATALOG_URL` is set

Corrupt/unreadable files are isolated: discovery logs a warning per bad file
and continues; one broken `.nc` never removes the healthy registry.

Remote datasets open lazily via xarray (`engine=pydap`) — no bulk downloads.
Paths are validated against path traversal; service URLs must be http(s).

## Canonical variable mapping (`app/ingestion/variable_mapping.py`)

All data responses expose a **canonical variable layer** so the frontend can
render any source schema without per-dataset special cases:

* Coordinates resolved by CF precedence — `standard_name` → `axis` attribute →
  units → known names. INCOIS conventions (`TAXIS/XAXIS/YAXIS/ZAX`,
  `TEMP/SAL`) resolve out of the box; result is reported in
  `metadata.coordinate_mapping`.
* Variables classified to canonical categories (`temperature`, `salinity`,
  `u_current`, `v_current`, `chlorophyll`, …) exposed as
  `canonical_name` on variables/slices/profiles/points.
* Vertical honesty: axis kind is `depth` (meters), `pressure` (native dbar)
  or `other`. Pressure values are **never silently converted** to meters;
  responses carry `vertical_kind` + `vertical_units`.

Regenerate the dataset manifest (what is registered, from which files) with:

```bash
uv run --project backend python scripts/generate_dataset_manifest.py
# -> data/datasets/datasets.json
```

## Argo provider selection

`ARGO_PROVIDER=auto|local|remote` (default `auto`). With NetCDF profile files
present in `data/argo_cache/`, `/argo/*` endpoints are served entirely
locally (no network); otherwise they fall through to argopy remote access.
Local files keep pressure as pressure — `depth_meters` is only populated
when the file itself provides depth.

Remote access defaults to the Ifremer ERDDAP (`ARGO_SOURCE=erddap`) with
`ARGO_API_TIMEOUT` seconds budgeted per query (`ARGO_ERDDAP_URL` /
`ARGO_GDAC_URL` override the endpoints). `gdac` mode downloads per-float
NetCDF files sequentially and needs much larger timeouts. When
`/argo/floats` or `/argo/search` are called without explicit dates the route
applies a rolling **90-day window** ending today so bulk region queries
finish inside request timeouts (argopy itself stays unbounded when used
programmatically — pinned by tests).

## Configuration

All configuration flows through `app/core/config.py` (`pydantic-settings`) and
`.env.example`. Key groups: application/CORS, THREDDS/OPeNDAP/WMS/WCS/ERDDAP
URLs, Argo source/dataset/timeout/server-URLs, data roots and caches, request
timeout, and response-size limits (`MAX_DATA_POINTS`, `MAX_PROFILE_POINTS`,
`MAX_GRID_POINTS`). Under docker compose the *advertised* service URLs use the
host-mapped port (`http://localhost:8080/thredds`) because the internal
`thredds` hostname is unresolvable from a user's browser; server-side catalog
discovery tolerates unreachable URLs by design.

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
uv run pytest            # 132 tests (real-data integration + offline units)
uv run ruff check .
uv run ruff format --check .
uv run mypy app          # strict mode
uv sync                  # dependency resolution from uv.lock
```

Tests run fully offline: synthetic NetCDF fixtures, mocked argopy/httpx, plus
`tests/test_real_data_integration.py` which value-verifies the real INCOIS
product when present (auto-skipped if the file is absent).

## Known limitations

* WCS is advertised only if an external WCS-capable service is configured;
  stock THREDDS 5.x exposes OPeNDAP/WMS/HTTPServer (catalog reflects this).
* ERDDAP tabledap records (e.g. `Indian_ARGO_Floats`) are listed but not
  openable through the gridded model API.
* Argo endpoints require internet access to the configured ERDDAP/GDAC.

---

## Development log

### Session 2026-08-23 — full-stack deployment live (THREDDS + TLS + Argo)

**Docker stack running end-to-end and verified against real upstreams**
(all green: 132 tests, ruff, strict mypy):

* Frontend shipped on top of the API: layer-toggle request gating,
  ServicesPanel + `useServices` hook, deck.gl WMS overlay with per-upstream
  `LAYERS` naming (THREDDS bare variable vs ERDDAP `dataset#var`).
* Compose advertises host-reachable THREDDS URLs (`localhost:8080`) — the
  internal `thredds:` name cannot resolve in a browser. Catalog
  `datasetScan` path aligned with the backend's `sample_netcdf` layout so
  catalog URLs match registry file paths.
* TLS fix: INCOIS ERDDAP serves only its leaf certificate and chains to
  GlobalSign R3, which modern CA bundles dropped. The image now installs
  GlobalSign R3 root + OV 2018 intermediate (public certs, in
  `docker_certs/`) into both the system store **and** the certifi bundle
  (httpx/requests trust certifi, not the OS store).
* argopy runtime: non-root user gets a home dir (`useradd --create-home`)
  for its cache; GDAC fetchers require string datetimes — box time bounds
  are passed as ISO strings.
* Argo route defaults: `/argo/floats|search` apply a rolling 90-day window
  when no dates are given. Unbounded region queries via GDAC never finish
  (~50 sequential per-float downloads); bounded ERDDAP queries return in
  ~30 s raw. Live call: HTTP 200 with 50 Indian-Ocean floats (~105 s first
  hit).
* Env additions: `ARGO_API_TIMEOUT`, `ARGO_ERDDAP_URL`, `ARGO_GDAC_URL`;
  compose defaults `ARGO_SOURCE=erddap`.

Known follow-up (deliberately deferred): the implicit `end = Timestamp.now()`
in `argo_client._region_box` participates in the FileCache key at microsecond
precision, so `/argo/floats` responses effectively never cache across
requests. Truncating the implicit end to day precision would restore caching.

### Session 2026-08-22 — real-data integration & final validation

**Real dataset integrated and live-verified** (all green: 114 tests, ruff,
format, strict mypy):

* Inventoried `data/`: real INCOIS ARGO Monthly VAM gridded product
  (280 MB NetCDF: TEMP/SAL on time=271 × ZAX=24 × lat=60 × lon=90,
  30.5–119.5 °E / 29.5 °S–29.5 °N, depth 5–2000 m in METERS, 2004‑01‑15 →
  2026‑07‑15) + 6 ISO 19115 records. No glider data; `argo_cache` empty.
* Registry: deterministic ISO-derived dataset IDs with sidecar prefix
  matching for ERDDAP-style download names; THREDDS local-copy service URLs
  merged with upstream ERDDAP endpoints; corrupt-file isolation kept.
* **WCS honesty fix**: `build_thredds_service_urls` no longer inherits WCS
  from the THREDDS base — advertised only when `WCS_BASE_URL` is explicitly
  configured (catalog defines OPeNDAP/WMS/HTTPServer only).
* Canonical variable resolution in `ModelDataService`: `/slice`, `/profile`,
  `/point` accept canonical names (`temperature`) *and* raw source names
  (`TEMP`). `/point` values now keyed by canonical category.
* Manifest regenerated (`data/datasets/datasets.json`, 7 datasets; real
  product is `local`, never `remote_only`).
* Live verification vs direct xarray truth: temperature/salinity slices
  element-wise identical (bbox orientation `values[lat][lon]` confirmed),
  profile column and point samples match to float32 precision; currents
  honestly unavailable; error contracts verified (404 unknown
  dataset/variable/index, 422 inverted bbox/negative index, controlled 503
  when Argo upstream unreachable, path-traversal IDs rejected).
* Performance on the real file (warm): metadata 5 ms, full-grid slice 7 ms
  (~76 KB), bbox slice 4 ms, profile/point 4 ms — fully lazy access.
* New `tests/test_real_data_integration.py` (16 tests, auto-skip when the
  real file is absent).
* Docs refreshed: `docs/api-contract.md`, new
  `docs/frontend-handoff.md`, this README.

**Verified:** everything above against the real file via live uvicorn run.

**NOT VERIFIED (environment egress blocks them):**

1. THREDDS container runtime — Docker daemon started but image pulls fail
   (registry CDN EOF). `docker compose config --quiet` passes; retry the
   stack on a working network.
2. Live INCOIS ERDDAP / IFREMER reachability — both blocked from this
   machine right now; upstream service URLs come from ISO metadata.

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
