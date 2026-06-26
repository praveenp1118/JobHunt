import { useQuery } from '@tanstack/react-query'
import { getJobStats } from '../../api/jobs'
import { getFeedsWithCounts } from '../../api/feeds'
import { getDomainCVs } from '../../api/cvs'

const MARKET_LABELS = { NL: 'Netherlands', EU: 'EU', Dubai: 'Dubai', SG: 'Singapore', IN: 'India' }

// Shared grouped filter dropdown (Dashboard + Career Insights). `value` is the filter
// string (e.g. "source:rss" | "feed:{id}" | "domain:{id}" | "market:NL" | "").
export default function JobFilterSelect({ value, onChange }) {
  const { data: statsData } = useQuery({ queryKey: ['job-stats', ''], queryFn: () => getJobStats(), retry: false })
  const { data: feedsData } = useQuery({ queryKey: ['feeds-with-counts'], queryFn: getFeedsWithCounts, retry: false })
  const { data: dcvData } = useQuery({ queryKey: ['domain-cvs'], queryFn: getDomainCVs, retry: false })
  const stats = statsData?.data || {}
  const feeds = feedsData?.data || []
  const domainCVs = dcvData?.data || []

  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="text-sm border border-gray-200 rounded-lg px-2.5 py-1.5 bg-white text-gray-700 outline-none focus:border-emerald-400 max-w-[220px]"
    >
      <option value="">All jobs ({stats.unfiltered_total ?? 0})</option>
      <optgroup label="By Source">
        {[['rss', 'RSS feeds'], ['apify', 'LinkedIn / Apify'], ['gmail_alert', 'Gmail Alerts'], ['manual', 'Manual']].map(([k, lbl]) => (
          <option key={k} value={`source:${k}`}>{lbl} ({(stats.by_source || {})[k] || 0})</option>
        ))}
      </optgroup>
      {feeds.length > 0 && (
        <optgroup label="By Feed">
          {feeds.map((f) => <option key={f.feed_id} value={`feed:${f.feed_id}`}>{f.name.slice(0, 28)} ({f.job_count})</option>)}
        </optgroup>
      )}
      {domainCVs.length > 0 && (
        <optgroup label="By Domain CV">
          {domainCVs.map((cv) => (
            <option key={cv.id} value={`domain:${cv.id}`}>
              {(cv.industry_label || 'Domain')} × {(cv.country_code || '—')} ({(stats.by_best_domain || {})[String(cv.id)] || 0})
            </option>
          ))}
        </optgroup>
      )}
      <optgroup label="By Market">
        {Object.entries(stats.by_market || {}).map(([m, c]) => (
          <option key={m} value={`market:${m}`}>{MARKET_LABELS[m] || m} ({c})</option>
        ))}
      </optgroup>
    </select>
  )
}

// Parse a filter string into the API query params used by stats/career endpoints.
export function filterToParams(filter) {
  const [t, v] = (filter || '').split(':')
  if (t === 'source') return { source: v }
  if (t === 'feed') return { feed_id: v }
  if (t === 'domain') return { domain_cv_id: v }
  if (t === 'market') return { market: v }
  return {}
}
