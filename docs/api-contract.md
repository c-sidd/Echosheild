# EchoShield Backend API Contract

Contract for frontend integration with the EchoShield FastAPI backend.
Every example below was captured from a **live verified** server run.
Primary verification dataset: the **real** INCOIS ARGO Monthly VAM gridded
product (`incois_argo_mnt_VAM`, 271 monthly steps 2004‑01‑15 → 2026‑07‑15,
60×90 grid, 30.5–119.5 °E / 29.5 °S–29.5 °N, depth axis 5–2000 m,
variables `TEMP`→`temperature`, `SAL`→`salinity`). The synthetic fixture
(`local_synthetic_ocean`) remains as a deterministic test dataset.

Interactive schema: `/docs` (Swagger UI), `/redoc`, `/openapi.json`.

---

## 1. Conventions

| Aspect | Value |
| --- | --- |
| Base URL | `http://<host>:<port>/api/v1` (prefix configurable via `API_V1_PREFIX`) |
| Methods | `GET` only (read-only API; CORS allows GET) |
| Encoding | JSON (UTF-8) |
| Timestamps | ISO-8601 strings, e.g. `"2024-01-01T00:00:00"` |
| Missing values | Never NaN/Inf — always JSON `null` |
| Longitudes | `-180..180` (inputs accept up to `360`) |
| Latitudes | `-90..90` |
| Vertical axis | `vertical_kind` on responses: `"depth"` (meters), `"pressure"` (native dbar — never silently converted) or `"other"` |
| Blocking safety | Data handlers run in the worker threadpool; a slow upstream never stalls unrelated requests |

## 2. Error contract

Errors are always `{"detail": "<human readable message>"}`.

| HTTP | Trigger | Example detail |
| --- | --- | --- |
| 404 | Unknown dataset / variable / float / cycle, out-of-range index | `"unknown variable 'oxygen'; available: ['salinity', 'temperature', 'u', 'v']"`, `"time_index 999 out of range [0, 7]"` |
| 422 | Malformed query params (FastAPI validation), partial bbox, bad lon/lat ordering | `"bbox requires all of west, east, south and north"` |
| 503 | Upstream scientific service failed after retries / circuit breaker; metadata-only dataset queried for data | `"upstream unavailable: Cannot connect to host erddap.ifremer.fr:443 ..."` |

Frontend guidance: treat 503 as *temporary* (backend already applies retry +
circuit-breaker); show a dismissible "data source temporarily unavailable"
banner with retry, never a crash screen. Treat 404 as *permanent* for the
current selection.

## 3. Health

### `GET /health` (i.e. `/api/v1/health`)
Liveness + environment report.

```json
{
  "status": "healthy",
  "service": "echoshield-backend",
  "version": "0.1.0",
  "environment": "development",
  "optional_dependencies": {
    "xarray": "available", "netCDF4": "available", "h5netcdf": "available",
    "pydap": "available", "argopy": "available"
  },
  "thredds_configured": false
}
```

### `GET /health/ready`
Readiness probe (checks data directory, registry, THREDDS config, INCOIS ERDDAP reachability).
Returns 200 even when `ready:false` — inspect `checks[].status`
(`ok | unavailable | not_configured`). Suitable for orchestrator probes and
frontend "system status" widgets.

## 4. Ocean model data (`/model`)

### `GET /model/datasets` → `DatasetInfo[]`
Registered datasets: local NetCDF samples, INCOIS ERDDAP products (discovered
from ISO 19115 metadata), cached Argo/Glider NetCDF files, and THREDDS catalog
entries when configured. Provenance fields `provider`, `license`,
`metadata_path` are populated when a sidecar ISO record or file attributes
supply them.

```json
[
  {
    "id": "incois_argo_mnt_VAM",
    "title": "INCOIS ARGO Monthly data Variational Analysis Methodology",
    "summary": "INCOIS ARGO Monthly data Variational Analysis Methodology",
    "source_type": "local",
    "time_range": {"start": "2004-01-15T00:00:00", "end": "2026-07-15T00:00:00", "count": 271},
    "spatial_bounds": {"west": 30.5, "east": 119.5, "south": -29.5, "north": 29.5},
    "services": {"dataset_id": "incois_argo_mnt_VAM", "erddap_griddap": "https://erddap.incois.gov.in/erddap/griddap/incois_argo_mnt_VAM", "...": "..."},
    "provider": "INCOIS",
    "license": "<use limitation text from the ISO record>",
    "metadata_path": "incois_argo_mnt_VAM_iso19115.xml",
    "enabled": true
  }
]
```

