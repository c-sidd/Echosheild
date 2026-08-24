"""Model-versus-observation comparison helpers for SIH 26067."""

from __future__ import annotations

from datetime import datetime
from math import sqrt
from statistics import mean
from typing import cast

from pydantic import BaseModel, Field

from app.models.schemas import ArgoProfile
from app.services.model_service import ModelDataService


class ComparisonPoint(BaseModel):
    depth_meters: float | None = None
    observation_temperature_c: float | None = None
    model_temperature_c: float | None = None
    temperature_error_c: float | None = None
    observation_salinity_psu: float | None = None
    model_salinity_psu: float | None = None
    salinity_error_psu: float | None = None


class ComparisonMetrics(BaseModel):
    temperature_count: int = 0
    salinity_count: int = 0
    temperature_bias_c: float | None = None
    temperature_mae_c: float | None = None
    temperature_rmse_c: float | None = None
    salinity_bias_psu: float | None = None
    salinity_mae_psu: float | None = None
    salinity_rmse_psu: float | None = None


class ModelObservationComparison(BaseModel):
    dataset_id: str
    platform_wmo: int
    cycle_number: int | None = None
    observation_time: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    model_time: str | None = None
    model_time_index: int | None = None
    metrics: ComparisonMetrics
    points: list[ComparisonPoint] = Field(default_factory=list)


def _as_naive_utc(value: datetime) -> datetime:
    # Argo feeds stamp UTC; decoded NetCDF times are usually tz-naive.
    # Compare wall-clock values so both conventions can be diffed.
    return value.replace(tzinfo=None) if value.tzinfo is not None else value


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return _as_naive_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
    except ValueError:
        return None


def _nearest_time_index(times: list[str], target: str | None) -> int | None:
    target_dt = _parse_time(target)
    if target_dt is None or not times:
        return None
    parsed = [(_parse_time(value), index) for index, value in enumerate(times)]
    candidates = [(abs((value - target_dt).total_seconds()), index) for value, index in parsed if value is not None]
    return min(candidates)[1] if candidates else None


def _metrics(errors: list[float], prefix: str) -> dict[str, float | int | None]:
    if not errors:
        return {f"{prefix}_count": 0, f"{prefix}_bias": None, f"{prefix}_mae": None, f"{prefix}_rmse": None}
    return {
        f"{prefix}_count": len(errors),
        f"{prefix}_bias": round(mean(errors), 6),
        f"{prefix}_mae": round(mean(abs(value) for value in errors), 6),
        f"{prefix}_rmse": round(sqrt(mean(value * value for value in errors)), 6),
    }


def compare_profile(model: ModelDataService, dataset_id: str, profile: ArgoProfile) -> ModelObservationComparison:
    times = model.get_times(dataset_id)
    model_time_index = _nearest_time_index(times, profile.time)
    model_time = times[model_time_index] if model_time_index is not None else None
    points: list[ComparisonPoint] = []
    temp_errors: list[float] = []
    sal_errors: list[float] = []

    if profile.latitude is None or profile.longitude is None:
        return ModelObservationComparison(
            dataset_id=dataset_id,
            platform_wmo=profile.platform_wmo,
            cycle_number=profile.cycle_number,
            observation_time=profile.time,
            metrics=ComparisonMetrics(),
        )

    for observed in profile.points:
        if observed.depth_meters is None:
            continue
        sample = model.read_point(
            dataset_id,
            ["temperature", "salinity"],
            latitude=profile.latitude,
            longitude=profile.longitude,
            time_index=model_time_index,
            depth_meters=observed.depth_meters,
        )
        model_temp = sample.values.get("temperature")
        model_sal = sample.values.get("salinity")
        temp_error = None
        sal_error = None
        if observed.temperature_c is not None and model_temp is not None:
            temp_error = model_temp - observed.temperature_c
            temp_errors.append(temp_error)
        if observed.salinity_psu is not None and model_sal is not None:
            sal_error = model_sal - observed.salinity_psu
            sal_errors.append(sal_error)
        points.append(
            ComparisonPoint(
                depth_meters=observed.depth_meters,
                observation_temperature_c=observed.temperature_c,
                model_temperature_c=model_temp,
                temperature_error_c=temp_error,
                observation_salinity_psu=observed.salinity_psu,
                model_salinity_psu=model_sal,
                salinity_error_psu=sal_error,
            )
        )

    tm = _metrics(temp_errors, "temperature")
    sm = _metrics(sal_errors, "salinity")
    return ModelObservationComparison(
        dataset_id=dataset_id,
        platform_wmo=profile.platform_wmo,
        cycle_number=profile.cycle_number,
        observation_time=profile.time,
        latitude=profile.latitude,
        longitude=profile.longitude,
        model_time=model_time,
        model_time_index=model_time_index,
        metrics=ComparisonMetrics(
            temperature_count=cast(int, tm["temperature_count"]),
            temperature_bias_c=tm["temperature_bias"],
            temperature_mae_c=tm["temperature_mae"],
            temperature_rmse_c=tm["temperature_rmse"],
            salinity_count=cast(int, sm["salinity_count"]),
            salinity_bias_psu=sm["salinity_bias"],
            salinity_mae_psu=sm["salinity_mae"],
            salinity_rmse_psu=sm["salinity_rmse"],
        ),
        points=points,
    )
