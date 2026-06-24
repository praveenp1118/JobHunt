import { useState, useEffect } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { getJob } from '../../api/jobs'
import { getDomainCVs } from '../../api/cvs'
import {
  generateTailor, getTailorChangelog, approveChange, rejectChange,
  editChange, applyTailor, regenerateCL, sendApplication,
} from '../../api/jobs'
import Button from '../../components/ui/Button'
import Spinner from '../../components/ui/Spinner'
import { ScorePill } from '../../components/ui/ScorePill'

import { toast } from '../../store/toast'

async function downloadPDF(url, filename) {
  const raw = localStorage.getItem('jobhunt-auth')
  let token = ''
  if (raw) { try { token = JSON.parse(raw).state?.token || '' } catch (_) {} }
  const res = await fetch(url, { headers: { Authorization: `Bearer ${token}` } })
  if (!res.ok) { alert('PDF generation failed — check backend logs'); return }
  const blob = await res.blob()
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = filename
  a.click()
  URL.revokeObjectURL(a.href)
}

const STEP_LABELS = ['Select domain CV', 'Review changes', 'Preview & send']
const CHANGE_TYPE_COLORS = {
  rephrase: 'bg-blue-100 text-blue-700',
  keyword_injection: 'bg-purple-100 text-purple-700',
  reorder: 'bg-gray-100 text-gray-600',
  deselect: 'bg-red-100 text-red-600',
}

