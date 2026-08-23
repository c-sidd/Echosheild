"""MOSDAC (ISRO satellite data) ingestion stub — NOT yet implemented.

Planned behaviour (see SIH PS-26067 multi-source requirement):

1. Query the MOSDAC portal for the configured product window.
2. Download GRIB/HDF5 swath or L3 gridded files into ``data/mosdac_cache``.
3. Convert to CF-compliant NetCDF under ``data/sample_netcdf`` so the
   standard :class:`~app.services.dataset_registry.DatasetRegistry` picks
   them up automatically.

Run ``uv run python scripts/sync_mosdac.py`` once implemented; until then the
script fails fast instead of pretending to work.
"""

from __future__ import annotations

import argparse
import sys


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync MOSDAC satellite products (stub).")
    parser.add_argument("--product", default="INSAT-3D SR", help="product identifier")
    parser.add_argument("--start", default=None, help="ISO start date")
    parser.add_argument("--end", default=None, help="ISO end date")
    parser.add_argument("--out", default="data/mosdac_cache", help="download directory")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    print(f"[stub] MOSDAC sync requested: product={args.product} out={args.out}")
    print("[stub] MOSDAC ingestion is not implemented yet.")
    print(
        "[stub] TODO: implement portal query, download, and CF-NetCDF conversion"
        " (see module docstring)."
    )
    return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
