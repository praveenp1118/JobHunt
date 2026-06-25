import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { formatDistanceToNow } from 'date-fns'
import {
  getDomainCVs, getMasterCV,
  generateDomainChangelog, getDomainChangelog,
  approveChange, rejectChange, editChange, bulkChangeAction,
  applyDomainCV,
} from '../../api/cvs'
import client from '../../api/client'
import Button from '../../components/ui/Button'
import Spinner from '../../components/ui/Spinner'
import { ScorePill } from '../../components/ui/ScorePill'
import { fmtTokens } from '../../components/ui/TokenBadge'
import { toast } from '../../store/toast'

const STATUS_CONFIG = {
  active:         { label: 'Active',        classes: 'bg-emerald-100 text-emerald-700' },
  stale:          { label: 'Stale',         classes: 'bg-yellow-100 text-yellow-700' },
  review_required:{ label: 'Review',        classes: 'bg-amber-100 text-amber-700' },
  blocked:        { label: 'Blocked',       classes: 'bg-red-100 text-red-600' },
  regenerating:   { label: 'Generating…',   classes: 'bg-blue-100 text-blue-600' },
}

const CHANGE_TYPE_COLORS = {
  rephrase:          'bg-blue-100 text-blue-700',
  keyword_injection: 'bg-purple-100 text-purple-700',
  reorder:           'bg-gray-100 text-gray-600',
  deselect:          'bg-red-100 text-red-600',
}

