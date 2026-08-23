const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

export function formatMonthYear(isoString) {
  if (!isoString) return '—'
  const d = new Date(isoString)
  if (Number.isNaN(d.getTime())) return isoString
  return `${MONTHS[d.getMonth()]} ${d.getFullYear()}`
}

export function formatDate(isoString) {
  if (!isoString) return '—'
  const d = new Date(isoString)
  if (Number.isNaN(d.getTime())) return isoString
  return `${MONTHS[d.getMonth()]} ${d.getDate()}, ${d.getFullYear()}`
}

export function formatLat(lat) {
  if (!Number.isFinite(lat)) return '—'
  return `${Math.abs(lat).toFixed(1)}°${lat >= 0 ? 'N' : 'S'}`
}

export function formatLon(lon) {
  if (!Number.isFinite(lon)) return '—'
  return `${Math.abs(lon).toFixed(1)}°${lon >= 0 ? 'E' : 'W'}`
}

export function formatValue(value, digits = 2) {
  if (value == null || !Number.isFinite(value)) return '—'
  return value.toFixed(digits)
}

export function formatDepth(depth) {
  if (!Number.isFinite(depth)) return '—'
  return depth >= 1000 ? `${(depth / 1000).toFixed(depth % 1000 === 0 ? 0 : 1)}km` : `${depth}m`
}

export function unitLabel(units) {
  if (!units) return ''
  const map = { degs: '°C', 'deg C': '°C', PSU: 'PSU', 'm s-1': 'm/s', '1e-3': '' }
  return map[units] ?? units
}

export function canonicalLabel(canonicalName) {
  if (!canonicalName) return 'Variable'
  return canonicalName.charAt(0).toUpperCase() + canonicalName.slice(1).replace(/_/g, ' ')
}

export const CANONICAL_RANGES = {
  temperature: { min: 5, max: 32 },
  salinity: { min: 32, max: 38 },
  chlorophyll: { min: 0, max: 2 },
}
