# EchoSheild Backend

FastAPI application layer for the EchoSheild 3D Ocean Data Visualization Platform.

## Responsibilities

- Ocean model data API
- NetCDF processing through xarray
- Argo data ingestion
- Glider data ingestion
- THREDDS/OPeNDAP integration
- Observation and model data APIs
- Backend reliability and error handling

## Development

Install dependencies:

    uv sync

Run the development server:

    uv run uvicorn app.main:app --reload

Run tests:

    uv run pytest

Lint:

    uv run ruff check .

Format:

    uv run ruff format .
