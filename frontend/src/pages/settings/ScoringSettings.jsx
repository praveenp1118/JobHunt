import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { getScoringConfig, updateScoringConfig, getScoringEstimate, recomputeMasterEssence } from '../../api/scoring'
import { getPreferences, updatePreferences } from '../../api/auth'
import { backfillScores } from '../../api/jobs'
import Button from '../../components/ui/Button'
import Spinner from '../../components/ui/Spinner'
import { toast } from '../../store/toast'

const PRESETS = [
  { key: 'maximum_quality', label: 'Maximum Quality', desc: 'Sonnet everywhere · ~₹80/scan' },
  { key: 'balanced', label: 'Balanced', desc: 'Haiku filter + Sonnet quality · ~₹25-30/scan' },
  { key: 'maximum_savings', label: 'Max Savings', desc: 'Haiku everywhere · ~₹10/scan' },
]
const ESSENCE_MODELS = [
  ['claude-haiku-4-5', 'Claude Haiku 4.5 — ₹0.03/job (fast)'],
  ['claude-sonnet-4-6', 'Claude Sonnet 4.6 — ₹0.58/job (quality)'],
]
const FULL_MODELS = [
  ['claude-haiku-4-5', 'Claude Haiku 4.5 — ₹0.06/job (economy)'],
  ['claude-sonnet-4-6', 'Claude Sonnet 4.6 — ₹0.58/job (recommended)'],
  ['claude-opus-4-6', 'Claude Opus 4.6 — ₹2.90/job (premium)'],
]

function Row({ label, info, children }) {
  return (
    <div className="flex items-start justify-between gap-3 py-2 border-b border-gray-50 last:border-0">
      <div className="min-w-0">
        <p className="text-sm text-gray-700">{label}</p>
        {info && <p className="text-[11px] text-gray-400 mt-0.5">{info}</p>}
      </div>
      <div className="shrink-0">{children}</div>
    </div>
  )
}
const sel = "text-xs border border-gray-200 rounded-md px-2 py-1 bg-white outline-none focus:border-emerald-400"

