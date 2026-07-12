import { useState, useEffect } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate, useSearchParams } from 'react-router-dom'
import JobFilterSelect, { filterToParams } from '../../components/dashboard/JobFilterSelect'
import { format } from 'date-fns'
import {
  getCareerAnalysis, triggerAnalysis, saveAnswer, getAnswers,
  updateRoadmapItem, getCommunityCareer, shareInsights, getReadinessScores,
} from '../../api/career'
import { getJobStats } from '../../api/jobs'
import ScoreToggle from '../../components/ui/ScoreToggle'
import { RadarChart, Radar, PolarGrid, PolarAngleAxis, ResponsiveContainer, Tooltip } from 'recharts'
import TokenBadge from '../../components/ui/TokenBadge'
import Button from '../../components/ui/Button'
import Spinner from '../../components/ui/Spinner'
import { toast } from '../../store/toast'

const TABS = ['Readiness', 'Keywords', 'Skills', 'Experience', 'Certifications', 'Build', 'Roadmap']

const QUESTIONS = [
  { key: 'manages_team', q: 'Do you currently manage a team?', options: ['Yes, currently', 'I have managed teams in the past', 'No'] },
  { key: 'public_work', q: 'Do you have public work or a portfolio (GitHub, publications, case studies, a deck)?', options: ['Yes, substantial', 'Some', 'No'] },
  { key: 'industry_focus', q: 'What is your primary industry focus?', options: ['Same as my target roles', 'An adjacent industry', 'Changing industries'] },
  { key: 'relocation', q: 'Are you open to relocating for the right role?', options: ['Yes, immediately', 'Yes, in 3-6 months', 'Remote only', 'Already in my target market'] },
  { key: 'willing_to_do', q: 'What are you willing to do in the next 3 months?', options: ['Get a certification', 'Build a public project', 'Write publicly (LinkedIn/blog)', 'Update CV only', 'All of the above'] },
]
const SCORE_LABELS = [['keywords', 'Keywords'], ['skills', 'Skills'], ['experience', 'Experience'], ['certifications', 'Certifications'], ['projects', 'Projects']]

function barColor(v) {
  if (v == null) return '#d1d5db'
  if (v >= 80) return '#10b981'
  if (v >= 65) return '#f59e0b'
  return '#ef4444'
}

