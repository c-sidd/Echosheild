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
  let res
  try {
    res = await fetch(`${BASE}${path}`, options)
  } catch (err) {
    throw new ApiError(0, 'Network error — backend unreachable', String(err))
  }

  const body = await res.json().catch(() => null)

  if (!res.ok) {
    throw new ApiError(res.status, body?.detail ?? body?.message, body)
  }
  return body
}

export const api = {
  get: (path) => request(path),
}
