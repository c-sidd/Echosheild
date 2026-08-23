import { get } from './api'

export function fetchGliderStatus(signal) {
  return get('/glider/status', { signal })
}

export function fetchGliderMissions(signal) {
  return get('/glider/missions', { signal })
}

export function fetchGliderProfiles(missionId, signal) {
  return get(`/glider/missions/${encodeURIComponent(missionId)}/profiles`, { signal })
}
