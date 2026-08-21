"""Parser for ISO 19115 / ERDDAP metadata records (``*iso19115*.xml``).

INCOIS publishes ERDDAP-generated ISO 19115 records describing each dataset,
including distribution links (ERDDAP griddap / tabledap, OPeNDAP, WMS), a
geographic bounding box and temporal extent. This module extracts those so the
EchoShield dataset registry can auto-discover real INCOIS products.
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from app.models.schemas import ServiceEndpoints, SpatialBounds

_LOG = logging.getLogger("echoshield.iso19115")

_NS = {
    "gmd": "http://www.isotc211.org/2005/gmd",
    "gco": "http://www.isotc211.org/2005/gco",
    "gml": "http://www.opengis.net/gml/3.2",
}


@dataclass(frozen=True)
class IsoDatasetRecord:
    """A single ISO 19115 metadata record mapped to EchoShield concepts."""

    dataset_id: str
    title: str
    summary: str | None = None
    source_file: str = ""
    spatial_bounds: SpatialBounds | None = None
    time_start: str | None = None
    time_end: str | None = None
    services: ServiceEndpoints = field(default_factory=lambda: ServiceEndpoints(dataset_id=""))


def _local_name(element: ET.Element) -> str:
    tag = element.tag
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _first_text(parent: ET.Element, local_name: str) -> str | None:
    """Text of *local_name* element or its nested CharacterString child."""
    for element in parent.iter():
        if _local_name(element) == local_name:
            own = (element.text or "").strip()
            if own:
                return own
            for child in element.iter():
                if _local_name(child) == "CharacterString":
                    text = (child.text or "").strip()
                    if text:
                        return text
    return None


def _decimal_child(bound_element: ET.Element) -> float | None:
    for child in bound_element.iter():
        if _local_name(child) == "Decimal" and child.text:
            try:
                return float(child.text)
            except ValueError:
                return None
    return None


def classify_link(protocol: str, url: str) -> tuple[str, str] | None:
    """Classify an online resource into ``(service_key, canonical_url)``."""
    proto_lower = protocol.lower()
    url_lower = url.lower()

    if "erddap:tabledap" in proto_lower or "/erddap/tabledap/" in url_lower:
        return "erddap_tabledap", url.rstrip("/")
    if "erddap:griddap" in proto_lower or "/erddap/griddap/" in url_lower:
        return "erddap_griddap", url.rstrip("/")
    if "opendap" in proto_lower and ("dodsc" in url_lower or "/dods/" in url_lower):
        return "opendap", url
    if "ogc:wms" in proto_lower or (
        "/wms/" in url_lower and "request=getcapabilities" in url_lower
    ):
        base = url.split("?")[0]
        if not base.endswith("/request"):
            base = base.rstrip("/")
        return "wms", f"{base}?SERVICE=WMS&REQUEST=GetCapabilities"
    if "wcs" in proto_lower:
        return "wcs", url
    if "opendap" in proto_lower:
        return "opendap", url
    return None


def _resource_url(element: ET.Element) -> str | None:
    """Extract the access URL from a CI_OnlineResource element.

    Supports both ISO 19115-2005 (``gmd:linkage/gmd:URL``) and the newer
    ISO 19115-1 style used by current ERDDAP exports
    (``cit:linkage/gcx:FileName/@src`` or a CharacterString).
    """
    direct = _first_text(element, "URL")
    if direct:
        return direct
    for child in element.iter():
        if _local_name(child) != "linkage":
            continue
        for sub in child.iter():
            src = sub.attrib.get("src", "")
            if src.startswith(("http://", "https://")):
                return src.strip()
            if _local_name(sub) == "CharacterString" and sub.text:
                text = sub.text.strip()
                if text.startswith(("http://", "https://")):
                    return text
    return None


def parse_iso19115_file(path: str | Path) -> IsoDatasetRecord | None:
    """Parse one ISO 19115 XML file; returns ``None`` when unusable."""
    try:
        root = ET.parse(path).getroot()  # noqa: S314 - trusted local metadata
    except ET.ParseError as exc:
        _LOG.warning("iso19115_parse_failed file=%s error=%s", path, exc)
        return None

    identifier = _first_text(root, "fileIdentifier") or Path(path).stem
    title = _first_text(root, "title") or identifier
    summary = _first_text(root, "abstract")

    # Geographic bounding box.
    west = east = south = north = None
    for element in root.iter():
        if _local_name(element) == "westBoundLongitude":
            west = _decimal_child(element)
        elif _local_name(element) == "eastBoundLongitude":
            east = _decimal_child(element)
        elif _local_name(element) == "southBoundLatitude":
            south = _decimal_child(element)
        elif _local_name(element) == "northBoundLatitude":
            north = _decimal_child(element)
    bounds: SpatialBounds | None
    if west is not None and east is not None and south is not None and north is not None:
        bounds = SpatialBounds(west=west, east=east, south=south, north=north)
    else:
        bounds = None

    # Temporal extent.
    time_start = time_end = None
    for element in root.iter():
        if _local_name(element) == "beginPosition" and element.text:
            time_start = element.text.strip() or None
        elif _local_name(element) == "endPosition" and element.text:
            time_end = element.text.strip() or None

    # Distribution links.
    services: dict[str, str] = {}
    dataset_id = identifier
    for element in root.iter():
        if _local_name(element) not in {"CI_OnlineResource"}:
            continue
        url = _resource_url(element)
        protocol = _first_text(element, "protocol") or ""
        if not url:
            continue
        classified = classify_link(protocol, url)
        if classified is None:
            continue
        key, canonical = classified
        services.setdefault(key, canonical)
        if key in {"erddap_griddap", "erddap_tabledap"} and "/" in canonical:
            candidate = canonical.rstrip("/").rsplit("/", 1)[-1]
            # Ignore Make-A-Graph / HTML / DAS variants (.graph, .html, ...).
            if candidate and "." not in candidate:
                dataset_id = candidate

    endpoints = ServiceEndpoints(dataset_id=dataset_id, **services)
    return IsoDatasetRecord(
        dataset_id=dataset_id,
        title=title,
        summary=summary,
        source_file=str(Path(path).name),
        spatial_bounds=bounds,
        time_start=time_start,
        time_end=time_end,
        services=endpoints,
    )


def scan_metadata_directory(directory: str | Path) -> list[IsoDatasetRecord]:
    """Scan *directory* for ``*iso19115*.xml`` metadata records."""
    root = Path(directory)
    if not root.is_dir():
        return []
    records: list[IsoDatasetRecord] = []
    seen_ids: set[str] = set()
    for xml_path in sorted(root.glob("*iso19115*.xml")):
        record = parse_iso19115_file(xml_path)
        if record is None or record.dataset_id in seen_ids:
            continue
        seen_ids.add(record.dataset_id)
        records.append(record)
    _LOG.info("iso19115_scan directory=%s found=%d", directory, len(records))
    return records
