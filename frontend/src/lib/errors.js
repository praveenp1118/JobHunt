/**
 * Turn an axios/JS error into a human-readable STRING.
 *
 * FastAPI returns the message under `response.data.detail`, which may be:
 *   - a string                                    → use it
 *   - an object {code, message, ...} (our 4xx gates: 402 entitlement, 429
 *     rate-limit, 400 invite errors)              → use .message
 *   - an array of {loc, msg, ...} (422 validation) → use the first .msg
 * Rendering those objects/arrays directly shows "[object Object]" (or crashes a
 * React text node), so always route error text through this.
 *
 * The axios response interceptor (api/client.js) uses this to flatten
 * `response.data.detail` to a string on every rejected request, so existing
 * `err.response?.data?.detail || 'fallback'` call sites render correctly. It is
 * also exported for direct use.
 */
export function errMsg(err, fallback = 'Something went wrong') {
  const res = err?.response
  const detail = res?.data?.detail

  if (typeof detail === 'string' && detail.trim()) return detail
  if (Array.isArray(detail) && detail[0]?.msg) return String(detail[0].msg)
  if (detail && typeof detail === 'object' &&
      typeof detail.message === 'string' && detail.message.trim()) {
    return detail.message
  }
  if (res?.status === 429) return 'Rate limit reached — please wait a moment and try again.'

  const dataMsg = res?.data?.message
  if (typeof dataMsg === 'string' && dataMsg.trim()) return dataMsg
  if (typeof err?.message === 'string' && err.message.trim()) return err.message
  return fallback
}
