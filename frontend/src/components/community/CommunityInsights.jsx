import { useQuery } from '@tanstack/react-query'
import { getCommunityInsights } from '../../api/community'

// Shared anonymised insights for a job's company+role. Renders nothing unless
// >= 2 members have contributed (privacy). `compact` = the slim Tailor-panel variant.
export default function CommunityInsights({ company, role, market, jdHash, compact = false }) {
  const { data } = useQuery({
    queryKey: ['community', company, role, market, jdHash],
    queryFn: () => getCommunityInsights(company, role, market, jdHash),
    enabled: !!(company && role),
    retry: false,
  })
  const d = data?.data
  if (!d?.available) return null

  const keywords = (d.keyword_patterns || []).slice(0, compact ? 3 : 5)

  if (compact) {
    return (
      <div className="rounded-xl border border-indigo-100 bg-indigo-50/60 p-3">
        <p className="text-xs font-semibold text-indigo-800 mb-1">
          💡 {d.contributor_count} member{d.contributor_count === 1 ? '' : 's'} targeted this role
        </p>
        <p className="text-[11px] text-gray-600">
          Avg fit: <strong className="tabular-nums">{d.avg_s1d ?? d.avg_s1 ?? '—'}</strong>
          {d.best_domain_cv_label ? ` · Top domain CV: ${d.best_domain_cv_label}` : ''}
        </p>
        {keywords.length > 0 && (
          <p className="text-[11px] text-gray-500 mt-1">
            Top keywords: {keywords.map((k) => `"${k.keyword}"`).join(', ')}
          </p>
        )}
        <p className="text-[11px] text-emerald-600 mt-1.5">⚡ 0 tokens spent — decide before you tailor</p>
      </div>
    )
  }

  return (
    <div className="rounded-2xl border border-indigo-100 bg-indigo-50/50 p-4 space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-sm font-semibold text-indigo-900">💡 Community Insights</p>
        <span className="text-xs text-indigo-500">👥 {d.contributor_count} members contributed</span>
      </div>

      <div className="grid grid-cols-2 gap-3 text-xs">
        <div>
          <p className="text-gray-400 uppercase tracking-wide text-[10px]">Avg fit score</p>
          <p className="text-gray-800 font-semibold tabular-nums">{d.avg_s1d ?? d.avg_s1 ?? '—'}</p>
        </div>
        {d.best_domain_cv_label && (
          <div>
            <p className="text-gray-400 uppercase tracking-wide text-[10px]">Top domain CV</p>
            <p className="text-gray-800 font-medium truncate">{d.best_domain_cv_label}</p>
          </div>
        )}
      </div>

      {(d.jd_highlights || []).length > 0 && (
        <div>
          <p className="text-[11px] font-medium text-gray-500 mb-1">Key JD highlights</p>
          <ul className="space-y-0.5">
            {d.jd_highlights.slice(0, 5).map((h, i) => (
              <li key={i} className="text-xs text-gray-700">
                ✓ {h.text} <span className="text-gray-400">({h.votes} member{h.votes === 1 ? '' : 's'})</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {keywords.length > 0 && (
        <div>
          <p className="text-[11px] font-medium text-gray-500 mb-1">Top keyword patterns</p>
          <ul className="space-y-0.5">
            {keywords.map((k, i) => (
              <li key={i} className="text-xs text-gray-700">
                → "{k.keyword}" <span className="text-gray-400">({k.injection_count}×, {Math.round((k.approval_rate || 0) * 100)}% approved)</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {(d.tailoring_patterns || []).length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {d.tailoring_patterns.map((t, i) => (
            <span key={i} className="text-[10px] bg-white border border-indigo-100 rounded-full px-2 py-0.5 text-gray-600">
              {t.change_type.replace('_', ' ')}: {t.approval_count}/{t.total_count}
            </span>
          ))}
        </div>
      )}

      <p className="text-[11px] text-emerald-600 font-medium border-t border-indigo-100 pt-2">
        ⚡ Used community data — 0 tokens spent
      </p>
    </div>
  )
}