export default function CareerPage() {
  const qc = useQueryClient()
  const navigate = useNavigate()
  const [sp, setSp] = useSearchParams()
  const [tab, setTab] = useState('Readiness')
  const [analysing, setAnalysing] = useState(false)
  const [lastUsage, setLastUsage] = useState(null)
  const [showQuestions, setShowQuestions] = useState(false)

  const filter = sp.get('filter') || ''
  const params = filterToParams(filter)
  const setFilter = (v) => {
    const next = new URLSearchParams(sp)
    if (v) next.set('filter', v); else next.delete('filter')
    setSp(next, { replace: true })
  }

  const { data, isLoading } = useQuery({ queryKey: ['career', filter], queryFn: () => getCareerAnalysis(params), retry: false })
  const { data: statsData } = useQuery({ queryKey: ['career-stats', filter], queryFn: () => getJobStats(params) })
  const stats = statsData?.data || {}
  // Real aggregated ATS + Pursuit readiness (instant, free, filter-aware).
  const { data: readinessData } = useQuery({ queryKey: ['career-readiness', filter], queryFn: () => getReadinessScores(params) })
  const readiness = readinessData?.data
  const hasReal = readiness && !readiness.no_data && readiness.jobs_scored > 0
  const d = data?.data
  const available = d?.available
  const a = d?.analysis || {}

  // First visit (the "all" view) with no analysis → offer the questions intro.
  useEffect(() => {
    if (!isLoading && d && !available && !filter) setShowQuestions(true)
  }, [isLoading, d, available, filter])

  const runAnalysis = async () => {
    setAnalysing(true)
    setShowQuestions(false)
    try {
      const res = await triggerAnalysis(params)
      setLastUsage(res.data.tokens_used ? { tokens: res.data.tokens_used, cost_inr: res.data.cost_inr } : null)
      qc.setQueryData(['career', filter], res)
      qc.invalidateQueries({ queryKey: ['career'] })
      toast.success('Career analysis complete')
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Analysis failed — check your Anthropic key + that you have a master CV')
    } finally { setAnalysing(false) }
  }

  if (isLoading) return <div className="p-6 flex justify-center"><Spinner /></div>

  return (
    <div className="p-6 max-w-5xl mx-auto">
      <div className="flex items-center justify-between mb-5">
        <div>
          <h1 className="text-xl font-semibold text-gray-900">Career Insights ✨</h1>
          <p className="text-sm text-gray-500 mt-0.5">
            Gap analysis across your tracked JDs{available && d.jd_count ? ` · ${d.jd_count} JDs` : ''}
          </p>
        </div>
        <div className="flex items-center gap-3">
          {lastUsage && <TokenBadge tokens={lastUsage.tokens} cost_inr={lastUsage.cost_inr} />}
          <JobFilterSelect value={filter} onChange={setFilter} />
          <Button size="sm" loading={analysing} onClick={runAnalysis}>{available ? 'Re-analyse' : 'Analyse now'}</Button>
        </div>
      </div>

      {/* Filter context banner — real readiness when available, else the Claude-analysis context */}
      {hasReal ? (
        <div className="bg-emerald-50 border border-emerald-100 rounded-lg px-3 py-2 mb-4 text-xs text-emerald-700 flex items-center justify-between gap-2">
          <span>
            Readiness from <strong>{readiness.jobs_scored}</strong> real scores · ATS avg: <strong>{readiness.avg_ats}</strong> ·
            Pursuit avg: <strong>{readiness.avg_pursuit}</strong> · <strong>{readiness.filter_label || 'All jobs'}</strong>
          </span>
          {filter && <button onClick={() => setFilter('')} className="text-emerald-600 hover:underline shrink-0">Clear ✕</button>}
        </div>
      ) : available && (
        <div className="bg-indigo-50 border border-indigo-100 rounded-lg px-3 py-2 mb-4 text-xs text-indigo-700 flex items-center justify-between gap-2">
          <span>
            Analysis based on <strong>{d.jd_count}</strong> jobs · <strong>{d.filter_label || 'All jobs'}</strong>
            {d.last_analysed_at ? ` · Last updated ${format(new Date(d.last_analysed_at), 'MMM d')}` : ''}
          </span>
          {filter && <button onClick={() => setFilter('')} className="text-indigo-500 hover:underline shrink-0">Clear ✕</button>}
        </div>
      )}

      {analysing && (
        <div className="bg-indigo-50 border border-indigo-100 rounded-xl p-4 mb-4 text-sm text-indigo-700">
          ⏳ Running one batch analysis across your JDs… (~30–60s)
        </div>
      )}

      {!available ? (
        <div className="bg-white rounded-2xl border border-gray-200 p-10 text-center">
          <p className="text-2xl mb-2">✨</p>
          <p className="text-sm font-medium text-gray-800">Get your career readiness score</p>
          <p className="text-xs text-gray-500 mt-1 mb-5">One analysis across all your tracked job descriptions. Cached for 7 days.</p>
          <Button loading={analysing} onClick={runAnalysis}>Analyse now →</Button>
        </div>
      ) : (
        <>
          <div className="flex gap-0 border-b border-gray-200 mb-5 overflow-x-auto">
            {TABS.map((t) => (
              <button key={t} onClick={() => setTab(t)}
                className={`px-4 py-2.5 text-sm font-medium border-b-2 whitespace-nowrap transition-colors ${tab === t ? 'border-emerald-500 text-emerald-600' : 'border-transparent text-gray-500 hover:text-gray-700'}`}>{t}</button>
            ))}
          </div>

          {tab === 'Readiness' && <ReadinessTab a={a} readiness={readiness} navigate={navigate} setTab={setTab} />}
          {tab === 'Keywords' && <KeywordsTab kw={a.keywords || {}} navigate={navigate} />}
          {tab === 'Skills' && <SkillsTab sk={a.skills || {}} />}
          {tab === 'Experience' && <ExperienceTab ex={a.experience || {}} navigate={navigate} />}
          {tab === 'Certifications' && <CertsTab ce={a.certifications || {}} />}
          {tab === 'Build' && <BuildTab pr={a.projects || {}} navigate={navigate} />}
          {tab === 'Roadmap' && <RoadmapTab items={d.roadmap_items || []} onReopen={() => setShowQuestions(true)} qc={qc} />}
        </>
      )}

      {showQuestions && <QuestionsModal onClose={() => setShowQuestions(false)} onAnalyse={runAnalysis} />}
    </div>
  )
}

