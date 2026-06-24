import { useState, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import Button from '../../components/ui/Button'
import Input from '../../components/ui/Input'
import Spinner from '../../components/ui/Spinner'
import useAuthStore from '../../store/auth'
import { updateCredentials, updatePreferences } from '../../api/auth'
import { saveMasterCVText, uploadMasterCVFile } from '../../api/cvs'
import { getSubscription, createCheckoutSession } from '../../api/billing'

const STEPS = [
  { id: 1, label: 'Subscribe', required: false },
  { id: 2, label: 'Master CV', required: true },
  { id: 3, label: 'Gmail', required: false },
  { id: 4, label: 'Targets', required: false },
  { id: 5, label: 'API Keys', required: false },
]

const MARKETS = ['NL/EU', 'Dubai', 'Singapore', 'India']
const DEFAULT_ROLES = ['Head of Product', 'VP Product', 'CPO', 'AI Product Lead']

export default function Onboarding() {
  const navigate = useNavigate()
  const { user, setOnboardingComplete } = useAuthStore()
  const [step, setStep] = useState(1)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  // Step 1 state
  const [cvMode, setCvMode] = useState('paste') // paste | upload
  const [cvText, setCvText] = useState('')
  const [cvFile, setCvFile] = useState(null)
  const [cvUploaded, setCvUploaded] = useState(false)
  const fileRef = useRef()

  // Step 2 state
  const [gmail, setGmail] = useState('')
  const [gmailPassword, setGmailPassword] = useState('')
  const [notificationEmail, setNotificationEmail] = useState(user?.email || '')

  // Step 3 state
  const [selectedRoles, setSelectedRoles] = useState([...DEFAULT_ROLES])
  const [selectedMarkets, setSelectedMarkets] = useState(['NL/EU', 'Dubai', 'Singapore'])
  const [customRole, setCustomRole] = useState('')

  // Step 4 state
  const [anthropicKey, setAnthropicKey] = useState('')
  const [apifyToken, setApifyToken] = useState('')

  // Step 1 (Subscribe) state
  const { data: subData } = useQuery({ queryKey: ['subscription'], queryFn: getSubscription, retry: false })
  const subActive = subData?.data?.is_active
  const [subBusy, setSubBusy] = useState(false)

  const handleSubscribe = async () => {
    setSubBusy(true)
    try {
      const res = await createCheckoutSession('pro')
      window.location.href = res.data.checkout_url
    } catch (e) {
      setError(e.response?.data?.detail?.message || e.response?.data?.detail || 'Could not start checkout')
      setSubBusy(false)
    }
  }

  const handleStep1 = async () => {
    setError('')
    setLoading(true)
    try {
      if (cvMode === 'paste') {
        if (!cvText.trim()) {
          setError('Please paste your CV content')
          return
        }
        await saveMasterCVText(cvText, 'Initial CV upload via onboarding')
      } else {
        if (!cvFile) {
          setError('Please select a file')
          return
        }
        await uploadMasterCVFile(cvFile)
      }
      setCvUploaded(true)
      setStep(3)
    } catch (err) {
      setError(err.response?.data?.detail || 'Upload failed. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  const handleStep2 = async () => {
    setError('')
    if (!gmail && !gmailPassword) {
      setStep(4)
      return
    }
    setLoading(true)
    try {
      await updateCredentials({
        gmail_address: gmail || undefined,
        gmail_app_password: gmailPassword || undefined,
        notification_email: notificationEmail || undefined,
      })
      setStep(4)
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to save Gmail settings')
    } finally {
      setLoading(false)
    }
  }

  const handleStep3 = async () => {
    setError('')
    setLoading(true)
    try {
      const roles = [...selectedRoles, customRole].filter(Boolean).join(',')
      await updatePreferences({ target_roles: roles })
      setStep(5)
    } catch (err) {
      setError('Failed to save preferences')
    } finally {
      setLoading(false)
    }
  }

  const handleStep4 = async () => {
    setError('')
    setLoading(true)
    try {
      if (anthropicKey || apifyToken) {
        await updateCredentials({
          anthropic_api_key: anthropicKey || undefined,
          apify_token: apifyToken || undefined,
        })
      }
      setOnboardingComplete()
      navigate('/dashboard')
    } catch (err) {
      setError('Failed to save API keys')
    } finally {
      setLoading(false)
    }
  }

  const toggleRole = (role) => {
    setSelectedRoles((prev) =>
      prev.includes(role) ? prev.filter((r) => r !== role) : [...prev, role]
    )
  }

  const toggleMarket = (market) => {
    setSelectedMarkets((prev) =>
      prev.includes(market) ? prev.filter((m) => m !== market) : [...prev, market]
    )
  }

  return (
    <div className="min-h-screen bg-slate-900 flex items-center justify-center p-4">
      <div className="w-full max-w-2xl">
        {/* Logo */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center gap-2">
            <div className="w-9 h-9 bg-emerald-500 rounded-xl flex items-center justify-center">
              <span className="text-white font-bold text-sm">JH</span>
            </div>
            <span className="text-white font-semibold text-xl tracking-tight">JobHunt</span>
          </div>
        </div>

        {/* Step indicators */}
        <div className="flex items-center justify-center gap-0 mb-8">
          {STEPS.map((s, i) => (
            <div key={s.id} className="flex items-center">
              <div className="flex flex-col items-center">
                <div
                  className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-semibold transition-colors ${
                    step > s.id
                      ? 'bg-emerald-500 text-white'
                      : step === s.id
                      ? 'bg-white text-slate-900'
                      : 'bg-slate-700 text-slate-400'
                  }`}
                >
                  {step > s.id ? (
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" />
                    </svg>
                  ) : (
                    s.id
                  )}
                </div>
                <span className={`text-xs mt-1.5 ${step === s.id ? 'text-white' : 'text-slate-500'}`}>
                  {s.label}
                  {s.required && <span className="text-red-400">*</span>}
                </span>
              </div>
              {i < STEPS.length - 1 && (
                <div className={`w-16 h-px mx-2 mb-4 ${step > s.id ? 'bg-emerald-500' : 'bg-slate-700'}`} />
              )}
            </div>
          ))}
        </div>

        {/* Card */}
        <div className="bg-white rounded-2xl shadow-xl p-8">
          {error && (
            <div className="bg-red-50 border border-red-200 rounded-lg px-3 py-2 text-sm text-red-600 mb-4">
              {error}
            </div>
          )}

          {/* ── Step 1: Subscribe ── */}
          {step === 1 && (
            <div>
              <h2 className="text-lg font-semibold text-gray-900 mb-1">Subscribe to JobHunt Pro</h2>
              <p className="text-sm text-gray-500 mb-6">
                One plan unlocks everything — CV tailoring, multi-domain scoring, job scanning, and application sending.
              </p>

              <div className="rounded-2xl border-2 border-emerald-200 bg-emerald-50 p-6 mb-6">
                <div className="flex items-baseline gap-2">
                  <span className="text-3xl font-bold text-gray-900">₹500</span>
                  <span className="text-sm text-gray-500">/ month</span>
                </div>
                <ul className="mt-4 space-y-2 text-sm text-gray-700">
                  {[
                    'AI CV tailoring + cover letters',
                    'Multi-domain job-fit scoring',
                    'Weekly job scanning (RSS + LinkedIn/Google)',
                    'Gmail job-alert parsing + application sending',
                  ].map((f) => (
                    <li key={f} className="flex items-center gap-2">
                      <svg className="w-4 h-4 text-emerald-500 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" />
                      </svg>
                      {f}
                    </li>
                  ))}
                </ul>
                <p className="mt-4 text-xs text-gray-500">
                  You bring your own Anthropic + Apify keys (set up in a later step) — you control AI costs directly.
                </p>
              </div>

              {subActive ? (
                <div className="flex items-center justify-between">
                  <p className="text-sm font-medium text-emerald-700">✅ You're already on JobHunt Pro</p>
                  <Button onClick={() => setStep(2)}>Continue →</Button>
                </div>
              ) : (
                <div className="flex items-center justify-between">
                  <button onClick={() => setStep(2)} className="text-sm text-gray-500 hover:text-gray-700 font-medium">
                    Skip for now →
                  </button>
                  <Button loading={subBusy} onClick={handleSubscribe}>Subscribe — ₹500/month</Button>
                </div>
              )}
            </div>
          )}

          {/* ── Step 2: Master CV ── */}
          {step === 2 && (
            <div>
              <h2 className="text-lg font-semibold text-gray-900 mb-1">Upload your master CV</h2>
              <p className="text-sm text-gray-500 mb-6">
                This is your source of truth. Every tailored CV starts from this.{' '}
                <span className="text-red-500 font-medium">Required.</span>
              </p>

              {/* Mode toggle */}
              <div className="flex gap-2 mb-4">
                {['paste', 'upload'].map((mode) => (
                  <button
                    key={mode}
                    onClick={() => setCvMode(mode)}
                    className={`px-4 py-1.5 rounded-lg text-sm font-medium border transition-colors ${
                      cvMode === mode
                        ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                        : 'bg-white text-gray-600 border-gray-200 hover:bg-gray-50'
                    }`}
                  >
                    {mode === 'paste' ? 'Paste markdown' : 'Upload PDF / DOCX'}
                  </button>
                ))}
              </div>

              {cvMode === 'paste' ? (
                <textarea
                  value={cvText}
                  onChange={(e) => setCvText(e.target.value)}
                  placeholder={`## PRAVEEN PRAKASH\nBengaluru, India | email@example.com\n\n## SUMMARY\nProduct leader with 15+ years...\n\n## EXPERIENCE\n...`}
                  rows={12}
                  className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm font-mono outline-none focus:border-emerald-400 focus:ring-2 focus:ring-emerald-100 resize-y"
                />
              ) : (
                <div
                  onClick={() => fileRef.current?.click()}
                  onDragOver={(e) => e.preventDefault()}
                  onDrop={(e) => {
                    e.preventDefault()
                    const f = e.dataTransfer.files[0]
                    if (f) setCvFile(f)
                  }}
                  className="border-2 border-dashed border-gray-200 rounded-xl p-10 text-center cursor-pointer hover:border-emerald-300 hover:bg-emerald-50/30 transition-colors"
                >
                  <input
                    ref={fileRef}
                    type="file"
                    accept=".pdf,.docx,.doc,.md,.txt"
                    onChange={(e) => setCvFile(e.target.files[0])}
                    className="hidden"
                  />
                  {cvFile ? (
                    <div>
                      <div className="w-10 h-10 bg-emerald-100 rounded-lg flex items-center justify-center mx-auto mb-3">
                        <svg className="w-5 h-5 text-emerald-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                        </svg>
                      </div>
                      <p className="text-sm font-medium text-gray-700">{cvFile.name}</p>
                      <p className="text-xs text-gray-400 mt-1">Click to change</p>
                    </div>
                  ) : (
                    <div>
                      <svg className="w-10 h-10 text-gray-300 mx-auto mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                      </svg>
                      <p className="text-sm text-gray-500">Drop your CV here or <span className="text-emerald-600 font-medium">browse</span></p>
                      <p className="text-xs text-gray-400 mt-1">PDF, DOCX, or Markdown</p>
                    </div>
                  )}
                </div>
              )}

              <div className="flex justify-end mt-6">
                <Button onClick={handleStep1} loading={loading} size="lg">
                  Continue →
                </Button>
              </div>
            </div>
          )}

          {/* ── Step 2: Gmail ── */}
          {step === 3 && (
            <div>
              <h2 className="text-lg font-semibold text-gray-900 mb-1">Connect Gmail</h2>
              <p className="text-sm text-gray-500 mb-1">
                Used to send applications and receive recruiter replies.
              </p>
              <p className="text-xs text-gray-400 mb-6">
                You'll need a Gmail App Password (not your regular password).{' '}
                <a
                  href="https://myaccount.google.com/apppasswords"
                  target="_blank"
                  rel="noreferrer"
                  className="text-emerald-600 hover:underline"
                >
                  Generate one here →
                </a>
              </p>

              <div className="flex flex-col gap-4">
                <Input
                  label="Gmail address (job search account)"
                  type="email"
                  placeholder="yourjobsearch@gmail.com"
                  value={gmail}
                  onChange={(e) => setGmail(e.target.value)}
                />
                <Input
                  label="Gmail App Password"
                  type="password"
                  placeholder="xxxx xxxx xxxx xxxx"
                  value={gmailPassword}
                  onChange={(e) => setGmailPassword(e.target.value)}
                  hint="16-character app password, not your Gmail login password"
                />
                <Input
                  label="Personal notification email"
                  type="email"
                  placeholder="personal@gmail.com"
                  value={notificationEmail}
                  onChange={(e) => setNotificationEmail(e.target.value)}
                  hint="Where to send alerts when recruiters reply (can be same as above)"
                />
              </div>

              <div className="flex justify-between mt-6">
                <Button variant="ghost" onClick={() => setStep(4)}>
                  Skip for now
                </Button>
                <Button onClick={handleStep2} loading={loading} size="lg">
                  Continue →
                </Button>
              </div>
            </div>
          )}

          {/* ── Step 3: Targets ── */}
          {step === 4 && (
            <div>
              <h2 className="text-lg font-semibold text-gray-900 mb-1">Set your targets</h2>
              <p className="text-sm text-gray-500 mb-6">
                Which roles and markets are you targeting?
              </p>

              <div className="mb-5">
                <p className="text-sm font-medium text-gray-700 mb-2">Target roles</p>
                <div className="flex flex-wrap gap-2 mb-3">
                  {DEFAULT_ROLES.map((role) => (
                    <button
                      key={role}
                      onClick={() => toggleRole(role)}
                      className={`px-3 py-1.5 rounded-full text-sm border transition-colors ${
                        selectedRoles.includes(role)
                          ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                          : 'bg-white text-gray-600 border-gray-200 hover:bg-gray-50'
                      }`}
                    >
                      {selectedRoles.includes(role) && '✓ '}{role}
                    </button>
                  ))}
                </div>
                <div className="flex gap-2">
                  <input
                    type="text"
                    placeholder="Add custom role..."
                    value={customRole}
                    onChange={(e) => setCustomRole(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && customRole.trim()) {
                        setSelectedRoles((p) => [...p, customRole.trim()])
                        setCustomRole('')
                      }
                    }}
                    className="flex-1 px-3 py-2 border border-gray-200 rounded-lg text-sm outline-none focus:border-emerald-400"
                  />
                  <Button
                    variant="secondary"
                    onClick={() => {
                      if (customRole.trim()) {
                        setSelectedRoles((p) => [...p, customRole.trim()])
                        setCustomRole('')
                      }
                    }}
                  >
                    Add
                  </Button>
                </div>
              </div>

              <div>
                <p className="text-sm font-medium text-gray-700 mb-2">Target markets</p>
                <div className="flex flex-wrap gap-2">
                  {MARKETS.map((market) => (
                    <button
                      key={market}
                      onClick={() => toggleMarket(market)}
                      className={`px-3 py-1.5 rounded-full text-sm border transition-colors ${
                        selectedMarkets.includes(market)
                          ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                          : 'bg-white text-gray-600 border-gray-200 hover:bg-gray-50'
                      }`}
                    >
                      {selectedMarkets.includes(market) && '✓ '}{market}
                    </button>
                  ))}
                </div>
              </div>

              <div className="flex justify-between mt-6">
                <Button variant="ghost" onClick={() => setStep(5)}>
                  Skip for now
                </Button>
                <Button onClick={handleStep3} loading={loading} size="lg">
                  Continue →
                </Button>
              </div>
            </div>
          )}

          {/* ── Step 4: API Keys ── */}
          {step === 5 && (
            <div>
              <h2 className="text-lg font-semibold text-gray-900 mb-1">Add your API keys</h2>
              <p className="text-sm text-gray-500 mb-6">
                JobHunt uses your own keys (billed directly to you). No markup.
              </p>

              <div className="flex flex-col gap-4">
                <Input
                  label="Anthropic API key"
                  type="password"
                  placeholder="sk-ant-..."
                  value={anthropicKey}
                  onChange={(e) => setAnthropicKey(e.target.value)}
                  hint={
                    <span>
                      Get your key at{' '}
                      <a href="https://console.anthropic.com" target="_blank" rel="noreferrer" className="text-emerald-600 hover:underline">
                        console.anthropic.com
                      </a>
                    </span>
                  }
                />
                <Input
                  label="Apify token (for weekly job scanning)"
                  type="password"
                  placeholder="apify_api_..."
                  value={apifyToken}
                  onChange={(e) => setApifyToken(e.target.value)}
                  hint={
                    <span>
                      Get your token at{' '}
                      <a href="https://console.apify.com" target="_blank" rel="noreferrer" className="text-emerald-600 hover:underline">
                        console.apify.com
                      </a>
                    </span>
                  }
                />
              </div>

              <div className="bg-slate-50 border border-slate-200 rounded-lg p-4 mt-4">
                <p className="text-xs text-slate-600">
                  🔒 Keys are encrypted with AES-256 and never shared. You can add or change them later in Settings → Plan & Keys.
                </p>
              </div>

              {error && (
                <div className="bg-red-50 border border-red-200 rounded-lg px-3 py-2 text-sm text-red-600 mt-4">
                  {error}
                </div>
              )}

              <div className="flex justify-between mt-6">
                <Button variant="ghost" onClick={() => { setOnboardingComplete(); navigate('/dashboard') }}>
                  Skip — I'll add keys later
                </Button>
                <Button onClick={handleStep4} loading={loading} size="lg">
                  Get started →
                </Button>
              </div>
            </div>
          )}
        </div>

        <p className="text-center text-xs text-slate-500 mt-4">
          Step {step} of {STEPS.length}
          {step === 2 && ' — Required'}
          {step !== 2 && ' — Optional (you can complete this later in Settings)'}
        </p>
      </div>
    </div>
  )
}
