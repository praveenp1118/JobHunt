// Hover breakdown for a DualRingPill. Positioned ABSOLUTE (not fixed) within the
// pill's relative wrapper, so it scrolls with the row.
function Bar({ score, color }) {
  return (
    <div className="flex-1 h-1.5 rounded-full bg-slate-200 overflow-hidden">
      <div className="h-full rounded-full" style={{ width: `${Math.max(0, Math.min(100, score || 0))}%`, background: color }} />
    </div>
  )
}

export default function ScoreTooltip({
  company, role, ats = null, pursuit = null,
  topGap, recommendation, atsPass, pursuitFit,
}) {
  return (
    <div className="absolute z-50 left-1/2 -translate-x-1/2 top-full mt-2 w-[260px] rounded-xl border border-slate-300 bg-white shadow-xl p-3 text-left"
      style={{ fontSize: 12 }}>
      {(company || role) && (
        <div className="font-semibold text-slate-900 truncate mb-2">
          {company}{company && role ? ' — ' : ''}<span className="font-normal text-slate-600">{role}</span>
        </div>
      )}
      <div className="space-y-1.5">
        <div className="flex items-center gap-2">
          <span className="w-14 text-slate-500">ATS</span>
          <Bar score={ats} color="#34d399" />
          <span className="w-6 text-right tabular-nums font-medium text-slate-700">{ats == null ? '—' : Math.round(ats)}</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="w-14 text-slate-500">Pursuit</span>
          <Bar score={pursuit} color="#10b981" />
          <span className="w-6 text-right tabular-nums font-medium text-slate-700">{pursuit == null ? '—' : Math.round(pursuit)}</span>
        </div>
      </div>
      <div className="border-t border-slate-100 my-2" />
      <div className="space-y-0.5 text-[11px]">
        <div className="text-emerald-600">{atsPass ?? (ats != null && ats >= 70 ? '✓ Will pass automated screening' : '✗ May not pass screening')}</div>
        <div className="text-emerald-600">{pursuitFit ?? (pursuit != null && pursuit >= 75 ? '✓ Strong human fit' : '○ Moderate human fit')}</div>
        {topGap && <div className="text-rose-500">✗ {topGap}</div>}
      </div>
      {recommendation && (
        <div className="mt-2 text-[11px] text-slate-700"><span className="text-slate-400">Recommendation:</span> <span className="font-medium">{recommendation}</span></div>
      )}
    </div>
  )
}
