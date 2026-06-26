import { useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { getFeedPerformance } from '../../api/feeds'

const TYPE_BADGE = {
  rss: { label: 'RSS', cls: 'bg-blue-50 text-blue-600' },
  apify: { label: 'Apify', cls: 'bg-purple-50 text-purple-600' },
  gmail_alert: { label: 'Alert', cls: 'bg-amber-50 text-amber-600' },
}

function qualityColor(fit) {
  if (fit == null) return '#d1d5db'
  if (fit < 60) return '#ef4444'
  if (fit < 75) return '#f59e0b'
  if (fit < 85) return '#84cc16'
  return '#10b981'
}

// key → [label, alignRight, accessor]
const COLUMNS = [
  ['feed_name', 'Feed', false, (r) => r.feed_name],
  ['feed_type', 'Type', false, (r) => r.feed_type],
  ['job_count', 'Jobs found', true, (r) => r.job_count],
  ['avg_s1', 'Avg S1', true, (r) => r.avg_s1],
  ['avg_s1d', 'Avg Best Fit', true, (r) => r.avg_s1d],
  ['above_threshold_count', 'Above threshold', true, (r) => r.above_threshold_count],
  ['applied_count', 'Applied', true, (r) => r.applied_count],
  ['quality_score', 'Quality', false, (r) => r.quality_score],
]

export default function FeedPerformance({ onSelectFeed }) {
  const navigate = useNavigate()
  const { data, isLoading } = useQuery({ queryKey: ['feed-performance'], queryFn: getFeedPerformance, refetchInterval: 60000 })
  const rows = data?.data || []
  const [sortKey, setSortKey] = useState('quality_score')
  const [sortDir, setSortDir] = useState('desc')  // default: quality descending

  const accessor = useMemo(() => Object.fromEntries(COLUMNS.map(([k, , , a]) => [k, a])), [])
  const sorted = useMemo(() => {
    const get = accessor[sortKey]
    const arr = [...rows]
    arr.sort((a, b) => {
      const va = get(a), vb = get(b)
      // Nulls always sink to the bottom regardless of direction.
      if (va == null && vb == null) return 0
      if (va == null) return 1
      if (vb == null) return -1
      const cmp = typeof va === 'string' ? va.localeCompare(vb) : va - vb
      return sortDir === 'asc' ? cmp : -cmp
    })
    return arr
  }, [rows, sortKey, sortDir, accessor])

  const toggleSort = (key) => {
    if (sortKey !== key) { setSortKey(key); setSortDir(key === 'feed_name' || key === 'feed_type' ? 'asc' : 'desc') }
    else setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
  }

  if (isLoading) return null
  if (rows.length === 0) return (
    <div className="bg-white rounded-xl border border-gray-200 p-8 text-center text-sm text-gray-400">
      No feed activity yet — run a scan to see which feeds find the best jobs.
    </div>
  )

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5">
      <div className="mb-4">
        <h3 className="text-sm font-semibold text-gray-900">Which feeds are finding the best jobs?</h3>
        <p className="text-xs text-gray-500 mt-0.5">Click any row to filter the dashboard to that feed.</p>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-xs text-gray-400 border-b border-gray-100">
              {COLUMNS.map(([key, label, alignRight]) => (
                <th key={key}
                  onClick={() => toggleSort(key)}
                  className={`font-medium px-3 py-2 cursor-pointer select-none hover:text-gray-600 ${alignRight ? 'text-right' : 'text-left'}`}>
                  {label}
                  <span className="ml-1 text-emerald-500">{sortKey === key ? (sortDir === 'asc' ? '▲' : '▼') : ''}</span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sorted.map((r, i) => {
              const badge = TYPE_BADGE[r.feed_type] || { label: r.feed_type, cls: 'bg-gray-100 text-gray-500' }
              const clickable = !!r.feed_id
              return (
                <tr key={r.feed_id || `alert-${i}`}
                  onClick={() => clickable && onSelectFeed?.(r.feed_id)}
                  className={`border-b border-gray-50 ${clickable ? 'cursor-pointer hover:bg-gray-50' : ''}`}>
                  <td className="px-3 py-2.5 text-gray-800 font-medium" title={r.feed_name}>{r.feed_name}</td>
                  <td className="px-3 py-2.5"><span className={`text-[10px] font-medium px-1.5 py-0.5 rounded-full ${badge.cls}`}>{badge.label}</span></td>
                  <td className="px-3 py-2.5 text-right tabular-nums text-gray-700">{r.job_count}</td>
                  <td className="px-3 py-2.5 text-right tabular-nums text-gray-700">{r.avg_s1 ?? '—'}</td>
                  <td className="px-3 py-2.5 text-right tabular-nums text-gray-700">{r.avg_s1d ?? '—'}</td>
                  <td className="px-3 py-2.5 text-right tabular-nums text-gray-700">{r.above_threshold_count}</td>
                  <td className="px-3 py-2.5 text-right tabular-nums text-gray-700">{r.applied_count}</td>
                  <td className="px-3 py-2.5">
                    <div className="flex items-center gap-2">
                      <div className="h-2 bg-gray-100 rounded-full overflow-hidden w-24 shrink-0">
                        <div className="h-full rounded-full" style={{ width: `${(r.quality_score ?? 0) * 100}%`, backgroundColor: qualityColor(r.avg_s1d) }} />
                      </div>
                      <span className="text-[11px] tabular-nums text-gray-400 w-8">{r.quality_score != null ? Math.round(r.quality_score * 100) : '—'}</span>
                    </div>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      <p className="text-[11px] text-gray-400 mt-3">
        Quality = 60% avg best-fit + 40% applied rate · <button onClick={() => navigate('/settings#feeds')} className="text-emerald-600 hover:underline">Manage feeds in Settings →</button>
      </p>
    </div>
  )
}