export default function DomainCVsTab() {
  const qc = useQueryClient()
  const [showWizard, setShowWizard] = useState(false)
  const [selectedCvId, setSelectedCvId] = useState(null)
  const [showChangelog, setShowChangelog] = useState(false)
  const [applying, setApplying] = useState(false)
  const [error, setError] = useState('')

  const { data: masterData } = useQuery({ queryKey: ['master-cv'], queryFn: getMasterCV })
  const { data: domainData, isLoading } = useQuery({ queryKey: ['domain-cvs'], queryFn: getDomainCVs })

  const domainCVs = domainData?.data || []
  const hasMaster = !!masterData?.data

  const handleApply = async (cvId) => {
    setApplying(true)
    setError('')
    try {
      const res = await applyDomainCV(cvId)
      qc.invalidateQueries({ queryKey: ['domain-cvs'] })
      setShowChangelog(false)
      setSelectedCvId(null)
      const tk = res.data?.tokens_used
      toast.success(tk ? `✅ Domain CV applied · ⚡ ${fmtTokens(tk)} · ₹${(res.data.cost_inr || 0).toFixed(2)}` : '✅ Domain CV applied')
    } catch (e) {
      setError(e.response?.data?.detail || 'Apply failed')
    } finally {
      setApplying(false)
    }
  }

  if (isLoading) return <div className="flex justify-center py-12"><Spinner /></div>

  return (
    <div>
      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg px-3 py-2 text-sm text-red-600 mb-4">{error}</div>
      )}

      {/* No master CV warning */}
      {!hasMaster && (
        <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 mb-5">
          <p className="text-sm text-amber-700">
            ⚠️ Upload your master CV first before generating domain CVs.
          </p>
        </div>
      )}

      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <p className="text-sm text-gray-600">
          {domainCVs.length} domain {domainCVs.length === 1 ? 'CV' : 'CVs'} — each tailored for a specific industry × function × country
        </p>
        <Button size="sm" onClick={() => setShowWizard(true)} disabled={!hasMaster}>
          + Generate domain CV
        </Button>
      </div>

      {/* Domain CV list */}
      {domainCVs.length === 0 ? (
        <div className="bg-white rounded-2xl border border-gray-200 p-12 text-center">
          <p className="text-sm text-gray-500 mb-4">No domain CVs yet</p>
          <Button onClick={() => setShowWizard(true)} disabled={!hasMaster}>Generate your first domain CV</Button>
        </div>
      ) : (
        <div className="grid gap-3">
          {domainCVs.map((cv) => {
            const statusCfg = STATUS_CONFIG[cv.status] || STATUS_CONFIG.active
            return (
              <div key={cv.id} className={`bg-white rounded-xl border-2 p-5 transition-colors ${
                cv.status === 'stale' ? 'border-yellow-200' : cv.status === 'blocked' ? 'border-red-200' : 'border-gray-100'
              }`}>
                <div className="flex items-start justify-between">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <h3 className="text-sm font-semibold text-gray-900">
                        {cv.industry_label || 'Industry'} × {cv.function_label || 'Function'}
                      </h3>
                      <span className={`text-[10px] font-medium px-2 py-0.5 rounded-full ${statusCfg.classes}`}>
                        {statusCfg.label}
                      </span>
                    </div>
                    <p className="text-xs text-gray-500">
                      {cv.country_name || cv.country_code} · v{cv.version} ·{' '}
                      {formatDistanceToNow(new Date(cv.updated_at), { addSuffix: true })}
                    </p>

                    {/* Stale notice */}
                    {cv.status === 'stale' && (
                      <p className="text-xs text-yellow-600 mt-1.5">
                        Master CV was updated — regenerate to sync
                      </p>
                    )}
                    {cv.status === 'blocked' && (
                      <p className="text-xs text-red-500 mt-1.5">
                        S3 below threshold — regenerate before using
                      </p>
                    )}
                  </div>

                  <div className="flex items-center gap-3 shrink-0 ml-4">
                    {/* S3 scores */}
                    <div className="flex items-center gap-2">
                      <ScorePill score={cv.s3_domain} label="F·Domain" type="s3" />
                      <ScorePill score={cv.s3_master} label="F·Master" type="s3" />
                    </div>

                    <div className="flex gap-2">
                      {(cv.status === 'stale' || cv.status === 'blocked') && (
                        <Button
                          size="sm"
                          variant="secondary"
                          onClick={async () => {
                            try {
                              await client.post(`/cvs/domains/${cv.id}/regenerate`)
                              qc.invalidateQueries({ queryKey: ['domain-cvs'] })
                            } catch (e) {
                              setError('Regenerate failed')
                            }
                          }}
                        >
                          Regenerate
                        </Button>
                      )}
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => {
                          setSelectedCvId(cv.id)
                          setShowChangelog(true)
                        }}
                      >
                        View changes
                      </Button>
                    </div>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}

      {/* ── Generate wizard ── */}
      {showWizard && (
        <GenerateWizard
          onClose={() => setShowWizard(false)}
          onSuccess={() => {
            qc.invalidateQueries({ queryKey: ['domain-cvs'] })
            setShowWizard(false)
          }}
        />
      )}

      {/* ── Changelog panel ── */}
      {showChangelog && selectedCvId && (
        <ChangelogPanel
          domainCvId={selectedCvId}
          onClose={() => { setShowChangelog(false); setSelectedCvId(null) }}
          onApply={() => handleApply(selectedCvId)}
          applying={applying}
        />
      )}
    </div>
  )
}

// ── Generate wizard ───────────────────────────────────────────────────────────

function GenerateWizard({ onClose, onSuccess }) {
  const [industryId, setIndustryId] = useState('')
  const [functionId, setFunctionId] = useState('')
  const [countryCode, setCountryCode] = useState('NL')
  const [generating, setGenerating] = useState(false)
  const [error, setError] = useState('')

  const { data: industriesData } = useQuery({
    queryKey: ['industries'],
    queryFn: () => client.get('/auth/admin/industries'),
    retry: false,
  })

  const { data: functionsData } = useQuery({
    queryKey: ['functions'],
    queryFn: () => client.get('/auth/admin/functions'),
    retry: false,
  })

  const industries = industriesData?.data || []
  const functions = functionsData?.data || []

  // Fallback: use seeded data if admin endpoints not available
  const industryOptions = industries.length > 0 ? industries : FALLBACK_INDUSTRIES
  const functionOptions = functions.length > 0 ? functions : FALLBACK_FUNCTIONS

  const handleGenerate = async () => {
    if (!industryId || !functionId || !countryCode) {
      setError('Select all three fields')
      return
    }
    setGenerating(true)
    setError('')
    try {
      const res = await generateDomainChangelog(industryId, functionId, countryCode)
      const tk = res.data?.tokens_used
      toast.success(tk
        ? `${res.data.change_count} changes generated · ⚡ ${fmtTokens(tk)} · ₹${(res.data.cost_inr || 0).toFixed(2)}`
        : `${res.data?.change_count ?? ''} changes generated`)
      onSuccess()
    } catch (e) {
      const msg = e.response?.data?.detail || 'Generation failed. Check your Anthropic API key in Settings.'
      setError(msg)
      toast.error(msg)
    } finally {
      setGenerating(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg">
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
          <h2 className="text-base font-semibold text-gray-900">Generate domain CV</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="px-6 py-5 space-y-4">
          <p className="text-sm text-gray-600">Claude will tailor your master CV for this specific combination.</p>

          <div>
            <label className="text-sm font-medium text-gray-700 block mb-1.5">Industry vertical</label>
            <select
              value={industryId}
              onChange={(e) => setIndustryId(e.target.value)}
              className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm outline-none focus:border-emerald-400"
            >
              <option value="">Select industry...</option>
              {industryOptions.map((ind) => (
                <option key={ind.id} value={ind.id}>{ind.label}</option>
              ))}
            </select>
          </div>

          <div>
            <label className="text-sm font-medium text-gray-700 block mb-1.5">Functional discipline</label>
            <select
              value={functionId}
              onChange={(e) => setFunctionId(e.target.value)}
              className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm outline-none focus:border-emerald-400"
            >
              <option value="">Select function...</option>
              {functionOptions.map((fn) => (
                <option key={fn.id} value={fn.id}>{fn.label}</option>
              ))}
            </select>
          </div>

          <div>
            <label className="text-sm font-medium text-gray-700 block mb-1.5">Target market</label>
            <select
              value={countryCode}
              onChange={(e) => setCountryCode(e.target.value)}
              className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm outline-none focus:border-emerald-400"
            >
              <option value="NL">Netherlands (GDPR)</option>
              <option value="EU">EU General (GDPR)</option>
              <option value="DU">Dubai / UAE</option>
              <option value="SG">Singapore</option>
              <option value="IN">India</option>
            </select>
          </div>

          {error && (
            <div className="bg-red-50 border border-red-200 rounded-lg px-3 py-2 text-sm text-red-600">{error}</div>
          )}
        </div>

        <div className="px-6 py-4 border-t border-gray-100 flex justify-between">
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button onClick={handleGenerate} loading={generating}>
            Generate change log →
          </Button>
        </div>
      </div>
    </div>
  )
}

// ── Changelog panel ───────────────────────────────────────────────────────────

function ChangelogPanel({ domainCvId, onClose, onApply, applying }) {
  const qc = useQueryClient()
  const [editingId, setEditingId] = useState(null)
  const [editText, setEditText] = useState('')

  const { data, refetch } = useQuery({
    queryKey: ['domain-changelog', domainCvId],
    queryFn: () => getDomainChangelog(domainCvId),
  })

  const changelog = data?.data || []
  const pending = changelog.filter((c) => c.status === 'pending').length

  const handle = async (fn) => { await fn(); refetch() }

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[88vh] flex flex-col">
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
          <h2 className="text-base font-semibold text-gray-900">Change log</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-5">
          {changelog.length === 0 ? (
            <div className="flex justify-center py-8"><Spinner /></div>
          ) : (
            <div className="space-y-3">
              <div className="flex justify-end gap-2 mb-2">
                <Button size="sm" variant="secondary" onClick={() => handle(() => bulkChangeAction(domainCvId, 'approve_all'))}>
                  Approve all
                </Button>
                <Button size="sm" variant="ghost" onClick={() => handle(() => bulkChangeAction(domainCvId, 'reject_all'))}>
                  Reject all
                </Button>
              </div>

              {changelog.map((change) => (
                <div key={change.id} className={`rounded-xl border p-4 ${
                  change.status === 'approved' || change.status === 'approved_edited'
                    ? 'border-emerald-200 bg-emerald-50/50'
                    : change.status === 'rejected'
                    ? 'border-gray-100 bg-gray-50 opacity-60'
                    : 'border-gray-200'
                }`}>
                  <div className="flex items-center gap-2 mb-2">
                    <span className={`text-[10px] font-medium px-2 py-0.5 rounded-full ${CHANGE_TYPE_COLORS[change.change_type] || 'bg-gray-100 text-gray-600'}`}>
                      {change.change_type?.replace('_', ' ')}
                    </span>
                    {change.section && <span className="text-xs text-gray-500 truncate">{change.section}</span>}
                    <span className="ml-auto text-xs">
                      {change.status === 'approved' && <span className="text-emerald-600 font-medium">✓ approved</span>}
                      {change.status === 'approved_edited' && <span className="text-emerald-600 font-medium">✓ edited</span>}
                      {change.status === 'rejected' && <span className="text-gray-400">✗ rejected</span>}
                    </span>
                  </div>

                  {change.original_text && (
                    <p className="text-xs text-gray-400 line-through mb-1">{change.original_text}</p>
                  )}
                  <p className="text-xs text-gray-800">{change.final_text || change.proposed_text}</p>
                  {change.reason && <p className="text-[10px] text-gray-400 mt-1 italic">{change.reason}</p>}

                  {change.status === 'pending' && (
                    <div className="flex gap-2 mt-3">
                      <Button size="sm" onClick={() => handle(() => approveChange(domainCvId, change.id))}>✓</Button>
                      <Button size="sm" variant="ghost" onClick={() => { setEditingId(change.id); setEditText(change.proposed_text || '') }}>Edit</Button>
                      <Button size="sm" variant="danger" onClick={() => handle(() => rejectChange(domainCvId, change.id))}>✗</Button>
                    </div>
                  )}

                  {editingId === change.id && (
                    <div className="mt-3">
                      <textarea value={editText} onChange={(e) => setEditText(e.target.value)} rows={3}
                        className="w-full px-3 py-2 border border-emerald-300 rounded-lg text-sm outline-none resize-none mb-2" />
                      <div className="flex gap-2">
                        <Button size="sm" onClick={() => handle(async () => { await editChange(domainCvId, change.id, editText); setEditingId(null) })}>
                          Approve edit
                        </Button>
                        <Button size="sm" variant="ghost" onClick={() => setEditingId(null)}>Cancel</Button>
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="px-6 py-4 border-t border-gray-100 flex justify-between">
          <Button variant="ghost" onClick={onClose}>Close</Button>
          <Button onClick={onApply} loading={applying} disabled={pending > 0}>
            {pending > 0 ? `Review ${pending} pending changes first` : 'Apply & compute S3 →'}
          </Button>
        </div>
      </div>
    </div>
  )
}

// Fallback industry/function options using seeded codes
const FALLBACK_INDUSTRIES = [
  { id: 'EC', label: 'eCommerce & Marketplace' },
  { id: 'AI', label: 'AI & Data Products' },
  { id: 'FP', label: 'Fintech & Payments' },
  { id: 'SC', label: 'Supply Chain & Operations' },
  { id: 'BS', label: 'B2B SaaS & Platform' },
]

const FALLBACK_FUNCTIONS = [
  { id: 'PB', label: 'P&L Ownership & Biz Building' },
  { id: 'ML', label: 'AI & ML Product Management' },
  { id: 'GR', label: 'Growth & Monetisation' },
  { id: 'PL', label: 'Platform & API Products' },
  { id: 'OA', label: 'Operations & Automation' },
]