Dataset IDs are **deterministic**: when a sidecar ISO 19115 record matches a
local file (exact stem, or ERDDAP-style download names with hash suffixes —
`incois_argo_mnt_VAM_<hash>.nc` ↔ `incois_argo_mnt_VAM_iso19115.xml`), the ISO
product identifier becomes the stable ID; otherwise files register as
`local_<stem>`.

### `GET /model/{dataset_id}/metadata` → `DatasetMetadata`
Dimensions dict, variable list (`name`, `canonical_name`, `long_name`,
`standard_name`, `units`, `dimensions`, `shape`), coordinates, global
attributes, time/depth ranges, spatial bounds, service endpoints when
available, plus `coordinate_mapping` — the resolved coordinate variables,
e.g. `{"time": "TAXIS", "latitude": "YAXIS", "longitude": "XAXIS",
"pressure": "ZAX"}` for INCOIS-style files. Live example (real VAM product):

```json
{
  "coordinate_mapping": {"time": "time", "latitude": "latitude", "longitude": "longitude", "depth": "ZAX"},
  "depth_range": {"min_meters": 5.0, "max_meters": 2000.0, "count": 24,
                   "positive_down": true, "vertical_kind": "depth", "vertical_units": "METERS"},
  "spatial_bounds": {"west": 30.5, "east": 119.5, "south": -29.5, "north": 29.5}
}
```

### `GET /model/{dataset_id}/variables` → `VariableMetadata[]`
Each variable carries `canonical_name` — the EchoShield canonical category
(`temperature`, `salinity`, `u_current`, `v_current`, `chlorophyll`, …) or
`null` when the variable has no canonical mapping.

### `GET /model/{dataset_id}/times` → `{start, end, count}`

### `GET /model/{dataset_id}/depths` → `float[]`
Vertical axis values in **native units** — meters for `vertical_kind:"depth"`,
dbar for `"pressure"` (no conversion applied). Interpret via
`metadata.coordinate_mapping` / slice responses. Real VAM product:
`[5.0, 10.0, 20.0, 30.0, 50.0, 75.0, 100.0, 125.0, 150.0, 200.0, 250.0,
300.0, 400.0, 500.0, 600.0, 700.0, 800.0, 900.0, 1000.0, 1200.0, 1400.0,
1600.0, 1800.0, 2000.0]`.

### `GET /model/{dataset_id}/slice` → `ModelSlice`
One horizontal 2-D field — the primary feed for 2-D rendering / volume slicing.

| Param | Type | Notes |
| --- | --- | --- |
| `variable` | str, required | e.g. `temperature`, `salinity`, or any source name (INCOIS `TEMP`, `SAL`, …) |
| `time_index` | int ≥ 0 | defaults to 0 |
| `depth` | float | nearest vertical level; units follow `vertical_kind` (meters for depth, dbar for pressure) |
| `west`,`east`,`south`,`north` | float | optional bbox; **all four required together** |

```json
{
  "dataset_id": "incois_argo_mnt_VAM",
  "variable": "TEMP",
  "canonical_name": "temperature",
  "units": "degs",
  "time_index": 100,
  "time": "2012-05-15T00:00:00",
  "depth_meters": 5.0,
  "vertical_kind": "depth",
  "vertical_units": "METERS",
  "latitude": [10.5, 11.5, "..."],
  "longitude": [60.5, 61.5, "..."],
  "values": [[29.51, 29.50, "..."], ["...", "..."]],
  "downsampling": {}
}
```

The `variable` parameter accepts **either the canonical category
(`temperature`, `salinity`, …) or the raw source name (`TEMP`, `SAL`)** —
canonical resolution is applied server-side.

