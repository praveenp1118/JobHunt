import { useState } from 'react'
import { toast } from '../../store/toast'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { getCredentials, updateCredentials } from '../../api/auth'
import Button from '../../components/ui/Button'
import Input from '../../components/ui/Input'

export default function PlanKeysTab() {
  const [anthropicKey, setAnthropicKey] = useState('')
  const [apifyToken, setApifyToken] = useState('')
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState('')

  const { data } = useQuery({
    queryKey: ['credentials'],
    queryFn: getCredentials,
  })

  const creds = data?.data || {}

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
      {/* Plan info */}
      <div className="bg-white rounded-2xl border border-gray-200 p-6">
        <h2 className="text-sm font-semibold text-gray-900 mb-3">Current plan</h2>
        <div className="flex items-center gap-3 p-4 bg-slate-50 rounded-xl">
          <div className="w-10 h-10 bg-slate-200 rounded-lg flex items-center justify-center">
            <svg className="w-5 h-5 text-slate-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z" />
            </svg>
          </div>
          <div>
            <p className="text-sm font-semibold text-gray-900">Default Plan — Own keys</p>
            <p className="text-xs text-gray-500 mt-0.5">You use your own Anthropic + Apify keys. Billed directly, no markup.</p>
          </div>
        </div>
      </div>

      {/* API keys */}
      <div className="bg-white rounded-2xl border border-gray-200 p-6">
        <h2 className="text-sm font-semibold text-gray-900 mb-1">API keys</h2>
        <p className="text-xs text-gray-500 mb-5">Keys are encrypted with AES-256 at rest. Never shared or logged.</p>

        <div className="space-y-4">
          {/* Anthropic */}
          <div>
            <div className="flex items-center justify-between mb-1.5">
              <label className="text-sm font-medium text-gray-700">Anthropic API key</label>
              <span className={`text-xs font-medium ${creds.has_anthropic_key ? 'text-emerald-600' : 'text-gray-400'}`}>
                {creds.has_anthropic_key ? '✓ Saved' : 'Not set'}
              </span>
            </div>
            <Input
              type="password"
              placeholder={creds.has_anthropic_key ? '••••••••••••••••• (saved)' : 'sk-ant-...'}
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
          </div>

          {/* Apify */}
          <div>
            <div className="flex items-center justify-between mb-1.5">
              <label className="text-sm font-medium text-gray-700">Apify token</label>
              <span className={`text-xs font-medium ${creds.has_apify_token ? 'text-emerald-600' : 'text-gray-400'}`}>
                {creds.has_apify_token ? '✓ Saved' : 'Not set'}
              </span>
            </div>
            <Input
              type="password"
              placeholder={creds.has_apify_token ? '••••••••••••••••• (saved)' : 'apify_api_...'}
              value={apifyToken}
              onChange={(e) => setApifyToken(e.target.value)}
              hint={
                <span>
                  Used for weekly job scanning.{' '}
                  <a href="https://console.apify.com" target="_blank" rel="noreferrer" className="text-emerald-600 hover:underline">
                    console.apify.com
                  </a>
                </span>
              }
            />
          </div>
        </div>

        {error && <p className="text-sm text-red-500 mt-3">{error}</p>}

        <div className="flex justify-end mt-5">
          <Button onClick={handleSave} loading={saving} disabled={!anthropicKey && !apifyToken} size="sm">
            Save keys
          </Button>
        </div>
      </div>

      {/* Model selector */}
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
