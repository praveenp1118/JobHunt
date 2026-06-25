import { useState, useEffect } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { format } from 'date-fns'
import {
  getCareerAnalysis, triggerAnalysis, saveAnswer, getAnswers,
  updateRoadmapItem, getCommunityCareer, shareInsights,
} from '../../api/career'
import { RadarChart, Radar, PolarGrid, PolarAngleAxis, ResponsiveContainer, Tooltip } from 'recharts'
import TokenBadge from '../../components/ui/TokenBadge'
import Button from '../../components/ui/Button'
import Spinner from '../../components/ui/Spinner'
import { toast } from '../../store/toast'

const TABS = ['Readiness', 'Keywords', 'Skills', 'Experience', 'Certifications', 'Build', 'Roadmap']

const QUESTIONS = [
  { key: 'manages_pms', q: 'Do you currently manage other Product Managers?', options: ['Yes, currently', 'I have managed PMs in the past', 'No'] },
  { key: 'github_public', q: 'Are your AI projects publicly visible on GitHub?', options: ['Yes, all public', 'Some are public', 'All private', 'Not on GitHub'] },
  { key: 'b2c_experience', q: 'Do you have B2C consumer product experience?', options: ['Yes, significant', 'Some side projects', 'No, mainly B2B'] },
  { key: 'relocation', q: 'Are you open to relocating to Netherlands?', options: ['Yes, immediately', 'Yes, in 3-6 months', 'Remote only', 'Already in NL/EU'] },
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
  const [tab, setTab] = useState('Readiness')
  const [analysing, setAnalysing] = useState(false)
  const [lastUsage, setLastUsage] = useState(null)
  const [showQuestions, setShowQuestions] = useState(false)

  const { data, isLoading } = useQuery({ queryKey: ['career'], queryFn: getCareerAnalysis, retry: false })
  const d = data?.data
  const available = d?.available
  const a = d?.analysis || {}

  // First visit with no analysis → offer the questions intro.
  useEffect(() => {
    if (!isLoading && d && !available) setShowQuestions(true)
  }, [isLoading, d, available])

  const runAnalysis = async () => {
    setAnalysing(true)
    setShowQuestions(false)
    try {
      const res = await triggerAnalysis()
      setLastUsage(res.data.tokens_used ? { tokens: res.data.tokens_used, cost_inr: res.data.cost_inr } : null)
      qc.setQueryData(['career'], res)
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
          {available && d.expires_at && (
            <span className="text-xs text-gray-400">
              Refreshes {format(new Date(d.expires_at), 'MMM d')}
            </span>
          )}
          <Button size="sm" loading={analysing} onClick={runAnalysis}>{available ? 'Re-analyse' : 'Analyse now'}</Button>
        </div>
      </div>

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

          {tab === 'Readiness' && <ReadinessTab a={a} navigate={navigate} />}
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

function ReadinessTab({ a, navigate }) {
  const scores = a.scores || {}
  const radarData = SCORE_LABELS.map(([k, label]) => ({ axis: label, score: scores[k] ?? 0 }))
  return (
    <div>
      <Section title="Overall readiness">
        <p className="text-4xl font-bold text-gray-900">{a.readiness_score ?? '—'}<span className="text-lg text-gray-400">%</span></p>

        {/* Radar across the 5 dimensions */}
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

        {/* Summary bars below the radar */}
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