export default function TailorOverlay({ jobId, onClose, onSuccess }) {
  const qc = useQueryClient()
  const [step, setStep] = useState(1)
  const [selectedDomainCvId, setSelectedDomainCvId] = useState(null)

  // Pre-select the best-fit domain CV (highest score), falling back to the
  // feed/alert-detected one.
  useEffect(() => {
    const preselect = job?.best_domain_cv_id || job?.detected_domain_cv_id
    if (preselect) setSelectedDomainCvId(preselect)
  }, [job?.best_domain_cv_id, job?.detected_domain_cv_id])
  const [tailoredCvId, setTailoredCvId] = useState(null)
  const [generating, setGenerating] = useState(false)
  const [applying, setApplying] = useState(false)
  const [sending, setSending] = useState(false)
  const [error, setError] = useState('')
  const [applyResult, setApplyResult] = useState(null)
  const [previewTab, setPreviewTab] = useState('cv')
  const [editingChangeId, setEditingChangeId] = useState(null)
  const [editText, setEditText] = useState('')
  const [includesCL, setIncludesCL] = useState(true)

  const { data: jobData } = useQuery({
    queryKey: ['job', jobId],
    queryFn: () => getJob(jobId),
  })

  const { data: domainCVsData } = useQuery({
    queryKey: ['domain-cvs'],
    queryFn: getDomainCVs,
  })

  const { data: changelogData, refetch: refetchChangelog } = useQuery({
    queryKey: ['tailor-changelog', tailoredCvId],
    queryFn: () => getTailorChangelog(tailoredCvId),
    enabled: !!tailoredCvId,
  })

  const job = jobData?.data
  const domainCVs = domainCVsData?.data || []
  const changelog = changelogData?.data || []

  // Per-domain-CV fit scores for THIS job (from the multi-domain scoring at ingest).
  const jobScores = job?.domain_cv_scores || {}
  const bestId = job?.best_domain_cv_id ? String(job.best_domain_cv_id) : null
  // Show best-fit CVs first.
  const sortedCVs = [...domainCVs].sort(
    (a, b) => (jobScores[b.id] ?? -1) - (jobScores[a.id] ?? -1)
  )

  const pendingCount = changelog.filter((c) => c.status === 'pending').length
  const approvedCount = changelog.filter((c) => c.status === 'approved' || c.status === 'approved_edited').length

  const handleGenerate = async () => {
    if (!selectedDomainCvId) return
    setError('')
    setGenerating(true)
    try {
      const res = await generateTailor(jobId, selectedDomainCvId)
      setTailoredCvId(res.data.tailored_cv_id)
      setStep(2)
    } catch (e) {
      setError(e.response?.data?.detail || 'Generation failed. Check your Anthropic API key in Settings.')
    } finally {
      setGenerating(false)
    }
  }

  const handleApprove = async (changeId) => {
    await approveChange(tailoredCvId, changeId)
    refetchChangelog()
  }

  const handleReject = async (changeId) => {
    await rejectChange(tailoredCvId, changeId)
    refetchChangelog()
  }

  const handleEditApprove = async (changeId) => {
    await editChange(tailoredCvId, changeId, editText)
    setEditingChangeId(null)
    refetchChangelog()
  }

  const handleApply = async () => {
    setError('')
    setApplying(true)
    try {
      const res = await applyTailor(tailoredCvId)
      setApplyResult(res.data)
      setStep(3)
    } catch (e) {
      setError(e.response?.data?.detail || 'Apply failed')
    } finally {
      setApplying(false)
    }
  }

  const handleSend = async () => {
    if (!job?.recruiter_email && applyResult?.s3_status !== 'green') {
      setError('S3 is below threshold — check for invented content before sending')
      return
    }
    setSending(true)
    setError('')
    try {
      await sendApplication({
        job_id: jobId,
        tailored_cv_id: tailoredCvId,
        include_cover_letter: includesCL,
        recruiter_email: job?.recruiter_email,
      })
      toast.success('Application sent!')
      onSuccess()
    } catch (e) {
      setError(e.response?.data?.detail || 'Send failed')
    } finally {
      setSending(false)
    }
  }

  const handleRegenerateCL = async () => {
    try {
      const res = await regenerateCL(tailoredCvId, applyResult?.cl_template_used)
      setApplyResult((prev) => ({ ...prev, cover_letter_md: res.data.cover_letter_md, cl_template_used: res.data.template_used }))
    } catch (e) {
      console.error(e)
    }
  }

  const s3Status = applyResult?.s3_status
  const s3Color = s3Status === 'green' ? 'bg-emerald-100 text-emerald-700' : s3Status === 'amber' ? 'bg-yellow-100 text-yellow-700' : 'bg-red-100 text-red-600'

  return (
    <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-3xl max-h-[92vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
          <div>
            <h2 className="text-base font-semibold text-gray-900">
              Tailor — {job?.company} · {job?.role}
            </h2>
            <div className="flex items-center gap-3 mt-1">
              {STEP_LABELS.map((label, i) => (
                <div key={i} className="flex items-center gap-1.5">
                  <div className={`w-5 h-5 rounded-full text-[10px] font-bold flex items-center justify-center ${
                    step > i + 1 ? 'bg-emerald-500 text-white' : step === i + 1 ? 'bg-slate-800 text-white' : 'bg-gray-200 text-gray-500'
                  }`}>
                    {step > i + 1 ? '✓' : i + 1}
                  </div>
                  <span className={`text-xs ${step === i + 1 ? 'text-gray-900 font-medium' : 'text-gray-400'}`}>{label}</span>
                  {i < 2 && <span className="text-gray-300 text-xs">→</span>}
                </div>
              ))}
            </div>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-5">
          {error && (
            <div className="bg-red-50 border border-red-200 rounded-lg px-3 py-2 text-sm text-red-600 mb-4">
              {error}
            </div>
          )}

          {/* ── Step 1: Select domain CV ── */}
          {step === 1 && (
            <div>
              <p className="text-sm text-gray-600 mb-4">
                Select the domain CV to tailor from. Claude will generate bounded changes for <strong>{job?.role}</strong> at <strong>{job?.company}</strong>.
              </p>
              {domainCVs.length === 0 ? (
                <div className="text-center py-8 bg-gray-50 rounded-xl">
                  <p className="text-sm text-gray-500 mb-2">No domain CVs yet</p>
                  <p className="text-xs text-gray-400">Generate a domain CV first in My CVs → Domain CVs</p>
                </div>
              ) : (
                <div className="space-y-2">
                  {sortedCVs.map((cv) => {
                    const fit = jobScores[cv.id]
                    const isBest = bestId && String(cv.id) === bestId
                    return (
                    <div
                      key={cv.id}
                      onClick={() => setSelectedDomainCvId(cv.id)}
                      className={`flex items-center justify-between p-4 rounded-xl border-2 cursor-pointer transition-colors ${
                        selectedDomainCvId === cv.id
                          ? 'border-emerald-400 bg-emerald-50'
                          : 'border-gray-100 hover:border-gray-200 bg-white'
                      } ${cv.status === 'blocked' ? 'opacity-50 cursor-not-allowed' : ''}`}
                    >
                      <div>
                        <p className="text-sm font-medium text-gray-900 flex items-center gap-2">
                          {cv.industry_label || 'Domain CV'} × {cv.function_label || 'Function'}
                          {isBest && (
                            <span className="text-[10px] bg-emerald-100 text-emerald-700 px-1.5 py-0.5 rounded-full font-medium">
                              best fit
                            </span>
                          )}
                        </p>
                        <p className="text-xs text-gray-500 mt-0.5">
                          {cv.country_name || cv.country_code} · v{cv.version} ·{' '}
                          <span className={cv.status === 'active' ? 'text-emerald-600' : cv.status === 'stale' ? 'text-yellow-600' : 'text-red-500'}>
                            {cv.status}
                          </span>
                        </p>
                      </div>
                      <div className="flex items-center gap-3">
                        {fit !== undefined && fit !== null && (
                          <ScorePill score={fit} label="Fit" />
                        )}
                        {cv.s3_master !== null && (
                          <ScorePill score={cv.s3_master} label="F·M" type="s3" />
                        )}
                        {selectedDomainCvId === cv.id && (
                          <div className="w-5 h-5 rounded-full bg-emerald-500 flex items-center justify-center">
                            <svg className="w-3 h-3 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
                            </svg>
                          </div>
                        )}
                      </div>
                    </div>
                    )
                  })}
                </div>
              )}
            </div>
          )}

          {/* ── Step 2: Review changelog ── */}
          {step === 2 && (
            <div>
              <div className="flex items-center justify-between mb-4">
                <p className="text-sm text-gray-600">
                  Review each proposed change. <strong>{approvedCount}</strong> approved · <strong>{pendingCount}</strong> pending.
                </p>
                <div className="flex gap-2">
                  <Button size="sm" variant="secondary" onClick={async () => {
                    for (const c of changelog.filter((x) => x.status === 'pending')) {
                      await approveChange(tailoredCvId, c.id)
                    }
                    refetchChangelog()
                  }}>
                    Approve all
                  </Button>
                  <Button size="sm" variant="ghost" onClick={async () => {
                    for (const c of changelog.filter((x) => x.status === 'pending')) {
                      await rejectChange(tailoredCvId, c.id)
                    }
                    refetchChangelog()
                  }}>
                    Reject all
                  </Button>
                </div>
              </div>

              {changelog.length === 0 ? (
                <div className="flex justify-center py-8"><Spinner /></div>
              ) : (
                <div className="space-y-3">
                  {changelog.map((change) => (
                    <div
                      key={change.id}
                      className={`rounded-xl border p-4 transition-colors ${
                        change.status === 'approved' || change.status === 'approved_edited'
                          ? 'border-emerald-200 bg-emerald-50/50'
                          : change.status === 'rejected'
                          ? 'border-gray-200 bg-gray-50 opacity-60'
                          : 'border-gray-200 bg-white'
                      }`}
                    >
                      <div className="flex items-center justify-between mb-2">
                        <div className="flex items-center gap-2">
                          <span className={`text-[10px] font-medium px-2 py-0.5 rounded-full ${CHANGE_TYPE_COLORS[change.change_type] || 'bg-gray-100 text-gray-600'}`}>
                            {change.change_type?.replace('_', ' ')}
                          </span>
                          {change.section && (
                            <span className="text-xs text-gray-500 truncate max-w-[200px]">{change.section}</span>
                          )}
                        </div>
                        {(change.status === 'approved' || change.status === 'approved_edited') && (
                          <span className="text-xs text-emerald-600 font-medium">
                            ✓ {change.status === 'approved_edited' ? 'approved (edited)' : 'approved'}
                          </span>
                        )}
                        {change.status === 'rejected' && (
                          <span className="text-xs text-gray-400">✗ rejected</span>
                        )}
                      </div>

                      {change.change_type !== 'deselect' ? (
                        <div className="space-y-1.5">
                          {change.original_text && (
                            <p className="text-xs text-gray-500 line-through">{change.original_text}</p>
                          )}
                          <p className="text-xs text-gray-800">
                            {change.final_text || change.proposed_text}
                          </p>
                        </div>
                      ) : (
                        <p className="text-xs text-red-500 line-through">{change.original_text}</p>
                      )}

                      {change.reason && (
                        <p className="text-[10px] text-gray-400 mt-1.5 italic">{change.reason}</p>
                      )}

                      {change.status === 'pending' && (
                        <div className="flex items-center gap-2 mt-3">
                          <Button size="sm" onClick={() => handleApprove(change.id)}>✓ Approve</Button>
                          <Button size="sm" variant="ghost" onClick={() => {
                            setEditingChangeId(change.id)
                            setEditText(change.proposed_text || '')
                          }}>Edit</Button>
                          <Button size="sm" variant="danger" onClick={() => handleReject(change.id)}>✗ Reject</Button>
                        </div>
                      )}

                      {editingChangeId === change.id && (
                        <div className="mt-3">
                          <textarea
                            value={editText}
                            onChange={(e) => setEditText(e.target.value)}
                            rows={3}
                            className="w-full px-3 py-2 border border-emerald-300 rounded-lg text-sm outline-none resize-none mb-2"
                          />
                          <div className="flex gap-2">
                            <Button size="sm" onClick={() => handleEditApprove(change.id)}>✓ Approve edit</Button>
                            <Button size="sm" variant="ghost" onClick={() => setEditingChangeId(null)}>Cancel</Button>
                          </div>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* ── Step 3: Preview & send ── */}
          {step === 3 && applyResult && (
            <div>
              {/* Scores */}
              <div className="flex items-center gap-4 mb-5 p-4 bg-gray-50 rounded-xl">
                <div className="flex items-center gap-3">
                  <ScorePill score={applyResult.s2_score} label="T (fit)" />
                  <ScorePill score={applyResult.s3_domain} label="F·Domain" type="s3" />
                  <ScorePill score={applyResult.s3_master} label="F·Master" type="s3" />
                  <span className={`text-xs font-medium px-2.5 py-1 rounded-full ${s3Color}`}>
                    {s3Status === 'green' ? '✓ Safe to send' : s3Status === 'amber' ? '⚠ Review before sending' : '✗ Blocked — invented content'}
                  </span>
                </div>
              </div>

              {applyResult.s3_flags?.length > 0 && (
                <div className="bg-red-50 border border-red-200 rounded-lg p-3 mb-4">
                  <p className="text-xs font-medium text-red-600 mb-1">Integrity flags — review these:</p>
                  {applyResult.s3_flags.map((f, i) => (
                    <p key={i} className="text-xs text-red-500">{f}</p>
                  ))}
                </div>
              )}

              {/* Preview tabs */}
              <div className="flex gap-0 border-b border-gray-100 mb-4">
                {['cv', 'cover_letter', 'email'].map((t) => (
                  <button
                    key={t}
                    onClick={() => setPreviewTab(t)}
                    className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
                      previewTab === t
                        ? 'border-emerald-500 text-emerald-600'
                        : 'border-transparent text-gray-500 hover:text-gray-700'
                    }`}
                  >
                    {t === 'cv' ? 'Tailored CV' : t === 'cover_letter' ? 'Cover Letter' : 'Email Draft'}
                  </button>
                ))}
              </div>

              {previewTab === 'cv' && (
                <div>
                  <div className="flex justify-end mb-2">
                    <button onClick={() => downloadPDF(`/api/pdfs/tailored-cv/${tailoredCvId}`, 'CV_Tailored.pdf')}
                      className="text-xs text-emerald-600 hover:text-emerald-700 font-medium">
                      ↓ Download PDF
                    </button>
                  </div>
                  <pre className="text-xs text-gray-700 whitespace-pre-wrap bg-gray-50 rounded-lg p-4 max-h-80 overflow-y-auto font-mono leading-relaxed">
                    {applyResult.tailored_cv_md}
                  </pre>
                </div>
              )}

              {previewTab === 'cover_letter' && (
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-xs text-gray-500">Template: {applyResult.cl_template_used?.replace('_', ' ')}</span>
                    <div className="flex gap-3">
                      <button onClick={() => downloadPDF(`/api/pdfs/cover-letter/${tailoredCvId}`, 'CoverLetter.pdf')}
                        className="text-xs text-emerald-600 hover:text-emerald-700 font-medium">
                        ↓ Download PDF
                      </button>
                      <button onClick={handleRegenerateCL} className="text-xs text-gray-500 hover:text-gray-700 font-medium">
                        Regenerate with different template
                      </button>
                    </div>
                  </div>
                  <pre className="text-xs text-gray-700 whitespace-pre-wrap bg-gray-50 rounded-lg p-4 max-h-80 overflow-y-auto leading-relaxed">
                    {applyResult.cover_letter_md}
                  </pre>
                </div>
              )}

              {previewTab === 'email' && (
                <pre className="text-xs text-gray-700 whitespace-pre-wrap bg-gray-50 rounded-lg p-4 max-h-80 overflow-y-auto leading-relaxed">
                  {applyResult.email_draft}
                </pre>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-gray-100 flex justify-between items-center">
          <Button variant="ghost" onClick={step === 1 ? onClose : () => setStep(step - 1)}>
            {step === 1 ? 'Cancel' : '← Back'}
          </Button>

          <div className="flex items-center gap-3">
            {step === 1 && (
              <Button
                onClick={handleGenerate}
                loading={generating}
                disabled={!selectedDomainCvId}
              >
                Generate →
              </Button>
            )}
            {step === 2 && (
              <Button onClick={handleApply} loading={applying}>
                Apply & preview →
              </Button>
            )}
            {step === 3 && (
              <>
                {s3Status !== 'blocked' && (
                  <>
                    <label className="flex items-center gap-2 text-sm text-gray-600 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={includesCL}
                        onChange={(e) => setIncludesCL(e.target.checked)}
                        className="w-4 h-4 rounded border-gray-300 text-emerald-600"
                      />
                      Include cover letter
                    </label>
                    <Button variant="secondary" onClick={handleSend} loading={sending}>
                      Send {includesCL ? 'with CL' : 'without CL'}
                    </Button>
                  </>
                )}
                {s3Status === 'blocked' && (
                  <span className="text-xs text-red-500">Fix integrity issues before sending</span>
                )}
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
