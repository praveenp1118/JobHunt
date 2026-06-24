import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import MasterCVTab from './MasterCVTab'
import DomainCVsTab from './DomainCVsTab'

export default function CVsPage() {
  const [tab, setTab] = useState('master')

  return (
    <div className="p-6 max-w-5xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-semibold text-gray-900">My CVs</h1>
          <p className="text-sm text-gray-500 mt-0.5">Master CV is your source of truth. Domain CVs are tailored per industry.</p>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 bg-gray-100 p-1 rounded-lg w-fit mb-6">
        {[
          { key: 'master', label: 'Master CV' },
          { key: 'domains', label: 'Domain CVs' },
        ].map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`px-5 py-1.5 rounded-md text-sm font-medium transition-colors ${
              tab === t.key ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500 hover:text-gray-700'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'master' && <MasterCVTab />}
      {tab === 'domains' && <DomainCVsTab />}
    </div>
  )
}
