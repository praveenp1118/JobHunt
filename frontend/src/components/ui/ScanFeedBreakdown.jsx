// Per-feed scan breakdown — shared by Activity (System tab) and Feeds (Scan History).
const REJECT_LABEL = {
  below_threshold: 'below threshold',
  duplicate: 'duplicate',
  'pre_filter_fail: not_a_product_role': 'pre-filter: not a product role',
  'pre_filter_fail: seniority_too_low': 'pre-filter: seniority too low',
  'pre_filter_fail: too_short': 'pre-filter: JD too short',
  'pre_filter_fail: rejected': 'pre-filter fail',
}

export default function ScanFeedBreakdown({ f }) {
  const rejected = f.rejected || []
  return (
    <div className="text-xs">
      <p className="font-medium text-gray-800">
        {f.feed_name} <span className="text-gray-300 uppercase">({f.feed_type})</span>
      </p>
      {f.note ? (
        <p className="text-gray-400 mt-0.5">{f.note}</p>
      ) : (
        <p className="text-gray-500 mt-0.5">
          {f.raw_results} raw → {f.pre_filter_passed} pre-filter pass
          {f.above_threshold != null ? ` → ${f.above_threshold} above S1` : ''} → <span className="text-emerald-600 font-medium">{f.saved} saved</span>
          {f.duplicates ? <span className="text-gray-400"> · {f.duplicates} dup</span> : ''}
        </p>
      )}
      {rejected.length > 0 && (
        <div className="mt-1 pl-2 border-l-2 border-gray-100 space-y-0.5">
          {rejected.map((r, j) => (
            <p key={j} className="text-gray-400 truncate">
              ✗ {r.title || '(untitled)'}{r.company ? ` · ${r.company}` : ''}
              {r.reason === 'below_threshold' && r.s1 != null ? ` · S1: ${r.s1} (below)` : ''}
              {r.reason !== 'below_threshold' ? ` · ${REJECT_LABEL[r.reason] || r.reason}` : ''}
            </p>
          ))}
        </div>
      )}
    </div>
  )
}
