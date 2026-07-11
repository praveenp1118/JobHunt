import { useState } from 'react'
import { toast } from '../../store/toast'
import { useQuery } from '@tanstack/react-query'
import { format } from 'date-fns'
import { getCredentials, updateCredentials } from '../../api/auth'
import { getSubscription, createCheckoutSession, cancelSubscription } from '../../api/billing'
import client from '../../api/client'
import Button from '../../components/ui/Button'
import Input from '../../components/ui/Input'

export default function PlanKeysTab() {
  const [anthropicKey, setAnthropicKey] = useState('')
  const [apifyToken, setApifyToken] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [subBusy, setSubBusy] = useState(false)
  const [testingApify, setTestingApify] = useState(false)

  const { data } = useQuery({ queryKey: ['credentials'], queryFn: getCredentials })
  const creds = data?.data || {}

  const { data: subData, refetch: refetchSub } = useQuery({
    queryKey: ['subscription'],
    queryFn: getSubscription,
  })
  const sub = subData?.data || {}
  const endLabel = sub.subscription_end ? format(new Date(sub.subscription_end), 'MMM d, yyyy') : null

  const handleSubscribe = async () => {
    setSubBusy(true)
    try {
      const res = await createCheckoutSession('pro')
      window.location.href = res.data.checkout_url
    } catch (e) {
      toast.error(e.response?.data?.detail?.message || e.response?.data?.detail || 'Could not start checkout')
      setSubBusy(false)
    }
  }

  const handleCancel = async () => {
    if (!window.confirm('Cancel your subscription? You keep full access until the current period ends.')) return
    setSubBusy(true)
    try {
      await cancelSubscription()
      toast.success('Subscription will cancel at period end')
      refetchSub()
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Cancel failed')
    } finally {
      setSubBusy(false)
    }
  }

  const handleSave = async () => {
    setSaving(true)
    setError('')
    try {
      await updateCredentials({
        anthropic_api_key: anthropicKey || undefined,
        apify_token: apifyToken || undefined,
      })
      setAnthropicKey('')
      setApifyToken('')
      toast.success('API keys saved securely')
    } catch (e) {
      const msg = e.response?.data?.detail || 'Save failed'
      setError(msg)
      toast.error(msg)
    } finally {
      setSaving(false)
    }
  }

  const handleTestApify = async () => {
    setTestingApify(true)
    try {
      const r = await client.get('/feeds/apify-actors', { params: { search: 'jobs' } })
      const n = (r.data || []).length
      toast.success(`Apify connected — ${n} actor${n === 1 ? '' : 's'} found`)
    } catch {
      toast.error('Apify test failed — save a valid token first')
    } finally {
      setTestingApify(false)
    }
  }

  const handleModelChange = async (model) => {
    try {
      const { updatePreferences } = await import('../../api/auth')
      await updatePreferences({ preferred_model: model })
      toast.success('Model preference saved')
    } catch {
      toast.error('Failed to save model preference')
    }
  }

  return (
    <div className="space-y-5">
      {/* ── Section 1: Current plan ── */}
      <div className="bg-white rounded-2xl border border-gray-200 p-6">
        <h2 className="text-sm font-semibold text-gray-900 mb-3">Current plan</h2>

        {sub.is_active ? (
          <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-4 flex items-center justify-between gap-4">
            <div>
              <p className="text-sm font-semibold text-emerald-800">✅ AIJobsHunt Pro</p>
              <p className="text-xs text-emerald-700 mt-0.5">
                {endLabel ? `Active until: ${endLabel}` : 'Active'} · ₹500/month
              </p>
            </div>
            <Button size="sm" variant="ghost" loading={subBusy} onClick={handleCancel}>Cancel plan</Button>
          </div>
        ) : sub.status === 'cancelled' ? (
          <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 flex items-center justify-between gap-4">
            <div>
              <p className="text-sm font-semibold text-amber-800">🟡 Cancelled</p>
              <p className="text-xs text-amber-700 mt-0.5">
                {endLabel ? `Access until: ${endLabel}` : 'Cancelling at period end'} · Resubscribe to continue after that
              </p>
            </div>
            <Button size="sm" loading={subBusy} onClick={handleSubscribe}>Resubscribe →</Button>
          </div>
        ) : (
          <div className="rounded-xl border border-gray-200 bg-slate-50 p-4 flex items-center justify-between gap-4">
            <div>
              <p className="text-sm font-semibold text-gray-900">⚪ No active subscription</p>
              <p className="text-xs text-gray-500 mt-0.5">Subscribe to unlock CV tailoring, scanning, and application sending.</p>
            </div>
            <Button size="sm" loading={subBusy} onClick={handleSubscribe}>Subscribe — ₹500/month →</Button>
          </div>
        )}
      </div>

      {/* ── Section 2: Anthropic API key ── */}
      <div className="bg-white rounded-2xl border border-gray-200 p-6">
        <h2 className="text-sm font-semibold text-gray-900 mb-1">Anthropic API key</h2>
        <p className="text-xs text-gray-500 mb-4">Encrypted with AES-256 at rest. Never shared or logged.</p>

        <div className="rounded-xl bg-slate-50 border border-slate-100 p-4 mb-4 text-xs text-gray-600 leading-relaxed space-y-2">
          <p><span className="font-semibold text-gray-800">Why you need this:</span> AIJobsHunt uses Claude AI to score job fit, tailor your CV, generate cover letters, and parse job descriptions. Your key connects to your own Anthropic account — you control the costs (~$3–5/month for active job searching).</p>
          <div>
            <p className="font-semibold text-gray-800">How to get your key:</p>
            <ol className="list-decimal list-inside mt-1 space-y-0.5">
              <li>Go to <a href="https://console.anthropic.com" target="_blank" rel="noreferrer" className="text-emerald-600 hover:underline">console.anthropic.com</a></li>
              <li>Sign up or log in</li>
              <li>Click <span className="font-medium">API Keys</span> in the left sidebar</li>
              <li>Click <span className="font-medium">Create Key</span></li>
              <li>Copy and paste below</li>
            </ol>
          </div>
          <p className="text-emerald-700">💡 New accounts get $5 free credit — enough for weeks of job searching.</p>
        </div>

        <div className="flex items-center justify-between mb-1.5">
          <label className="text-sm font-medium text-gray-700">API key</label>
          <span className={`text-xs font-medium ${creds.has_anthropic_key ? 'text-emerald-600' : 'text-gray-400'}`}>
            {creds.has_anthropic_key ? '✓ Saved' : 'Not set'}
          </span>
        </div>
        <Input
          type="password"
          placeholder={creds.has_anthropic_key ? '••••••••••••••••• (saved)' : 'sk-ant-...'}
          value={anthropicKey}
          onChange={(e) => setAnthropicKey(e.target.value)}
        />
        <KeyRotation when={creds.anthropic_key_updated_at} consoleUrl="https://console.anthropic.com/settings/keys" />

        {/* Typical cost estimates (static, informational) */}
        <div className="mt-4 rounded-xl bg-slate-50 border border-slate-100 p-4">
          <p className="text-xs font-semibold text-gray-800 mb-2">💡 Typical costs with Claude Sonnet</p>
          <div className="space-y-1 text-xs text-gray-600">
            {[
              ['Score a job', '~1K', '~₹0.10'],
              ['Tailor a CV', '~12K', '~₹1.20'],
              ['Generate domain CV', '~9K', '~₹0.90'],
              ['Monthly (active search)', '~150K', '~₹15–30'],
            ].map(([label, tok, cost]) => (
              <div key={label} className="flex items-center justify-between">
                <span>{label}</span>
                <span className="tabular-nums text-gray-500">⚡ {tok} <span className="text-gray-700 font-medium ml-2">{cost}</span></span>
              </div>
            ))}
          </div>
          <p className="text-[11px] text-gray-400 mt-3">
            Set a $10 spending limit on Anthropic to protect against unexpected usage.{' '}
            <a href="https://console.anthropic.com/settings/limits" target="_blank" rel="noreferrer" className="text-emerald-600 hover:underline">Open Anthropic Console →</a>
          </p>
        </div>
      </div>

      {/* ── Section 3: Apify token ── */}
      <div className="bg-white rounded-2xl border border-gray-200 p-6">
        <h2 className="text-sm font-semibold text-gray-900 mb-1">Apify token <span className="text-gray-400 font-normal">(optional)</span></h2>
        <p className="text-xs text-gray-500 mb-4">Encrypted with AES-256 at rest.</p>

        <div className="rounded-xl bg-slate-50 border border-slate-100 p-4 mb-4 text-xs text-gray-600 leading-relaxed space-y-2">
          <p><span className="font-semibold text-gray-800">Why you need this (optional):</span> Apify powers LinkedIn Jobs and Google Jobs scanning. Without it, RSS feeds still find jobs (Jobicy etc). With it, 50+ additional jobs per scan from LinkedIn and Google.</p>
          <p>Free tier: $5 credit on signup (~500 job scans).</p>
          <div>
            <p className="font-semibold text-gray-800">How to get your token:</p>
            <ol className="list-decimal list-inside mt-1 space-y-0.5">
              <li>Go to <a href="https://apify.com" target="_blank" rel="noreferrer" className="text-emerald-600 hover:underline">apify.com</a></li>
              <li>Sign up (free)</li>
              <li>Click your profile → <span className="font-medium">Settings</span></li>
              <li>Go to the <span className="font-medium">Integrations</span> tab</li>
              <li>Copy your <span className="font-medium">Personal API token</span></li>
            </ol>
          </div>
          <p className="text-emerald-700">💡 Free tier is enough for weeks of scanning.</p>
        </div>

        <div className="flex items-center justify-between mb-1.5">
          <label className="text-sm font-medium text-gray-700">Token</label>
          <span className={`text-xs font-medium ${creds.has_apify_token ? 'text-emerald-600' : 'text-gray-400'}`}>
            {creds.has_apify_token ? '✓ Saved' : 'Not set'}
          </span>
        </div>
        <Input
          type="password"
          placeholder={creds.has_apify_token ? '••••••••••••••••• (saved)' : 'apify_api_...'}
          value={apifyToken}
          onChange={(e) => setApifyToken(e.target.value)}
        />
        <div className="flex justify-end mt-2">
          <Button size="sm" variant="ghost" loading={testingApify} onClick={handleTestApify}>Test connection</Button>
        </div>
      </div>

      {error && <p className="text-sm text-red-500">{error}</p>}
      <div className="flex justify-end">
        <Button onClick={handleSave} loading={saving} disabled={!anthropicKey && !apifyToken} size="sm">
          Save keys
        </Button>
      </div>

      {/* ── Section 4: Model selector ── */}
      <div className="bg-white rounded-2xl border border-gray-200 p-6">
        <h2 className="text-sm font-semibold text-gray-900 mb-1">Claude model</h2>
        <p className="text-xs text-gray-500 mb-4">Used for all AI operations — tailoring, scoring, domain CV generation.</p>
        <div className="space-y-2">
          {[
            { value: 'claude-sonnet-4-5', label: 'Claude Sonnet 4.5', desc: 'Recommended — fast and capable' },
            { value: 'claude-opus-4-5', label: 'Claude Opus 4.5', desc: 'Most capable — slower and more expensive' },
            { value: 'claude-haiku-4-5', label: 'Claude Haiku 4.5', desc: 'Fastest and cheapest — good for scoring' },
          ].map((m) => (
            <label key={m.value} className="flex items-start gap-3 cursor-pointer p-3 rounded-lg hover:bg-gray-50 border border-transparent hover:border-gray-200 transition-colors">
              <input
                type="radio"
                name="model"
                value={m.value}
                defaultChecked={m.value === 'claude-sonnet-4-5'}
                onChange={() => handleModelChange(m.value)}
                className="mt-0.5 accent-emerald-500"
              />
              <div>
                <p className="text-sm font-medium text-gray-800">{m.label}</p>
                <p className="text-xs text-gray-400">{m.desc}</p>
              </div>
            </label>
          ))}
        </div>
      </div>
    </div>
  )
}

// Key-rotation reminder — best practice is to rotate every 90 days.
function KeyRotation({ when, consoleUrl }) {
  if (!when) return null
  const days = Math.floor((Date.now() - new Date(when).getTime()) / 86400000)
  const stale = days > 90
  return (
    <p className={`mt-1.5 text-xs ${stale ? 'text-amber-700' : 'text-gray-400'}`}>
      {stale ? '⚠️ ' : ''}Last updated {days} day{days === 1 ? '' : 's'} ago.
      {stale && <> Consider rotating your API key (best practice: every 90 days). <a href={consoleUrl} target="_blank" rel="noreferrer" className="text-emerald-600 hover:underline">Rotate →</a></>}
    </p>
  )
}
