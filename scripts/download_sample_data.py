"""Generate a small SYNTHETIC NetCDF sample dataset for local development.

Usage (from repository root):
    uv run --project backend python scripts/download_sample_data.py

The output file is clearly labelled as synthetic test/sample data — it is
NOT real INCOIS data and must never be presented as such.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.testing_utils import SYNTHETIC_NOTE, write_synthetic_netcdf  # noqa: E402


def main() -> None:
    target = REPO_ROOT / "data" / "sample_netcdf" / "synthetic_ocean.nc"
    path = write_synthetic_netcdf(target)
    size_kb = path.stat().st_size / 1024
    print(f"wrote synthetic sample: {path} ({size_kb:.1f} KB)")
    print(f"note: {SYNTHETIC_NOTE}")


if __name__ == "__main__":
    main()
