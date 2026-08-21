"""Configuration loading tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.config import Settings


def test_defaults_are_sane() -> None:
    settings = Settings(DATA_ROOT=Path("data"))
    assert settings.APP_NAME == "echoshield-backend"
    assert settings.API_V1_PREFIX == "/api/v1"
    assert settings.MAX_DATA_POINTS > 0
    assert settings.REQUEST_TIMEOUT > 0


def test_cors_origins_accept_comma_separated() -> None:
    settings = Settings(DATA_ROOT=Path("data"), CORS_ORIGINS="http://a.test, http://b.test")  # type: ignore[arg-type]
    assert settings.CORS_ORIGINS == ["http://a.test", "http://b.test"]


def test_resolve_data_path_blocks_traversal(tmp_path: Path) -> None:
    settings = Settings(DATA_ROOT=tmp_path)
    resolved = settings.resolve_data_path("sample_netcdf/x.nc")
    assert resolved.is_relative_to(tmp_path)
    with pytest.raises(ValueError, match="escapes DATA_ROOT"):
        settings.resolve_data_path("../outside.nc")


def test_derived_paths_fall_back_to_data_root(tmp_path: Path) -> None:
    settings = Settings(DATA_ROOT=tmp_path)
    assert settings.netcdf_data_root == tmp_path / "sample_netcdf"
    assert settings.argo_cache_dir == tmp_path / "argo_cache"
    assert settings.glider_cache_dir == tmp_path / "glider_cache"


def test_env_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MAX_GRID_POINTS", "1234")
    monkeypatch.setenv("DATA_ROOT", str(tmp_path))
    settings = Settings()
    assert settings.MAX_GRID_POINTS == 1234
