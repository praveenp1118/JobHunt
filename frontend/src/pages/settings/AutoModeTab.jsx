import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { getPreferences, updatePreferences } from '../../api/auth'
import Button from '../../components/ui/Button'
import { toast } from '../../store/toast'

export default function AutoModeTab() {
  const qc = useQueryClient()
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  const { data } = useQuery({ queryKey: ['preferences'], queryFn: getPreferences })
  const prefs = data?.data || {}

  const handleToggle = async (field, value) => {
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
      {/* Auto mode master toggle */}
      <div className="bg-white rounded-2xl border border-gray-200 p-6">
        <div className="flex items-start justify-between">
          <div>
            <h2 className="text-sm font-semibold text-gray-900">Auto mode</h2>
            <p className="text-xs text-gray-500 mt-1 max-w-md">
              When ON, after you approve the change log, the application is sent automatically.
              When OFF (default), you always review before sending.
            </p>
            <div className="mt-3 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
              <p className="text-xs text-amber-700">
                ⚠️ Auto mode skips the final preview step. HITL is always preserved for recruiter replies.
              </p>
            </div>
          </div>
          <button
            onClick={() => handleToggle('auto_mode', !prefs.auto_mode)}
            className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors shrink-0 ml-4 ${
              prefs.auto_mode ? 'bg-emerald-500' : 'bg-gray-200'
            }`}
          >
            <span className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
              prefs.auto_mode ? 'translate-x-6' : 'translate-x-1'
            }`} />
          </button>
        </div>
      </div>

      {/* Auto mode settings */}
      <div className={`bg-white rounded-2xl border border-gray-200 p-6 transition-opacity ${!prefs.auto_mode ? 'opacity-50 pointer-events-none' : ''}`}>
        <h2 className="text-sm font-semibold text-gray-900 mb-4">Auto mode settings</h2>
        <div className="space-y-4">
          {/* Min S1 threshold */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="text-sm text-gray-700">Minimum S1 score to auto-apply</label>
              <span className="text-sm font-semibold text-gray-900">{prefs.auto_min_s1 || 80}</span>
            </div>
            <input
              type="range" min={50} max={95} step={5}
              value={prefs.auto_min_s1 || 80}
              onChange={(e) => handleToggle('auto_min_s1', parseInt(e.target.value))}
              className="w-full accent-emerald-500"
            />
            <div className="flex justify-between text-[10px] text-gray-400 mt-1">
              <span>50 — More applications</span>
              <span>95 — Only perfect fits</span>
            </div>
          </div>

          {/* Include CL */}
          <div className="flex items-center justify-between pt-3 border-t border-gray-100">
            <div>
              <p className="text-sm text-gray-700">Include cover letter</p>
              <p className="text-xs text-gray-400">Auto-attach cover letter when sending</p>
            </div>
            <button
              onClick={() => handleToggle('auto_include_cl', !prefs.auto_include_cl)}
              className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                prefs.auto_include_cl !== false ? 'bg-emerald-500' : 'bg-gray-200'
              }`}
            >
              <span className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                prefs.auto_include_cl !== false ? 'translate-x-6' : 'translate-x-1'
              }`} />
            </button>
          </div>
        </div>
      </div>

      {/* Follow-up settings */}
      <div className="bg-white rounded-2xl border border-gray-200 p-6">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="text-sm font-semibold text-gray-900">Auto follow-up</h2>
            <p className="text-xs text-gray-500 mt-0.5">Draft a follow-up email after no response</p>
          </div>
          <button
            onClick={() => handleToggle('auto_follow_up', !prefs.auto_follow_up)}
            className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
              prefs.auto_follow_up ? 'bg-emerald-500' : 'bg-gray-200'
            }`}
          >
            <span className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
              prefs.auto_follow_up ? 'translate-x-6' : 'translate-x-1'
            }`} />
          </button>
        </div>
        <div className={`transition-opacity ${!prefs.auto_follow_up ? 'opacity-50 pointer-events-none' : ''}`}>
          <div className="flex items-center gap-3">
            <label className="text-sm text-gray-700">Follow up after</label>
            <select
              value={prefs.follow_up_days || 7}
              onChange={(e) => handleToggle('follow_up_days', parseInt(e.target.value))}
              className="px-3 py-1.5 border border-gray-200 rounded-lg text-sm outline-none focus:border-emerald-400"
            >
              {[3, 5, 7, 10, 14].map((d) => (
                <option key={d} value={d}>{d} days</option>
              ))}
            </select>
            <span className="text-sm text-gray-500">of no response</span>
          </div>
        </div>
      </div>

      {saved && <p className="text-sm text-emerald-600">✓ Saved</p>}
    </div>
  )
}
