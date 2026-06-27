import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useState } from 'react'
import { format } from 'date-fns'
import { getCareerAnalysis, triggerAnalysis, getReadinessScores } from '../../api/career'
import { filterToParams } from './JobFilterSelect'
import { toast } from '../../store/toast'

const MINI = [['keywords', 'Keywords'], ['skills', 'Skills'], ['experience', 'Experience'], ['certifications', 'Certs']]

function color(v) {
  if (v == null) return '#d1d5db'
  if (v >= 80) return '#10b981'
  if (v >= 65) return '#f59e0b'
  return '#ef4444'
}

export default function CareerWidget() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [sp] = useSearchParams()
  const filter = sp.get('filter') || ''
  const params = filterToParams(filter)
  const [refreshing, setRefreshing] = useState(false)
  const { data, isLoading } = useQuery({ queryKey: ['career', filter], queryFn: () => getCareerAnalysis(params), retry: false })
  const d = data?.data

  // When a dashboard filter is active, also pull the "all jobs" analysis for the "(vs overall)" comparison.
  const { data: overallData } = useQuery({ queryKey: ['career', ''], queryFn: () => getCareerAnalysis(), retry: false, enabled: !!filter })
  const overall = overallData?.data
  const overallReadiness = filter && overall?.available ? Math.round(overall.readiness_score) : null

  // Real aggregated readiness — preferred over the Claude estimate when jobs are scored.
  const { data: readinessData } = useQuery({ queryKey: ['career-readiness', filter], queryFn: () => getReadinessScores(params), retry: false })
  const real = readinessData?.data
  const hasReal = real && !real.no_data && real.jobs_scored > 0
  const realBars = hasReal ? [
    { label: 'Keywords', src: 'ATS', score: real.ats.components.keyword_density?.score },
    { label: 'Skills', src: 'ATS', score: real.ats.components.required_skills?.score },
    { label: 'Career fit', src: 'Pursuit', score: real.pursuit.components.career_move_quality?.score },
    { label: 'Achievability', src: 'Pursuit', score: real.pursuit.components.achievability?.score },
  ] : []

  const refresh = async () => {
    setRefreshing(true)
    try {
      const res = await triggerAnalysis(params)
      qc.setQueryData(['career', filter], res)
      toast.success('Career analysis refreshed')
    } catch (e) { toast.error(e.response?.data?.detail || 'Analysis failed') }
    finally { setRefreshing(false) }
  }

  if (isLoading) return null

  if (!d?.available && !hasReal) {
    return (
      <div className="bg-gradient-to-br from-indigo-50 to-emerald-50 rounded-xl p-5 border border-indigo-100 mb-4">
        <p className="text-sm font-medium text-gray-800">✨ Get your career readiness score</p>
        <p className="text-xs text-gray-500 mt-1 mb-3">One analysis across all your tracked JDs.</p>
        <button onClick={() => navigate(`/career${filter ? '?filter=' + encodeURIComponent(filter) : ''}`)} className="text-sm font-medium text-indigo-600 hover:underline">Analyse now →</button>
      </div>
    )
  }

  const scores = d?.scores || {}
  const top = d?.analysis?.top_action
  return (
    <div className="bg-white rounded-xl p-5 border border-gray-200 mb-4">
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Career readiness ✨</span>
        <button onClick={() => navigate(`/career${filter ? '?filter=' + encodeURIComponent(filter) : ''}`)} className="text-xs text-emerald-600 hover:underline font-medium">Full report →</button>
      </div>
      {filter && (real?.filter_label || d?.filter_label) && (
        <p className="text-xs text-indigo-600 font-medium mb-1">
          {real?.filter_label || d?.filter_label}: {hasReal ? real.overall : Math.round(d?.readiness_score || 0)}%
          {overallReadiness != null && !hasReal && <span className="text-gray-400 font-normal"> (vs {overallReadiness}% overall)</span>}
        </p>
      )}
      <div className="flex items-end gap-3 mb-3">
        <p className="text-3xl font-bold text-gray-900 leading-none">{hasReal ? real.overall : Math.round(d.readiness_score)}<span className="text-base text-gray-400">%</span></p>
        <div className="flex-1 h-2.5 bg-gray-100 rounded-full overflow-hidden mb-1.5">
          <div className="h-full bg-emerald-500 rounded-full" style={{ width: `${hasReal ? real.overall : d.readiness_score}%` }} />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 mb-3">
        {hasReal ? realBars.map((b) => (
          <div key={b.label} className="flex items-center gap-2">
            <span className="text-[11px] text-gray-500 w-24 truncate">{b.label} <span className="text-gray-300">({b.src})</span></span>
            <div className="flex-1 h-1.5 bg-gray-100 rounded-full overflow-hidden">
              <div className="h-full rounded-full" style={{ width: `${b.score || 0}%`, backgroundColor: color(b.score) }} />
            </div>
            <span className="text-[10px] text-gray-400 tabular-nums w-7 text-right">{b.score ?? '—'}%</span>
          </div>
        )) : MINI.map(([k, label]) => (
          <div key={k} className="flex items-center gap-2">
            <span className="text-[11px] text-gray-500 w-16">{label}</span>
            <div className="flex-1 h-1.5 bg-gray-100 rounded-full overflow-hidden">
              <div className="h-full rounded-full" style={{ width: `${scores[k] || 0}%`, backgroundColor: color(scores[k]) }} />
            </div>
            <span className="text-[10px] text-gray-400 tabular-nums w-7 text-right">{scores[k] ?? '—'}%</span>
          </div>
        ))}
      </div>

      {top && (
        <div className="bg-amber-50 rounded-lg px-3 py-2 mb-3">
          <p className="text-xs text-amber-800">💡 {top.title}{top.impact_pct != null ? ` · +${top.impact_pct}%` : ''}</p>
        </div>
      )}

      <div className="flex items-center justify-between text-[11px] text-gray-400">
        <span>
          {d.last_analysed_at ? `Last updated: ${format(new Date(d.last_analysed_at), 'MMM d')}` : ''}
          {d.last_cost_inr != null ? ` · ⚡ ₹${d.last_cost_inr}` : ''}
        </span>
        <button onClick={refresh} disabled={refreshing} className="text-emerald-600 hover:underline font-medium disabled:opacity-50">
          {refreshing ? 'Refreshing…' : 'Refresh'}
        </button>
      </div>
    </div>
  )
}
