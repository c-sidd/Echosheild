# 🌊 EchoShield — 3D Ocean Data Visualization Platform

> **Smart India Hackathon 2026 · Problem Statement 26067**
> Organization: **INCOIS** (Indian National Centre for Ocean Information Services) · Ministry of Earth Sciences (MoES)
> Category: Software · Theme: Smart Automation

A web-based interactive 3D visualization platform that turns real ocean-model outputs and in-situ observations into explorable, judge-friendly visuals — volumetric temperature/salinity fields over the Indian Ocean, Argo float overlays, depth/time animation and honest handling of what the data does *not* contain.

---

## 📋 Table of Contents

- [Problem Statement](#-problem-statement)
- [Our Solution](#-our-solution)
- [Key Features](#-key-features)
- [Tech Stack](#-tech-stack)
- [Architecture](#-architecture)
- [Real Data](#-real-data)
- [API Reference](#-api-reference)
- [Getting Started](#-getting-started)
- [Project Structure](#-project-structure)
- [Testing & Quality](#-testing--quality)
- [Configuration](#-configuration)
- [Roadmap](#-roadmap)
- [Team](#-team)
- [License & Acknowledgements](#-license--acknowledgements)

---

## 🎯 Problem Statement

**PS-26067** (INCOIS / MoES): Build a scalable, web-based interactive 3D visualization system that lets scientists, students and decision-makers explore ocean model outputs and in-situ observations — depth profiles, time animation, variable switching — using open standards (NetCDF, OPeNDAP, WMS/WCS, CF conventions).

**The hard parts:**

| Challenge | How EchoShield addresses it |
|---|---|
| Multi-GB scientific formats in a browser | Lazy xarray reads → downsampled JSON grids (NaN-safe, ≤100k points), never full-file dumps |
| Heterogeneous sources (local NetCDF, ERDDAP, OPeNDAP, THREDDS, Argo) | One registry with deterministic dataset IDs, ISO 19115 metadata sidecars, canonical CF variable mapping |
| Missing data must never be fabricated | Explicit contracts: currents → `{"available": false}`, gliders → `{"configured": false}`, NaN → `null`, upstream failures → clean 503 |
| Judges need it to *just run* | Offline-first demo mode: local Argo cache + launchers that need zero network access |

## 💡 Our Solution

**EchoShield** is a three-tier platform:

1. **FastAPI application layer** — validated REST API (`/api/v1`) serving gridded model slices, profiles, point samples and Argo observations from the real INCOIS ARGO Monthly VAM product.
2. **Scientific data layer** — xarray/netCDF4 lazy I/O locally and remotely (OPeNDAP/pydap), argopy for Argo ingestion, THREDDS client for OPeNDAP/WMS delegation (scientific serving is *never* reimplemented).
3. **React 19 + Three.js presentation layer** — a GPU-rendered volumetric "ocean box" you can fly through, scrub through time, peel by depth and inspect pixel-by-pixel, backed by deck.gl 2-D maps.

### Feature highlights

- 🧊 **Volumetric rendering**: 24 stacked depth planes as GPU `DataTexture`s with colormapped LUTs, active-depth glow edge and vertical exaggeration
- ⏱️ **Time animation**: rAF-driven playback across 271 monthly timesteps (2004→2026) with prefetch-ahead so scrubbing never stalls
- 🎚️ **Full control set**: depth slider, canonical variable selector, editable colorbar ranges/colormaps, layer toggles
- 🗺️ **2-D map sync**: deck.gl heatmap + ArcGIS basemap + Argo float scatter, pickable hover inspection
- 📈 **Profile charts**: Recharts temperature/salinity columns at any grid point (inverted depth axis)
- 🔬 **Instrument overlay**: pulsing Argo float markers with drill-down profiles; honest glider placeholder
- 🛡️ **Error contracts the UI respects**: 404 permanent · 422 silent · 503 → retry banner with readiness recovery

<!-- 📸 TODO before final submission: add screenshots/GIF here -->
<!-- ▶️ TODO: add 2–3 min demo video link -->

---

## 🛠️ Tech Stack

### Frontend (`frontend/`)

| Layer | Technology |
|---|---|
| Framework | React 19 + Vite 6 (ESM) |
| 3D Rendering | Three.js ^0.182 via @react-three/fiber ^9, drei, postprocessing |
| Mapping | deck.gl ^9 (TileLayer, HeatmapLayer, BitmapLayer, ScatterplotLayer), react-map-gl |
| State | Zustand ^5 (client state) + TanStack Query ^5 (server state, caching, prefetch) |
| Styling | Tailwind CSS v4 (CSS-first `@theme` config) |
| Charts | Recharts ^2 |
| Animation | GSAP ^3 (camera fly-to, number rolls), Framer Motion ^12 |
| Quality | oxlint, production build w/ vendor chunk splitting |

### Backend (`backend/`)

| Layer | Technology |
|---|---|
| API | FastAPI + Pydantic v2 (strict response models), uvicorn |
| Scientific I/O | xarray, netCDF4 / h5netcdf, dask (lazy), pydap (OPeNDAP) |
| Observations | argopy (Argo ERDDAP/GDAC), pluggable local-cache provider |
| Metadata | ISO 19115 XML parser, CF standard-name variable classification |
| Config | pydantic-settings (all infra via environment, nothing hardcoded) |
| Quality | pytest (132 tests incl. value-level checks against real data), mypy `--strict` (clean), ruff |

### Data & Infrastructure

| Concern | Choice |
|---|---|
| Source product | INCOIS ERDDAP — ARGO Monthly VAM gridded NetCDF (~280 MB, real) |
| Scientific serving | THREDDS (OPeNDAP/WMS/fileServer URLs advertised, not proxied) |
| Caching | FileCache TTL JSON (Argo searches/float details), LRU open-dataset pool |
| Packaging | uv workspace, npm; docker-compose scaffold present |

---

## 🏗️ Architecture

```
                    ┌──────────────────────────────┐
                    │   React 19 + Three.js SPA    │
                    │  (vite :5173 → proxy /api)   │
                    └──────────────┬───────────────┘
                                   │ REST /api/v1
                    ┌──────────────▼───────────────┐
                    │        FastAPI app           │
                    │  validation · contracts      │
                    ├────────┬─────────┬───────────┤
                    │ Model  │  Argo   │  Glider   │
                    │ Service│ Client  │  (stub)   │
                    └───┬────┴────┬────┴───────────┘
                        │         │
             ┌──────────▼──┐  ┌───▼──────────────┐
             │   xarray    │  │     argopy       │
             │ netCDF4/dask│  │ ERDDAP/GDAC/local│
             └──────┬──────┘  └──────────────────┘
                    │
      ┌─────────────┼──────────────────────┐
      ▼             ▼                      ▼
 local NetCDF   remote OPeNDAP /      ISO 19115
 (INCOIS VAM)   ERDDAP / THREDDS      metadata
```

Design rules enforced in code:

- **Registry-gated access** — the API can only open datasets registered at startup; no arbitrary server paths.
- **Canonical variables** — frontend speaks stable names (`temperature`, `salinity`, …); raw source names (`TEMP`, `SAL`) keep working.
- **Orientation contract** — every grid is `values[i][j] = latitude[i] × longitude[j]`; NaN becomes `null`, never `NaN`/`Infinity` in JSON.
- **Optional ≠ broken** — an unreachable Argo upstream degrades to a null client (503 responses); startup always succeeds if model data is readable.

---

## 📊 Real Data

The flagship dataset is the **actual INCOIS product**, registered automatically at startup:

| Property | Value |
|---|---|
| Product | `incois_argo_mnt_VAM` — INCOIS ARGO Monthly data, Variational Analysis Methodology |
| Provider | INCOIS (via INCOIS ERDDAP griddap) |
| Variables | `TEMP` (°C), `SAL` (PSU) → exposed canonically as `temperature`, `salinity` |
| Time axis | 271 monthly steps, 2004-01-15 → 2026-07-15 |
| Depth axis | 24 levels: 5, 10, 20 … 1800, 2000 m (native meters, positive-down) |
| Grid | 60 × 90 — 30.5–119.5 °E, 29.5 °S–29.5 °N |
| Size | ~280 MB NetCDF (lazy-opened; only requested slabs are read) |
| Currents | Genuinely absent → API returns explicit `{"available": false}` (never fabricated) |

Utility scripts:

```bash
uv run python scripts/fetch_incois_vam.py         # real ~280 MB INCOIS VAM product (one-time, before offline deploys)
uv run python scripts/download_argo.py --box 50 100 -10 30 --start 2023-01-01 \
    # ↑ cache real Argo float profiles (one <WMO>.nc each) for offline demos
```

### Data & assets shipped in-repo (deploy-ready)

Everything needed to run a fresh clone is committed — no manual downloads
required for a working demo:

| Asset | Purpose |
|---|---|
| `data/datasets/datasets.json` | Dataset registry (7 INCOIS products) loaded at backend startup |
| `data/*_iso19115.xml` | ISO 19115 metadata records backing `/model/{id}/metadata` |
| `data/sample_netcdf/synthetic_ocean.nc` | Tiny (~80 KB) labelled synthetic dataset — registered as `local_synthetic_ocean`, works out of the box |
| `frontend/public/assets/waternormals.jpg` | three.js water-normal texture for the 3D ocean surface |
| `frontend/fetch-assets.ps1` | Re-downloads the water texture if it ever goes missing |

The only file **not** in git is the ~280 MB `incois_argo_mnt_VAM` NetCDF
(GitHub hard-limits files at 100 MB). Fetch it once with
`scripts/fetch_incois_vam.py`; without it the app falls back to the
synthetic dataset and/or live ERDDAP access.

---

## 🔌 API Reference

Base URL: `/api/v1` · Interactive docs: `http://localhost:8000/docs`

### Health
| Method | Path | Description |
|---|---|---|
| GET | `/health` | Liveness + optional-dependency import status |
| GET | `/health/ready` | Readiness checks array (registry, argo, thredds…) |

### Model data
| Method | Path | Description |
|---|---|---|
| GET | `/model/datasets` | Registered datasets with **real** time counts + spatial bounds |
| GET | `/model/{id}/extent` | Single-call startup payload: time range, all depths, lat/lon footprint, variables |
| GET | `/model/{id}/metadata` | Dimensions, variables, coordinates, attributes, ranges |
| GET | `/model/{id}/variables` | Variable list with canonical mapping + units |
| GET | `/model/{id}/times` | First/last timestep + count |
| GET | `/model/{id}/times/list` | Full decoded ISO time axis (cap 2000) |
| GET | `/model/{id}/timestamps` | Explicit `[{"index": i, "iso": …}]` pairs for scrubbers/deep-links |
| GET | `/model/{id}/depths` | Vertical levels (native units; see `vertical_kind`) |
| GET | `/model/{id}/slice` | 2-D horizontal slice (`variable,time_index,depth,bbox`) with auto-downsampling |
| POST | `/model/{id}/slice/batch` | Up to 10 slices in one round-trip, read concurrently |
| GET | `/model/{id}/profile` | Vertical profile at nearest grid point |
| GET | `/model/{id}/point` | Multi-variable nearest-grid sample |
| GET | `/model/{id}/currents` | `(u,v)` field or explicit unavailability contract |
| GET | `/model/{id}/services` | Advertised OPeNDAP/WMS/ERDDAP endpoints (WCS only if real) |

### Argo observations
| Method | Path | Description |
|---|---|---|
| GET | `/argo/floats` | Float search in bbox (+optional time window); cached 1 h |
| GET | `/argo/floats/{wmo}` | Float detail: availability, ranges, recent profiles |
| GET | `/argo/floats/{wmo}/profile` | One profile (latest or by cycle) |

### Gliders (honest stub)
| Method | Path | Description |
|---|---|---|
| GET | `/glider/status` | `{"configured": false}` until a provider plugin exists |
| GET | `/glider/missions` | Mission listing (empty until configured) |

**Response guarantees:** unknown entities → `404` · bad parameters → `422` · upstream outage → `503` with actionable detail. All numbers are finite or `null`.

---

## 🚀 Getting Started

**Prerequisites:** Python ≥ 3.12 with [uv](https://docs.astral.sh/uv/), Node.js ≥ 20, Git.

### 1 · Backend

```bash
cd backend
uv sync                       # locked dependency install
./run.ps1                     # Windows  — sets demo defaults (ARGO_PROVIDER=local)
# or: ./run.sh                # Linux/macOS
# or manually:
ARGO_PROVIDER=local uv run uvicorn app.main:app --reload --port 8000
```

Open `http://localhost:8000/docs` — you should already see the real VAM product listed.

> `ARGO_PROVIDER=local` serves Argo from `data/argo_cache/*.nc` when offline.
> Use `auto` (default) to prefer local files then fall back to remote, or `remote` to force live argopy.
> Populate the cache with `scripts/download_argo.py` (needs Internet once).

### 2 · Frontend

```bash
cd frontend
npm install
npm run dev                   # http://localhost:5173  (proxies /api → :8000)
```

### 3 · Verify the loop

```bash
curl http://localhost:8000/api/v1/model/incois_argo_mnt_VAM/extent
curl -X POST http://localhost:8000/api/v1/model/incois_argo_mnt_VAM/slice/batch \
     -H "Content-Type: application/json" \
     -d '{"slices":[{"variable":"temperature","time_index":130,"depth_meters":5}]}'
```

Then open the dashboard: pick the VAM dataset, drag the depth slider, hit play on time controls.

---

## 📁 Project Structure

```
Echosheild/
├── backend/
│   ├── app/
│   │   ├── api/routes/          # health, model_data, argo, glider routers
│   │   ├── core/                # settings, logging, reliability helpers
│   │   ├── ingestion/           # netcdf_parser, iso19115, thredds/argo clients
│   │   ├── models/              # pydantic schemas (response contracts)
│   │   └── services/            # dataset_registry, model_service, cache
│   ├── tests/                   # 132 tests (incl. real-data integration)
│   ├── run.ps1 / run.sh         # one-command launchers
│   └── pyproject.toml           # deps, pytest, ruff, mypy(strict) config
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── Viewer3D/        # OceanViewer, VolumeRenderer, OceanSurface…
│   │   │   ├── Map2D/           # OceanMap (deck.gl)
│   │   │   ├── Controls/        # depth/time/colorbar/variable/layer controls
│   │   │   ├── ProfileChart/
│   │   │   ├── Layout/
│   │   │   └── UI/              # banners, inspector, status, loaders
│   │   ├── hooks/               # TanStack Query wrappers, animation loop
│   │   ├── services/            # typed fetch layer (/api/v1)
│   │   ├── store/               # zustand ocean store
│   │   └── utils/               # colormaps, depth scaling, formatters
│   └── vite.config.js           # port 5173 + /api proxy + chunk splitting
├── scripts/                     # download_argo, download_sample_data, manifest…
├── docs/                        # api-contract.md, frontend-handoff.md
└── data/                        # sample_netcdf/, argo_cache/  (gitignored)
```

---

## ✅ Testing & Quality

```bash
# Backend (from repo root)
uv run --project backend pytest backend/tests -q     # 132 passed
uv run --project backend ruff check backend/app      # lint
cd backend && uv run --project . mypy app            # strict type-check: clean

# Frontend
cd frontend && npm run lint && npm run build
```

Highlights of the test suite: value-level parity between API slices/profiles and direct xarray reads of the real INCOIS file, NaN→null contracts, error-code matrix (404/422/503), batch-vs-single parity, corrupt-file isolation, and offline-argo degradation.

---

## ⚙️ Configuration

All configuration flows through environment variables (or `backend/.env`) — see `backend/app/core/config.py`:

| Variable | Default | Purpose |
|---|---|---|
| `DATA_ROOT` | `<repo>/data` | Root for all data trees |
| `NETCDF_DATA_ROOT` | `$DATA_ROOT/sample_netcdf` | Local gridded products scanned at startup |
| `ARGO_CACHE_DIR` | `$DATA_ROOT/argo_cache` | Per-WMO Argo profile files (offline mode) |
| `GLIDER_CACHE_DIR` | `$DATA_ROOT/glider_cache` | Reserved for future glider provider |
| `ARGO_PROVIDER` | `auto` | `auto` / `local` / `remote` |
| `THREDDS_BASE_URL` | unset | Enables deterministic THREDDS service URLs |
| `CORS_ORIGINS` | `localhost:5173,3000` | Comma-separated allow-list |
| `CACHE_TTL_SECONDS` | `3600` | Argo FileCache TTL |
| `MAX_GRID_POINTS` | `100000` | Slice downsampling threshold |

---

## 🗺️ Roadmap

- [ ] Isosurface extraction (marching cubes) alongside plane stacks
- [ ] MOSDAC satellite ingestion (`scripts/sync_mosdac.py` stub ready)
- [ ] Glider provider plugin (seam + schema already in place)
- [ ] BGC (oxygen/chlorophyll) variables when upstream product available
- [ ] WebSocket push for long-running remote dataset opens
- [ ] Docker compose hardening incl. THREDDS container smoke test

---

## 👥 Team EchoShield

| Name | Email |
|---|---|
| Kartikey Singh *(Team Leader)* | kartikey.24b1531026@abes.ac.in |
| Kartik Sharma | kartik.24b15310207@abes.ac.in |
| Devansh Dhama | devansh.24b0101418@abes.ac.in |
| Shaily Malik | shaily.24b0101617@abes.ac.in |
| Shrishti Saini | shrishti.24b0101294@abes.ac.in |
| Chandrachud Siddharth | chandrachud.24b0101356@abes.ac.in |

---

## 📄 License & Acknowledgements

Released under the [MIT License](backend/pyproject.toml).

- **INCOIS / MoES** for the ARGO Monthly VAM product and problem mentorship
- The **Argo program** — data collected and made freely available by the international Argo project ([doi:10.17882/42182](https://doi.org/10.17882/42182))
- Open-source scientific Python (xarray, argopy, FastAPI) and React/Three.js communities

<p align="center">Built with 🌊 for Smart India Hackathon 2026</p>
