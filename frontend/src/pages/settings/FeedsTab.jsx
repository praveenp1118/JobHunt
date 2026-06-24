import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { format } from 'date-fns'
import { getDomainCVs } from '../../api/cvs'
import { getFeeds, toggleFeed, updateFeed, triggerScan, getScannerStatus } from '../../api/feeds'
import Button from '../../components/ui/Button'
import Spinner from '../../components/ui/Spinner'
import { toast } from '../../store/toast'

export default function FeedsTab() {
  const qc = useQueryClient()
  const [scanning, setScanning] = useState(false)
  const [editingFeedId, setEditingFeedId] = useState(null)
  const [editKeywords, setEditKeywords] = useState('')

  const { data: domainData } = useQuery({
    queryKey: ['domain-cvs'],
    queryFn: getDomainCVs,
  })

  const { data: feedsData, isLoading } = useQuery({
    queryKey: ['feeds'],
    queryFn: getFeeds,
    refetchInterval: 10000,
  })

  const { data: scanData } = useQuery({
    queryKey: ['scanner-status'],
    queryFn: getScannerStatus,
    refetchInterval: scanning ? 5000 : 30000,
  })

  const domainCVs = domainData?.data || []
  const feeds = feedsData?.data || []
  const scans = scanData?.data || []

  // Group feeds by domain CV
  const autoFeeds = feeds.filter((f) => f.is_auto_generated)
  const platformFeeds = feeds.filter((f) => f.is_platform && !f.is_auto_generated)
  const customFeeds = feeds.filter((f) => !f.is_platform && !f.is_auto_generated)

  const getDomainCVLabel = (domainCvId) => {
    const cv = domainCVs.find((c) => c.id === domainCvId)
    if (!cv) return 'Unknown domain'
    return `${cv.industry_label || 'Industry'} × ${cv.function_label || 'Function'}`
  }

  const handleToggle = async (id) => {
    await toggleFeed(id)
    qc.invalidateQueries({ queryKey: ['feeds'] })
  }

  const handleSaveKeywords = async (feedId) => {
    try {
      await updateFeed(feedId, { search_keywords: editKeywords })
      qc.invalidateQueries({ queryKey: ['feeds'] })
      setEditingFeedId(null)
      toast.success('Keywords updated')
    } catch {
      toast.error('Failed to update keywords')
    }
  }

  const handleScan = async () => {
    setScanning(true)
    try {
      await triggerScan()
      toast.success('Scan queued — check history below')
      setTimeout(() => {
        qc.invalidateQueries({ queryKey: ['scanner-status'] })
        setScanning(false)
      }, 3000)
    } catch (e) {
      toast.error('Scan failed: ' + (e.response?.data?.detail || e.message))
      setScanning(false)
    }
  }

  if (isLoading) return <div className="flex justify-center py-8"><Spinner /></div>

  return (
    <div className="space-y-6">
      {/* Header + scan button */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold text-gray-900">Feeds & Scanning</h2>
          <p className="text-xs text-gray-500 mt-0.5">
            Feed profiles are auto-generated from your domain CVs
          </p>
        </div>
        <Button size="sm" onClick={handleScan} loading={scanning}>
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
          </svg>
          Run scan now
        </Button>
      </div>

      {/* Domain CV feed profiles */}
      {autoFeeds.length > 0 && (
        <div className="bg-white rounded-2xl border border-gray-200 overflow-hidden">
          <div className="px-5 py-3 border-b border-gray-100 bg-emerald-50">
            <p className="text-xs font-semibold text-emerald-700">
              Domain CV feed profiles — auto-generated, personalised keywords
            </p>
          </div>
          <div className="divide-y divide-gray-50">
            {autoFeeds.map((feed) => (
              <div key={feed.id} className="px-5 py-4">
                <div className="flex items-start justify-between gap-3">
                  <div className="flex items-start gap-3 flex-1 min-w-0">
                    <button
                      onClick={() => handleToggle(feed.id)}
                      className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors shrink-0 mt-0.5 ${
                        feed.is_active ? 'bg-emerald-500' : 'bg-gray-200'
                      }`}
                    >
                      <span className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white transition-transform ${
                        feed.is_active ? 'translate-x-4' : 'translate-x-0.5'
                      }`} />
                    </button>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <p className="text-sm font-medium text-gray-900 truncate">{feed.name}</p>
                        <span className="text-[10px] bg-emerald-100 text-emerald-700 px-1.5 py-0.5 rounded-full font-medium shrink-0">
                          {feed.domain_cv_id ? getDomainCVLabel(feed.domain_cv_id) : 'Generic'}
                        </span>
                      </div>

                      {/* Keywords display/edit */}
                      {editingFeedId === feed.id ? (
                        <div className="mt-2 flex items-center gap-2">
                          <input
                            value={editKeywords}
                            onChange={(e) => setEditKeywords(e.target.value)}
                            className="flex-1 px-2 py-1 border border-emerald-300 rounded text-xs outline-none"
                            placeholder="head of product ecommerce..."
                          />
                          <Button size="sm" onClick={() => handleSaveKeywords(feed.id)}>Save</Button>
                          <Button size="sm" variant="ghost" onClick={() => setEditingFeedId(null)}>Cancel</Button>
                        </div>
                      ) : (
                        <div className="flex items-center gap-2 mt-1">
                          <p className="text-xs text-gray-500 truncate">
                            🔍 {feed.search_keywords || feed.keywords || 'No keywords set'}
                          </p>
                          <button
                            onClick={() => { setEditingFeedId(feed.id); setEditKeywords(feed.search_keywords || feed.keywords || '') }}
                            className="text-[10px] text-emerald-600 hover:text-emerald-700 font-medium shrink-0"
                          >
                            Edit
                          </button>
                        </div>
                      )}

                      {/* Job boards */}
                      {feed.job_boards && (
                        <div className="flex flex-wrap gap-1 mt-1.5">
                          {JSON.parse(feed.job_boards).slice(0, 4).map((b, i) => (
                            <span key={i} className="text-[10px] bg-gray-100 text-gray-500 px-1.5 py-0.5 rounded">
                              {b.name}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {autoFeeds.length === 0 && (
        <div className="bg-emerald-50 border border-emerald-200 rounded-xl p-4 text-sm text-emerald-700">
          💡 Generate and apply a domain CV — a personalised feed profile will be created automatically.
        </div>
      )}

      {/* Platform feeds */}
      {platformFeeds.length > 0 && (
        <div className="bg-white rounded-2xl border border-gray-200 overflow-hidden">
          <div className="px-5 py-3 border-b border-gray-100">
            <p className="text-xs font-semibold text-gray-600">Platform feeds — generic keywords</p>
          </div>
          <div className="divide-y divide-gray-50">
            {platformFeeds.map((feed) => (
              <div key={feed.id} className="flex items-center justify-between px-5 py-3">
                <div className="flex items-center gap-3 flex-1 min-w-0">
                  <button
                    onClick={() => handleToggle(feed.id)}
                    className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors shrink-0 ${
                      feed.is_active ? 'bg-emerald-500' : 'bg-gray-200'
                    }`}
                  >
                    <span className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white transition-transform ${
                      feed.is_active ? 'translate-x-4' : 'translate-x-0.5'
                    }`} />
                  </button>
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-gray-700 truncate">{feed.name}</p>
                    <p className="text-xs text-gray-400 truncate">{feed.url_or_actor}</p>
                  </div>
                </div>
                <span className={`text-[10px] font-medium px-2 py-0.5 rounded-full ${
                  feed.feed_type === 'rss' ? 'bg-orange-100 text-orange-600' : 'bg-purple-100 text-purple-600'
                }`}>
                  {feed.feed_type.toUpperCase()}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Scan history */}
      <div className="bg-white rounded-2xl border border-gray-200 overflow-hidden">
        <div className="px-5 py-3 border-b border-gray-100">
          <p className="text-xs font-semibold text-gray-600">Scan history</p>
        </div>
        {scans.length === 0 ? (
          <p className="text-sm text-gray-400 text-center py-6">No scans yet — click Run scan now</p>
        ) : (
          <table className="w-full">
            <thead className="border-b border-gray-50">
              <tr>
                {['Started', 'Status', 'Found', 'Added', 'Duration'].map((h) => (
                  <th key={h} className="px-4 py-2 text-left text-xs font-medium text-gray-500">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {scans.map((scan) => (
                <tr key={scan.id}>
                  <td className="px-4 py-2.5 text-xs text-gray-500">
                    {scan.started_at ? format(new Date(scan.started_at), 'MMM d HH:mm') : '—'}
                  </td>
                  <td className="px-4 py-2.5">
                    <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${
                      scan.status === 'success' ? 'bg-emerald-100 text-emerald-700' :
                      scan.status === 'error' ? 'bg-red-100 text-red-600' :
                      scan.status === 'running' ? 'bg-blue-100 text-blue-600 animate-pulse' :
                      'bg-yellow-100 text-yellow-700'
                    }`}>
                      {scan.status}
                    </span>
                  </td>
                  <td className="px-4 py-2.5 text-sm text-gray-700">{scan.jobs_found ?? '—'}</td>
                  <td className="px-4 py-2.5 text-sm font-medium text-emerald-600">{scan.jobs_added ?? '—'}</td>
                  <td className="px-4 py-2.5 text-xs text-gray-400">
                    {scan.completed_at && scan.started_at
                      ? `${Math.round((new Date(scan.completed_at) - new Date(scan.started_at)) / 1000)}s`
                      : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