**Grid orientation:** `values[i][j]` is row `latitude[i]`, column
`longitude[j]`. Grids larger than `MAX_GRID_POINTS` (100 000) are
automatically downsampled; the applied strides are reported in
`downsampling` (e.g. `{"latitude_stride": 2, "longitude_stride": 2}`).

**Vertical axis honesty:** `vertical_kind` is `"depth"` (values in meters),
`"pressure"` (values in native pressure units, e.g. dbar — *no silent
conversion*), or `"other"`. INCOIS products whose vertical axis is pressure
(e.g. `ZAX` in dbar) are reported as `"pressure"`.

### `GET /model/{dataset_id}/profile` → `OceanProfile`
Vertical profile at the nearest grid point. Params: `variable` (required),
`latitude`, `longitude` (required), `time_index`. Returns parallel arrays
`depths_meters[]` and `values[]` (null where missing), plus
`vertical_kind`/`vertical_units` describing the axis and `canonical_name`
for the variable. Capped at `MAX_PROFILE_POINTS` (500).

### `GET /model/{dataset_id}/point` → `PointSample`
Multi-variable sample for hover popups / inspector panels. Params:
`variables` (comma-separated, 1–8 names), `latitude`, `longitude`,
optional `time_index`, `depth`. The `values` map keys are the canonical
variable categories when a mapping exists, else source names.

```json
{
  "dataset_id": "incois_argo_mnt_VAM",
  "latitude": 15.5, "longitude": 70.5,
  "time": "2008-03-15T00:00:00", "depth_meters": 75.0,
  "vertical_kind": "depth", "vertical_units": "METERS",
  "nearest_grid": {"latitude": 15.5, "longitude": 70.5},
  "values": {"temperature": 24.865334, "salinity": 36.109665},
  "units": {"temperature": "degs", "salinity": "PSU"}
}
```

`values`/`units` keys are the **canonical categories** when a mapping exists
(stable across datasets), falling back to source names otherwise.
`variables` accepts canonical or raw names, comma-separated.

### `GET /model/{dataset_id}/currents` → `CurrentVectorField | CurrentsUnavailable`
Horizontal u/v vector field for flow overlays. Params: `time_index`,
`depth`, optional bbox. Detection is **metadata-driven**: the (u, v) pair is
resolved from canonical variable mapping (`u`/`v`, `uo`/`vo`,
`usurf`/`vsurf`, `eastward_velocity`/…, INCOIS-style names). Datasets
without currents return **200** with an explicit unavailability contract —
never fabricated data:

```json
{"dataset_id": "incois_argo_mnt_VAM", "available": false, "reason": "Current vector variables are not available in this dataset."}
```

When available, the response adds `max_speed_ms` for color-scale
normalization; grids are decimated to half of `MAX_GRID_POINTS` per
component.

```json
{
  "available": true,
  "dataset_id": "local_synthetic_ocean",
  "u_variable": "u", "v_variable": "v", "units": "m s-1",
  "time": "2024-01-01T00:00:00", "depth_meters": 0.0,
  "latitude": ["..."], "longitude": ["..."],
  "u": [["..."]], "v": [["..."]],
  "max_speed_ms": 0.42
}
```

### `GET /model/{dataset_id}/services` → `ServiceEndpoints`
Direct scientific-service URLs (`opendap`, `erddap_griddap`,
`erddap_tabledap`, `wms`, `wcs`, `thredds_catalog`, `http_download`; absent
capabilities are `null`). The backend does **not** proxy WMS/WCS/OPeNDAP
payloads — the frontend should hand these URLs directly to map/tile layers.

Live-verified example (real INCOIS product, dev mode without THREDDS —
upstream URLs come from the ISO 19115 record):

```json
{
  "dataset_id": "incois_argo_mnt_VAM",
  "opendap": null,
  "erddap_griddap": "https://erddap.incois.gov.in/erddap/griddap/incois_argo_mnt_VAM",
  "erddap_tabledap": null,
  "wms": "https://erddap.incois.gov.in/erddap/wms/incois_argo_mnt_VAM/request?SERVICE=WMS&REQUEST=GetCapabilities",
  "wcs": null,
  "thredds_catalog": null,
  "http_download": null
}
```