export default function ScoringSettings() {
  const qc = useQueryClient()
  const [recomputing, setRecomputing] = useState(false)
  const { data: cfgData, isLoading } = useQuery({ queryKey: ['scoring-config'], queryFn: getScoringConfig })
  const { data: estData } = useQuery({ queryKey: ['scoring-estimate'], queryFn: getScoringEstimate })
  const { data: prefsData } = useQuery({ queryKey: ['preferences'], queryFn: getPreferences })
  const c = cfgData?.data
  const est = estData?.data
  const p = prefsData?.data || {}
  const [backfilling, setBackfilling] = useState(false)

  const savePref = async (patch) => {
    try { await updatePreferences(patch); qc.invalidateQueries({ queryKey: ['preferences'] }) }
    catch { toast.error('Save failed') }
  }
  const runBackfill = async () => {
    if (!window.confirm('Compute ATS + Pursuit scores for your existing jobs? This uses Claude tokens (~₹0.15/job).')) return
    setBackfilling(true)
    try {
      const r = await backfillScores()
      toast.success(r.data.queued ? `Queued ${r.data.jobs} jobs · ~₹${r.data.estimated_cost_inr}` : r.data.message)
    } catch (e) { toast.error(e.response?.data?.detail || 'Backfill failed') }
    finally { setBackfilling(false) }
  }

  const save = async (patch) => {
    try {
      await updateScoringConfig(patch)
      qc.invalidateQueries({ queryKey: ['scoring-config'] })
      qc.invalidateQueries({ queryKey: ['scoring-estimate'] })
    } catch (e) { toast.error('Save failed') }
  }
  const recompute = async () => {
    setRecomputing(true)
    try { const r = await recomputeMasterEssence(); toast.success(`CV essence updated (${r.data.keywords} keywords)`); qc.invalidateQueries({ queryKey: ['scoring-estimate'] }) }
    catch (e) { toast.error(e.response?.data?.detail || 'Recompute failed') } finally { setRecomputing(false) }
  }

  if (isLoading || !c) return <div className="flex justify-center py-8"><Spinner /></div>

  return (
    <div className="space-y-5">
      <div>
        <h3 className="text-sm font-semibold text-gray-900">Scoring &amp; Cost Optimization</h3>
        <p className="text-xs text-gray-500 mt-0.5">A 3-stage hybrid-RAG pipeline keeps quality on saved jobs while cutting token cost ~80%.</p>
      </div>

      {/* Preset cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
        {PRESETS.map((p) => {
          const active = c.scoring_preset === p.key
          return (
            <button key={p.key} onClick={() => save({ scoring_preset: p.key })}
              className={`text-left rounded-xl border p-3 transition-colors ${active ? 'border-emerald-500 bg-emerald-50' : 'border-gray-200 hover:border-gray-300'}`}>
              <p className={`text-sm font-medium ${active ? 'text-emerald-700' : 'text-gray-800'}`}>{active ? '● ' : ''}{p.label}</p>
              <p className="text-[11px] text-gray-500 mt-0.5">{p.desc}</p>
            </button>
          )
        })}
      </div>
      {c.scoring_preset === 'custom' && <p className="text-[11px] text-amber-600">Custom — you’ve fine-tuned the settings below.</p>}

      {/* Scoring timing */}
      <div className="bg-white rounded-xl border border-gray-200 p-4">
        <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Scoring timing</p>
        <div className="space-y-2">
          {[
            ['immediate', 'Score immediately', 'Scores appear as soon as jobs are found (real-time, default).'],
            ['overnight', 'Score overnight (cheapest)', 'Jobs are saved immediately; scores are computed at night in one optimized batch.'],
            ['manual', 'Manual only', 'Jobs saved unscored — click “Score now” on each job.'],
          ].map(([k, label, desc]) => (
            <label key={k} className="flex items-start gap-2 cursor-pointer">
              <input type="radio" name="timing" checked={c.scoring_timing === k} onChange={() => save({ scoring_timing: k })} className="mt-0.5 accent-emerald-500" />
              <div>
                <p className="text-sm text-gray-800">{label}</p>
                <p className="text-[11px] text-gray-400">{desc}</p>
                {k === 'overnight' && c.scoring_timing === 'overnight' && (
                  <div className="mt-1 flex items-center gap-2">
                    <span className="text-[11px] text-gray-500">Night batch time:</span>
                    <select className={sel} value={c.night_batch_time} onChange={(e) => save({ night_batch_time: e.target.value })}>
                      {['00:00', '01:00', '02:00', '03:00', '04:00', '05:00'].map((t) => <option key={t} value={t}>{t} IST</option>)}
                    </select>
                  </div>
                )}
              </div>
            </label>
          ))}
        </div>
        {est && (
          <p className="text-[11px] text-gray-500 mt-2">
            Immediate: ~₹{est.estimated_cost_inr}/scan · Overnight: ~₹{Math.round(est.estimated_cost_inr * 0.72)}/scan <span className="text-emerald-600">(~28% cheaper, larger batches)</span>
          </p>
        )}
      </div>

      {/* Stage settings */}
      <div className="bg-white rounded-xl border border-gray-200 p-4">
        <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Stage 1 — keyword pre-filter (free)</p>
        <Row label="Min keyword matches" info="Jobs with fewer keyword matches are rejected without any Claude call (free).">
          <select className={sel} value={c.keyword_match_threshold} onChange={(e) => save({ keyword_match_threshold: Number(e.target.value) })}>
            {[1, 2, 3, 4, 5, 6, 8, 10].map((n) => <option key={n} value={n}>{n}</option>)}
          </select>
        </Row>

        <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mt-4 mb-1">Stage 2 — essence scoring</p>
        <Row label="Essence model">
          <select className={sel} value={c.s1_essence_model} onChange={(e) => save({ s1_essence_model: e.target.value })}>
            {ESSENCE_MODELS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </Row>
        <Row label="Reject below score" info="Jobs scoring below this are rejected without full-CV scoring.">
          <input type="number" min="0" max="70" className={`${sel} w-16`} value={c.s1_essence_reject_below} onChange={(e) => save({ s1_essence_reject_below: Number(e.target.value) })} />
        </Row>

        <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mt-4 mb-1">Stage 3 — full CV scoring</p>
        <Row label="Full-CV model">
          <select className={sel} value={c.s1_full_model} onChange={(e) => save({ s1_full_model: e.target.value })}>
            {FULL_MODELS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </Row>
        <Row label="Borderline range" info="Jobs in this range get full-CV scoring. Above high = saved immediately; below low = rejected.">
          <span className="flex items-center gap-1">
            <input type="number" className={`${sel} w-14`} value={c.s1_borderline_low} onChange={(e) => save({ s1_borderline_low: Number(e.target.value) })} />
            <span className="text-xs text-gray-400">to</span>
            <input type="number" className={`${sel} w-14`} value={c.s1_borderline_high} onChange={(e) => save({ s1_borderline_high: Number(e.target.value) })} />
          </span>
        </Row>

        <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mt-4 mb-1">Domain CV scoring</p>
        <Row label="Domain model">
          <select className={sel} value={c.domain_score_model} onChange={(e) => save({ domain_score_model: e.target.value })}>
            {ESSENCE_MODELS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </Row>
        <Row label="Skip if S1 below" info="Skip domain-CV scoring for low-scoring jobs.">
          <input type="number" className={`${sel} w-16`} value={c.domain_score_min_s1} onChange={(e) => save({ domain_score_min_s1: Number(e.target.value) })} />
        </Row>

        <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mt-4 mb-1">Other</p>
        <Row label="Career insights model" info="Runs once every 7 days.">
          <select className={sel} value={c.career_model} onChange={(e) => save({ career_model: e.target.value })}>
            {FULL_MODELS.map(([v, l]) => <option key={v} value={v}>{l.split(' — ')[0]}</option>)}
          </select>
        </Row>
        <Row label="Jobs per API call" info="Larger batches = faster + fewer API calls.">
          <select className={sel} value={c.scoring_batch_size} onChange={(e) => save({ scoring_batch_size: Number(e.target.value) })}>
            {[5, 10, 12, 15, 20].map((n) => <option key={n} value={n}>{n}</option>)}
          </select>
        </Row>
      </div>

      {/* Live cost calculator */}
      {est && (
        <div className="bg-slate-50 border border-slate-200 rounded-xl p-4">
          <p className="text-xs font-semibold text-gray-800 mb-2">💡 Estimated scan cost with current settings</p>
          <p className="text-[11px] text-gray-500 mb-2">Active feeds: {est.active_feeds} × ~{est.avg_jobs_per_feed} jobs = {est.estimated_total_jobs} jobs · {est.num_domain_cvs} domain CVs</p>
          <div className="space-y-0.5 text-xs text-gray-600">
            <div className="flex justify-between"><span>Stage 1 (free) · ~{est.stage1_rejected_estimate} rejected</span><span>₹0.00</span></div>
            <div className="flex justify-between"><span>Stage 2 · ~{est.stage2_jobs_estimate} scored</span><span>₹{est.cost_stage2}</span></div>
            <div className="flex justify-between"><span>Stage 3 · ~{est.stage3_jobs_estimate} scored</span><span>₹{est.cost_stage3}</span></div>
            <div className="flex justify-between"><span>Domain CV · ~{est.domain_jobs_estimate} scored</span><span>₹{est.cost_domain}</span></div>
          </div>
          <div className="flex justify-between text-sm font-semibold text-gray-900 mt-2 pt-2 border-t border-slate-200">
            <span>Estimated per scan</span><span>₹{est.estimated_cost_inr}</span>
          </div>
          <div className="flex justify-between text-xs text-gray-500"><span>Monthly (4 scans)</span><span>₹{est.monthly_cost_inr}</span></div>
          <p className="text-[11px] text-emerald-600 mt-2">Without optimization: ₹{est.unoptimized_cost_inr}/scan · saving ~{est.savings_pct}%</p>
        </div>
      )}

      <div className="flex items-center justify-between">
        <p className="text-[11px] text-gray-400">Stage 1 + 2 use your CV “essence” — recompute it after editing your CV.</p>
        <Button size="sm" variant="secondary" loading={recomputing} onClick={recompute}>Recompute CV essence</Button>
      </div>

      {/* Score display — ATS + Pursuit */}
      <div className="bg-white rounded-xl border border-gray-200 p-4">
        <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Score display</p>
        <p className="text-[11px] text-gray-400 mb-3">Each job gets two scores: <strong>ATS</strong> (will you pass automated screening?) and <strong>Pursuit</strong> (should you pursue it?).</p>
        <p className="text-xs text-gray-600 mb-1">Default score view</p>
        <div className="space-y-2 mb-4">
          {[
            ['pursuit', 'Pursuit score (recommended)', 'Overall fit — should you pursue this opportunity?'],
            ['ats', 'ATS score', 'Keyword/requirement match — will you pass automated screening?'],
            ['combined', 'Combined', '40% ATS + 60% Pursuit'],
          ].map(([k, label, desc]) => (
            <label key={k} className="flex items-start gap-2 cursor-pointer">
              <input type="radio" name="scoreview" checked={(p.default_score_view ?? 'pursuit') === k}
                onChange={() => savePref({ default_score_view: k })} className="mt-0.5 accent-emerald-500" />
              <div><p className="text-sm text-gray-800">{label}</p><p className="text-[11px] text-gray-400">{desc}</p></div>
            </label>
          ))}
        </div>
        <p className="text-xs text-gray-600 mb-1">Score pill style</p>
        <div className="space-y-2 mb-4">
          {[
            ['dual_ring', 'Dual ring (ATS outer, Pursuit inner)'],
            ['single', 'Single colour (default score only)'],
            ['number_only', 'Number only (minimal)'],
          ].map(([k, label]) => (
            <label key={k} className="flex items-center gap-2 cursor-pointer">
              <input type="radio" name="pillstyle" checked={(p.score_pill_style ?? 'dual_ring') === k}
                onChange={() => savePref({ score_pill_style: k })} className="accent-emerald-500" />
              <span className="text-sm text-gray-800">{label}</span>
            </label>
          ))}
        </div>
        <div className="flex items-center justify-between border-t border-gray-100 pt-3">
          <p className="text-[11px] text-gray-400">Existing jobs have no ATS/Pursuit scores until computed (~₹0.15/job).</p>
          <Button size="sm" variant="secondary" loading={backfilling} onClick={runBackfill}>Compute scores for existing jobs</Button>
        </div>
      </div>
    </div>
  )
}
