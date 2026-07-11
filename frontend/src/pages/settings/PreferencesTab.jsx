import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { getPreferences, updatePreferences } from '../../api/auth'
import { updateCommunityPreferences } from '../../api/community'
import ScoringSettings from './ScoringSettings'
import Button from '../../components/ui/Button'
import { toast } from '../../store/toast'

export default function PreferencesTab() {
  const qc = useQueryClient()
  const navigate = useNavigate()
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  const { data } = useQuery({ queryKey: ['preferences'], queryFn: getPreferences })
  const prefs = data?.data || {}

  const toggleCommunity = async (value) => {
    try {
      await updateCommunityPreferences(value)
      qc.invalidateQueries({ queryKey: ['preferences'] })
      toast.success(value ? 'Community sharing enabled' : 'Community sharing disabled')
    } catch { toast.error('Failed to update') }
  }

  const update = async (field, value) => {
    setSaving(true)
    try {
      await updatePreferences({ [field]: value })
      qc.invalidateQueries({ queryKey: ['preferences'] })
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
      toast.success('Saved')
    } catch (e) { console.error(e) }
    finally { setSaving(false) }
  }

  return (
    <div className="space-y-5">
      {/* Cover letter */}
      <div className="bg-white rounded-2xl border border-gray-200 p-6">
        <h2 className="text-sm font-semibold text-gray-900 mb-4">Cover letter</h2>
        <div className="space-y-4">
          <div>
            <label className="text-sm font-medium text-gray-700 block mb-1.5">Tone</label>
            <select value={prefs.cl_tone || 'professional'} onChange={(e) => update('cl_tone', e.target.value)}
              className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm outline-none focus:border-emerald-400">
              <option value="formal">Formal</option>
              <option value="professional">Professional (recommended)</option>
              <option value="conversational">Conversational</option>
              <option value="concise">Concise</option>
            </select>
          </div>
          <div>
            <label className="text-sm font-medium text-gray-700 block mb-1.5">Template</label>
            <div className="space-y-2">
              {[
                { value: 'random', label: 'Random (recommended)', desc: 'Rotates automatically — never uses same template twice in a row' },
                { value: 'hook_first', label: 'Hook-first', desc: 'Opens with a bold, specific statement about what you bring' },
                { value: 'story_led', label: 'Story-led', desc: 'Opens with a relevant achievement story' },
                { value: 'problem_solver', label: 'Problem-solver', desc: 'Opens by identifying a company challenge you would solve' },
                { value: 'concise', label: 'Concise', desc: '3 short paragraphs, no fluff' },
              ].map((t) => (
                <label key={t.value} className="flex items-start gap-3 cursor-pointer p-3 rounded-lg hover:bg-gray-50 border border-transparent hover:border-gray-200 transition-colors">
                  <input type="radio" name="cl_template" value={t.value}
                    checked={(prefs.cl_template || 'random') === t.value}
                    onChange={() => update('cl_template', t.value)}
                    className="mt-0.5 accent-emerald-500"
                  />
                  <div>
                    <p className="text-sm font-medium text-gray-800">{t.label}</p>
                    <p className="text-xs text-gray-400">{t.desc}</p>
                  </div>
                </label>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Scoring thresholds */}
      <div className="bg-white rounded-2xl border border-gray-200 p-6">
        <h2 className="text-sm font-semibold text-gray-900 mb-4">Scoring thresholds</h2>
        <div className="space-y-4">
          <div>
            <div className="flex items-center justify-between mb-1">
              <label className="text-sm text-gray-700">Minimum S1 to show in tracker</label>
              <span className="text-sm font-semibold text-gray-900">{prefs.s1_min_threshold || 65}</span>
            </div>
            <input type="range" min={40} max={90} step={5}
              value={prefs.s1_min_threshold || 65}
              onChange={(e) => update('s1_min_threshold', parseInt(e.target.value))}
              className="w-full accent-emerald-500" />
            <p className="text-xs text-gray-400 mt-1">Jobs below this score are saved but de-prioritised</p>
          </div>

          <div className="pt-3 border-t border-gray-100">
            <div className="flex items-center justify-between mb-1">
              <label className="text-sm text-gray-700">S3 block threshold (below = cannot send)</label>
              <span className="text-sm font-semibold text-red-600">{prefs.s3_block_threshold || 85}%</span>
            </div>
            <input type="range" min={70} max={90} step={5}
              value={prefs.s3_block_threshold || 85}
              onChange={(e) => update('s3_block_threshold', parseInt(e.target.value))}
              className="w-full accent-red-500" />
          </div>

          <div className="pt-3 border-t border-gray-100">
            <div className="flex items-center justify-between mb-1">
              <label className="text-sm text-gray-700">S3 review threshold (below = amber warning)</label>
              <span className="text-sm font-semibold text-amber-600">{prefs.s3_review_threshold || 90}%</span>
            </div>
            <input type="range" min={85} max={98} step={1}
              value={prefs.s3_review_threshold || 90}
              onChange={(e) => update('s3_review_threshold', parseInt(e.target.value))}
              className="w-full accent-amber-500" />
          </div>
        </div>
      </div>

      {/* Ghosting */}
      <div className="bg-white rounded-2xl border border-gray-200 p-6">
        <h2 className="text-sm font-semibold text-gray-900 mb-4">Ghosting detection</h2>
        <div className="flex items-center gap-3">
          <label className="text-sm text-gray-700">Auto-flag as Ghosted after</label>
          <select value={prefs.ghost_after_days || 28}
            onChange={(e) => update('ghost_after_days', parseInt(e.target.value))}
            className="px-3 py-1.5 border border-gray-200 rounded-lg text-sm outline-none focus:border-emerald-400">
            {[14, 21, 28, 35, 42].map((d) => (
              <option key={d} value={d}>{d} days</option>
            ))}
          </select>
          <span className="text-sm text-gray-500">of no response (Applied status)</span>
        </div>
      </div>

      {saved && <p className="text-sm text-emerald-600">✓ Saved</p>}

      {/* Community */}
      <div className="bg-white rounded-2xl border border-gray-200 p-6">
        <h2 className="text-sm font-semibold text-gray-900 mb-4">🤝 Community</h2>
        <div className="flex items-start justify-between gap-4">
          <div className="flex-1">
            <p className="text-sm font-medium text-gray-700">Share job insights with the AIJobsHunt community</p>
            <p className="text-xs text-gray-500 mt-1">
              When ON, your <span className="font-medium">anonymised</span> job scores, JD highlights, and tailoring
              patterns help other members — at no token cost to them. Your CV is never shared.
            </p>
          </div>
          <button
            onClick={() => toggleCommunity(!prefs.community_sharing_enabled)}
            className={`shrink-0 w-11 h-6 rounded-full transition-colors relative ${prefs.community_sharing_enabled ? 'bg-emerald-500' : 'bg-gray-300'}`}
          >
            <span className={`absolute top-0.5 w-5 h-5 bg-white rounded-full shadow transition-transform ${prefs.community_sharing_enabled ? 'translate-x-5' : 'translate-x-0.5'}`} />
          </button>
        </div>
        <button onClick={() => navigate('/community/contributions')}
          className="mt-4 text-xs font-medium text-emerald-600 hover:underline">
          View my contributions →
        </button>
      </div>

      {/* Scoring & Cost Optimization */}
      <div className="bg-white rounded-2xl border border-gray-200 p-5">
        <ScoringSettings />
      </div>
    </div>
  )
}
