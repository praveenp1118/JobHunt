import axios from 'axios'
import { errMsg } from '../lib/errors'

const client = axios.create({
  baseURL: '/api',
  headers: { 'Content-Type': 'application/json' },
})

// Attach token to every request
client.interceptors.request.use((config) => {
  // Import here to avoid circular dependency
  const raw = localStorage.getItem('jobhunt-auth')
  if (raw) {
    try {
      const { state } = JSON.parse(raw)
      if (state?.token) {
        config.headers.Authorization = `Bearer ${state.token}`
      }
    } catch (_) {}
  }
  return config
})

// Handle 401 globally
client.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem('jobhunt-auth')
      window.location.href = '/login'
    }
    // Normalize FastAPI's error body so every catch site renders a STRING, never
    // "[object Object]". `detail` can be a dict {code, message} (our 4xx gates) or
    // a 422 validation array; flatten it to a string (raw kept under detailRaw).
    // No code branches on detail's object shape, so this is safe. `userMessage` is
    // always a clean string for convenience.
    const msg = errMsg(err)
    const data = err.response?.data
    if (data && typeof data === 'object' && data.detail !== undefined &&
        typeof data.detail !== 'string') {
      data.detailRaw = data.detail
      data.detail = msg
    }
    err.userMessage = msg
    return Promise.reject(err)
  }
)

export default client