function Section({ title, children }) {
  return (
    <div className="bg-white rounded-2xl border border-gray-200 p-5 mb-4">
      <h3 className="text-sm font-semibold text-gray-900 mb-3">{title}</h3>
      {children}
    </div>
  )
}

// Real ATS/Pursuit readiness from aggregated scores — dual radar with a toggle.
function RealReadiness({ readiness, view, setView, setTab }) {
  const block = view === 'ats' ? readiness.ats : readiness.pursuit
  const color = view === 'ats' ? '#f59e0b' : '#10b981'
  const comps = Object.entries(block.components || {})
  const radarData = comps.map(([, v]) => ({ axis: v.label, score: v.score ?? 0 }))
  const insightAction = view === 'ats'
    ? { text: 'add missing terms to improve ATS screening', label: 'Go to Keywords tab →', tab: 'Keywords' }
    : { text: 'often high competition — focus on referrals and differentiation', label: 'Go to Roadmap tab →', tab: 'Roadmap' }

  return (
    <Section title={`Readiness from ${readiness.jobs_scored} scored jobs`}>
      <div className="flex items-center justify-between gap-3 -mt-1 mb-3">
        <p className="text-[11px] text-gray-400">Real data · updates automatically as jobs are scored</p>
        <ScoreToggle value={view} onChange={setView} size="sm"
          options={[{ value: 'ats', label: 'ATS Readiness' }, { value: 'pursuit', label: 'Pursuit Readiness' }]} />
      </div>

      {/* Weighted overall */}
      <div className="flex items-end gap-4 flex-wrap mb-1">
        <p className="text-4xl font-bold" style={{ color }}>{block.overall ?? '—'}<span className="text-lg text-gray-400">%</span></p>
        <div className="text-xs text-gray-500 pb-1">
          <p>ATS <strong className="text-amber-600">{readiness.ats.overall}</strong> · Pursuit <strong className="text-emerald-600">{readiness.pursuit.overall}</strong></p>
          <p>Overall <strong>{readiness.overall}%</strong> <span className="text-gray-400">(ATS×0.4 + Pursuit×0.6)</span></p>
        </div>
      </div>

      <div className="mt-3">
        <ResponsiveContainer width="100%" height={300}>
          <RadarChart data={radarData} outerRadius="72%">
            <PolarGrid />
            <PolarAngleAxis dataKey="axis" tick={{ fontSize: 12, fill: '#64748b' }} />
            <Radar dataKey="score" stroke={color} fill={color} fillOpacity={0.3} />
            <Tooltip formatter={(v) => [`${v}%`, view === 'ats' ? 'ATS' : 'Pursuit']} />
          </RadarChart>
        </ResponsiveContainer>
      </div>

      <div className="mt-3 space-y-2">
        {comps.map(([k, v]) => (
          <div key={k} className="flex items-center gap-2">
            <span className="text-xs text-gray-500 w-28">{v.label}</span>
            <div className="flex-1 h-3 bg-gray-100 rounded-full overflow-hidden">
              <div className="h-full rounded-full" style={{ width: `${v.score || 0}%`, backgroundColor: barColor(v.score) }} />
            </div>
            <span className="text-xs text-gray-500 w-10 text-right tabular-nums">{v.score ?? '—'}%</span>
          </div>
        ))}
      </div>

      {block.top_gap_label && (
        <div className="mt-3 pt-3 border-t border-gray-100 text-xs text-gray-600">
          Weakest: <strong>{block.top_gap_label}</strong> ({block.components[block.top_gap]?.score}%) — {insightAction.text}.
          <button onClick={() => setTab(insightAction.tab)} className="ml-1 text-emerald-600 font-medium hover:underline">{insightAction.label}</button>
        </div>
      )}
    </Section>
  )
}

