import { useOceanStore } from '@/store/oceanStore'

const BASE = import.meta.env.VITE_API_BASE_URL ?? '/api/v1'

export class ApiError extends Error {
  constructor(status, message, detail) {
    super(message ?? `API error ${status}`)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
    this.permanent = status === 404 || status === 422
    this.retryable = status === 503
  }
}

async function request(path, options = {}) {
  const { signal, noStore = false, ...rest } = options
  let res
  try {
    res = await fetch(`${BASE}${path}`, {
      ...rest,
      signal,
      headers: {
        Accept: 'application/json',
        ...(noStore ? { 'Cache-Control': 'no-store' } : {}),
        ...rest.headers,
      },
    })
  } catch (err) {
    if (err?.name === 'AbortError') throw err
    throw new ApiError(0, 'Network error — backend unreachable', String(err))
  }

  const body = await res.json().catch(() => null)

  if (!res.ok) {
    if (res.status === 503) {
      const store = useOceanStore.getState()
      store.setUpstream503(true, body?.detail ?? 'Data source temporarily unavailable')
    }
    throw new ApiError(res.status, body?.detail ?? body?.message, body)
  }
  return body
}

export function get(path, options = {}) {
  return request(path, { method: 'GET', ...options })
}
