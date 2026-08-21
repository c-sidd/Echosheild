"""Text / delimited data parser tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.ingestion.text_parser import (
    TextParseConfig,
    parse_delimited_file,
    parse_to_records,
    sniff_delimiter,
)


@pytest.fixture()
def csv_file(tmp_path: Path) -> Path:
    content = """ISO_TIME,LAT,LON,DEPTH_M,TEMP_C
2024-01-01T00:00:00Z,10.5,72.3,0,28.4
2024-01-02T00:00:00Z,10.6,72.4,10,NA
2024-01-03T00:00:00Z,10.7,72.5,20,27.9
"""
    path = tmp_path / "observations.csv"
    path.write_text(content, encoding="utf-8")
    return path


@pytest.fixture()
def tsv_file(tmp_path: Path) -> Path:
    content = "time\tlat\tlon\tsst\n2024-01-01\t8.1\t76.2\t29.1\n2024-01-02\t8.2\t76.3\t-9999\n"
    path = tmp_path / "observations.tsv"
    path.write_text(content, encoding="utf-8")
    return path


CSV_CONFIG = TextParseConfig(
    delimiter=",",
    column_map={
        "time": "ISO_TIME",
        "latitude": "LAT",
        "longitude": "LON",
        "depth": "DEPTH_M",
        "temperature": "TEMP_C",
    },
)


def test_parse_summary(csv_file: Path) -> None:
    result = parse_delimited_file(csv_file, CSV_CONFIG)
    assert result.records_parsed == 3
    assert result.delimiter == ","
    assert result.coordinate_columns["latitude"] == "LAT"
    assert len(result.sample_records) == 3
    assert result.sample_records[1]["TEMP_C"] is None  # NA -> missing


def test_tsv_sniffing(tsv_file: Path) -> None:
    result = parse_delimited_file(tsv_file)
    assert result.delimiter == "\t"
    assert result.records_parsed == 2


def test_missing_values_and_numeric_conversion(tsv_file: Path) -> None:
    records = parse_to_records(
        tsv_file,
        TextParseConfig(delimiter="\t", column_map={"temperature": "sst"}),
    )
    assert records[0]["temperature"] == 29.1
    assert records[1]["temperature"] is None  # -9999 treated as missing


def test_records_capped(tmp_path: Path) -> None:
    path = tmp_path / "big.csv"
    rows = "a\n" + "\n".join(str(i) for i in range(100))
    path.write_text(rows, encoding="utf-8")
    result = parse_delimited_file(path, TextParseConfig(max_records=10))
    assert result.records_parsed == 10


def test_unsupported_delimiter_rejected() -> None:
    with pytest.raises(ValueError, match="delimiter"):
        TextParseConfig(delimiter=":")


def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        parse_delimited_file(tmp_path / "nope.csv")


def test_empty_file_raises(tmp_path: Path) -> None:
    path = tmp_path / "empty.csv"
    path.write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="empty"):
        parse_delimited_file(path)


def test_sniff_delimiter_prefers_tab() -> None:
    assert sniff_delimiter("a\tb\tc") == "\t"
    assert sniff_delimiter("a,b,c") == ","