// Fallback: the old Claude-estimate radar (5 readiness axes).
function ClaudeReadiness({ a }) {
  const scores = a.scores || {}
  const radarData = SCORE_LABELS.map(([k, label]) => ({ axis: label, score: scores[k] ?? 0 }))
  return (
    <Section title="Overall readiness (Claude estimate)">
      <p className="text-4xl font-bold text-gray-900">{a.readiness_score ?? '—'}<span className="text-lg text-gray-400">%</span></p>
      <div className="mt-4">
        <ResponsiveContainer width="100%" height={300}>
          <RadarChart data={radarData} outerRadius="72%">
            <PolarGrid />
            <PolarAngleAxis dataKey="axis" tick={{ fontSize: 12, fill: '#64748b' }} />
            <Radar dataKey="score" stroke="#10b981" fill="#10b981" fillOpacity={0.3} />
            <Tooltip formatter={(v) => [`${v}%`, 'Score']} />
          </RadarChart>
        </ResponsiveContainer>
      </div>
      <div className="mt-3 space-y-2">
        {SCORE_LABELS.map(([k, label]) => (
          <div key={k} className="flex items-center gap-2">
            <span className="text-xs text-gray-500 w-24">{label}</span>
            <div className="flex-1 h-3 bg-gray-100 rounded-full overflow-hidden">
              <div className="h-full rounded-full" style={{ width: `${scores[k] || 0}%`, backgroundColor: barColor(scores[k]) }} />
            </div>
            <span className="text-xs text-gray-500 w-10 text-right tabular-nums">{scores[k] ?? '—'}%</span>
          </div>
        ))}
      </div>
    </Section>
  )
}

function ReadinessTab({ a, readiness, navigate, setTab }) {
  const [view, setView] = useState('ats')
  const hasReal = readiness && !readiness.no_data && readiness.jobs_scored > 0
  return (
    <div>
      {hasReal ? (
        <RealReadiness readiness={readiness} view={view} setView={setView} setTab={setTab} />
      ) : (
        <>
          <div className="bg-amber-50 border border-amber-100 rounded-xl p-4 mb-4 text-sm text-amber-800">
            ⚡ Real-time readiness not yet computed. Run the backfill to see ATS + Pursuit readiness from your actual job scores.
            <button onClick={() => navigate('/settings')} className="block mt-2 text-amber-700 font-medium hover:underline">Go to Settings → Backfill →</button>
            <p className="text-[11px] text-amber-600 mt-2">In the meantime, showing the Claude estimate below.</p>
          </div>
          <ClaudeReadiness a={a} />
        </>
      )}

      {a.top_action && (
        <Section title="Top action">
          <p className="text-sm font-medium text-gray-800">💡 {a.top_action.title}</p>
          <p className="text-xs text-gray-500 mt-0.5">{a.top_action.reason}</p>
          {a.top_action.impact_pct != null && <span className="text-xs text-emerald-600 font-medium">+{a.top_action.impact_pct}% readiness</span>}
        </Section>
      )}

      {(a.quick_wins || []).length > 0 && (
        <Section title="Quick wins">
          <ul className="space-y-2">
            {a.quick_wins.slice(0, 3).map((w, i) => (
              <li key={i} className="flex items-center justify-between text-sm">
                <span className="text-gray-700">{w.title}</span>
                {w.impact_pct != null && <span className="text-xs text-emerald-600 font-medium">+{w.impact_pct}%</span>}
              </li>
            ))}
          </ul>
        </Section>
      )}

      <CommunityBenchmark />
    </div>
  )
}

