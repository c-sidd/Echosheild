# EchoShield backend startup (Windows PowerShell).
# Sets demo-safe defaults, then serves the API on http://localhost:<Port>/docs
#
# Usage:
#   .\run.ps1                 # port 8000, local-first Argo provider
#   .\run.ps1 -Port 9000
#   $env:ARGO_PROVIDER="auto"; .\run.ps1   # override any default via env

param(
    [int]$Port = 8000,
    [string]$HostAddr = "0.0.0.0"
)

$ErrorActionPreference = "Stop"
$backendDir = $PSScriptRoot
$repoRoot = Split-Path $backendDir -Parent

# --- data locations (repo-relative unless already configured) ---------------
if (-not $env:DATA_ROOT)          { $env:DATA_ROOT          = Join-Path $repoRoot "data" }
if (-not $env:NETCDF_DATA_ROOT)   { $env:NETCDF_DATA_ROOT   = Join-Path $env:DATA_ROOT "sample_netcdf" }
if (-not $env:ARGO_CACHE_DIR)     { $env:ARGO_CACHE_DIR     = Join-Path $env:DATA_ROOT "argo_cache" }
if (-not $env:GLIDER_CACHE_DIR)   { $env:GLIDER_CACHE_DIR   = Join-Path $env:DATA_ROOT "glider_cache" }

# Demo default: prefer cached local Argo profiles (no network needed).
# Set ARGO_PROVIDER=remote/auto in the environment to override.
if (-not $env:ARGO_PROVIDER)       { $env:ARGO_PROVIDER       = "local" }

Write-Host "EchoShield backend"
Write-Host "  DATA_ROOT         = $env:DATA_ROOT"
Write-Host "  NETCDF_DATA_ROOT  = $env:NETCDF_DATA_ROOT"
Write-Host "  ARGO_CACHE_DIR    = $env:ARGO_CACHE_DIR"
Write-Host "  ARGO_PROVIDER     = $env:ARGO_PROVIDER"
Write-Host "  http://localhost:$Port/docs"

& uv run --project $backendDir uvicorn app.main:app --host $HostAddr --port $Port
exit $LASTEXITCODE
