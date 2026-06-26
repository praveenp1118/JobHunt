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

export default function FeedPerformance({ onSelectFeed }) {
  const navigate = useNavigate()
  const { data, isLoading } = useQuery({ queryKey: ['feed-performance'], queryFn: getFeedPerformance, refetchInterval: 60000 })
  const rows = data?.data || []
  if (isLoading || rows.length === 0) return null

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5 mb-4">
      <div className="mb-3">
        <h3 className="text-sm font-semibold text-gray-900">Feed Performance</h3>
        <p className="text-xs text-gray-500">Which feeds are finding the best jobs?</p>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-xs text-gray-400 border-b border-gray-100">
              <th className="text-left font-medium px-2 py-1.5">Feed</th>
              <th className="text-left font-medium px-2 py-1.5">Type</th>
              <th className="text-right font-medium px-2 py-1.5">Jobs</th>
              <th className="text-right font-medium px-2 py-1.5">Avg Fit</th>
              <th className="text-right font-medium px-2 py-1.5">Applied</th>
              <th className="text-left font-medium px-2 py-1.5 w-28">Quality</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => {
              const badge = TYPE_BADGE[r.feed_type] || { label: r.feed_type, cls: 'bg-gray-100 text-gray-500' }
              const clickable = !!r.feed_id
              return (
                <tr key={r.feed_id || `alert-${i}`}
                  onClick={() => clickable && onSelectFeed?.(r.feed_id)}
                  className={`border-b border-gray-50 ${clickable ? 'cursor-pointer hover:bg-gray-50' : ''}`}>
                  <td className="px-2 py-2 text-gray-800 font-medium truncate max-w-[180px]" title={r.feed_name}>{r.feed_name.length > 20 ? r.feed_name.slice(0, 20) + '…' : r.feed_name}</td>
                  <td className="px-2 py-2"><span className={`text-[10px] font-medium px-1.5 py-0.5 rounded-full ${badge.cls}`}>{badge.label}</span></td>
                  <td className="px-2 py-2 text-right tabular-nums text-gray-700">{r.job_count}</td>
                  <td className="px-2 py-2 text-right tabular-nums text-gray-700">{r.avg_s1d ?? '—'}</td>
                  <td className="px-2 py-2 text-right tabular-nums text-gray-700">{r.applied_count}</td>
                  <td className="px-2 py-2">
                    <div className="h-2 bg-gray-100 rounded-full overflow-hidden w-24">
                      <div className="h-full rounded-full" style={{ width: `${r.avg_s1d || 0}%`, backgroundColor: qualityColor(r.avg_s1d) }} />
                    </div>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      <p className="text-[11px] text-gray-400 mt-3">
        Click a feed to filter the dashboard · <button onClick={() => navigate('/settings#feeds')} className="text-emerald-600 hover:underline">Manage feeds in Settings →</button>
      </p>
    </div>
  )
}
