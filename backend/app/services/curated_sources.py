"""Curated INCOIS remote datasets used to complete SIH 26067 coverage.

These are optional upstreams: if INCOIS is unavailable the application still
starts and existing local/ISO-19115 datasets remain usable.
"""

from __future__ import annotations

from app.models.schemas import DatasetInfo, ServiceEndpoints, SpatialBounds, TimeRange
from app.services.dataset_registry import DatasetRegistry, RegisteredDataset

INCOIS_ERDDAP = "https://erddap.incois.gov.in/erddap"


def register_curated_sources(registry: DatasetRegistry) -> None:
    sources = [
        RegisteredDataset(
            info=DatasetInfo(
                id="incois_valueadded_currents",
                title="INCOIS Value Added Products — Geostrophic Currents",
                summary="INCOIS gridded value-added ocean products containing GEO_U and GEO_V geostrophic current components.",
                source_type="erddap_remote",
                provider="INCOIS",
                time_range=TimeRange(start="2004-01-10T00:00:00Z", end="2019-03-30T00:00:00Z", count=549),
                spatial_bounds=SpatialBounds(west=30.5, east=119.5, south=-29.5, north=29.5),
                services=ServiceEndpoints(
                    dataset_id="incois_valueadded_currents",
                    opendap=f"{INCOIS_ERDDAP}/griddap/incois_valueadded_products_datasets",
                    erddap_griddap=f"{INCOIS_ERDDAP}/griddap/incois_valueadded_products_datasets",
                    wms=f"{INCOIS_ERDDAP}/wms/incois_valueadded_products_datasets/request?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetCapabilities",
                ),
            ),
            remote_url=f"{INCOIS_ERDDAP}/griddap/incois_valueadded_products_datasets",
            engine="pydap",
        ),
        RegisteredDataset(
            info=DatasetInfo(
                id="incois_satellite_chlorophyll",
                title="INCOIS IRS P4 OCM Chlorophyll",
                summary="INCOIS satellite chlorophyll-a product for ocean-colour visualization and analysis.",
                source_type="erddap_remote",
                provider="INCOIS",
                spatial_bounds=SpatialBounds(west=60.0101, east=103.9482, south=0.0233, north=26.0460),
                services=ServiceEndpoints(
                    dataset_id="incois_satellite_chlorophyll",
                    opendap=f"{INCOIS_ERDDAP}/griddap/IRS_chlorophyll_datasets",
                    erddap_griddap=f"{INCOIS_ERDDAP}/griddap/IRS_chlorophyll_datasets",
                    wms=f"{INCOIS_ERDDAP}/wms/IRS_chlorophyll_datasets/request?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetCapabilities",
                ),
            ),
            remote_url=f"{INCOIS_ERDDAP}/griddap/IRS_chlorophyll_datasets",
            engine="pydap",
        ),
    ]

    for entry in sources:
        # DatasetRegistry already prevents curated entries from overwriting a
        # working local/ISO registration with the same ID.
        registry._register(entry)  # noqa: SLF001 - curated source bootstrap