function FreqRow({ label, freq, impact, suggestion, action, onAct }) {
  return (
    <div className="py-2.5 border-b border-gray-50 last:border-0">
      <div className="flex items-center justify-between gap-2">
        <span className="text-sm text-gray-800 font-medium">{label}</span>
        <div className="flex items-center gap-2 shrink-0">
          {impact != null && <span className="text-[10px] bg-emerald-50 text-emerald-700 rounded-full px-1.5 py-0.5 font-medium">+{impact}%</span>}
          {action && <button onClick={onAct} className="text-xs text-emerald-600 hover:underline font-medium">{action} →</button>}
        </div>
      </div>
      {freq != null && (
        <div className="flex items-center gap-2 mt-1">
          <div className="flex-1 h-1.5 bg-gray-100 rounded-full overflow-hidden max-w-[160px]">
            <div className="h-full bg-indigo-400 rounded-full" style={{ width: `${freq}%` }} />
          </div>
          <span className="text-[10px] text-gray-400">{freq}% of JDs</span>
        </div>
      )}
      {suggestion && <p className="text-xs text-gray-400 italic mt-1">{suggestion}</p>}
    </div>
  )
}

function KeywordsTab({ kw, navigate }) {
  return (
    <div>
      <Section title={`Missing keywords (${(kw.missing || []).length})`}>
        {(kw.missing || []).map((k, i) => (
          <FreqRow key={i} label={k.keyword} freq={k.frequency_pct} impact={k.impact_pct} suggestion={k.suggestion}
            action="Add to CV" onAct={() => navigate(`/cvs?suggest=${encodeURIComponent(k.keyword)}`)} />
        ))}
        {!(kw.missing || []).length && <p className="text-xs text-gray-400">No missing keywords — great coverage!</p>}
      </Section>
      <Section title="Present keywords">
        <div className="flex flex-wrap gap-1.5">
          {(kw.present || []).map((k, i) => (
            <span key={i} className="text-xs bg-emerald-50 text-emerald-700 rounded-full px-2 py-0.5">✓ {k.keyword}{k.frequency_pct ? ` (${k.frequency_pct}%)` : ''}</span>
          ))}
          {!(kw.present || []).length && <p className="text-xs text-gray-400">—</p>}
        </div>
      </Section>
    </div>
  )
}

function SkillsTab({ sk }) {
  return (
    <div>
      <Section title="Skill gaps">
        {(sk.gaps || []).map((g, i) => (
          <FreqRow key={i} label={g.skill} freq={g.frequency_pct} impact={g.impact_pct}
            suggestion={`${g.suggestion || ''}${g.timeframe ? ` · ${g.timeframe.replace('_', ' ')}` : ''}`} />
        ))}
        {!(sk.gaps || []).length && <p className="text-xs text-gray-400">No major skill gaps.</p>}
      </Section>
      <Section title="Strengths">
        <div className="flex flex-wrap gap-1.5">
          {(sk.strengths || []).map((s, i) => <span key={i} className="text-xs bg-emerald-50 text-emerald-700 rounded-full px-2 py-0.5">✓ {typeof s === 'string' ? s : s.skill}</span>)}
        </div>
      </Section>
    </div>
  )
}

function ExperienceTab({ ex, navigate }) {
  return (
    <div>
      {(ex.reframes || []).length > 0 && (
        <Section title="Reframe suggestions">
          {ex.reframes.map((r, i) => (
            <FreqRow key={i} label={r.gap} freq={r.frequency_pct} suggestion={r.suggestion}
              action="Reframe" onAct={() => navigate('/cvs')} />
          ))}
        </Section>
      )}
      <Section title="Gaps">
        <ul className="space-y-1 text-sm text-gray-700">{(ex.gaps || []).map((g, i) => <li key={i}>• {typeof g === 'string' ? g : g.gap}</li>)}{!(ex.gaps || []).length && <li className="text-xs text-gray-400">—</li>}</ul>
      </Section>
      <Section title="Strengths">
        <div className="flex flex-wrap gap-1.5">{(ex.strengths || []).map((s, i) => <span key={i} className="text-xs bg-emerald-50 text-emerald-700 rounded-full px-2 py-0.5">✓ {typeof s === 'string' ? s : s.strength}</span>)}</div>
      </Section>
    </div>
  )
}

