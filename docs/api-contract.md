# EchoShield Backend API Contract

Contract for frontend integration with the EchoShield FastAPI backend.
Every example below was captured from a **live verified** server run
(`uvicorn app.main:app`, dataset `local_synthetic_ocean`).

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
| Depths | meters, positive down |
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

### `GET /health`
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
from ISO 19115 metadata), THREDDS catalog entries when configured.

```json
[
  {
    "id": "local_synthetic_ocean",
    "title": "Synthetic Ocean",
    "summary": "Local sample NetCDF file (synthetic_ocean.nc).",
    "source_type": "local",
    "time_range": {"start": "2024-01-01T00:00:00", "end": "2024-01-08T00:00:00", "count": 8},
    "spatial_bounds": {"west": 60.0, "east": 70.0, "south": 5.0, "north": 10.0},
    "services": null
  }
]
```

### `GET /model/{dataset_id}/metadata` → `DatasetMetadata`
Dimensions dict, variable list (`name`, `long_name`, `standard_name`, `units`,
`dimensions`, `shape`), coordinates, global attributes, time/depth ranges,
spatial bounds, service endpoints when available.

### `GET /model/{dataset_id}/variables` → `VariableMetadata[]`

### `GET /model/{dataset_id}/times` → `{start, end, count}`

### `GET /model/{dataset_id}/depths` → `float[]`
Depth levels in meters (positive down), e.g. `[0.0, 10.0, 20.0, 50.0, 100.0]`.

### `GET /model/{dataset_id}/slice` → `ModelSlice`
One horizontal 2-D field — the primary feed for 2-D rendering / volume slicing.

| Param | Type | Notes |
| --- | --- | --- |
| `variable` | str, required | e.g. `temperature`, `salinity` |
| `time_index` | int ≥ 0 | defaults to 0 |
| `depth` | float | nearest depth level (meters); omit for surface |
| `west`,`east`,`south`,`north` | float | optional bbox; **all four required together** |

```json
{
  "dataset_id": "local_synthetic_ocean",
  "variable": "temperature",
  "units": "degC",
  "time_index": 0,
  "time": "2024-01-01T00:00:00",
  "depth_meters": 0.0,
  "latitude": [5.0, 6.0],
  "longitude": [60.0, 61.0],
  "values": [[27.1, 27.2], [26.9, null]],
  "downsampling": {}
}
```

**Grid orientation:** `values[i][j]` is row `latitude[i]`, column
`longitude[j]`. Grids larger than `MAX_GRID_POINTS` (100 000) are
automatically downsampled; the applied strides are reported in
`downsampling` (e.g. `{"latitude_step": 2, "longitude_step": 2}`).

### `GET /model/{dataset_id}/profile` → `OceanProfile`
Vertical profile at the nearest grid point. Params: `variable` (required),
`latitude`, `longitude` (required), `time_index`. Returns parallel arrays
`depths_meters[]` and `values[]` (null where missing). Capped at
`MAX_PROFILE_POINTS` (500).

### `GET /model/{dataset_id}/point` → `PointSample`
Multi-variable sample for hover popups / inspector panels. Params:
`variables` (comma-separated, 1–8 names), `latitude`, `longitude`,
optional `time_index`, `depth`.

```json
{
  "dataset_id": "local_synthetic_ocean",
  "latitude": 8.0, "longitude": 65.0,
  "time": "2024-01-02T00:00:00", "depth_meters": 20.0,
  "nearest_grid": {"latitude": 8.0, "longitude": 65.0},
  "values": {"temperature": 22.5, "salinity": 35.1},
  "units": {"temperature": "degC", "salinity": "1e-3"}
}
```

### `GET /model/{dataset_id}/currents` → `CurrentVectorField`
Horizontal u/v vector field for flow overlays. Params: `time_index`,
`depth`, optional bbox. Variable auto-detection accepts common naming
families (`u/v`, `uo/vo`, `usurf/vsurf`, `eastward_velocity/…`,
`u_current/…`). Response adds `max_speed_ms` for color-scale normalization;
grids are decimated to half of `MAX_GRID_POINTS` per component.

```json
{
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
capabilities are omitted/null). The backend does **not** proxy WMS/WCS/OPeNDAP
payloads — the frontend should hand these URLs directly to map/tile layers.
503 for local files that expose no external service.

## 5. Argo observations (`/argo`)

Requires a reachable Argo upstream (ERDDAP/GDAC via argopy). All failures are
controlled 503s.

### `GET /argo/floats` → `ArgoFloatSummary[]`
Params: `lon_min=50`, `lon_max=100`, `lat_min=-10`, `lat_max=30`
(Indian Ocean defaults), optional `start`/`end` dates, `max_floats=50`
(1–500). The region box always carries the standard 0–2000 m depth range.

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
