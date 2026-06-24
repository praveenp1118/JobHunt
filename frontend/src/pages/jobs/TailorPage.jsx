import { useState, useEffect, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { clsx } from 'clsx'
import {
  getJob, getJdHighlights, generateTailor, getTailorChangelog,
  approveChange, rejectChange, editChange, applyTailor, regenerateCL,
  sendApplication, updateJobStatus,
} from '../../api/jobs'
import { getDomainCVs } from '../../api/cvs'
import { getPreferences, getSettingsMode } from '../../api/auth'
import useAuthStore from '../../store/auth'
import { MarketBadge } from '../../components/ui/Badge'
import ScorePill from '../../components/ui/ScorePill'
import Button from '../../components/ui/Button'
import Spinner from '../../components/ui/Spinner'
import { toast } from '../../store/toast'

// Mirrors backend pdf_generator.make_filename: {Firstname}{Lastname}_{suffix}.pdf
// (neutral — no company/role, so the same name goes to every firm).
function makeFilename(userName, suffix) {
  const parts = (userName || 'Candidate').trim().split(/\s+/)
  const first = parts[0] || 'Candidate'
  const last = parts.length > 1 ? parts[parts.length - 1] : ''
  const name = `${first}${last}`.replace(/[^\w]/g, '') || 'Candidate'
  return `${name}_${suffix}.pdf`
}

async function downloadPDF(url, filename) {
  const raw = localStorage.getItem('jobhunt-auth')
  let token = ''
  if (raw) { try { token = JSON.parse(raw).state?.token || '' } catch (_) {} }
  const res = await fetch(url, { headers: { Authorization: `Bearer ${token}` } })
  if (!res.ok) { toast.error('PDF generation failed'); return }
  const blob = await res.blob()
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = filename
  a.click()
  URL.revokeObjectURL(a.href)
}

const CHANGE_TYPE_COLORS = {
  rephrase: 'bg-blue-100 text-blue-700',
  keyword_injection: 'bg-purple-100 text-purple-700',
  reorder: 'bg-gray-100 text-gray-600',
  deselect: 'bg-red-100 text-red-600',
}
const CHANGE_TYPE_LABELS = {
  rephrase: 'REPHRASE', keyword_injection: 'KEYWORD INJECTION',
  reorder: 'REORDER', deselect: 'DESELECT',
}
const SEND_STATUSES = ['applied', 'bookmarked', 'screening']

export default function TailorPage() {
  const { jobId } = useParams()
  const navigate = useNavigate()

  const [selectedDomainCvId, setSelectedDomainCvId] = useState(null)
  const [showCvPicker, setShowCvPicker] = useState(false)
  const [tailoredCvId, setTailoredCvId] = useState(null)
  const [highlights, setHighlights] = useState(null)
  const [generating, setGenerating] = useState(false)
  const [applying, setApplying] = useState(false)
  const [applyResult, setApplyResult] = useState(null)
  const [rightTab, setRightTab] = useState('cv')
  const [editingChangeId, setEditingChangeId] = useState(null)
  const [editText, setEditText] = useState('')
  const [includesCL, setIncludesCL] = useState(true)
  const [sending, setSending] = useState(false)
  const [sendStatus, setSendStatus] = useState('applied')
  const [emailSubject, setEmailSubject] = useState('')
  const [emailBody, setEmailBody] = useState('')
  const [error, setError] = useState('')

  const { data: jobData } = useQuery({ queryKey: ['job', jobId], queryFn: () => getJob(jobId), enabled: !!jobId })
  const { data: domainCVsData } = useQuery({ queryKey: ['domain-cvs'], queryFn: getDomainCVs })
  const { data: prefsData } = useQuery({ queryKey: ['preferences'], queryFn: getPreferences })
  const { data: modeData } = useQuery({ queryKey: ['settings-mode'], queryFn: getSettingsMode })
  const { data: changelogData, refetch: refetchChangelog } = useQuery({
    queryKey: ['tailor-changelog', tailoredCvId],
    queryFn: () => getTailorChangelog(tailoredCvId),
    enabled: !!tailoredCvId,
  })

  const user = useAuthStore((s) => s.user)
  const job = jobData?.data
  const domainCVs = domainCVsData?.data || []
  const changelog = changelogData?.data || []
  const selectedCV = domainCVs.find((c) => c.id === selectedDomainCvId)
  const jobScores = job?.domain_cv_scores || {}
  // auto_mode: undefined while loading, then boolean. OFF → generation is manual.
  const autoMode = prefsData?.data?.auto_mode
  // Send mode: { mode: 'test'|'production', notification_email } — where the email really goes.
  const sendMode = modeData?.data

  // Attachment filenames (match the backend Content-Disposition names).
  const cvFilename = makeFilename(user?.name, 'CV')
  const clFilename = makeFilename(user?.name, 'CoverLetter')

  // Pre-select best-fit domain CV.
  useEffect(() => {
    if (!selectedDomainCvId) {
      const pre = job?.best_domain_cv_id || job?.detected_domain_cv_id
      if (pre) setSelectedDomainCvId(pre)
      else if (domainCVs.length) setSelectedDomainCvId(domainCVs[0].id)
    }
  }, [job, domainCVs]) // eslint-disable-line

  // Per chosen domain CV: always load JD highlights; AUTO-generate the change log only
  // when auto_mode is ON. In manual mode the middle panel shows a "Suggest changes" button.
  const genRef = useRef(null)
  useEffect(() => {
    if (!job || !selectedDomainCvId || autoMode === undefined) return
    if (genRef.current === selectedDomainCvId) return
    genRef.current = selectedDomainCvId
    setTailoredCvId(null); setApplyResult(null); setHighlights(null)
    getJdHighlights(jobId, selectedDomainCvId).then((r) => setHighlights(r.data)).catch(() => {})
    if (autoMode) runGenerate()
  }, [job, selectedDomainCvId, autoMode]) // eslint-disable-line

  const runGenerate = async () => {
    setError(''); setGenerating(true); setApplyResult(null); setTailoredCvId(null)
    try {
      const res = await generateTailor(jobId, selectedDomainCvId)
      setTailoredCvId(res.data.tailored_cv_id)
    } catch (e) {
      setError(e.response?.data?.detail || 'Generation failed — check your Anthropic API key in Settings.')
    } finally {
      setGenerating(false)
    }
  }

  const pending = changelog.filter((c) => c.status === 'pending')
  const approved = changelog.filter((c) => c.status === 'approved' || c.status === 'approved_edited')
  const rejected = changelog.filter((c) => c.status === 'rejected')
  // Apply is allowed once generation finished (tailoredCvId set), the change log has
  // loaded, and nothing is left pending — INCLUDING the valid 0-changes case (a CV
  // with no edits is still applicable). Previously this required changelog.length > 0,
  // so a 0-change generation left the button permanently disabled → blank preview.
  const allReviewed = !!tailoredCvId && changelogData !== undefined && pending.length === 0

  const handleApprove = async (id) => { await approveChange(tailoredCvId, id); refetchChangelog() }
  const handleReject = async (id) => { await rejectChange(tailoredCvId, id); refetchChangelog() }
  const handleEditApprove = async (id) => { await editChange(tailoredCvId, id, editText); setEditingChangeId(null); refetchChangelog() }
  const approveAll = async () => { for (const c of pending) await approveChange(tailoredCvId, c.id); refetchChangelog() }
  const rejectAll = async () => { for (const c of pending) await rejectChange(tailoredCvId, c.id); refetchChangelog() }

  const handleApply = async () => {
    setError(''); setApplying(true)
    try {
      const res = await applyTailor(tailoredCvId)
      setApplyResult(res.data)
      setEmailSubject(`Application: ${job?.role} — ${job?.company}`)
      setEmailBody(res.data.email_draft || '')
      setRightTab('cv')
    } catch (e) {
      setError(e.response?.data?.detail || 'Apply failed')
    } finally {
      setApplying(false)
    }
  }

  const handleRegenerateCL = async () => {
    try {
      const res = await regenerateCL(tailoredCvId, applyResult?.cl_template_used)
      setApplyResult((p) => ({ ...p, cover_letter_md: res.data.cover_letter_md, cl_template_used: res.data.template_used }))
    } catch (e) { console.error(e) }
  }

  const s3Status = applyResult?.s3_status
  const canSend = applyResult && s3Status !== 'blocked'

  const handleSend = async () => {
    if (!canSend) return
    setSending(true); setError('')
    try {
      await sendApplication({
        job_id: jobId, tailored_cv_id: tailoredCvId,
        include_cover_letter: includesCL, recruiter_email: job?.recruiter_email,
      })
      if (sendStatus) await updateJobStatus(jobId, sendStatus)
      toast.success('Application sent!')
      navigate('/jobs')
    } catch (e) {
      setError(e.response?.data?.detail || 'Send failed')
    } finally {
      setSending(false)
    }
  }

  const saveDraft = () => { toast.success('Draft saved'); navigate('/jobs') }

  if (!job) {
    return <div className="flex h-screen items-center justify-center bg-gray-50"><Spinner /></div>
  }

  return (
    <div className="flex flex-col h-screen bg-gray-50">
      {/* Top bar */}
      <div className="flex items-center justify-between px-5 h-14 bg-white border-b border-gray-200 shrink-0">
        <div className="flex items-center gap-3 min-w-0">
          <button onClick={() => navigate('/jobs')} className="text-sm text-gray-500 hover:text-gray-800 flex items-center gap-1">
            ← Jobs
          </button>
          <span className="text-gray-300">/</span>
          <h1 className="text-sm font-semibold text-gray-900 truncate">
            Tailor — {job.company} · {job.role}
          </h1>
        </div>
        {generating && <span className="text-xs text-gray-400 flex items-center gap-2"><Spinner /> Generating change log…</span>}
      </div>

      {error && (
        <div className="bg-red-50 border-b border-red-200 px-5 py-2 text-sm text-red-600 shrink-0">{error}</div>
      )}

      {/* 3-column body */}
      <div className="flex-1 flex overflow-hidden">
        {/* ── LEFT (280px) ── */}
        <aside className="w-[320px] shrink-0 border-r border-gray-200 bg-white overflow-y-auto p-4 space-y-5">
          {/* Job context */}
          <div className="rounded-xl border border-gray-200 p-3">
            <p className="text-sm font-semibold text-gray-900">{job.company}</p>
            <p className="text-xs text-gray-500 mb-2">{job.role}</p>
            {job.market && <MarketBadge market={job.market} />}
            <div className="flex items-center gap-2 mt-3">
              <ScorePill score={job.s1} label="B" />
              <ScorePill score={job.s1d} label="Best" />
              <ScorePill score={job.s2} label="T" />
              <ScorePill score={job.s3_master} label="F" type="s3" />
            </div>
          </div>

          {/* Domain CV used */}
          <div>
            <p className="text-[10px] uppercase tracking-wide text-gray-400 font-medium mb-1.5">Domain CV used</p>
            {selectedCV ? (
              <div className="rounded-xl border border-emerald-200 bg-emerald-50/50 p-3">
                <p className="text-sm font-medium text-gray-900">
                  {selectedCV.industry_label || 'Domain'} × {selectedCV.function_label || selectedCV.country_code}
                </p>
                <p className="text-xs text-gray-500 mt-0.5">
                  S3 {selectedCV.s3_master != null ? Math.round(selectedCV.s3_master) : '—'} · {selectedCV.status} · v{selectedCV.version}
                  {jobScores[selectedCV.id] != null && <> · Fit {Math.round(jobScores[selectedCV.id])}</>}
                </p>
                <button onClick={() => setShowCvPicker((v) => !v)} className="text-xs text-emerald-600 hover:text-emerald-700 font-medium mt-1.5">
                  Change domain CV
                </button>
              </div>
            ) : (
              <p className="text-xs text-gray-400">No domain CV selected</p>
            )}
            {showCvPicker && (
              <div className="mt-2 space-y-1">
                {[...domainCVs].sort((a, b) => (jobScores[b.id] ?? -1) - (jobScores[a.id] ?? -1)).map((cv) => (
                  <button
                    key={cv.id}
                    onClick={() => { setSelectedDomainCvId(cv.id); setShowCvPicker(false) }}
                    className={clsx('w-full text-left px-2 py-1.5 rounded-lg text-xs border flex items-center justify-between',
                      cv.id === selectedDomainCvId ? 'border-emerald-300 bg-emerald-50' : 'border-gray-100 hover:bg-gray-50')}
                  >
                    <span className="truncate">{cv.industry_label || 'Domain'} × {cv.country_code}</span>
                    {jobScores[cv.id] != null && <span className="text-gray-500 font-medium ml-2">{Math.round(jobScores[cv.id])}</span>}
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* JD Highlights */}
          <div>
            <p className="text-[10px] uppercase tracking-wide text-gray-400 font-medium mb-1.5">JD Highlights</p>
            {!highlights ? (
              <p className="text-xs text-gray-300">Analysing JD…</p>
            ) : (
              <div className="space-y-1">
                {highlights.matches?.map((m, i) => (
                  <div key={`m${i}`} className="flex items-start gap-1.5 text-xs text-gray-700">
                    <span className="text-emerald-500 mt-px">✓</span><span>{m}</span>
                  </div>
                ))}
                {highlights.gaps?.map((g, i) => (
                  <div key={`g${i}`} className="flex items-start gap-1.5 text-xs text-gray-400">
                    <span className="mt-px">○</span><span>{g}</span>
                  </div>
                ))}
                {!highlights.matches?.length && !highlights.gaps?.length && (
                  <p className="text-xs text-gray-300">No highlights extracted.</p>
                )}
              </div>
            )}
          </div>

          {/* Country rules */}
          {highlights?.country_rules?.length > 0 && (
            <div>
              <p className="text-[10px] uppercase tracking-wide text-gray-400 font-medium mb-1.5">Country rules applied</p>
              <div className="space-y-1">
                {highlights.country_rules.map((r, i) => (
                  <div key={i} className={clsx('flex items-start gap-1.5 text-xs', r.applied ? 'text-gray-700' : 'text-gray-500')}>
                    <span className={r.applied ? 'text-emerald-500' : 'text-red-400'}>{r.applied ? '✓' : '×'}</span>
                    <span>{r.text}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </aside>

        {/* ── MIDDLE (380px fixed) ── */}
        <main className="w-[380px] shrink-0 flex flex-col overflow-hidden border-r border-gray-200">
          <div className="px-5 pt-4 pb-3 border-b border-gray-100 bg-white shrink-0">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-sm font-semibold text-gray-900">
                  Change log · {changelog.length} changes · {pending.length} pending
                </h2>
                <p className="text-xs text-gray-400 mt-0.5">Golden rule: reorder / rephrase / inject keywords only — never invent.</p>
              </div>
              {changelog.length > 0 && (
                <div className="flex gap-2">
                  <Button size="sm" variant="secondary" onClick={approveAll} disabled={!pending.length}>Approve all</Button>
                  <Button size="sm" variant="ghost" onClick={rejectAll} disabled={!pending.length}>Reject all</Button>
                </div>
              )}
            </div>
          </div>

          <div className="flex-1 overflow-y-auto px-5 py-4 space-y-3">
            {generating ? (
              <div className="flex justify-center py-12"><Spinner /></div>
            ) : !tailoredCvId ? (
              autoMode === false ? (
                <div className="flex flex-col items-center justify-center py-16 text-center px-6">
                  <p className="text-sm font-medium text-gray-700 mb-1">No changes generated yet</p>
                  <p className="text-xs text-gray-400 mb-5 max-w-sm">
                    Auto mode is off — click to generate AI-powered change recommendations for this job.
                  </p>
                  <Button onClick={runGenerate}>⚡ Suggest changes</Button>
                </div>
              ) : (
                <div className="flex justify-center py-12"><Spinner /></div>
              )
            ) : changelogData === undefined ? (
              <div className="flex justify-center py-12"><Spinner /></div>
            ) : !changelog.length ? (
              <p className="text-sm text-gray-400 text-center py-12">
                No changes suggested — the domain CV already fits this role. You can still generate the tailored CV.
              </p>
            ) : (
              changelog.map((change) => {
                const isApproved = change.status === 'approved' || change.status === 'approved_edited'
                return (
                  <div key={change.id} className={clsx('rounded-xl border p-4',
                    isApproved ? 'border-emerald-200 bg-emerald-50/40' :
                    change.status === 'rejected' ? 'border-gray-200 bg-gray-50 opacity-60' : 'border-gray-200 bg-white')}>
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-2">
                        <span className={clsx('text-[10px] font-semibold px-2 py-0.5 rounded-full', CHANGE_TYPE_COLORS[change.change_type] || 'bg-gray-100 text-gray-600')}>
                          {CHANGE_TYPE_LABELS[change.change_type] || change.change_type?.replace('_', ' ').toUpperCase()}
                        </span>
                        {change.section && <span className="text-xs text-gray-500 truncate max-w-[260px]">{change.section}</span>}
                      </div>
                      {isApproved && <span className="text-xs text-emerald-600 font-medium">✓ {change.status === 'approved_edited' ? 'edited' : 'approved'}</span>}
                      {change.status === 'rejected' && <span className="text-xs text-gray-400">✗ rejected</span>}
                    </div>

                    {change.change_type !== 'deselect' ? (
                      <div className="space-y-1.5">
                        {change.original_text && <p className="text-xs text-gray-500 line-through">{change.original_text}</p>}
                        <p className="text-xs text-gray-800">{change.final_text || change.proposed_text}</p>
                      </div>
                    ) : (
                      <p className="text-xs text-red-500 line-through">{change.original_text}</p>
                    )}
                    {change.reason && <p className="text-[10px] text-gray-400 mt-1.5 italic">{change.reason}</p>}

                    {change.status === 'pending' && (
                      <div className="flex items-center gap-2 mt-3">
                        <Button size="sm" onClick={() => handleApprove(change.id)}>✓ Approve</Button>
                        <Button size="sm" variant="ghost" onClick={() => { setEditingChangeId(change.id); setEditText(change.proposed_text || '') }}>Edit</Button>
                        <Button size="sm" variant="danger" onClick={() => handleReject(change.id)}>✗ Reject</Button>
                      </div>
                    )}
                    {editingChangeId === change.id && (
                      <div className="mt-3">
                        <textarea value={editText} onChange={(e) => setEditText(e.target.value)} rows={3}
                          className="w-full px-3 py-2 border border-emerald-300 rounded-lg text-sm outline-none resize-none mb-2" />
                        <div className="flex gap-2">
                          <Button size="sm" onClick={() => handleEditApprove(change.id)}>✓ Approve edit</Button>
                          <Button size="sm" variant="ghost" onClick={() => setEditingChangeId(null)}>Cancel</Button>
                        </div>
                      </div>
                    )}
                  </div>
                )
              })
            )}
          </div>

          {/* Sticky bottom — generate tailored CV */}
          <div className="px-5 py-3 border-t border-gray-200 bg-white shrink-0 flex items-center justify-between">
            <span className="text-xs text-gray-500">
              {approved.length} approved · {rejected.length} rejected · {pending.length} pending
            </span>
            <Button onClick={handleApply} loading={applying} disabled={!allReviewed || !!applyResult}>
              ⚡ Generate tailored CV + cover letter
            </Button>
          </div>
        </main>

        {/* ── RIGHT (flex — CV/CL preview gets the most room) ── */}
        <aside className="flex-1 min-w-0 border-l border-gray-200 bg-white flex flex-col overflow-hidden">
          <div className="flex border-b border-gray-100 shrink-0">
            {[['cv', 'Tailored CV'], ['cover_letter', 'Cover Letter'], ['email', 'Email Draft']].map(([t, label]) => (
              <button key={t} onClick={() => setRightTab(t)}
                className={clsx('flex-1 px-3 py-2.5 text-xs font-medium border-b-2 transition-colors',
                  rightTab === t ? 'border-emerald-500 text-emerald-600' : 'border-transparent text-gray-500 hover:text-gray-700')}>
                {label}
              </button>
            ))}
          </div>

          <div className="flex-1 overflow-y-auto p-4">
            {!applyResult ? (
              <div className="text-center py-12 text-sm text-gray-400">
                Review the change log, then<br />“Generate tailored CV + cover letter”<br />to preview here.
              </div>
            ) : rightTab === 'cv' ? (
              <div>
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <ScorePill score={applyResult.s2_score} label="T" />
                    <ScorePill score={applyResult.s3_domain} label="F·D" type="s3" />
                    <ScorePill score={applyResult.s3_master} label="F·M" type="s3" />
                  </div>
                  <button onClick={() => downloadPDF(`/api/pdfs/tailored-cv/${tailoredCvId}`, cvFilename)}
                    className="text-xs text-emerald-600 hover:text-emerald-700 font-medium">↓ PDF</button>
                </div>
                {applyResult.s3_flags?.length > 0 && (
                  <div className="bg-red-50 border border-red-200 rounded-lg p-2 mb-2">
                    {applyResult.s3_flags.map((f, i) => <p key={i} className="text-[11px] text-red-500">{f}</p>)}
                  </div>
                )}
                <pre className="text-[11px] text-gray-700 whitespace-pre-wrap bg-gray-50 rounded-lg p-3 font-mono leading-relaxed">
                  {applyResult.tailored_cv_md}
                </pre>
              </div>
            ) : rightTab === 'cover_letter' ? (
              <div>
                <div className="flex items-center justify-between mb-2">
                  <span className="text-[11px] text-gray-500">Template: {applyResult.cl_template_used?.replace('_', ' ')}</span>
                  <div className="flex gap-2">
                    <button onClick={handleRegenerateCL} className="text-xs text-gray-500 hover:text-gray-700 font-medium">Regenerate</button>
                    <button onClick={() => downloadPDF(`/api/pdfs/cover-letter/${tailoredCvId}`, clFilename)}
                      className="text-xs text-emerald-600 hover:text-emerald-700 font-medium">↓ PDF</button>
                  </div>
                </div>
                <pre className="text-[11px] text-gray-700 whitespace-pre-wrap bg-gray-50 rounded-lg p-3 leading-relaxed">
                  {applyResult.cover_letter_md}
                </pre>
              </div>
            ) : (
              <div className="space-y-3">
                {/* Send-mode banner — where the email will actually go */}
                {sendMode && (sendMode.mode === 'production' ? (
                  <div className="bg-emerald-50 border border-emerald-200 rounded-lg px-3 py-2">
                    <p className="text-xs text-emerald-700 font-medium">
                      🟢 Production mode — email goes to{' '}
                      {job.recruiter_email || 'the recruiter (none on file — will open the portal)'}
                    </p>
                  </div>
                ) : (
                  <div className="bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
                    <p className="text-xs text-amber-700 font-medium">
                      🟠 Test mode ON — email will be sent to {sendMode.notification_email}
                      {job.recruiter_email ? `, not ${job.recruiter_email}` : ''}
                    </p>
                  </div>
                ))}

                {/* Recipient */}
                <div className="bg-gray-50 rounded-lg px-3 py-2">
                  <span className="text-[10px] uppercase tracking-wide text-gray-400 font-medium">To</span>
                  {job.recruiter_email ? (
                    <p className="text-xs text-gray-800 mt-0.5">{job.recruiter_email}</p>
                  ) : (
                    <p className="text-xs text-amber-600 mt-0.5">No recruiter email — will open the job portal</p>
                  )}
                </div>

                {/* Attachments */}
                <div className="bg-gray-50 rounded-lg px-3 py-2">
                  <span className="text-[10px] uppercase tracking-wide text-gray-400 font-medium">📎 Attachments</span>
                  <ul className="mt-1 space-y-0.5">
                    <li className="text-xs text-gray-700 truncate">• {cvFilename}</li>
                    {includesCL && <li className="text-xs text-gray-700 truncate">• {clFilename}</li>}
                  </ul>
                </div>

                <div>
                  <label className="text-[10px] uppercase tracking-wide text-gray-400 font-medium">Subject</label>
                  <input value={emailSubject} onChange={(e) => setEmailSubject(e.target.value)}
                    className="w-full mt-1 px-2.5 py-1.5 border border-gray-200 rounded-lg text-xs outline-none focus:border-emerald-400" />
                </div>
                <div>
                  <label className="text-[10px] uppercase tracking-wide text-gray-400 font-medium">Body</label>
                  <textarea value={emailBody} onChange={(e) => setEmailBody(e.target.value)} rows={8}
                    className="w-full mt-1 px-2.5 py-1.5 border border-gray-200 rounded-lg text-xs outline-none focus:border-emerald-400 resize-none leading-relaxed" />
                </div>
              </div>
            )}
          </div>

          {/* Sticky send bar */}
          <div className="px-4 py-3 border-t border-gray-200 bg-white shrink-0 space-y-2">
            {applyResult && s3Status && (
              <p className={clsx('text-[11px] font-medium px-2 py-1 rounded-md text-center',
                s3Status === 'green' ? 'bg-emerald-50 text-emerald-700' : s3Status === 'amber' ? 'bg-yellow-50 text-yellow-700' : 'bg-red-50 text-red-600')}>
                {s3Status === 'green' ? '✓ Safe to send' : s3Status === 'amber' ? '⚠ Review before sending' : '✗ Blocked — invented content'}
              </p>
            )}
            <div className="flex items-center gap-2 text-xs">
              <span className="text-gray-400">Status:</span>
              <select value={sendStatus} onChange={(e) => setSendStatus(e.target.value)}
                className="flex-1 border border-gray-200 rounded-lg px-2 py-1 outline-none capitalize">
                {SEND_STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            </div>
            <label className="flex items-center gap-2 text-xs text-gray-600">
              <input type="checkbox" checked={includesCL} onChange={(e) => setIncludesCL(e.target.checked)} className="w-3.5 h-3.5 rounded" />
              Include cover letter
            </label>
            {job.recruiter_email && (
              <p className="text-[11px] text-gray-400 truncate">Send via: {job.recruiter_email}</p>
            )}
            <div className="flex gap-2">
              <Button size="sm" className="flex-1" onClick={handleSend} loading={sending} disabled={!canSend}>
                📤 Send application
              </Button>
              <Button size="sm" variant="ghost" onClick={saveDraft}>Save draft</Button>
            </div>
          </div>
        </aside>
      </div>
    </div>
  )
}