function CertsTab({ ce }) {
  return (
    <div>
      <Section title="Recommended certifications">
        {(ce.recommended || []).map((c, i) => (
          <div key={i} className="py-2.5 border-b border-gray-50 last:border-0">
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium text-gray-800">{c.name}</span>
              {c.impact_pct != null && <span className="text-[10px] bg-emerald-50 text-emerald-700 rounded-full px-1.5 py-0.5 font-medium">+{c.impact_pct}%</span>}
            </div>
            <p className="text-xs text-gray-400 mt-0.5">
              {c.frequency_pct ? `${c.frequency_pct}% of JDs` : ''}{c.cost ? ` · ${c.cost}` : ''}{c.duration ? ` · ${c.duration}` : ''}{c.timeframe ? ` · ${c.timeframe.replace('_', ' ')}` : ''}
            </p>
          </div>
        ))}
        {!(ce.recommended || []).length && <p className="text-xs text-gray-400">No additional certs recommended.</p>}
      </Section>
      <Section title="Present">
        <div className="flex flex-wrap gap-1.5">{(ce.present || []).map((c, i) => <span key={i} className="text-xs bg-emerald-50 text-emerald-700 rounded-full px-2 py-0.5">✓ {typeof c === 'string' ? c : c.name}</span>)}{!(ce.present || []).length && <p className="text-xs text-gray-400">—</p>}</div>
      </Section>
    </div>
  )
}

function BuildTab({ pr, navigate }) {
  return (
    <div>
      <Section title="Your projects">
        {(pr.existing || []).map((p, i) => (
          <div key={i} className="py-2.5 border-b border-gray-50 last:border-0 flex items-center justify-between">
            <div>
              <span className="text-sm font-medium text-gray-800">{p.name}</span>
              <span className="ml-2 text-[10px] text-gray-400">{p.is_public ? 'public' : 'private'}{p.is_on_cv ? ' · on CV' : ' · not on CV'}</span>
              {p.suggestion && <p className="text-xs text-gray-400 italic">{p.suggestion}</p>}
            </div>
            {!p.is_on_cv && <button onClick={() => navigate('/cvs')} className="text-xs text-emerald-600 hover:underline font-medium shrink-0">Add to CV →</button>}
          </div>
        ))}
        {!(pr.existing || []).length && <p className="text-xs text-gray-400">No projects detected.</p>}
      </Section>
      <Section title="Suggested projects">
        {(pr.suggested || []).map((p, i) => (
          <div key={i} className="py-2.5 border-b border-gray-50 last:border-0">
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium text-gray-800">{p.name}</span>
              {p.impact_pct != null && <span className="text-[10px] bg-emerald-50 text-emerald-700 rounded-full px-1.5 py-0.5 font-medium">+{p.impact_pct}%</span>}
            </div>
            <p className="text-xs text-gray-400 mt-0.5">{p.rationale}{p.duration ? ` · ${p.duration}` : ''}</p>
          </div>
        ))}
        {!(pr.suggested || []).length && <p className="text-xs text-gray-400">—</p>}
      </Section>
    </div>
  )
}

