import { useState, useRef } from 'react'
import Button from '../../components/ui/Button'
import Input from '../../components/ui/Input'
import Spinner from '../../components/ui/Spinner'
import { ScorePill } from '../../components/ui/ScorePill'
import TokenBadge from '../../components/ui/TokenBadge'
import CommunityInsights from '../../components/community/CommunityInsights'
import { parseJobFromText, parseJobFromURL, confirmJob } from '../../api/jobs'

export default function AddJobModal({ onClose, onSuccess }) {
  const [mode, setMode] = useState('text') // text | url | file
  const [step, setStep] = useState(1) // 1=input, 2=preview, 3=saving
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const fileRef = useRef()

  // Input state
  const [text, setText] = useState('')
  const [url, setUrl] = useState('')
  const [file, setFile] = useState(null)

  // Parse result
  const [parseResult, setParseResult] = useState(null)

  // Editable confirm fields
  const [company, setCompany] = useState('')
  const [role, setRole] = useState('')
  const [location, setLocation] = useState('')
  const [market, setMarket] = useState('')
  const [recruiterEmail, setRecruiterEmail] = useState('')
  const [portalUrl, setPortalUrl] = useState('')

  const handleParse = async () => {
    setError('')
    setLoading(true)
    try {
      let res
      if (mode === 'text') {
        if (!text.trim()) { setError('Paste the job description first'); return }
        res = await parseJobFromText(text)
      } else if (mode === 'url') {
        if (!url.trim()) { setError('Enter a URL'); return }
        res = await parseJobFromURL(url)
      } else {
        if (!file) { setError('Select a file'); return }
        const formData = new FormData()
        formData.append('file', file)
        const { default: client } = await import('../../api/client')
        res = await client.post('/jobs/parse/file', formData, {
          headers: { 'Content-Type': 'multipart/form-data' },
        })
      }

      const result = res.data
      if (result.is_duplicate) {
        setError(`This job already exists in your tracker (${result.company} — ${result.role})`)
        return
      }

      setParseResult(result)
      setCompany(result.company || '')
      setRole(result.role || '')
      setLocation(result.location || '')
      setMarket(result.market || '')
      setRecruiterEmail(result.recruiter_email || '')
      setPortalUrl('')
      setStep(2)
    } catch (err) {
      setError(err.response?.data?.detail || 'Parse failed. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  const handleConfirm = async () => {
    if (!company || !role) { setError('Company and role are required'); return }
    setError('')
    setLoading(true)
    setStep(3)
    try {
      await confirmJob(parseResult.temp_id, {
        company, role, location, market,
        recruiter_email: recruiterEmail || null,
        portal_url: portalUrl || null,
      })
      onSuccess()
    } catch (err) {
      setError(err.response?.data?.detail || 'Save failed')
      setStep(2)
    } finally {
      setLoading(false)
    }
  }

  const s1 = parseResult?.s1_score
  const passed = parseResult?.pre_filter_passed

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
          <h2 className="text-base font-semibold text-gray-900">
            {step === 1 ? 'Add job' : step === 2 ? 'Review parsed details' : 'Saving...'}
          </h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 transition-colors">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-5">
          {/* ── Step 1: Input ── */}
          {step === 1 && (
            <div>
              {/* Mode selector */}
              <div className="flex gap-2 mb-4">
                {[
                  { key: 'text', label: 'Paste JD' },
                  { key: 'url', label: 'From URL' },
                  { key: 'file', label: 'Upload file' },
                ].map(({ key, label }) => (
                  <button
                    key={key}
                    onClick={() => setMode(key)}
                    className={`px-4 py-1.5 rounded-lg text-sm font-medium border transition-colors ${
                      mode === key
                        ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                        : 'bg-white text-gray-600 border-gray-200 hover:bg-gray-50'
                    }`}
                  >
                    {label}
                  </button>
                ))}
              </div>

              {mode === 'text' && (
                <textarea
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                  placeholder="Paste the full job description here..."
                  rows={14}
                  className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm outline-none focus:border-emerald-400 focus:ring-2 focus:ring-emerald-100 resize-none"
                />
              )}

              {mode === 'url' && (
                <Input
                  label="Job posting URL"
                  placeholder="https://careers.adyen.com/jobs/..."
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  hint="Works best with direct job posting pages"
                />
              )}

              {mode === 'file' && (
                <div
                  onClick={() => fileRef.current?.click()}
                  className="border-2 border-dashed border-gray-200 rounded-xl p-10 text-center cursor-pointer hover:border-emerald-300 hover:bg-emerald-50/20 transition-colors"
                >
                  <input ref={fileRef} type="file" accept=".pdf,.docx,.doc" onChange={(e) => setFile(e.target.files[0])} className="hidden" />
                  {file ? (
                    <p className="text-sm font-medium text-gray-700">{file.name}</p>
                  ) : (
                    <p className="text-sm text-gray-500">Drop PDF/DOCX or <span className="text-emerald-600 font-medium">browse</span></p>
                  )}
                </div>
              )}

              {error && (
                <div className="mt-3 bg-red-50 border border-red-200 rounded-lg px-3 py-2 text-sm text-red-600">
                  {error}
                </div>
              )}
            </div>
          )}

          {/* ── Step 2: Preview ── */}
          {step === 2 && parseResult && (
            <div>
              {/* Pre-filter status */}
              {!passed && (
                <div className="bg-yellow-50 border border-yellow-200 rounded-lg px-3 py-2 text-sm text-yellow-700 mb-4">
                  ⚠️ Pre-filter: {parseResult.pre_filter_reason} — saved without S1 scoring.
                </div>
              )}

              {/* S1 score */}
              {passed && (
                <div className="bg-gray-50 rounded-xl p-4 mb-5">
                  <div className="flex items-center justify-between mb-3">
                    <span className="text-sm font-medium text-gray-700">Base fit score (S1)</span>
                    <div className="flex items-center gap-2">
                      {parseResult.s1_tokens && <TokenBadge tokens={parseResult.s1_tokens} cost_inr={parseResult.s1_cost_inr} />}
                      <ScorePill score={s1} />
                    </div>
                  </div>
                  {parseResult.key_matches?.length > 0 && (
                    <div className="mb-2">
                      <p className="text-xs font-medium text-gray-500 mb-1">Key matches</p>
                      <ul className="space-y-0.5">
                        {parseResult.key_matches.map((m, i) => (
                          <li key={i} className="text-xs text-gray-600 flex gap-1.5">
                            <span className="text-emerald-500">✓</span>{m}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {parseResult.gaps?.length > 0 && (
                    <div>
                      <p className="text-xs font-medium text-gray-500 mb-1">Gaps</p>
                      <ul className="space-y-0.5">
                        {parseResult.gaps.map((g, i) => (
                          <li key={i} className="text-xs text-gray-600 flex gap-1.5">
                            <span className="text-amber-500">△</span>{g}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              )}

              {/* Community insights — helps decide save/skip before spending tailoring tokens */}
              {(company && role) && (
                <div className="mb-5">
                  <CommunityInsights company={company} role={role} market={market} compact />
                </div>
              )}

              {/* Editable fields */}
              <div className="grid grid-cols-2 gap-3">
                <Input label="Company *" value={company} onChange={(e) => setCompany(e.target.value)} required />
                <Input label="Role *" value={role} onChange={(e) => setRole(e.target.value)} required />
                <Input label="Location" value={location} onChange={(e) => setLocation(e.target.value)} />
                <div>
                  <label className="text-sm font-medium text-gray-700 block mb-1">Market</label>
                  <select
                    value={market}
                    onChange={(e) => setMarket(e.target.value)}
                    className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm outline-none focus:border-emerald-400"
                  >
                    <option value="">Unknown</option>
                    <option value="NL">Netherlands</option>
                    <option value="EU">EU</option>
                    <option value="Dubai">Dubai</option>
                    <option value="SG">Singapore</option>
                    <option value="IN">India</option>
                  </select>
                </div>
                <Input label="Recruiter email" type="email" value={recruiterEmail} onChange={(e) => setRecruiterEmail(e.target.value)} />
                <Input label="Portal URL" value={portalUrl} onChange={(e) => setPortalUrl(e.target.value)} />
              </div>

              {error && (
                <div className="mt-3 bg-red-50 border border-red-200 rounded-lg px-3 py-2 text-sm text-red-600">
                  {error}
                </div>
              )}
            </div>
          )}

          {/* ── Step 3: Saving ── */}
          {step === 3 && (
            <div className="flex flex-col items-center justify-center py-12">
              <Spinner size="lg" />
              <p className="text-sm text-gray-500 mt-3">Saving job...</p>
            </div>
          )}
        </div>

        {/* Footer */}
        {step !== 3 && (
          <div className="px-6 py-4 border-t border-gray-100 flex justify-between">
            <Button variant="ghost" onClick={step === 1 ? onClose : () => setStep(1)}>
              {step === 1 ? 'Cancel' : '← Back'}
            </Button>
            <Button onClick={step === 1 ? handleParse : handleConfirm} loading={loading}>
              {step === 1 ? 'Parse & score →' : 'Save to tracker →'}
            </Button>
          </div>
        )}
      </div>
    </div>
  )
}
