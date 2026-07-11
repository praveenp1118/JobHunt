import { useState, useEffect } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { getCredentials, updateCredentials, getPreferences, updatePreferences } from '../../api/auth'
import Button from '../../components/ui/Button'
import Input from '../../components/ui/Input'
import client from '../../api/client'
import { toast } from '../../store/toast'

export default function GmailTab() {
  const qc = useQueryClient()
  const [gmailAddress, setGmailAddress] = useState('')
  const [gmailPassword, setGmailPassword] = useState('')
  const [notificationEmail, setNotificationEmail] = useState('')
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState(null)
  const [error, setError] = useState('')

  const { data: credsData } = useQuery({
    queryKey: ['credentials'],
    queryFn: getCredentials,
    onSuccess: (d) => {
      if (d.data.gmail_address) setGmailAddress(d.data.gmail_address)
      if (d.data.notification_email) setNotificationEmail(d.data.notification_email)
    },
  })

  const { data: prefsData } = useQuery({
    queryKey: ['preferences'],
    queryFn: getPreferences,
  })

  const creds = credsData?.data || {}
  const prefs = prefsData?.data || {}

  // Local state for numeric alert controls (save on blur)
  const [minS1, setMinS1] = useState(65)
  const [maxLinks, setMaxLinks] = useState(10)

  useEffect(() => {
    if (prefsData?.data) {
      setMinS1(prefsData.data.s1_min_threshold ?? 65)
      setMaxLinks(prefsData.data.job_alert_max_links ?? 10)
    }
  }, [prefsData])

  const savePref = async (patch) => {
    try {
      await updatePreferences(patch)
      qc.invalidateQueries({ queryKey: ['preferences'] })
    } catch (e) {
      toast.error('Failed to save setting')
    }
  }

  const handleSave = async () => {
    setSaving(true)
    setError('')
    try {
      await updateCredentials({
        gmail_address: gmailAddress || undefined,
        gmail_app_password: gmailPassword || undefined,
        notification_email: notificationEmail || undefined,
      })
      setGmailPassword('')
      setSaved(true)
      toast.success('Gmail settings saved')
      qc.invalidateQueries({ queryKey: ['credentials'] })
      setTimeout(() => setSaved(false), 3000)
    } catch (e) {
      setError('Save failed')
    } finally {
      setSaving(false)
    }
  }

  const handleTest = async () => {
    setTesting(true)
    setTestResult(null)
    try {
      const res = await client.post('/gmail/test-connection')
      setTestResult(res.data)
      if (res.data.success) toast.success('Gmail connected successfully')
      else toast.error('Connection failed: ' + res.data.message)
    } catch (e) {
      setTestResult({ success: false, message: e.response?.data?.detail || 'Connection failed' })
    } finally {
      setTesting(false)
    }
  }

  const handlePollIntervalChange = async (minutes) => {
    try {
      await updatePreferences({ gmail_poll_interval_minutes: parseInt(minutes) })
      qc.invalidateQueries({ queryKey: ['preferences'] })
    } catch (e) { console.error(e) }
  }

  return (
    <div className="space-y-5">
      {/* Test mode notice */}
      <div className="bg-amber-50 border border-amber-200 rounded-xl p-4">
        <div className="flex items-start gap-3">
          <div className="w-5 h-5 rounded-full bg-amber-400 flex items-center justify-center shrink-0 mt-0.5">
            <span className="text-white text-[10px] font-bold">!</span>
          </div>
          <div>
            <p className="text-sm font-medium text-amber-800">Test mode is ON</p>
            <p className="text-xs text-amber-600 mt-0.5">
              All outgoing emails are redirected to your notification address. No emails reach real recruiters.
              Switch to production mode in your <code className="bg-amber-100 px-1 rounded">.env</code> file by setting <code className="bg-amber-100 px-1 rounded">ENV=production</code>.
            </p>
          </div>
        </div>
      </div>

      {/* Gmail credentials */}
      <div className="bg-white rounded-2xl border border-gray-200 p-6">
        <h2 className="text-sm font-semibold text-gray-900 mb-1">Gmail configuration</h2>
        <p className="text-xs text-gray-500 mb-5">
          Used to send applications and receive recruiter replies via IMAP.{' '}
          <a href="https://myaccount.google.com/apppasswords" target="_blank" rel="noreferrer" className="text-emerald-600 hover:underline">
            Generate app password →
          </a>
        </p>

        <div className="space-y-4">
          <Input
            label="Gmail address (job search account)"
            type="email"
            placeholder="yourjobsearch@gmail.com"
            value={gmailAddress}
            onChange={(e) => setGmailAddress(e.target.value)}
          />
          <Input
            label="Gmail app password"
            type="password"
            placeholder={creds.has_gmail_password ? '••••••••••••••••• (saved)' : 'xxxx xxxx xxxx xxxx'}
            value={gmailPassword}
            onChange={(e) => setGmailPassword(e.target.value)}
            hint="16-character app password, not your regular Gmail password"
          />
          <Input
            label="Personal notification email"
            type="email"
            placeholder="personal@gmail.com"
            value={notificationEmail}
            onChange={(e) => setNotificationEmail(e.target.value)}
            hint="Where to receive HITL alerts when recruiters reply"
          />
        </div>

        {testResult && (
          <div className={`mt-3 px-3 py-2 rounded-lg text-sm ${testResult.success ? 'bg-emerald-50 text-emerald-700' : 'bg-red-50 text-red-600'}`}>
            {testResult.success ? '✓ Connected successfully' : `✗ ${testResult.message}`}
          </div>
        )}
        {error && <p className="text-sm text-red-500 mt-3">{error}</p>}
        {saved && <p className="text-sm text-emerald-600 mt-3">✓ Gmail settings saved</p>}

        <div className="flex justify-between mt-5">
          <Button variant="secondary" size="sm" onClick={handleTest} loading={testing}>
            Test connection
          </Button>
          <Button size="sm" onClick={handleSave} loading={saving}>
            Save
          </Button>
        </div>
      </div>

      {/* Poll settings */}
      <div className="bg-white rounded-2xl border border-gray-200 p-6">
        <h2 className="text-sm font-semibold text-gray-900 mb-4">Poll frequency</h2>
        <div className="flex items-center gap-3">
          <label className="text-sm text-gray-700">Check inbox every</label>
          <select
            value={prefs.gmail_poll_interval_minutes || 60}
            onChange={(e) => handlePollIntervalChange(e.target.value)}
            className="px-3 py-1.5 border border-gray-200 rounded-lg text-sm outline-none focus:border-emerald-400"
          >
            <option value={30}>30 minutes</option>
            <option value={60}>1 hour</option>
            <option value={120}>2 hours</option>
            <option value={0}>Manual only</option>
          </select>
        </div>
      </div>

      {/* Job alert parsing (V3) */}
      <div className="bg-white rounded-2xl border border-gray-200 p-6">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 className="text-sm font-semibold text-gray-900">Parse job alert emails</h2>
            <p className="text-xs text-gray-500 mt-0.5">
              Auto-extract jobs from alert digests (LinkedIn, Indeed, company careers),
              score them, and add matches to your tracker.
            </p>
          </div>
          <Toggle
            on={prefs.parse_job_alerts ?? true}
            onChange={() => savePref({ parse_job_alerts: !(prefs.parse_job_alerts ?? true) })}
          />
        </div>

        {(prefs.parse_job_alerts ?? true) && (
          <div className="mt-5 space-y-4 border-t border-gray-100 pt-4">
            <div className="flex items-center justify-between">
              <label className="text-sm text-gray-700">Min S1 to save</label>
              <input
                type="number" min="0" max="100"
                value={minS1}
                onChange={(e) => setMinS1(e.target.value)}
                onBlur={() => savePref({ s1_min_threshold: parseInt(minS1) || 0 })}
                className="w-20 px-2 py-1 border border-gray-200 rounded-lg text-sm text-right outline-none focus:border-emerald-400"
              />
            </div>
            <div className="flex items-center justify-between">
              <label className="text-sm text-gray-700">Max links per email</label>
              <input
                type="number" min="1" max="50"
                value={maxLinks}
                onChange={(e) => setMaxLinks(e.target.value)}
                onBlur={() => savePref({ job_alert_max_links: parseInt(maxLinks) || 10 })}
                className="w-20 px-2 py-1 border border-gray-200 rounded-lg text-sm text-right outline-none focus:border-emerald-400"
              />
            </div>
            <div className="flex items-center justify-between gap-4">
              <div>
                <label className="text-sm text-gray-700">Pre-filter by job title</label>
                <p className="text-xs text-gray-400 mt-0.5">
                  Cheaply skip non-matching jobs (fetch page title only) before full parsing
                </p>
              </div>
              <Toggle
                on={prefs.job_alert_title_filter ?? true}
                onChange={() => savePref({ job_alert_title_filter: !(prefs.job_alert_title_filter ?? true) })}
              />
            </div>
          </div>
        )}
      </div>

      {/* Auto-detect external applications (V3) */}
      <div className="bg-white rounded-2xl border border-gray-200 p-6">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 className="text-sm font-semibold text-gray-900">Auto-detect applications</h2>
            <p className="text-xs text-gray-500 mt-0.5">
              When a Gmail “application sent / received” confirmation arrives, mark the matching
              tracked job as <strong>Applied</strong> — or add it as an applied job if it isn’t
              tracked yet. Detected during each poll, no extra cost.
            </p>
          </div>
          <Toggle
            on={prefs.auto_detect_applications ?? true}
            onChange={() => savePref({ auto_detect_applications: !(prefs.auto_detect_applications ?? true) })}
          />
        </div>
      </div>

      {/* Email to JobHunt (V3) */}
      <div className="bg-white rounded-2xl border border-gray-200 p-6">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 className="text-sm font-semibold text-gray-900">Email to AIJobsHunt</h2>
            <p className="text-xs text-gray-500 mt-0.5">
              Send any job URL to your job-search Gmail with a subject containing
              <strong> “jobhunt” </strong> or starting with <strong>“jh:”</strong> — it’s
              automatically fetched, scored, and saved to your tracker.
            </p>
          </div>
          <Toggle
            on={prefs.enable_email_to_jobhunt ?? true}
            onChange={() => savePref({ enable_email_to_jobhunt: !(prefs.enable_email_to_jobhunt ?? true) })}
          />
        </div>

        {(prefs.enable_email_to_jobhunt ?? true) && (
          <div className="mt-5 border-t border-gray-100 pt-4">
            <label className="text-xs text-gray-500">Your job-search email</label>
            {gmailAddress ? (
              <div className="flex items-center gap-2 mt-1.5">
                <code className="flex-1 text-sm bg-gray-50 border border-gray-200 rounded-lg px-3 py-2 text-gray-800 truncate">
                  {gmailAddress}
                </code>
                <button
                  onClick={() => { navigator.clipboard?.writeText(gmailAddress); toast.success('Email address copied') }}
                  className="text-xs font-medium px-3 py-2 rounded-lg border border-gray-200 hover:bg-gray-50 whitespace-nowrap"
                >
                  Copy
                </button>
              </div>
            ) : (
              <p className="text-xs text-amber-600 mt-1.5">Add your Gmail address above to use this feature.</p>
            )}
            <p className="text-[11px] text-gray-400 mt-2">
              Example subject: <code className="text-gray-500">jh: Head of Product at Adyen</code> ·
              you’ll get a confirmation email back with the scores.
            </p>
          </div>
        )}
      </div>
    </div>
  )
}

function Toggle({ on, onChange }) {
  return (
    <button
      type="button"
      onClick={onChange}
      className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors shrink-0 mt-0.5 ${
        on ? 'bg-emerald-500' : 'bg-gray-200'
      }`}
    >
      <span className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white transition-transform ${
        on ? 'translate-x-4' : 'translate-x-0.5'
      }`} />
    </button>
  )
}
