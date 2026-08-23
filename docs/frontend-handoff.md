# EchoShield — Frontend Handoff (Backend Frozen Contract)

Backend status: **READY FOR FRONTEND**. This document is the entry point for
the React + 3D visualization phase. Full request/response details live in
[`api-contract.md`](api-contract.md); this file summarizes what exists, what
is verified, and how to build each UI feature against it.

Everything below was verified live against the **real local INCOIS NetCDF
product** on 2026-08-22 (not synthetic fixtures).

---

## 1. Available datasets

| Dataset ID | Source | What it is | Usable now |
| --- | --- | --- | --- |
| `incois_argo_mnt_VAM` | local file (`data/sample_netcdf/incois_argo_mnt_VAM_*.nc`, ~280 MB) | **Real** INCOIS ARGO Monthly gridded product (Variational Analysis). TEMP/SAL, 271 monthly steps 2004‑01‑15 → 2026‑07‑15, 60×90 grid (30.5–119.5 °E, 29.5 °S–29.5 °N), depth 5–2000 m (24 native levels) | YES — fully value-verified |
| `local_synthetic_ocean` | local file | Small deterministic test fixture (temperature/salinity/currents) | YES |
| `incois_argo_10d_VAM`, `incois_argo_10day_McCreary`, `incois_argo_mnt_McCreary`, `incois_argo_sst_weekly` | ISO‑registered remote ERDDAP products | Metadata + service URLs only; data not downloaded locally | listing/services only (503 on data endpoints unless upstream reachable) |
| `Indian_ARGO_Floats` | ISO‑registered remote tabledap | Float profile collection via ERDDAP | same as above |

Discover at runtime: `GET /api/v1/model/datasets` — never hardcode this list.

## 2. Canonical variable layer

The frontend never needs raw names like `TEMP`. Use canonical names:

* `temperature`, `salinity`, `u_current`, `v_current`, `chlorophyll`
* Coordinates resolved automatically (`coordinate_mapping` in `/metadata`)
* Raw source names are still accepted server-side (back-compat)
* `GET /model/{id}/variables` returns `name` (source), `canonical_name`,
  `units`, `dimensions`, `shape` — build the variable picker from this.

For the real VAM dataset: `temperature → TEMP (degs)`,
`salinity → SAL (PSU)`; currents/chlorophyll do **not** exist and are never
fabricated (`/currents` returns `{"available": false, ...}`).

## 3. Vertical axis honesty

Every data response carries `vertical_kind` + `vertical_units`.

* VAM product: `"depth"`, `"METERS"`, levels `[5 … 2000]`, positive down.
* Pressure-axis datasets would report `"pressure"`/dbar with values passed
  through natively — **never convert client-side either.**

## 4. Slice orientation contract (verified)

`values[i][j]` = row `latitude[i]`, column `longitude[j]`.
Live check: bbox(60,80,10,20) returned shape (10 lat × 20 lon), element-wise
identical to a direct xarray read of the same file.

## 5. Feature recipes

| UI feature | How |
| --- | --- |
| Dataset picker | `GET /model/datasets`; filter `source_type == "local"` for offline-capable ones |
| Variable picker | `GET /model/{id}/variables`, group by `canonical_name` |
| Depth slider | `GET /model/{id}/depths` (discrete native levels; nearest is applied server-side) |
| Time animation | `GET /model/{id}/times` → `{start,end,count}`; iterate `time_index` 0…count‑1 into `/slice` |
| 2-D slice render | `GET /model/{id}/slice?variable=temperature&time_index=N&depth=D&bbox=…`; NaN → `null` already |
| 3-D volume prep | stack slices across the depth array (24 requests ≈ 24×5 ms warm for VAM); respect `downsampling` strides when present |
| Current vectors | `GET /model/{id}/currents`; if `available:false`, hide the layer (VAM has no currents) |
| Profile chart | `GET /model/{id}/profile?variable&latitude&longitude&time_index`; plot `values[]` vs `depths_meters[]` honoring `vertical_kind` |
| Hover inspector | `GET /model/{id}/point?variables=temperature,salinity&latitude&longitude&time_index&depth`; keys are canonical names |
| Argo markers | `GET /argo/floats` (defaults to Indian Ocean box) → drilldown `/argo/{wmo}` → `/argo/{wmo}/profile` |
| Glider markers | check `GET /glider/status`; `configured:false` → render "coming soon" placeholder |
| Heavy raster overlays | take URLs from `GET /model/{id}/services` (OPeNDAP/WMS/ERDDAP); backend never proxies these payloads. **Implemented** in `OceanMap.jsx`: WMS `TileLayer` with per-upstream `LAYERS` — bare variable name for THREDDS, `datasetId#variable` for ERDDAP; `TIME` must match an available timestep |
| Services panel | `GET /model/{id}/services` rendered as copyable links (`ServicesPanel.jsx`, polled via `useServices`) |

## 6. Performance envelope (measured, real 280 MB file)

| Operation | Warm latency | Payload |
| --- | --- | --- |
| metadata / times / depths | 3–6 ms | < 5 KB |
| full-grid slice (5400 pts) | ~7 ms | ~76 KB |
| bbox slice (2°×2°) | ~4 ms | < 1 KB |
| profile / point | ~4 ms | < 1 KB |

Server caps: `MAX_GRID_POINTS` (auto-downsampling with reported strides),
`MAX_PROFILE_POINTS`. Open-handle LRU (4 datasets) is transparent.

## 7. Errors & degradation

* 404 unknown dataset/variable/index · 422 bad params (incl. inverted bbox)
* 503 upstream scientific source down (retry/circuit-breaker already applied;
  show a retry banner)
* Path traversal / arbitrary paths are impossible — IDs resolve through the
  registry only
* Offline dev: run only the backend without THREDDS; `incois_argo_mnt_VAM`
  serves fully locally. Argo remote & upstream ERDDAP need network.

## 8. Known limitations (honest)

* THREDDS container runtime **verified live 2026-08-23** (healthy container;
  catalog and WMS GetMap return HTTP 200). Advertised service URLs are
  host-reachable under compose (`localhost:8080`). No WCS configured
  anywhere.
* Argo `/argo/*` needs Internet (remote argopy, ERDDAP by default);
  `/argo/floats` defaults to a rolling 90-day window when no dates are
  given. Drop NetCDF profiles into `data/argo_cache/` to switch to the
  local provider automatically (`ARGO_PROVIDER=auto`).
* Glider ingestion awaits a real data source (client seam ready).