function RoadmapTab({ items, onReopen, qc }) {
  const groups = [['this_week', 'This week'], ['this_month', 'This month'], ['3_months', 'Next 3 months']]
  const toggle = async (item) => {
    try {
      const res = await updateRoadmapItem(item.id, !item.is_completed)
      qc.invalidateQueries({ queryKey: ['career'] })
      if (!item.is_completed) toast.success(`✅ Roadmap item complete!${item.impact_pct ? ` +${item.impact_pct}% readiness` : ''}`)
    } catch { toast.error('Failed') }
  }
  return (
    <div>
      {groups.map(([tf, label]) => {
        const its = items.filter((i) => i.timeframe === tf)
        if (!its.length) return null
        return (
          <Section key={tf} title={label}>
            {its.map((i) => (
              <label key={i.id} className="flex items-center gap-3 py-1.5 cursor-pointer">
                <input type="checkbox" checked={i.is_completed} onChange={() => toggle(i)} className="accent-emerald-500" />
                <span className={`text-sm flex-1 ${i.is_completed ? 'line-through text-gray-400' : 'text-gray-700'}`}>{i.title}</span>
                {i.impact_pct != null && <span className="text-[10px] bg-emerald-50 text-emerald-700 rounded-full px-1.5 py-0.5 font-medium">+{i.impact_pct}%</span>}
                <span className="text-[10px] text-gray-400 capitalize">{i.category}</span>
              </label>
            ))}
          </Section>
        )
      })}
      {!items.length && <p className="text-sm text-gray-400 text-center py-8">No roadmap items.</p>}
      <button onClick={onReopen} className="text-xs text-emerald-600 hover:underline font-medium">Update your answers →</button>
    </div>
  )
}

function CommunityBenchmark() {
  const { data } = useQuery({ queryKey: ['career-community'], queryFn: getCommunityCareer, retry: false })
  const c = data?.data
  const [sharing, setSharing] = useState(false)
  const share = async () => {
    setSharing(true)
    try { const r = await shareInsights(); toast.success(`Shared ${r.data.patterns_shared} patterns — thank you!`) }
    catch (e) { toast.error(e.response?.data?.detail || 'Failed') } finally { setSharing(false) }
  }
  if (!c) return null
  return (
    <Section title="Community benchmark">
      {c.warming_up ? (
        <div>
          <p className="text-sm text-gray-600">🌱 Warming up — be one of the first to contribute!</p>
          <p className="text-xs text-gray-400 mt-1 mb-3">Your anonymised insights help others targeting the same roles. No CV content is shared.</p>
          <Button size="sm" variant="secondary" loading={sharing} onClick={share}>Share my insights →</Button>
        </div>
      ) : (
        <ul className="space-y-1 text-sm text-gray-700">
          <p className="text-xs text-gray-400 mb-1">{c.contributor_count} members · top patterns:</p>
          {(c.insights || []).slice(0, 5).map((i, idx) => (
            <li key={idx}>→ {i.value} {i.frequency_pct ? `(${i.frequency_pct}%)` : ''}</li>
          ))}
        </ul>
      )}
    </Section>
  )
}

function QuestionsModal({ onClose, onAnalyse }) {
  const [answers, setAnswers] = useState({})
  const { data } = useQuery({ queryKey: ['career-answers'], queryFn: getAnswers, retry: false })
  useEffect(() => { if (data?.data) setAnswers(data.data) }, [data])

  const pick = async (key, value) => {
    setAnswers((p) => ({ ...p, [key]: value }))
    try { await saveAnswer(key, value) } catch (_) {}
  }

  return (
    <div className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-xl max-w-lg w-full max-h-[85vh] overflow-y-auto p-6">
        <div className="flex items-center justify-between mb-1">
          <h2 className="text-lg font-semibold text-gray-900">A few quick questions</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-lg">×</button>
        </div>
        <p className="text-xs text-gray-500 mb-4">These sharpen your analysis. Optional — you can analyse with defaults.</p>
        <div className="space-y-5">
          {QUESTIONS.map((q) => (
            <div key={q.key}>
              <p className="text-sm font-medium text-gray-800 mb-1.5">{q.q}</p>
              <div className="flex flex-wrap gap-1.5">
                {q.options.map((o) => (
                  <button key={o} onClick={() => pick(q.key, o)}
                    className={`text-xs px-2.5 py-1 rounded-full border ${answers[q.key] === o ? 'bg-emerald-500 text-white border-emerald-500' : 'bg-white text-gray-600 border-gray-200 hover:bg-gray-50'}`}>{o}</button>
                ))}
              </div>
            </div>
          ))}
        </div>
        <div className="flex justify-between mt-6">
          <button onClick={onClose} className="text-sm text-gray-500 hover:text-gray-700">Skip for now</button>
          <Button onClick={onAnalyse}>Analyse →</Button>
        </div>
      </div>
    </div>
  )
}
