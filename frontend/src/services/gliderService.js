import { get } from './api'

export function fetchGliderStatus(signal) {
  return get('/glider/status', { signal })
}
