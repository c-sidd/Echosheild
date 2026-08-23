# EchoShield Codebase Analysis — Superseded Snapshot

> **Important:** this file is retained for historical context. It is **not** the current implementation specification.
>
> The current authoritative status is [`docs/sih-26067-current-status.md`](docs/sih-26067-current-status.md).

## Current architecture

```text
INCOIS NetCDF / ERDDAP / THREDDS / Argo / authorized Glider source
                         │
                         ▼
              FastAPI + xarray backend
                         │
          ┌──────────────┼──────────────┐
          ▼              ▼              ▼
       slices         profiles        currents
          │              │              │
          └──────────────┼──────────────┘
                         ▼
                 React Query cache
                         │
              camera-distance LOD
                         │
                 React Three Fiber
                         │
        ┌────────────────┼─────────────────┐
        ▼                ▼                 ▼
    3D slices        currents          instruments
        │
        ├── optional Marching Cubes isosurface
        └── Web Worker texture conversion
```

## Important current behavior

- The browser requests at most eight depth levels for the 3D stack by default.
- Slice requests are sent through the backend batch endpoint rather than one request per depth.
- A camera-distance controller supplies a geographic bbox to the backend so zooming can reduce the requested area.
- Surface-only datasets such as chlorophyll are rendered as a surface layer rather than being forced into fake depth levels.
- Large JSON responses are gzip-compressed.
- Repeated scientific slices have a bounded server-side TTL cache.
- Descending/negative depth axes are normalized before slice indexing so the selected physical depth is not silently swapped.
- Current vectors recognize INCOIS `GEO_U` / `GEO_V`.
- Model-vs-Argo validation is available through the Argo comparison endpoint and frontend panel.
- Isosurfaces are opt-in because Marching Cubes is substantially more expensive than slice rendering.

## Data-source policy

EchoShield does not fabricate missing ocean observations. If an upstream is unavailable, the UI reports the capability as unavailable. Real authorized glider data can be supplied through `GLIDER_DATA_URL`.

For the full SIH 26067 requirement matrix, use the current status document rather than this historical file.
