# EchoShield — SIH 26067 Current Implementation Status

**This file is the authoritative status snapshot for the current `main` branch.**

## Implemented

- Browser-native React + React Three Fiber / Three.js 3D ocean viewer.
- 3D model slice rendering with bounded depth selection (maximum eight render levels by default).
- Batched model-slice requests using `/slice/batch` instead of one HTTP request per depth.
- TanStack Query caching and request cancellation through `AbortSignal`.
- Adaptive WebGL DPR based on device memory/CPU class.
- Reduced post-processing: Bloom + Vignette only; expensive DOF/chromatic/noise passes removed.
- Reduced water-shader resolution and animation update rate.
- Current-flow particle budget reduced to 1,600 and simulation updates capped at 30 Hz.
- Argo marker budget reduced to 80 and individual point lights removed.
- Backend GZip compression for large scientific JSON responses.
- Bounded server-side scientific slice-result cache (128 entries, 30-minute TTL).
- INCOIS Value Added Products geostrophic current source (`GEO_U`, `GEO_V`).
- INCOIS IRS P4 OCM chlorophyll source (`CHLOROPHYLL`).
- Model-versus-Argo comparison endpoint with nearest model timestep and temperature/salinity bias, MAE and RMSE.
- Model/Argo validation panel in the frontend.
- Optional Marching Cubes isosurface layer, deliberately disabled by default because it is more expensive than slice rendering.
- CF-aware variable mapping including INCOIS `GEO_U` / `GEO_V` aliases.
- Synthetic NetCDF data remains available for deterministic local testing.
- Argo and Glider provider abstractions remain explicit; no observational data is fabricated when an upstream is unavailable.

## Data sources

### Model

The preferred local demonstration dataset remains the INCOIS Argo/McCreary VAM model product. The backend also retains ISO-19115/ERDDAP/THREDDS discovery.

### Currents

INCOIS Value Added Products exposes `GEO_U` and `GEO_V` on a 60 × 90 grid. EchoShield registers this as a remote ERDDAP/OPeNDAP source.

### Chlorophyll

INCOIS IRS P4 OCM-Chlorophyll is registered as a remote ERDDAP/OPeNDAP source. It is a high-resolution 2556 × 4315 grid, so EchoShield's existing bbox and `MAX_GRID_POINTS` downsampling are important when using it.

### Gliders

INCOIS glider data is available for research through the INCOIS data-requisition process rather than a public ERDDAP dataset. EchoShield therefore keeps the provider seam and does **not** invent a public glider endpoint. A real INCOIS glider NetCDF/ERDDAP source can be connected through the existing `GLIDER_DATA_URL` integration when the data is supplied/authorized.

## Performance policy

The browser must not render the full scientific dataset at full resolution merely because the camera is looking at the whole Earth. The current render budget intentionally favors:

1. small depth stack,
2. server-side spatial subsetting,
3. server-side downsampling,
4. batched requests,
5. query caching,
6. adaptive DPR,
7. optional expensive effects.

## Scientific policy

- Missing variables are reported as unavailable; they are never synthesized.
- Observation/model comparison uses the nearest available model timestep rather than silently pretending exact temporal coincidence.
- Units and source metadata remain attached to API responses.
- Isosurface rendering is an analytical visualization, not a replacement for the underlying slice values.

## Remaining work before final SIH demo

- Add the authorized real INCOIS glider dataset.
- Add a full spatial viewport/LOD controller driven by camera distance and geographic selection.
- Add automated frontend performance benchmarks (FPS, draw calls, GPU memory, payload size).
- Move very large texture-color conversion to a shared Web Worker if profiling shows it is still a main-thread bottleneck.
- Add dedicated CTD/BGC/ADCP/mooring/HF-radar adapters.
