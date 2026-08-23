"""Generate ``data/datasets/datasets.json`` from actually-present artifacts.

Offline and idempotent: discovers local NetCDF files + ISO 19115 records
exactly like the backend does at startup, then writes one manifest record
per dataset. Run again whenever files are added to ``data/``.

Usage::

    uv run python ../scripts/generate_dataset_manifest.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import Settings
from app.ingestion import netcdf_parser as ncp
from app.services.dataset_registry import (
    DatasetRegistry,
    RegisteredDataset,
)

MANIFEST_PATH = PROJECT_ROOT / "data" / "datasets" / "datasets.json"


def _relative(path: Path | None) -> str | None:
    if path is None:
        return None
    try:
        return path.resolve().relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return path.name


def _enrich(entry: RegisteredDataset) -> dict[str, object]:
    info = entry.info
    record: dict[str, object] = {
        "id": info.id,
        "title": info.title,
        "provider": info.provider,
        "description": info.summary,
        "source_type": info.source_type,
        "format": "NetCDF" if entry.local_path is not None else "ISO-19115 metadata",
        "local_path": _relative(entry.local_path),
        "metadata_path": (
            _relative(PROJECT_ROOT / "data" / info.metadata_path)
            if info.metadata_path
            else None
        ),
        "enabled": info.enabled,
        "license": info.license,
        "services": info.services.model_dump(exclude_none=True) if info.services else None,
    }
    if entry.local_path is not None:
        # Only local files are probed; remote access would require network.
        try:
            ds = ncp.open_dataset(
                entry.local_path if entry.local_path is not None else entry.remote_url,
                engine=entry.engine or None,
                decode_times=True,
            )
        except Exception as exc:  # noqa: BLE001 - manifest stays honest
            record["accessible"] = False
            record["access_error"] = str(exc)[:300]
            return record
        try:
            cmap = ncp.CoordinateMap(ds)
            variables = ncp.list_variables(ds)
            canonical = {
                v.canonical_name: v.name
                for v in variables
                if v.canonical_name is not None
            }
            record.update(
                {
                    "accessible": True,
                    "dimensions": ncp.get_dimensions(ds),
                    "variables": {
                        "canonical_mapping": canonical,
                        "source_names": [v.name for v in variables],
                    },
                    "coordinate_mapping": cmap.resolved.mapping,
                    "vertical_kind": cmap.vertical_kind,
                    "vertical_units": cmap.vertical_units,
                    "time_range": (
                        ncp.get_time_range(ds).model_dump() if ncp.get_time_range(ds) else None
                    ),
                    "depth_range": (
                        ncp.get_depth_range(ds).model_dump() if ncp.get_depth_range(ds) else None
                    ),
                    "spatial_bounds": (
                        ncp.get_spatial_bounds(ds).model_dump()
                        if ncp.get_spatial_bounds(ds)
                        else None
                    ),
                }
            )
        finally:
            ncp.close_dataset(ds)
    else:
        record["accessible"] = entry.accessible
        record["remote_only"] = True
        record["note"] = (
            "Registered from ISO 19115 metadata; the gridded NetCDF file is not"
            " stored locally and is accessed remotely when the upstream is"
            " reachable."
        )
        if info.time_range:
            record["time_range"] = info.time_range.model_dump()
        if info.spatial_bounds:
            record["spatial_bounds"] = info.spatial_bounds.model_dump()
    return record


def main() -> int:
    settings = Settings()
    registry = DatasetRegistry(settings)
    registry.discover()

    entries = [_enrich(entry) for entry in registry.entries()]
    manifest = {
        "generated_by": "scripts/generate_dataset_manifest.py",
        "dataset_count": len(entries),
        "datasets": sorted(entries, key=lambda item: str(item["id"])),
    }
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {MANIFEST_PATH} ({len(entries)} datasets)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
