/**
 * Lightweight Google Analytics 4 loader + event helper for the public landing page.
 *
 * The Measurement ID is read from the build-time env var VITE_GA_ID — never
 * hardcoded. If it's unset (e.g. local dev), initGA() is a no-op and trackEvent()
 * silently does nothing, so CTA handlers can call trackEvent() unconditionally.
 */
const GA_ID = import.meta.env.VITE_GA_ID

let loaded = false

export function initGA() {
  if (loaded || !GA_ID || typeof document === 'undefined') return
  loaded = true

  const s = document.createElement('script')
  s.async = true
  s.src = `https://www.googletagmanager.com/gtag/js?id=${GA_ID}`
  document.head.appendChild(s)

  window.dataLayer = window.dataLayer || []
  window.gtag = function gtag() { window.dataLayer.push(arguments) }
  window.gtag('js', new Date())
  window.gtag('config', GA_ID)
}

export function trackEvent(name, params) {
  try {
    if (typeof window !== 'undefined' && typeof window.gtag === 'function') {
      window.gtag('event', name, params || {})
    }
  } catch (_) { /* analytics must never break the UI */ }
}
