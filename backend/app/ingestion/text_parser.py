"""Configurable delimited-text (CSV/TSV) parsing for simple tabular sources."""

from __future__ import annotations

import csv
import logging
from dataclasses import dataclass, field
from pathlib import Path

from app.models.schemas import TextParseResult

_LOG = logging.getLogger("echoshield.text")

DEFAULT_MISSING = {"", "NA", "N/A", "NaN", "nan", "null", "-999", "-9999"}


@dataclass(frozen=True)
class TextParseConfig:
    """Configuration for one delimited text format.

    ``column_map`` maps semantic roles to file columns, e.g.::

        {"latitude": "LAT", "longitude": "LON", "depth": "DEPTH_M",
         "time": "ISO_TIME", "temperature": "TEMP_C"}
    """

    delimiter: str = ","
    encoding: str = "utf-8"
    column_map: dict[str, str] = field(default_factory=dict)
    missing_values: frozenset[str] = frozenset(DEFAULT_MISSING)
    skip_rows: int = 0
    max_records: int = 100_000
    has_header: bool = True

    def __post_init__(self) -> None:
        if self.delimiter not in {",", "\t", ";", "|"}:
            raise ValueError(f"unsupported delimiter {self.delimiter!r}")


def sniff_delimiter(sample_line: str) -> str:
    """Pick a delimiter from a sample line (defaults to comma)."""
    counts = {delimiter: sample_line.count(delimiter) for delimiter in (",", "\t", ";", "|")}
    best = max(counts.items(), key=lambda item: item[1])[0]
    return best if counts[best] > 0 else ","


def parse_delimited_file(
    path: str | Path,
    config: TextParseConfig | None = None,
) -> TextParseResult:
    """Parse a delimited file and return a summary plus sample records."""
    cfg = config or TextParseConfig()
    source = Path(path)
    if not source.exists():
        raise FileNotFoundError(f"text file not found: {source}")

    with source.open(encoding=cfg.encoding, newline="") as handle:
        for _ in range(cfg.skip_rows):
            handle.readline()
        sample = handle.readline()
        # An explicitly configured non-default delimiter wins; otherwise sniff.
        delimiter = cfg.delimiter if cfg.delimiter != "," else sniff_delimiter(sample)
        handle.seek(0)
        for _ in range(cfg.skip_rows):
            handle.readline()

        reader = csv.reader(handle, delimiter=delimiter)
        header: list[str] | None = None
        if cfg.has_header:
            try:
                header = next(reader)
            except StopIteration as exc:
                raise ValueError("text file is empty") from exc

        records_parsed = 0
        sample_records: list[dict[str, str | None]] = []
        first_data_row: list[str] | None = None
        for row in reader:
            if not row or all(cell.strip() == "" for cell in row):
                continue
            if header is not None and len(row) > len(header):
                row = row[: len(header)]
            record = _row_to_dict(row, header)
            records_parsed += 1
            if first_data_row is None:
                first_data_row = row
            if len(sample_records) < 5:
                sample_records.append(
                    {
                        key: (None if value in cfg.missing_values else value)
                        for key, value in record.items()
                    }
                )
            if records_parsed >= cfg.max_records:
                break

    columns = (
        header
        if header is not None
        else ([f"column_{i + 1}" for i in range(len(first_data_row or []))])
    )
    coordinate_columns = {
        role: file_column for role, file_column in cfg.column_map.items() if file_column in columns
    }
    return TextParseResult(
        file=source.name,
        delimiter=delimiter,
        records_parsed=records_parsed,
        columns=list(columns),
        coordinate_columns=coordinate_columns,
        sample_records=sample_records,
    )


def parse_to_records(
    path: str | Path,
    config: TextParseConfig | None = None,
) -> list[dict[str, str | float | None]]:
    """Parse into normalised records using the configured column map.

    Keys of each record are the *semantic* names from ``column_map`` when a
    mapping exists; unmapped columns keep their original header names. Values
    are converted to floats where possible; missing markers become ``None``.
    """
    cfg = config or TextParseConfig()
    source = Path(path)
    reverse_map = {file_col: semantic for semantic, file_col in cfg.column_map.items()}

    with source.open(encoding=cfg.encoding, newline="") as handle:
        for _ in range(cfg.skip_rows):
            handle.readline()
        reader = csv.reader(handle, delimiter=cfg.delimiter)
        header: list[str] | None = next(reader, None) if cfg.has_header else None
        out: list[dict[str, str | float | None]] = []
        width = len(header) if header is not None else 0
        for row in reader:
            if not row or all(cell.strip() == "" for cell in row):
                continue
            record: dict[str, str | float | None] = {}
            limit = min(width, len(row)) if width else len(row)
            for index in range(limit):
                column_name = header[index] if header else f"column_{index + 1}"
                key = reverse_map.get(column_name, column_name)
                cleaned = row[index].strip()
                if cleaned in cfg.missing_values:
                    record[key] = None
                    continue
                try:
                    record[key] = float(cleaned)
                except ValueError:
                    record[key] = cleaned
            out.append(record)
            if len(out) >= cfg.max_records:
                break
        return out


def _row_to_dict(row: list[str], header: list[str] | None) -> dict[str, str]:
    if header:
        return dict(zip(header, row, strict=False))
    return {f"column_{i + 1}": cell for i, cell in enumerate(row)}
