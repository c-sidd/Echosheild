import { get } from './api'

const INDO_BOX = { lon_min: 50, lon_max: 100, lat_min: -10, lat_max: 30 }

export function fetchArgoFloats(bounds = INDO_BOX, maxFloats = 200, signal) {
  const b = bounds ?? INDO_BOX
  const p = new URLSearchParams({
    lon_min: String(b.lon_min),
    lon_max: String(b.lon_max),
    lat_min: String(b.lat_min),
    lat_max: String(b.lat_max),
    max_floats: String(maxFloats),
  })
  return get(`/argo/floats?${p.toString()}`, { signal })
}

export function fetchArgoDetail(wmo, signal) {
  return get(`/argo/${encodeURIComponent(wmo)}`, { signal })
}

export function fetchArgoProfile(wmo, cycle, signal) {
  const suffix = Number.isFinite(cycle) ? `?cycle=${cycle}` : ''
  return get(`/argo/${encodeURIComponent(wmo)}/profile${suffix}`, { signal })
}
