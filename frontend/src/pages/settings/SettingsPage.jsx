import { useState } from 'react'
import ProfileTab from './ProfileTab'
import PlanKeysTab from './PlanKeysTab'
import GmailTab from './GmailTab'
import AutoModeTab from './AutoModeTab'
import PreferencesTab from './PreferencesTab'
import ErrorLogTab from './ErrorLogTab'
import FeedsTab from './FeedsTab'
import UsageTab from './UsageTab'

const TABS = [
  { key: 'profile',     label: 'Profile' },
  { key: 'plan',        label: 'Plan & Keys' },
  { key: 'gmail',       label: 'Gmail' },
  { key: 'auto',        label: 'Auto Mode' },
  { key: 'preferences', label: 'Preferences' },
  { key: 'feeds',       label: 'Feeds & Scanning' },
  { key: 'errors',      label: 'Error Log' },
  { key: 'usage',       label: 'API Usage' },
]

export default function SettingsPage() {
  // Honour /settings#<tab> (e.g. Dashboard "Manage feeds" → #feeds, billing cancel → #plan).
  const [tab, setTab] = useState(() => {
    const h = typeof window !== 'undefined' ? window.location.hash.replace('#', '') : ''
    return TABS.some((t) => t.key === h) ? h : 'profile'
  })

  return (
    <div className="p-6 mx-auto max-w-5xl">
      <div className="mb-6">
        <h1 className="text-xl font-semibold text-gray-900">Settings</h1>
        <p className="text-sm text-gray-500 mt-0.5">Manage your profile, API keys, and preferences</p>
      </div>

      {/* Tab nav */}
      <div className="flex flex-wrap gap-0 border-b border-gray-200 mb-6">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-colors whitespace-nowrap ${
              tab === t.key
                ? 'border-emerald-500 text-emerald-600'
                : 'border-transparent text-gray-500 hover:text-gray-700'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'profile'     && <ProfileTab />}
      {tab === 'plan'        && <PlanKeysTab />}
      {tab === 'gmail'       && <GmailTab />}
      {tab === 'auto'        && <AutoModeTab />}
      {tab === 'preferences' && <PreferencesTab />}
      {tab === 'feeds'       && <FeedsTab />}
      {tab === 'errors'      && <ErrorLogTab />}
      {tab === 'usage'       && <UsageTab />}
    </div>
  )
}
