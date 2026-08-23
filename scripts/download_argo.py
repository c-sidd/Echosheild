"""Download real Argo profiles into the local cache for offline serving.

Fetches Argo float profiles for a geographic box / time window via ``argopy``
and writes one NetCDF file per float (``<WMO>.nc``) into ``data/argo_cache``.
The layout matches what ``app.ingestion.argo_local.LocalArgoClient`` expects
(``N_PROF`` profiles with PLATFORM_NUMBER / CYCLE_NUMBER / JULD-TIME /
LATITUDE / LONGITUDE / PRES / TEMP / PSAL), so after running this script the
backend serves /argo endpoints fully offline (ARGO_PROVIDER=local or auto).

Examples::

    uv run python scripts/download_argo.py --box 50 100 -10 30 \
        --start 2023-01-01 --end 2024-01-01

    uv run python scripts/download_argo.py --source gdac --max-floats 20

Requires Internet access to an Argo upstream (ERDDAP/GDAC).
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd

if TYPE_CHECKING:  # pragma: no cover
    import xarray as xr

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = REPO_ROOT / "data" / "argo_cache"

_LOG = logging.getLogger("echoshield.download_argo")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Cache real Argo profiles locally (one NetCDF per float)."
    )
    parser.add_argument(
        "--source", choices=("erddap", "gdac"), default="erddap", help="argopy upstream"
    )
    parser.add_argument("--dataset", default="phy", help="argopy dataset id (phy, bgc, ...)")
    parser.add_argument(
        "--box",
        nargs=4,
        type=float,
        metavar=("LON_MIN", "LON_MAX", "LAT_MIN", "LAT_MAX"),
        default=[50.0, 100.0, -10.0, 30.0],
        help="geographic box (default: Indian Ocean)",
    )
    parser.add_argument("--start", default=None, help="ISO date, e.g. 2023-01-01")
    parser.add_argument("--end", default=None, help="ISO date, defaults to now")
    parser.add_argument(
        "--max-floats", type=int, default=None, help="cap the number of floats written"
    )
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="output directory")
    parser.add_argument(
        "--force", action="store_true", help="re-download floats already present in --out"
    )
    return parser.parse_args(argv)


def _numeric_or_drop(da: Any) -> Any:
    """Coerce ``da`` to a netcdf-friendly dtype, or return ``None`` to drop it."""
    values = np.asarray(da.values)
    if values.dtype.kind in "fiuM":
        return da
    flat = pd.to_numeric(
        pd.Series(values.ravel()).map(_decode_bytes), errors="coerce"
    ).to_numpy()
    if np.isfinite(flat).any():
        return da.copy(data=flat.reshape(values.shape).astype("float64"))
    return None


def _decode_bytes(value: object) -> object:
    if isinstance(value, bytes):
        return value.decode(errors="ignore").strip()
    if isinstance(value, np.ndarray) and value.dtype.kind in "US":
        return str(value)
    return value


def clean_for_netcdf(ds: xr.Dataset) -> xr.Dataset:
    """Keep only variables that round-trip through NetCDF cleanly.

    Numeric and datetime variables survive; string QC flags are dropped
    except PLATFORM_NUMBER-style identifiers, which become numeric WMO ids so
    LocalArgoClient can read them.
    """
    keep: dict[str, Any] = {}
    for name in ds.variables:
        coerced = _numeric_or_drop(ds[name])
        if coerced is not None:
            keep[str(name)] = coerced
    cleaned = ds.drop_vars([str(n) for n in ds.variables if str(n) not in keep])
    for name, da in keep.items():
        if name in cleaned.variables:
            cleaned[name] = da
    return cleaned


def fetch_region(args: argparse.Namespace) -> xr.Dataset:
    import argopy

    box: list[Any] = [*args.box, 0, 2000]
    start = args.start or "2000-01-01"
    end = args.end or pd.Timestamp.now("UTC").tz_localize(None).strftime("%Y-%m-%d")
    box.extend([start, end])
    _LOG.info("fetching region=%s source=%s dataset=%s", box, args.source, args.dataset)
    fetcher = argopy.DataFetcher(src=args.source, ds=args.dataset, mode="standard").region(box)
    frame = fetcher.to_xarray()
    if frame is None or int(frame.sizes.get("N_PROF", 0)) == 0:
        raise RuntimeError("argopy returned no profiles for the requested region/window")
    return frame


def float_ids_of(ds: xr.Dataset) -> list[int]:
    name = next(
        (str(v) for v in ds.variables if str(v).upper() in {"PLATFORM_NUMBER", "WMO"}),
        None,
    )
    if name is None:
        raise RuntimeError("dataset lacks PLATFORM_NUMBER; cannot split per float")
    raw = pd.Series(np.asarray(ds[name].values).ravel()).map(_decode_bytes)
    ids = pd.to_numeric(raw, errors="coerce").dropna().astype("int64")
    return sorted({int(w) for w in ids if int(w) > 0})


def save_float(ds: xr.Dataset, wmo: int, out_dir: Path) -> Path:
    destination = out_dir / f"{wmo}.nc"
    name = next(
        (str(v) for v in ds.variables if str(v).upper() in {"PLATFORM_NUMBER", "WMO"}),
        None,
    )
    subset = ds
    if name is not None:
        platform = pd.to_numeric(
            pd.Series(np.asarray(ds[name].values).ravel()).map(_decode_bytes),
            errors="coerce",
        ).to_numpy()
        indices = np.flatnonzero(platform == wmo)
        if indices.size:
            dim = ds[name].dims[0] if ds[name].dims else "N_PROF"
            subset = ds.isel({dim: indices})
    subset = clean_for_netcdf(subset)
    if name is not None and name in subset:
        subset[name] = np.full(subset[name].shape, float(wmo), dtype="float64")
    subset.attrs.update(
        {
            "title": f"Argo float {wmo} profiles (cached by EchoShield)",
            "source": "argopy download (scripts/download_argo.py)",
            "date_created": pd.Timestamp.now("UTC").isoformat(),
        }
    )
    encoding = {
        str(v): {"zlib": True, "complevel": 4}
        for v in subset.data_vars
        if np.asarray(subset[v].values).dtype.kind in "fiu"
    }
    subset.to_netcdf(destination, engine="netcdf4", encoding=encoding)
    return destination


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    args = parse_args(argv)
    out_dir: Path = args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        ds = fetch_region(args)
    except Exception as exc:  # noqa: BLE001 - report any upstream failure clearly
        _LOG.error("download failed: %s", exc)
        _LOG.error(
            "Check network access to the Argo %s upstream, then retry.",
            args.source.upper(),
        )
        return 1

    try:
        wmos = float_ids_of(ds)
        if args.max_floats is not None:
            wmos = wmos[: max(0, args.max_floats)]
        written = 0
        for wmo in wmos:
            destination = out_dir / f"{wmo}.nc"
            if destination.exists() and not args.force:
                _LOG.info("skip existing %s", destination.name)
                continue
            path = save_float(ds, wmo, out_dir)
            written += 1
            _LOG.info("wrote %s", path.name)
    except Exception as exc:  # noqa: BLE001
        _LOG.error("failed while writing floats: %s", exc)
        return 1
    finally:
        ds.close()

    _LOG.info("done: %d new file(s), %d total float(s) considered, out=%s",
              written, len(wmos), out_dir)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
