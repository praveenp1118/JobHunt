import { clsx } from 'clsx'

// 10-step token colour scale — the single source of truth (shared with UsageTab).
export function tokenColor(n) {
  if (n == null) return '#9ca3af'
  if (n < 1000) return '#10b981'
  if (n < 2000) return '#34d399'
  if (n < 3000) return '#6ee7b7'
  if (n < 5000) return '#a3e635'
  if (n < 8000) return '#fbbf24'
  if (n < 12000) return '#f59e0b'
  if (n < 18000) return '#f97316'
  if (n < 25000) return '#ef4444'
  if (n < 40000) return '#dc2626'
  return '#991b1b'
}

// < 1000 → "842"; >= 1000 → "12.4K"
export function fmtTokens(n) {
  if (n == null) return '—'
  return n < 1000 ? String(n) : (n / 1000).toFixed(1) + 'K'
}

// Inline "⚡ 12.4K · ₹1.24" badge shown at the point of any Claude/Apify action.
// Renders null when tokens is null/undefined (graceful — never blocks the UI).
export default function TokenBadge({ tokens, cost_inr, size = 'sm', className = '' }) {
  if (tokens == null) return null
  const sz = size === 'md' ? 'text-sm px-2.5 py-1' : 'text-[11px] px-2 py-0.5'
  return (
    <span
      className={clsx('inline-flex items-center gap-1 rounded-full font-semibold text-white tabular-nums', sz, className)}
      style={{ backgroundColor: tokenColor(tokens) }}
      title={`${tokens.toLocaleString()} tokens${cost_inr != null ? ` · ₹${cost_inr.toFixed(2)}` : ''}`}
    >
      ⚡ {fmtTokens(tokens)}{cost_inr != null ? ` · ₹${Number(cost_inr).toFixed(2)}` : ''}
    </span>
  )
}
