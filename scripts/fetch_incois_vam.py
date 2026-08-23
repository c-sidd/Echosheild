"""Download the real INCOIS ARGO Monthly VAM NetCDF for local/offline deploys.

Fetches the flagship ``incois_argo_mnt_VAM`` product (271 monthly steps,
24 depth levels, 60x90 grid, ~280 MB) from the INCOIS ERDDAP griddap
upstream and writes it to the exact filename registered in
``data/datasets/datasets.json`` so the backend picks it up with no
configuration changes.

The file is deliberately NOT stored in git (GitHub hard-limits files at
100 MB); run this script once after cloning / before deploying:

    uv run python scripts/fetch_incois_vam.py            # default location
    uv run python scripts/fetch_incois_vam.py --url ...  # mirror/override

If INCOIS ERDDAP is unreachable from your deployment network, the backend
still serves this dataset remotely through the same griddap upstream
(``source_type: erddap_remote`` behaviour) — the local file is only needed
for fully offline demos.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST = REPO_ROOT / "data" / "datasets" / "datasets.json"

DEFAULT_BASE = (
    "https://erddap.incois.gov.in/erddap/griddap/incois_argo_mnt_VAM.nc"
)
# Exact filename expected by data/datasets/datasets.json -> local_path.
TARGET_NAME = "incois_argo_mnt_VAM_f99c_fe7d_a5a3_U1787403117643.nc"

CHUNK = 1024 * 1024  # 1 MiB


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch the real incois_argo_mnt_VAM NetCDF (~280 MB)."
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=REPO_ROOT / "data" / "sample_netcdf" / TARGET_NAME,
        help="destination path (default: repo data/sample_netcdf)",
    )
    parser.add_argument(
        "--url",
        default=None,
        help=(
            "override the full ERDDAP .nc URL (e.g. a mirror). "
            f"default: {DEFAULT_BASE}?TEMP,SAL"
        ),
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="re-download even if the destination already exists",
    )
    return parser.parse_args(argv)


def manifest_local_path() -> str | None:
    """Read the registered local_path straight from the dataset manifest."""
    import json

    try:
        payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    except OSError:
        return None
    for ds in payload.get("datasets", []):
        if ds.get("id") == "incois_argo_mnt_VAM":
            return ds.get("local_path")
    return None


def download(url: str, destination: Path) -> None:
    request = urllib.request.Request(url, headers={"Accept": "application/x-netcdf"})
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        dir=destination.parent, suffix=".part", delete=False
    ) as scratch:
        temp_path = Path(scratch.name)
    try:
        with urllib.request.urlopen(request, timeout=120) as response, temp_path.open(
            "wb"
        ) as handle:
            total = int(response.headers.get("Content-Length") or 0)
            done = 0
            while True:
                block = response.read(CHUNK)
                if not block:
                    break
                handle.write(block)
                done += len(block)
                if total:
                    pct = min(100.0, done * 100.0 / total)
                    sys.stdout.write(f"\r{done / (1 << 20):7.1f} / {total / (1 << 20):.1f} MB ({pct:5.1f}%)")
                    sys.stdout.flush()
        print()
        if temp_path.stat().st_size < 1024:
            raise RuntimeError(
                "downloaded payload is suspiciously small — the upstream likely "
                "returned an error page instead of NetCDF"
            )
        shutil.move(str(temp_path), str(destination))
    finally:
        temp_path.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    registered = manifest_local_path()
    if registered and not args.out.name == Path(registered).name:
        print(
            f"note: manifest expects {registered!r}; writing to {args.out} anyway.\n"
            "      Update datasets.json via scripts/generate_dataset_manifest.py "
            "if you keep a different name."
        )

    if args.out.exists() and not args.force:
        size_mb = args.out.stat().st_size / (1 << 20)
        print(f"already present: {args.out} ({size_mb:.1f} MB) — use --force to re-download")
        return 0

    url = args.url or f"{DEFAULT_BASE}?TEMP,SAL"
    print(f"downloading incois_argo_mnt_VAM from:\n  {url}")
    try:
        download(url, args.out)
    except urllib.error.URLError as exc:
        print(f"\ndownload failed: {exc}", file=sys.stderr)
        print(
            "\nCheck network access to erddap.incois.gov.in. If your deploy "
            "environment cannot reach it, the backend still serves this "
            "dataset remotely via ERDDAP; the local file is only required "
            "for offline demos.",
            file=sys.stderr,
        )
        return 1
    except Exception as exc:  # noqa: BLE001 - report any failure clearly
        print(f"\ndownload failed: {exc}", file=sys.stderr)
        return 1

    size_mb = args.out.stat().st_size / (1 << 20)
    print(f"wrote {args.out} ({size_mb:.1f} MB)")
    print("restart the backend (or re-run scripts/generate_dataset_manifest.py) "
          "if upstream dimensions changed.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
