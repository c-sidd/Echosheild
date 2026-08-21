"""Shared pytest fixtures for the EchoShield backend test suite."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.config import Settings
from app.main import create_app
from app.testing_utils import write_synthetic_netcdf


@pytest.fixture(scope="session")
def sample_netcdf_file(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """One synthetic NetCDF file shared across the session (fast)."""
    return write_synthetic_netcdf(tmp_path_factory.mktemp("data") / "synthetic_ocean.nc")


@pytest.fixture()
def settings(
    tmp_path: Path,
    sample_netcdf_file: Path,
) -> Settings:
    """Isolated settings pointing at a temp data root with the sample file."""
    data_root = tmp_path / "data"
    netcdf_root = data_root / "sample_netcdf"
    netcdf_root.mkdir(parents=True)
    target = netcdf_root / sample_netcdf_file.name
    target.write_bytes(sample_netcdf_file.read_bytes())
    return Settings(
        DATA_ROOT=data_root,
        NETCDF_DATA_ROOT=netcdf_root,
        ARGO_CACHE_DIR=data_root / "argo_cache",
        GLIDER_CACHE_DIR=data_root / "glider_cache",
        THREDDS_BASE_URL=None,
        THREDDS_CATALOG_URL=None,
        INCOIS_ERDDAP_URL=None,
        CACHE_TTL_SECONDS=60,
    )


@pytest.fixture()
def client(settings: Settings):
    """TestClient with lifespan executed (registry populated, etc.)."""
    from fastapi.testclient import TestClient

    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def iso_metadata_dir(tmp_path: Path) -> Path:
    """A minimal ISO 19115 record mimicking INCOIS ERDDAP metadata."""
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<gmd:MD_Metadata xmlns:gmd="http://www.isotc211.org/2005/gmd"
                 xmlns:gco="http://www.isotc211.org/2005/gco">
  <gmd:fileIdentifier><gco:CharacterString>incois_test_product</gco:CharacterString></gmd:fileIdentifier>
  <gmd:identificationInfo>
    <gmd:MD_DataIdentification>
      <gmd:citation><gmd:title><gco:CharacterString>INCOIS Test Product</gco:CharacterString></gmd:title></gmd:citation>
      <gmd:abstract><gco:CharacterString>Metadata fixture for tests.</gco:CharacterString></gmd:abstract>
      <gmd:extent>
        <gmd:EX_Extent>
          <gmd:geographicElement>
            <gmd:EX_GeographicBoundingBox>
              <gmd:westBoundLongitude><gco:Decimal>50.0</gco:Decimal></gmd:westBoundLongitude>
              <gmd:eastBoundLongitude><gco:Decimal>100.0</gco:Decimal></gmd:eastBoundLongitude>
              <gmd:southBoundLatitude><gco:Decimal>-10.0</gco:Decimal></gmd:southBoundLatitude>
              <gmd:northBoundLatitude><gco:Decimal>30.0</gco:Decimal></gmd:northBoundLatitude>
            </gmd:EX_GeographicBoundingBox>
          </gmd:geographicElement>
        </gmd:EX_Extent>
      </gmd:extent>
      <gmd:distributionInfo>
        <gmd:MD_Distribution>
          <gmd:transferOptions>
            <gmd:MD_DigitalTransferOptions>
              <gmd:onLine>
                <gmd:CI_OnlineResource>
                  <gmd:linkage><gmd:URL>https://erddap.example.gov/erddap/griddap/incois_test_product</gmd:URL></gmd:linkage>
                  <gmd:protocol><gco:CharacterString>ERDDAP:griddap</gco:CharacterString></gmd:protocol>
                </gmd:CI_OnlineResource>
              </gmd:onLine>
              <gmd:onLine>
                <gmd:CI_OnlineResource>
                  <gmd:linkage><gmd:URL>https://erddap.example.gov/erddap/wms/incois_test_product/request?service=WMS&amp;version=1.3.0&amp;request=GetCapabilities</gmd:URL></gmd:linkage>
                  <gmd:protocol><gco:CharacterString>OGC:WMS</gco:CharacterString></gmd:protocol>
                </gmd:CI_OnlineResource>
              </gmd:onLine>
            </gmd:MD_DigitalTransferOptions>
          </gmd:transferOptions>
        </gmd:MD_Distribution>
      </gmd:distributionInfo>
    </gmd:MD_DataIdentification>
  </gmd:identificationInfo>
</gmd:MD_Metadata>
"""
    directory = tmp_path / "metadata"
    directory.mkdir()
    (directory / "incois_test_product_iso19115.xml").write_text(xml, encoding="utf-8")
    return directory
