import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { formatDistanceToNow, format } from 'date-fns'
import { getJob, getJobEmails, updateJobStatus, updateJob, deleteJob, draftFollowUp, scoreNow, getJobScores } from '../../api/jobs'
import { sendReply } from '../../api/jobs'
import { toast } from '../../store/toast'
import { StatusBadge, MarketBadge } from '../../components/ui/Badge'
import { ThreeScores } from '../../components/ui/ScorePill'
import DualRingPill from '../../components/ui/DualRingPill'
import Button from '../../components/ui/Button'
import Spinner from '../../components/ui/Spinner'
import CommunityInsights from '../../components/community/CommunityInsights'
import PartialJdPanel from '../../components/jobs/PartialJdPanel'
import { getCommunityInsights } from '../../api/community'

const STATUSES = [
  'new', 'bookmarked', 'applied', 'screening',
  'interview_r1', 'interview_r2', 'offer_received',
  'offer_accepted', 'offer_declined', 'rejected', 'ghosted', 'not_interested',
]

export default function JobDetail({ jobId, onClose, onUpdate, onTailor }) {
  const qc = useQueryClient()
  const [tab, setTab] = useState('details')
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)
  const [replyBody, setReplyBody] = useState('')
  const [sendingReply, setSendingReply] = useState(false)
  const [jdExpanded, setJdExpanded] = useState(false)
  const [followUpDraft, setFollowUpDraft] = useState('')
  const [loadingFollowUp, setLoadingFollowUp] = useState(false)
  const [scoring, setScoring] = useState(false)

  const { data: jobData, isLoading } = useQuery({
    queryKey: ['job', jobId],
    queryFn: () => getJob(jobId),
    enabled: !!jobId,
  })

  const { data: emailData } = useQuery({
    queryKey: ['job-emails', jobId],
    queryFn: () => getJobEmails(jobId),
    enabled: !!jobId && tab === 'emails',
  })

  const job = jobData?.data
  const emails = emailData?.data || []

  const { data: communityData } = useQuery({
    queryKey: ['community', job?.company, job?.role, job?.market],
    queryFn: () => getCommunityInsights(job.company, job.role, job.market, job.jd_hash),
    enabled: !!(job?.company && job?.role),
    retry: false,
  })
  const communityCount = communityData?.data?.available ? communityData.data.contributor_count : 0

  const handleStatusChange = async (newStatus) => {
    await updateJobStatus(jobId, newStatus)
    qc.invalidateQueries({ queryKey: ['job', jobId] })
    qc.invalidateQueries({ queryKey: ['jobs'] })
    onUpdate?.()
  }

  const handleDelete = async () => {
    await deleteJob(jobId)
    qc.invalidateQueries({ queryKey: ['jobs'] })
    onUpdate?.()
    onClose()
  }

  const handleScoreNow = async () => {
    setScoring(true)
    try {
      const r = await scoreNow(jobId)
      toast.success(r.data.scored ? `Scored — B ${Math.round(r.data.s1 ?? 0)}${r.data.cost_inr ? ` · ⚡ ₹${r.data.cost_inr}` : ''}` : 'Already scored')
      qc.invalidateQueries({ queryKey: ['job', jobId] })
      qc.invalidateQueries({ queryKey: ['jobs'] })
      qc.invalidateQueries({ queryKey: ['job-stats'] })
      onUpdate?.()
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Scoring failed')
    } finally { setScoring(false) }
  }

  const handleSendReply = async (emailId) => {
    if (!replyBody.trim()) return
    setSendingReply(true)
    try {
      await sendReply({
        job_id: jobId,
        email_thread_id: emailId,
        body: replyBody,
      })
      setReplyBody('')
      qc.invalidateQueries({ queryKey: ['job-emails', jobId] })
      qc.invalidateQueries({ queryKey: ['job', jobId] })
      onUpdate?.()
    } catch (e) {
      console.error(e)
    } finally {
      setSendingReply(false)
    }
  }

  const handleDraftFollowUp = async () => {
    setLoadingFollowUp(true)
    try {
      const res = await draftFollowUp(jobId)
      setFollowUpDraft(res.data.email_draft)
      setTab('emails')
    } catch (e) {
      console.error(e)
    } finally {
      setLoadingFollowUp(false)
    }
  }

  if (isLoading) {
    return (
      <div className="flex justify-center items-center h-full">
        <Spinner />
      </div>
    )
  }

  if (!job) return null

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className={`px-5 pt-4 pb-3 border-b border-gray-100 ${job.needs_hitl ? 'bg-red-50 border-red-200' : 'bg-white'}`}>
        <div className="flex items-start justify-between gap-3">
          <div className="flex-1 min-w-0">
            {job.needs_hitl && (
              <div className="flex items-center gap-1.5 mb-2">
                <div className="w-2 h-2 rounded-full bg-red-500 animate-pulse" />
                <span className="text-xs font-medium text-red-600">Recruiter replied — action needed</span>
              </div>
            )}
            <h2 className="text-base font-semibold text-gray-900 truncate">{job.company}</h2>
            <p className="text-sm text-gray-600 mt-0.5 truncate">{job.role}</p>
            <div className="flex items-center gap-2 mt-2">
              {job.market && <MarketBadge market={job.market} />}
              <StatusBadge status={job.status} />
            </div>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 shrink-0">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Scores */}
        <div className="flex items-center justify-between mt-3">
          <ThreeScores s1={job.s1} s2={job.s2} s3Master={job.s3_master} />
          <div className="flex gap-2">
            {job.scoring_status === 'pending' && (
              <Button size="sm" loading={scoring} onClick={handleScoreNow}>⚡ Score now</Button>
            )}
            <span title={job.has_partial_jd ? 'Tailoring requires the full JD — add it in the JD tab first' : undefined}>
              <Button size="sm" disabled={job.has_partial_jd} onClick={() => onTailor?.(jobId)}>
                Tailor →
              </Button>
            </span>
            <Button size="sm" variant="secondary" onClick={handleDraftFollowUp} loading={loadingFollowUp}>
              Follow up
            </Button>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-0 border-b border-gray-100 bg-white px-4">
        {['details', 'scores', 'emails', 'jd', 'community'].map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-colors capitalize ${
              tab === t
                ? 'border-emerald-500 text-emerald-600'
                : 'border-transparent text-gray-500 hover:text-gray-700'
            }`}
          >
            {t === 'jd' ? 'JD' : t === 'community' ? '💡 Community' : t === 'scores' ? 'Scores' : t}
            {t === 'emails' && emails.length > 0 && (
              <span className="ml-1.5 bg-gray-100 text-gray-600 text-[10px] font-medium px-1.5 py-0.5 rounded-full">
                {emails.length}
              </span>
            )}
            {t === 'community' && communityCount > 0 && (
              <span className="ml-1.5 bg-indigo-100 text-indigo-600 text-[10px] font-medium px-1.5 py-0.5 rounded-full">
                {communityCount}
              </span>
            )}
          </button>
        ))}
      </div>

      <div className="flex-1 overflow-y-auto bg-white">
        {/* ── Details tab ── */}
        {tab === 'details' && (
          <div className="p-5 space-y-5">
            {/* Status update */}
            <div>
              <label className="text-xs font-medium text-gray-500 uppercase tracking-wide block mb-2">Update status</label>
              <div className="flex flex-wrap gap-1.5">
                {STATUSES.map((s) => (
                  <button
                    key={s}
                    onClick={() => handleStatusChange(s)}
                    className={`px-2.5 py-1 rounded-full text-xs font-medium border transition-colors capitalize ${
                      job.status === s
                        ? 'bg-slate-800 text-white border-slate-800'
                        : 'bg-white text-gray-600 border-gray-200 hover:bg-gray-50'
                    }`}
                  >
                    {s.replace(/_/g, ' ')}
                  </button>
                ))}
              </div>
            </div>

            {/* Key details */}
            <div className="grid grid-cols-2 gap-3 text-sm">
              {job.location && (
                <div>
                  <p className="text-xs text-gray-400 mb-0.5">Location</p>
                  <p className="text-gray-700">{job.location}</p>
                </div>
              )}
              {job.salary_range_raw && (
                <div>
                  <p className="text-xs text-gray-400 mb-0.5">Salary</p>
                  <p className="text-gray-700">{job.salary_range_raw}</p>
                </div>
              )}
              {job.recruiter_email && (
                <div>
                  <p className="text-xs text-gray-400 mb-0.5">Recruiter</p>
                  <a href={`mailto:${job.recruiter_email}`} className="text-emerald-600 hover:underline truncate block">{job.recruiter_email}</a>
                </div>
              )}
              {job.applied_at && (
                <div>
                  <p className="text-xs text-gray-400 mb-0.5">Applied</p>
                  <p className="text-gray-700">{format(new Date(job.applied_at), 'MMM d, yyyy')}</p>
                </div>
              )}
              {job.portal_url && (
                <div className="col-span-2">
                  <p className="text-xs text-gray-400 mb-0.5">Portal</p>
                  <a href={job.portal_url} target="_blank" rel="noreferrer" className="text-emerald-600 hover:underline text-xs truncate block">
                    {job.portal_url}
                  </a>
                </div>
              )}
            </div>

            {/* Notes */}
            <div>
              <label className="text-xs font-medium text-gray-500 uppercase tracking-wide block mb-2">Notes</label>
              <textarea
                defaultValue={job.notes || ''}
                onBlur={(e) => updateJob(jobId, { notes: e.target.value })}
                placeholder="Add notes..."
                rows={3}
                className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm outline-none focus:border-emerald-400 resize-none"
              />
            </div>

            {/* Delete */}
            <div className="pt-2 border-t border-gray-100">
              {!showDeleteConfirm ? (
                <button
                  onClick={() => setShowDeleteConfirm(true)}
                  className="text-xs text-red-400 hover:text-red-600 transition-colors"
                >
                  Delete this job
                </button>
              ) : (
                <div className="flex items-center gap-3 bg-red-50 rounded-lg p-3">
                  <p className="text-xs text-red-600 flex-1">Are you sure? This cannot be undone.</p>
                  <Button size="sm" variant="danger" onClick={handleDelete}>Delete</Button>
                  <Button size="sm" variant="ghost" onClick={() => setShowDeleteConfirm(false)}>Cancel</Button>
                </div>
              )}
            </div>
          </div>
        )}

        {/* ── Emails tab ── */}
        {tab === 'emails' && (
          <div className="p-5">
            {emails.length === 0 && !followUpDraft ? (
              <div className="text-center py-8">
                <p className="text-sm text-gray-400 mb-3">No emails yet</p>
                <p className="text-xs text-gray-400">Emails will appear after you send an application or receive a recruiter reply.</p>
              </div>
            ) : (
              <div className="space-y-3 mb-4">
                {emails.map((email) => (
                  <div
                    key={email.id}
                    className={`rounded-xl border p-4 ${
                      email.needs_hitl
                        ? 'border-red-200 bg-red-50'
                        : email.direction === 'sent'
                        ? 'border-gray-100 bg-gray-50'
                        : 'border-blue-100 bg-blue-50'
                    }`}
                  >
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-medium text-gray-500">
                          {email.direction === 'sent' ? '📤 Sent' : '📥 Received'}
                        </span>
                        {email.classification && (
                          <span className="text-[10px] bg-white border border-gray-200 px-1.5 py-0.5 rounded-full text-gray-500">
                            {email.classification.replace(/_/g, ' ')}
                          </span>
                        )}
                        {email.needs_hitl && (
                          <span className="text-[10px] bg-red-100 text-red-600 px-1.5 py-0.5 rounded-full font-medium">
                            Needs reply
                          </span>
                        )}
                      </div>
                      <span className="text-[10px] text-gray-400">
                        {email.received_at || email.sent_at
                          ? formatDistanceToNow(new Date(email.received_at || email.sent_at), { addSuffix: true })
                          : ''}
                      </span>
                    </div>
                    <p className="text-xs font-medium text-gray-700 mb-1 truncate">{email.subject}</p>
                    <p className="text-xs text-gray-500 line-clamp-2">{email.body_preview}</p>
                    {email.needs_hitl && (
                      <div className="mt-3">
                        <textarea
                          value={replyBody}
                          onChange={(e) => setReplyBody(e.target.value)}
                          placeholder="Type your reply..."
                          rows={4}
                          className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm outline-none focus:border-emerald-400 resize-none mb-2"
                        />
                        <Button
                          size="sm"
                          onClick={() => handleSendReply(email.id)}
                          loading={sendingReply}
                          disabled={!replyBody.trim()}
                        >
                          Send reply
                        </Button>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}

            {/* Follow-up draft */}
            {followUpDraft && (
              <div className="border border-emerald-200 bg-emerald-50 rounded-xl p-4">
                <p className="text-xs font-medium text-emerald-700 mb-2">Follow-up draft</p>
                <textarea
                  value={followUpDraft}
                  onChange={(e) => setFollowUpDraft(e.target.value)}
                  rows={5}
                  className="w-full px-3 py-2 border border-emerald-200 bg-white rounded-lg text-sm outline-none focus:border-emerald-400 resize-none mb-2"
                />
                <p className="text-xs text-emerald-600">Copy this and send from your Gmail, or use Send Reply above if you have a recruiter thread.</p>
              </div>
            )}
          </div>
        )}

        {/* ── Scores tab (ATS + Pursuit breakdown) ── */}
        {tab === 'scores' && <ScoresTab jobId={jobId} job={job} />}

        {/* ── JD tab ── */}
        {tab === 'jd' && (
          <div className="p-5">
            {(() => {
              const jd = job.jd_md || job.jd_raw || ''
              const isPartial = job.has_partial_jd || (jd.length > 0 && jd.length < 200)

              if (!jd && job.portal_url) {
                return (
                  <div className="py-4">
                    <div className="bg-amber-50 border border-amber-200 rounded-lg px-3 py-3">
                      <p className="text-sm text-amber-700 mb-1">⚠️ Partial JD — scores unavailable. Read the full JD first.</p>
                      <PartialJdPanel job={job} onEnriched={onUpdate} />
                    </div>
                  </div>
                )
              }
              if (!jd) {
                return <p className="text-sm text-gray-400 text-center py-8">No job description available</p>
              }
              return (
                <div>
                  {isPartial && (
                    <div className="mb-3 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
                      <div className="flex items-start gap-2">
                        <span className="text-amber-500 text-sm leading-none mt-0.5">⚠️</span>
                        <p className="text-xs text-amber-700">
                          <strong>Partial JD — scores unavailable.</strong> Read the full JD first.
                        </p>
                      </div>
                      <PartialJdPanel job={job} onEnriched={onUpdate} className="mt-2" />
                    </div>
                  )}
                  <div className={`text-sm text-gray-700 whitespace-pre-wrap leading-relaxed ${!jdExpanded ? 'line-clamp-20' : ''}`}>
                    {jd}
                  </div>
                  {jd.length > 600 && (
                    <button
                      onClick={() => setJdExpanded(!jdExpanded)}
                      className="mt-3 text-xs text-emerald-600 hover:text-emerald-700 font-medium"
                    >
                      {jdExpanded ? 'Show less' : 'Show full JD'}
                    </button>
                  )}
                </div>
              )
            })()}
          </div>
        )}

        {tab === 'community' && (
          <div className="p-5">
            <CommunityInsights company={job.company} role={job.role} market={job.market} jdHash={job.jd_hash} jobId={jobId} />
            {communityCount === 0 && (
              <div className="text-center py-8">
                <p className="text-sm text-gray-400">No community insights yet for this role.</p>
                <p className="text-xs text-gray-400 mt-1">
                  They appear once 2+ members anonymously share for this company + role.
                </p>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

const ATS_MAX = { keyword_density: 30, required_skills: 25, experience_years: 20, seniority_alignment: 15, education: 10 }
const ATS_LABEL = { keyword_density: 'Keyword density', required_skills: 'Required skills', experience_years: 'Experience years', seniority_alignment: 'Seniority', education: 'Education' }
const PUR_MAX = { human_excitement: 40, career_move_quality: 25, achievability: 20, effort_reward: 15 }
const PUR_LABEL = { human_excitement: 'Human excitement', career_move_quality: 'Career move', achievability: 'Achievability', effort_reward: 'Effort-reward' }

function CompBar({ label, score, max }) {
  const pct = Math.max(0, Math.min(100, ((score || 0) / max) * 100))
  return (
    <div className="flex items-center gap-2 text-[11px]">
      <span className="w-28 text-gray-600 shrink-0">{label}</span>
      <div className="flex-1 h-2 rounded-full bg-gray-100 overflow-hidden">
        <div className="h-full rounded-full bg-emerald-400" style={{ width: `${pct}%` }} />
      </div>
      <span className="w-10 text-right tabular-nums text-gray-500">{score ?? 0}/{max}</span>
    </div>
  )
}

function ScoresTab({ jobId, job }) {
  const [entity, setEntity] = useState('master')
  const { data, isLoading } = useQuery({ queryKey: ['job-scores', jobId], queryFn: () => getJobScores(jobId) })
  const scores = data?.data
  const entHas = (e) => job?.[`ats_${e}`] != null || job?.[`pursuit_${e}`] != null

  if (isLoading) return <div className="p-5 text-sm text-gray-400">Loading…</div>
  if (!entHas('master') && !entHas('domain') && !entHas('tailored')) {
    return <div className="p-5 text-sm text-gray-400">No ATS / Pursuit scores yet. Add them via Settings → Scoring → “Compute scores for existing jobs”, or they compute when you tailor.</div>
  }

  const block = scores?.[entity] || {}
  const ats = block.ats || {}
  const pur = block.pursuit || {}
  const rec = pur.recommendation
  const recCls = rec === 'Apply now' ? 'bg-emerald-50 text-emerald-700' : rec === 'Skip' ? 'bg-rose-50 text-rose-600' : 'bg-amber-50 text-amber-700'

  return (
    <div className="p-5 space-y-4">
      <div className="flex items-center gap-3">
        <DualRingPill atsScore={job?.[`ats_${entity}`]} pursuitScore={job?.[`pursuit_${entity}`]} defaultView="pursuit" size="lg" showTooltip={false} />
        <div className="flex gap-1">
          {['master', 'domain', 'tailored'].map((e) => (
            <button key={e} onClick={() => setEntity(e)} disabled={!entHas(e)}
              className={`text-xs px-2.5 py-1 rounded-lg capitalize ${entity === e ? 'bg-emerald-100 text-emerald-700 font-medium' : entHas(e) ? 'text-gray-500 hover:bg-gray-50' : 'text-gray-300 cursor-not-allowed'}`}>
              {e}
            </button>
          ))}
        </div>
      </div>

      {ats.components && (
        <div>
          <p className="text-xs font-semibold text-gray-700 mb-1.5">ATS breakdown <span className="text-gray-400">· {ats.total ?? '—'}/100</span></p>
          <div className="space-y-1">
            {Object.keys(ATS_MAX).map((k) => <CompBar key={k} label={ATS_LABEL[k]} score={ats.components?.[k]?.score} max={ATS_MAX[k]} />)}
          </div>
          {ats.dealbreaker_applied && <p className="text-[11px] text-rose-500 mt-1">⚠ Dealbreaker applied (capped at 40)</p>}
        </div>
      )}
      {pur.components && (
        <div>
          <p className="text-xs font-semibold text-gray-700 mb-1.5">Pursuit breakdown <span className="text-gray-400">· {pur.total ?? '—'}/100</span></p>
          <div className="space-y-1">
            {Object.keys(PUR_MAX).map((k) => <CompBar key={k} label={PUR_LABEL[k]} score={pur.components?.[k]?.score} max={PUR_MAX[k]} />)}
          </div>
        </div>
      )}
      {(pur.top_strength || pur.top_gap || rec) && (
        <div className="border-t border-gray-100 pt-3 space-y-1 text-xs">
          {pur.top_strength && <p className="text-emerald-600">✓ {pur.top_strength}</p>}
          {(pur.top_gap || ats.top_gap) && <p className="text-rose-500">✗ {pur.top_gap || ats.top_gap}</p>}
          {rec && <span className={`inline-block mt-1 text-[11px] font-medium px-2 py-0.5 rounded-full ${recCls}`}>{rec}</span>}
        </div>
      )}
    </div>
  )
}
