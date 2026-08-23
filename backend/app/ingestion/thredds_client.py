"""THREDDS server integration.

EchoShield does **not** implement OPeNDAP/WMS/WCS itself; this client talks to
an existing THREDDS (or ERDDAP-flavoured OPeNDAP) deployment:

* catalog discovery (XML catalog parsing),
* service URL construction,
* endpoint availability validation with retries and a circuit breaker.
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote, urlsplit

import httpx

from app.core.config import Settings
from app.core.reliability.circuit_breaker import CircuitBreaker
from app.core.reliability.retry import async_retry
from app.models.schemas import ServiceEndpoints

_LOG = logging.getLogger("echoshield.thredds")


class ThreddsClientError(RuntimeError):
    """Raised for THREDDS discovery/communication problems."""


@dataclass(frozen=True)
class CatalogDataset:
    """A dataset entry found in a THREDDS catalog."""

    id: str
    title: str
    catalog_url: str
    services: list[str] = field(default_factory=list)


def validate_service_url(url: str) -> str:
    """Reject malformed / unsafe URLs before they are handed to the frontend."""
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"}:
        raise ValueError(f"service URL must be http(s): {url!r}")
    if not parts.netloc:
        raise ValueError(f"service URL has no host: {url!r}")
    return url


def build_thredds_service_urls(
    *,
    dataset_path: str,
    settings: Settings,
    supported: set[str] | None = None,
) -> ServiceEndpoints:
    """Build THREDDS service endpoints for *dataset_path* from configuration.

    ``supported`` may restrict which services are advertised (THREDDS datasets
    do not necessarily enable WMS/WCS).
    """
    base = settings.THREDDS_BASE_URL.rstrip("/") if settings.THREDDS_BASE_URL else None
    opendap_base = settings.OPENDAP_BASE_URL.rstrip("/") if settings.OPENDAP_BASE_URL else base
    wms_base = settings.WMS_BASE_URL.rstrip("/") if settings.WMS_BASE_URL else base
    # WCS is only advertised when an explicit WCS-capable service is
    # configured — never silently inherited from the THREDDS base URL,
    # because the catalog may not enable a WCS service at all.
    wcs_base = settings.WCS_BASE_URL.rstrip("/") if settings.WCS_BASE_URL else None
    catalog = settings.THREDDS_CATALOG_URL or None

    path = dataset_path.strip("/")
    allowed = supported  # None => advertise whatever bases are configured

    def _include(service: str) -> bool:
        return allowed is None or service in allowed

    urls: dict[str, Any] = {}
    if base and _include("httpserver"):
        urls["http_download"] = validate_service_url(f"{base}/fileServer/{path}")
    if opendap_base and _include("opendap"):
        urls["opendap"] = validate_service_url(f"{opendap_base}/dodsC/{path}")
    if wms_base and _include("wms"):
        urls["wms"] = validate_service_url(
            f"{wms_base}/wms/{path}?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetCapabilities"
        )
    if wcs_base and _include("wcs"):
        urls["wcs"] = validate_service_url(
            f"{wcs_base}/wcs/{path}?SERVICE=WCS&VERSION=2.0.1&REQUEST=GetCapabilities"
        )
    if catalog:
        urls["thredds_catalog"] = validate_service_url(catalog)

    return ServiceEndpoints(dataset_id=path.rsplit("/", 1)[-1], **urls)


def build_erddap_griddap_urls(base_url: str, dataset_id: str) -> ServiceEndpoints:
    """ERDDAP griddap is an OPeNDAP flavour; expose it plus its WMS view."""
    base = base_url.rstrip("/")
    return ServiceEndpoints(
        dataset_id=dataset_id,
        erddap_griddap=validate_service_url(f"{base}/griddap/{quote(dataset_id)}"),
        erddap_tabledap=None,
        opendap=validate_service_url(f"{base}/griddap/{quote(dataset_id)}"),
        wms=validate_service_url(
            f"{base}/wms/{quote(dataset_id)}/request?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetCapabilities"
        ),
    )


class ThreddsClient:
    """Async THREDDS catalog + availability client."""

    def __init__(
        self,
        settings: Settings,
        *,
        http_client: httpx.AsyncClient | None = None,
        circuit_breaker: CircuitBreaker | None = None,
    ) -> None:
        self._settings = settings
        self._client = http_client
        self._circuit = circuit_breaker or CircuitBreaker(
            "thredds", failure_threshold=5, reset_timeout=30.0
        )

    @property
    def configured(self) -> bool:
        return bool(self._settings.THREDDS_CATALOG_URL or self._settings.THREDDS_BASE_URL)

    def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._settings.REQUEST_TIMEOUT)
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    @async_retry("thredds_catalog_fetch")
    async def fetch_catalog_xml(self, catalog_url: str) -> bytes:
        """GET a THREDDS catalog document as raw XML bytes."""
        validate_service_url(catalog_url)
        if not self._circuit.allow_call():
            raise ThreddsClientError("THREDDS circuit breaker is open; skipping call")
        try:
            response = await self._ensure_client().get(catalog_url)
            response.raise_for_status()
        except Exception:
            self._circuit.record_failure()
            raise
        self._circuit.record_success()
        return response.content

    async def discover_datasets(self, catalog_url: str | None = None) -> list[CatalogDataset]:
        """Parse a THREDDS catalog into dataset entries."""
        url = catalog_url or self._settings.THREDDS_CATALOG_URL
        if not url:
            raise ThreddsClientError("no THREDDS catalog URL configured")
        content = await self.fetch_catalog_xml(url)
        try:
            root = ET.fromstring(content)  # noqa: S314 - upstream catalog XML
        except ET.ParseError as exc:
            raise ThreddsClientError(f"invalid catalog XML from {url}: {exc}") from exc

        datasets: list[CatalogDataset] = []
        for element in root.iter():
            local = element.tag.rsplit("}", 1)[-1]
            if local != "dataset":
                continue
            dataset_id = element.get("ID") or element.get("urlPath") or element.get("name", "")
            title = element.get("name") or dataset_id
            services = [
                str(child.text or "").strip()
                for child in element
                if child.tag.rsplit("}", 1)[-1] == "serviceName"
            ]
            access_urls = {
                child.get("href", "")
                for child in element.iter()
                if child.tag.rsplit("}", 1)[-1] == "access"
            }
            catalog_ref = next(iter(access_urls), "") or url
            if dataset_id:
                datasets.append(
                    CatalogDataset(
                        id=str(dataset_id),
                        title=str(title),
                        catalog_url=catalog_ref,
                        services=[s for s in services if s],
                    )
                )
        _LOG.info("thredds_catalog_parsed url=%s datasets=%d", url, len(datasets))
        return datasets

    async def check_endpoint(self, url: str) -> tuple[bool, float | None, str | None]:
        """Probe a service endpoint; returns ``(available, latency_ms, error)``."""
        started = __import__("time").perf_counter()
        try:
            validate_service_url(url)
            client = self._ensure_client()
            response = await client.head(url, follow_redirects=True)
            available = response.status_code < 500
            error = None if available else f"HTTP {response.status_code}"
        except Exception as exc:  # noqa: BLE001
            available, error = False, type(exc).__name__
        latency_ms = (__import__("time").perf_counter() - started) * 1000.0
        return available, latency_ms, error