Inside docker compose (`THREDDS_BASE_URL` set) the same dataset additionally
exposes local `opendap`, `wms`, `thredds_catalog` and `http_download` URLs
served from the mounted file. Advertised THREDDS URLs use the host-mapped
port (`http://localhost:8080/thredds/...`) so they are reachable directly
from a browser. **WCS is advertised only when an explicit WCS-capable service
is configured** (`WCS_BASE_URL`) — it is never silently inherited from other
service bases.

## 5. Argo observations (`/argo`)

Requires an Argo data source. `ARGO_PROVIDER` selects it: `local` (NetCDF
profiles cached under `data/argo_cache/` — served with zero network access),
`remote` (argopy → ERDDAP/GDAC), or `auto` (default: local when cache files
exist, else remote). All upstream failures are controlled 503s.

### `GET /argo/floats` → `ArgoFloatSummary[]`
Params: `lon_min=50`, `lon_max=100`, `lat_min=-10`, `lat_max=30`
(Indian Ocean defaults), optional `start`/`end` dates, `max_floats=50`
(1–500). The region box always carries the standard 0–2000 m depth range.
When `start`/`end` are omitted the route applies a rolling **90-day window**
ending today — this keeps upstream bulk region queries (ERDDAP/GDAC) inside
request timeouts; explicit dates bypass it. Results are cached for
`CACHE_TTL_SECONDS` (1 h default).

```json
[{"platform_wmo": 2902123, "cycles": 6, "last_location": [12.0, 70.0], "last_time": "2024-03-21T00:00:00"}]
```

### `GET /argo/search`
Alias of `/floats` (same params minus paging/time filters).

### `GET /argo/{float_id}` → `ArgoFloatDetail`
`platform_wmo`, `profiles_available`, `time_range`, `spatial_bounds`,
`recent_profiles[]` (`cycle_number`, `time`, position, `points[]` with
`pressure_dbar`, `depth_meters`, `temperature_c`, `salinity_psu`).
Param: `max_profiles=5` (1–20).

### `GET /argo/{float_id}/profile` → `ArgoProfile`
Single profile; latest cycle by default, specific via `?cycle=N`.
Unknown cycle → 404.

## 6. Gliders (`/glider` + aliases)

Glider ingestion is pluggable (`GLIDER_DATA_URL` + a registered
`GliderClient`). Until a provider is configured:

- `GET /glider/status` → `{"configured": false, "provider": "null"}`
- `GET /glider/missions`, `GET /glider/missions/{mission_id}/profiles`
  → 200 with explicit not-configured body:
  `{"detail": "No glider data source is configured. Set GLIDER_DATA_URL ...", "status": "not_configured"}`
- Frontend-friendly aliases: `GET /gliders` (collection) and
  `GET /gliders/{glider_id}` behave identically (hidden from OpenAPI).

Frontend guidance: check `/glider/status` once; if `configured:false`, render
the glider section as "coming soon" instead of an error state.

## 7. Feature → endpoint map

| UI feature | Endpoints |
| --- | --- |
| Dataset picker | `/model/datasets` (once, plus background refresh) |
| 3-D volume / depth slider | `/model/{id}/slice?variable&time_index&depth` per frame |
| Time animation | iterate `time_index` over `/model/{id}/times` count |
| Color scale normalization | `downsampling` + sample min/max from slice values |
| Current arrows / particles | `/model/{id}/currents` |
| Vertical profile chart | `/model/{id}/profile` |
| Hover inspector | `/model/{id}/point?variables=a,b,c` |
| Argo float map + drill-down | `/argo/floats` → `/argo/{wmo}` → `/argo/{wmo}/profile` |
| Heavy raster overlays (WMS/WCS) | URL from `/model/{id}/services`, loaded client-side |
| System status widget | `/health`, `/health/ready` |

## 8. Performance limits (server-enforced)

| Limit | Default | Effect |
| --- | --- | --- |
| `MAX_GRID_POINTS` | 100 000 | slice grids auto-downsampled, strides reported |
| `MAX_PROFILE_POINTS` | 500 | profiles truncated |
| Open dataset cache | 4 xarray handles | LRU eviction; transparent |
| Upstream retries | exponential backoff + circuit breaker | 503 surfaces quickly when a provider is down |
