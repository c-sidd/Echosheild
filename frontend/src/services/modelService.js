import { get, post } from './api'

export function fetchDatasets(signal) {
  return get('/model/datasets', { signal })
}

export function fetchMetadata(id, signal) {
  return get(`/model/${encodeURIComponent(id)}/metadata`, { signal })
}

export function fetchVariables(id, signal) {
  return get(`/model/${encodeURIComponent(id)}/variables`, { signal })
}

export function fetchTimes(id, signal) {
  return get(`/model/${encodeURIComponent(id)}/times`, { signal })
}

export function fetchDepths(id, signal) {
  return get(`/model/${encodeURIComponent(id)}/depths`, { signal })
}

export function fetchExtent(id, signal) {
  return get(`/model/${encodeURIComponent(id)}/extent`, { signal })
}

export function fetchTimesList(id, signal) {
  return get(`/model/${encodeURIComponent(id)}/times/list`, { signal })
}

function bboxQuery(bbox) {
  if (!bbox) return ''
  const p = new URLSearchParams({
    west: String(bbox.west),
    east: String(bbox.east),
    south: String(bbox.south),
    north: String(bbox.north),
  })
  return `&${p.toString()}`
}

export function slicePath(id, variable, timeIndex, depth, bbox) {
  const p = new URLSearchParams({
    variable,
    time_index: String(timeIndex ?? 0),
  })
  if (Number.isFinite(depth)) p.set('depth', String(depth))
  return `/model/${encodeURIComponent(id)}/slice?${p.toString()}${bboxQuery(bbox)}`
}

export function fetchSlice(id, variable, timeIndex, depth, bbox, signal) {
  return get(slicePath(id, variable, timeIndex, depth, bbox), { signal })
}

export function fetchSliceBatch(id, slices, signal) {
  return post(
    `/model/${encodeURIComponent(id)}/slice/batch`,
    { slices },
    { signal }
  )
}

export function profilePath(id, variable, lat, lon, timeIndex) {
  const p = new URLSearchParams({
    variable,
    latitude: String(lat),
    longitude: String(lon),
  })
  if (timeIndex != null) p.set('time_index', String(timeIndex))
  return `/model/${encodeURIComponent(id)}/profile?${p.toString()}`
}

export function fetchProfile(id, variable, lat, lon, timeIndex, signal) {
  return get(profilePath(id, variable, lat, lon, timeIndex), { signal })
}

export function pointPath(id, variables, lat, lon, timeIndex, depth) {
  const p = new URLSearchParams({
    variables: Array.isArray(variables) ? variables.join(',') : variables,
    latitude: String(lat),
    longitude: String(lon),
  })
  if (timeIndex != null && Number.isFinite(timeIndex)) p.set('time_index', String(timeIndex))
  if (Number.isFinite(depth)) p.set('depth', String(depth))
  return `/model/${encodeURIComponent(id)}/point?${p.toString()}`
}

export function fetchPoint(id, variables, lat, lon, timeIndex, depth, signal) {
  return get(pointPath(id, variables, lat, lon, timeIndex, depth), { signal })
}

export function currentsPath(id, timeIndex, depth, bbox) {
  const p = new URLSearchParams({ time_index: String(timeIndex ?? 0) })
  if (Number.isFinite(depth)) p.set('depth', String(depth))
  return `/model/${encodeURIComponent(id)}/currents?${p.toString()}${bboxQuery(bbox)}`
}

export function fetchCurrents(id, timeIndex, depth, bbox, signal) {
  return get(currentsPath(id, timeIndex, depth, bbox), { signal })
}

export function fetchServices(id, signal) {
  return get(`/model/${encodeURIComponent(id)}/services`, { signal })
}
