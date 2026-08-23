"""THREDDS client tests â€” HTTP layer is mocked, no live server required."""

from __future__ import annotations

import asyncio
import contextlib
from pathlib import Path

import httpx
import pytest

from app.core.config import Settings
from app.ingestion.iso19115_parser import scan_metadata_directory
from app.ingestion.thredds_client import (
    CatalogDataset,
    ThreddsClient,
    ThreddsClientError,
    build_erddap_griddap_urls,
    build_thredds_service_urls,
    validate_service_url,
)

# --- URL building -----------------------------------------------------------


def test_build_thredds_service_urls(settings: Settings) -> None:
    configured = settings.model_copy(
        update={
            "THREDDS_BASE_URL": "http://thredds:8080/thredds",
            "THREDDS_CATALOG_URL": "http://thredds:8080/thredds/catalog.xml",
        }
    )
    urls = build_thredds_service_urls(dataset_path="incois/test.nc", settings=configured)
    assert urls.opendap == "http://thredds:8080/thredds/dodsC/incois/test.nc"
    assert urls.wms is not None and "GetCapabilities" in urls.wms
    # WCS is never silently inherited from the THREDDS base URL: the catalog
    # may not enable a WCS service at all (false advertising guard).
    assert urls.wcs is None
    assert urls.http_download == "http://thredds:8080/thredds/fileServer/incois/test.nc"


def test_wcs_only_when_explicitly_configured(settings: Settings) -> None:
    configured = settings.model_copy(
        update={
            "THREDDS_BASE_URL": "http://thredds:8080/thredds",
            "WCS_BASE_URL": "http://wcs.example.gov/wcs",
        }
    )
    urls = build_thredds_service_urls(dataset_path="a.nc", settings=configured)
    assert urls.wcs is not None and urls.wcs.startswith("http://wcs.example.gov/wcs")


def test_supported_services_are_respected(settings: Settings) -> None:
    configured = settings.model_copy(update={"THREDDS_BASE_URL": "http://t:8080/thredds"})
    urls = build_thredds_service_urls(
        dataset_path="a.nc", settings=configured, supported={"opendap"}
    )
    assert urls.opendap is not None
    assert urls.wms is None and urls.wcs is None and urls.http_download is None


def test_validate_rejects_non_http() -> None:
    with pytest.raises(ValueError):
        validate_service_url("file:///etc/passwd")
    with pytest.raises(ValueError):
        validate_service_url("notaurl")


def test_erddap_griddap_urls() -> None:
    endpoints = build_erddap_griddap_urls("https://erddap.incois.gov.in/erddap", "sst_weekly")
    assert endpoints.erddap_griddap == "https://erddap.incois.gov.in/erddap/griddap/sst_weekly"
    assert endpoints.wms is not None and "wms/sst_weekly" in endpoints.wms


# --- catalog discovery (mocked transport) -----------------------------------


CATALOG_XML = b"""<?xml version="1.0"?>
<catalog xmlns="http://www.unidata.ucar.edu/namespaces/thredds/InvCatalog/v1.0">
  <dataset name="INCOIS SST" ID="incois_sst.nc" urlPath="incois/sst.nc">
    <serviceName>OPeNDAP</serviceName>
  </dataset>
  <dataset name="Broken" />
</catalog>
"""


def test_discover_datasets_parses_catalog(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    async def fake_get(self: httpx.AsyncClient, url: str, **kwargs: object) -> httpx.Response:
        request = httpx.Request("GET", url)
        return httpx.Response(200, content=CATALOG_XML, request=request)

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    configured = settings.model_copy(
        update={"THREDDS_CATALOG_URL": "http://thredds:8080/thredds/catalog.xml"}
    )
    client = ThreddsClient(configured)

    entries = asyncio.run(client.discover_datasets())
    assert len(entries) == 2
    assert isinstance(entries[0], CatalogDataset)
    assert entries[0].id == "incois_sst.nc"
    assert entries[0].services == ["OPeNDAP"]


def test_catalog_http_error_propagates(monkeypatch: pytest.MonkeyPatch, settings: Settings) -> None:
    async def fake_get(self: httpx.AsyncClient, url: str, **kwargs: object) -> httpx.Response:
        request = httpx.Request("GET", url)
        return httpx.Response(503, content=b"", request=request)

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    configured = settings.model_copy(
        update={"THREDDS_CATALOG_URL": "http://thredds:8080/catalog.xml"}
    )
    client = ThreddsClient(configured)

    with pytest.raises(Exception):  # noqa: B017 - tenacity reraises original
        asyncio.run(client.discover_datasets())


def test_no_catalog_configured_raises(settings: Settings) -> None:
    client = ThreddsClient(settings)
    assert client.configured is False
    with pytest.raises(ThreddsClientError, match="no THREDDS catalog"):
        asyncio.run(client.discover_datasets())


def test_circuit_breaker_opens_after_failures(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    calls = {"count": 0}

    def failing_get(self: httpx.AsyncClient, url: str) -> httpx.Response:
        calls["count"] += 1
        request = httpx.Request("GET", url)
        return httpx.Response(500, content=b"", request=request)

    monkeypatch.setattr(httpx.AsyncClient, "get", failing_get)
    configured = settings.model_copy(
        update={"THREDDS_CATALOG_URL": "http://thredds:8080/catalog.xml"}
    )
    client = ThreddsClient(configured)

    async def attempt() -> None:
        await client.fetch_catalog_xml("http://thredds:8080/catalog.xml")

    for _ in range(5):
        with contextlib.suppress(Exception):
            asyncio.run(attempt())
    assert client._circuit.state.value == "open"
    # Once open, requests are rejected without hitting the network.
    before = calls["count"]
    with contextlib.suppress(Exception):
        asyncio.run(attempt())
    assert calls["count"] == before


# --- ISO 19115 metadata parsing ----------------------------------------------


def test_iso19115_record_parsing(iso_metadata_dir: Path) -> None:
    records = scan_metadata_directory(iso_metadata_dir)
    assert len(records) == 1
    record = records[0]
    assert record.dataset_id == "incois_test_product"
    assert record.title == "INCOIS Test Product"
    assert record.spatial_bounds is not None
    assert record.spatial_bounds.south == -10.0
    services = record.services
    assert (
        services.erddap_griddap == "https://erddap.example.gov/erddap/griddap/incois_test_product"
    )
    assert services.wms is not None and "GetCapabilities" in services.wms


def test_registry_registers_iso19115_dataset(iso_metadata_dir: Path, tmp_path: Path) -> None:
    from app.services.dataset_registry import DatasetRegistry

    data_root = tmp_path / "data"
    data_root.mkdir(exist_ok=True)
    settings = Settings(DATA_ROOT=data_root, NETCDF_DATA_ROOT=tmp_path / "nc")
    settings.NETCDF_DATA_ROOT = iso_metadata_dir.parent / "nc"  # type: ignore[assignment]
    # Copy metadata into DATA_ROOT so scan finds it.
    for xml_file in iso_metadata_dir.glob("*.xml"):
        (data_root / xml_file.name).write_text(xml_file.read_text(encoding="utf-8"))
    registry = DatasetRegistry(settings)
    registry.discover()
    entry = registry.get("incois_test_product")
    assert entry.info.source_type == "erddap_remote"
    assert entry.remote_url is not None and "griddap" in entry.remote_url
