"""Dataset discovery tests: corruption isolation, sidecars, deterministic IDs."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.dataset_registry import DatasetRegistry


def _write_minimal_iso_xml(path: Path, *, stem: str, title: str, provider: str) -> None:
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<gmd:MD_Metadata xmlns:gmd="http://www.isotc211.org/2005/gmd"
                 xmlns:gco="http://www.isotc211.org/2005/gco"
                 xmlns:cit="http://standards.iso.org/iso/19115/-3/cit/2.0">
  <gmd:fileIdentifier><gco:CharacterString>{stem}</gco:CharacterString></gmd:fileIdentifier>
  <gmd:identificationInfo><gmd:MD_DataIdentification>
    <gmd:citation><gmd:title><gco:CharacterString>{title}</gco:CharacterString></gmd:title></gmd:citation>
    <gmd:abstract><gco:CharacterString>Sidecar fixture.</gco:CharacterString></gmd:abstract>
  </gmd:MD_DataIdentification></gmd:identificationInfo>
  <gmd:contact>
    <cit:CI_Responsibility>
      <cit:party><cit:CI_Organisation>
        <cit:name><gco:CharacterString>{provider}</gco:CharacterString></cit:name>
      </cit:CI_Organisation></cit:party>
    </cit:CI_Responsibility>
  </gmd:contact>
</gmd:MD_Metadata>
"""
    path.write_text(xml, encoding="utf-8")


def test_corrupt_netcdf_is_isolated(settings, sample_netcdf_file: Path) -> None:
    """A garbage .nc must be skipped with a warning; healthy files still load."""
    netcdf_root: Path = settings.NETCDF_DATA_ROOT
    (netcdf_root / "corrupted.nc").write_bytes(b"NOT A NETCDF FILE" * 32)

    registry = DatasetRegistry(settings)
    count = registry.discover()

    ids = {entry.id for entry in registry.list()}
    assert "local_synthetic_ocean" in ids
    assert "local_corrupted" not in ids
    assert count >= 1


def test_sidecar_metadata_association(settings, sample_netcdf_file: Path) -> None:
    """`<stem>_iso19115.xml` enriches title/provider of the local dataset."""
    _write_minimal_iso_xml(
        settings.DATA_ROOT / "synthetic_ocean_iso19115.xml",
        stem="synthetic_ocean",
        title="Enriched Synthetic Title",
        provider="TEST-PROVIDER",
    )

    registry = DatasetRegistry(settings)
    registry.discover()
    info = registry.get("synthetic_ocean").info
    assert info.title == "Enriched Synthetic Title"
    assert info.provider == "TEST-PROVIDER"
    assert info.metadata_path == "synthetic_ocean_iso19115.xml"
    # The sidecar product ID replaces the file-stem based ID.
    ids = {entry.id for entry in registry.list()}
    assert "local_synthetic_ocean" not in ids


def test_sidecar_prefix_match_erddap_style_names(settings, sample_netcdf_file: Path) -> None:
    """ERDDAP download names (hash suffixes) still match their ISO record."""
    _write_minimal_iso_xml(
        settings.DATA_ROOT / "incois_argo_mnt_VAM_iso19115.xml",
        stem="incois_argo_mnt_VAM",
        title="INCOIS ARGO Monthly VAM",
        provider="INCOIS",
    )
    erddap_name = settings.NETCDF_DATA_ROOT / (
        "incois_argo_mnt_VAM_f99c_fe7d_a5a3_U1787403117643.nc"
    )
    erddap_name.write_bytes(sample_netcdf_file.read_bytes())

    registry = DatasetRegistry(settings)
    registry.discover()

    info = registry.get("incois_argo_mnt_VAM").info
    assert info.title == "INCOIS ARGO Monthly VAM"
    assert info.provider == "INCOIS"
    # The plain-stem synthetic copy keeps its own unrelated registration.
    assert "local_synthetic_ocean" in {entry.id for entry in registry.list()}


def test_sidecar_most_specific_match_wins(settings, sample_netcdf_file: Path) -> None:
    """When two records prefix-match, the longer (more specific) one wins."""
    _write_minimal_iso_xml(
        settings.DATA_ROOT / "incois_argo_iso19115.xml",
        stem="incois_argo",
        title="Generic Argo Record",
        provider="GENERIC",
    )
    _write_minimal_iso_xml(
        settings.DATA_ROOT / "incois_argo_mnt_VAM_iso19115.xml",
        stem="incois_argo_mnt_VAM",
        title="Specific Monthly VAM Record",
        provider="INCOIS",
    )
    target = settings.NETCDF_DATA_ROOT / "incois_argo_mnt_VAM_deadbeef.nc"
    target.write_bytes(sample_netcdf_file.read_bytes())

    registry = DatasetRegistry(settings)
    registry.discover()
    info = registry.get("incois_argo_mnt_VAM").info
    assert info.title == "Specific Monthly VAM Record"


def test_deterministic_ids_across_cache_dirs(
    settings, sample_netcdf_file: Path, sample_netcdf_file_again: Path
) -> None:
    """Same file stem in two roots yields stable, distinct dataset IDs."""
    argo_cache: Path = settings.ARGO_CACHE_DIR
    argo_cache.mkdir(parents=True, exist_ok=True)
    target = argo_cache / "synthetic_ocean.nc"
    target.write_bytes(sample_netcdf_file_again.read_bytes())

    registry = DatasetRegistry(settings)
    registry.discover()
    ids = {entry.id for entry in registry.list()}
    assert "local_synthetic_ocean" in ids
    assert f"local_{argo_cache.name}_synthetic_ocean" in ids


@pytest.fixture()
def sample_netcdf_file_again(sample_netcdf_file: Path) -> Path:
    """Second handle on the same bytes for copy-based collision tests."""
    return sample_netcdf_file
