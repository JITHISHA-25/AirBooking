const base = (import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000/api').replace(/\/$/, '')
const storageKey = 'airbooking-session'
let session = null

try {
  session = JSON.parse(sessionStorage.getItem(storageKey))
} catch {
  sessionStorage.removeItem(storageKey)
}

let refreshInProgress
const listeners = new Set()

export function subscribe(listener) {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

export function getSession() {
  return session
}

function saveSession(value) {
  session = value
  if (value) sessionStorage.setItem(storageKey, JSON.stringify(value))
  else sessionStorage.removeItem(storageKey)
  listeners.forEach(listener => listener())
}

function describeError(data) {
  if (typeof data?.detail === 'string') return data.detail
  if (data && typeof data === 'object') {
    return Object.entries(data).map(([field, value]) => {
      const message = Array.isArray(value) ? value.join(' ') : String(value)
      return field === 'non_field_errors' ? message : field.replaceAll('_', ' ') + ' · ' + message
    }).join(' ')
  }
  return 'The request failed. Try again.'
}

async function send(path, { method = 'GET', body, signal, token } = {}) {
  let response
  try {
    response = await fetch(base + path, {
      method,
      signal,
      headers: {
        Accept: 'application/json',
        ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
        ...(token ? { Authorization: 'Bearer ' + token } : {}),
      },
      body: body === undefined ? undefined : JSON.stringify(body),
    })
  } catch (error) {
    if (error.name === 'AbortError') throw error
    throw new Error('Could not reach AirBooking. Check that the API is running and try again.')
  }
  if (response.status === 204) return null
  const data = await response.json().catch(() => null)
  if (!response.ok) {
    const error = new Error(describeError(data))
    error.status = response.status
    throw error
  }
  return data
}

async function refreshSession(initial) {
  if (session !== initial) return session
  if (refreshInProgress?.initial === initial) return refreshInProgress.promise
  const request = {
    initial,
    promise: send('/auth/token/refresh/', { method: 'POST', body: { refresh: initial.refresh } })
      .then(tokens => {
        if (session === initial) saveSession({ ...initial, ...tokens })
        return { ...initial, ...tokens }
      })
      .catch(error => {
        if (session === initial && [400, 401, 403].includes(error.status)) saveSession(null)
        throw error
      })
      .finally(() => { if (refreshInProgress === request) refreshInProgress = null }),
  }
  refreshInProgress = request
  return request.promise
}

export async function api(path, options = {}) {
  const initial = session
  try {
    return await send(path, { ...options, token: initial?.access })
  } catch (error) {
    if (error.status !== 401 || !initial?.refresh) throw error
    if (session?.user.id !== initial.user.id) throw error
    await refreshSession(initial)
    if (session?.user.id !== initial.user.id) throw error
    return send(path, { ...options, token: session.access })
  }
}

export async function signIn(credentials) {
  const next = await send('/auth/login/', { method: 'POST', body: credentials })
  saveSession(next)
  return next.user
}

export function register(details) {
  return send('/auth/register/', { method: 'POST', body: details })
}

export async function signOut() {
  const pending = refreshInProgress?.promise
  const initial = session
  saveSession(null)
  if (!initial) return
  const rotated = await pending?.catch(() => null)
  await send('/auth/logout/', { method: 'POST', body: { refresh: rotated?.refresh || initial.refresh } }).catch(() => {})
}
