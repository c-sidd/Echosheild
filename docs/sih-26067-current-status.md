# EchoShield — SIH 26067 Current Implementation Status

**Authoritative status snapshot for the current `main` branch.**

## Implemented

- Browser-native React + React Three Fiber / Three.js 3D ocean viewer.
- Camera-distance geographic LOD: overview uses the full registered extent; zooming progressively narrows the requested geographic bbox.
- Bounded 3D depth rendering: maximum eight depth levels by default, with the active level retained.
- Batched model-slice requests using `/slice/batch` instead of one HTTP request per depth.
- Surface-only dataset support, so 2D chlorophyll products can render without fake depth levels.
- TanStack Query caching, request cancellation and bbox-aware query keys.
- Adaptive WebGL DPR based on device memory/CPU class.
- Reduced post-processing: Bloom + Vignette only; expensive DOF/chromatic/noise passes removed.
- Reduced water-shader resolution and animation update rate.
- Current-flow particle budget reduced to 1,600 and simulation updates capped at 30 Hz.
- Argo marker budget reduced to 80 and individual point lights removed.
- Scientific slice color conversion moved to a shared Web Worker.
- Backend GZip compression for large scientific JSON responses.
- Bounded server-side scientific slice-result cache (128 entries, 30-minute TTL).
- Physically correct vertical slice ordering for descending/negative-depth source coordinates.
- INCOIS Value Added Products geostrophic current source (`GEO_U`, `GEO_V`).
- INCOIS IRS P4 OCM chlorophyll source (`CHLOROPHYLL`).
- Model-versus-Argo comparison endpoint with nearest model timestep and temperature/salinity bias, MAE and RMSE.
- Model/Argo validation panel in the frontend.
- Optional Marching Cubes isosurface layer, disabled by default because it is more expensive than slice rendering.
- CF-aware variable mapping including INCOIS `GEO_U` / `GEO_V` aliases.
- Generic authorized NetCDF/OPeNDAP glider provider wired to `GLIDER_DATA_URL`.
- Synthetic NetCDF data remains available for deterministic local testing.
- Backend tests added for INCOIS current aliases and model-observation validation metrics.

## Data sources

### Model

The preferred local demonstration dataset remains the INCOIS Argo/McCreary VAM model product. ISO-19115, ERDDAP and THREDDS discovery remain supported.

### Currents

INCOIS Value Added Products exposes `GEO_U` and `GEO_V` on a 60 × 90 grid. EchoShield registers this as a remote ERDDAP/OPeNDAP source.

### Chlorophyll

INCOIS IRS P4 OCM-Chlorophyll is registered as a remote ERDDAP/OPeNDAP source. The public product is a high-resolution 2556 × 4315 grid, so EchoShield's bbox and `MAX_GRID_POINTS` downsampling are important when using it.

### Gliders

The code now accepts a real authorized glider NetCDF/OPeNDAP source through `GLIDER_DATA_URL`. A public INCOIS glider endpoint was not fabricated; when INCOIS supplies/authorizes the actual mission source, it can be connected without changing the renderer architecture.

## Performance policy

The browser does not render the full scientific dataset at full resolution merely because the camera is looking at the whole Earth. The current pipeline favors:

1. camera-distance geographic LOD,
2. server-side spatial subsetting,
3. server-side downsampling,
4. batched requests,
5. client + server caching,
6. adaptive DPR,
7. worker-based texture conversion,
8. optional expensive effects.

## Scientific policy

- Missing variables are reported as unavailable; they are never synthesized.
- Observation/model comparison uses the nearest available model timestep rather than silently pretending exact temporal coincidence.
- Units and source metadata remain attached to API responses.
- Isosurface rendering uses only real depth-resolved data and is disabled for surface-only products.
- Negative/descending depth axes are normalized without changing the physical selected level.

## Remaining work before final SIH demo

- Connect the actual authorized INCOIS glider mission dataset through `GLIDER_DATA_URL`.
- Add dedicated CTD/BGC/ADCP/mooring/HF-radar adapters.
- Add automated browser performance benchmarks (FPS, draw calls, GPU memory, payload size).
- Profile the worker path on low-end hardware and tune the render budget further if needed.
