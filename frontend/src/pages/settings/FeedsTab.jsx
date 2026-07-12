import { useState, useEffect } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { formatDistanceToNow, format } from 'date-fns'
import {
  getFeeds, toggleFeed, deleteFeed, createFeed, updateFeed, suggestFeed, searchApifyActors, runFeed,
  getTargetCompanies, addTargetCompany, removeTargetCompany,
  triggerScan, getScannerStatus,
} from '../../api/feeds'
import { getDomainCVs } from '../../api/cvs'
import Button from '../../components/ui/Button'
import Input from '../../components/ui/Input'
import Spinner from '../../components/ui/Spinner'
import ScanFeedBreakdown from '../../components/ui/ScanFeedBreakdown'
import Pagination, { usePagination } from '../../components/ui/Pagination'
import TokenBadge from '../../components/ui/TokenBadge'
import { toast } from '../../store/toast'

export default function FeedsTab() {
  const qc = useQueryClient()
  const [tab, setTab] = useState('feeds')
  const [scanning, setScanning] = useState(false)
  const [scanMsg, setScanMsg] = useState('')
  const [showAddFeed, setShowAddFeed] = useState(false)
  const [showAddCompany, setShowAddCompany] = useState(false)
  const [editFeed, setEditFeed] = useState(null)

  const { data: feedsData, isLoading: feedsLoading } = useQuery({
    queryKey: ['feeds'],
    queryFn: getFeeds,
  })

  const { data: domainData } = useQuery({
    queryKey: ['domain-cvs'],
    queryFn: getDomainCVs,
  })

  const { data: companiesData } = useQuery({
    queryKey: ['companies'],
    queryFn: getTargetCompanies,
  })

  const { data: scanData, refetch: refetchScans } = useQuery({
    queryKey: ['scanner-status'],
    queryFn: getScannerStatus,
    refetchInterval: scanning ? 5000 : false,
  })

  const feeds = feedsData?.data || []
  const domainCVs = domainData?.data || []
  const companies = companiesData?.data || []
  const scans = scanData?.data || []
  const scansPg = usePagination(scans, 10)

  // Auto-generated domain-CV feeds get their own section; the rest split platform/custom
  const autoFeeds = feeds.filter((f) => f.is_auto_generated)
  const platformFeeds = feeds.filter((f) => f.is_platform && !f.is_auto_generated)
  const customFeeds = feeds.filter((f) => !f.is_platform && !f.is_auto_generated)

  const domainCVChip = (id) => {
    const cv = domainCVs.find((c) => c.id === id)
    if (!cv) return null
    return `${cv.industry_label || 'Industry'} × ${cv.function_label || 'Function'}`
  }

  const handleToggle = async (id) => {
    await toggleFeed(id)
    qc.invalidateQueries({ queryKey: ['feeds'] })
  }

  const handleDelete = async (id) => {
    await deleteFeed(id)
    qc.invalidateQueries({ queryKey: ['feeds'] })
  }

  // Run a single feed now (synchronous) and report the result
  const handleRunFeed = async (feed) => {
    const { data } = await runFeed(feed.id)
    if (data.quota_exhausted) {
      toast.error(`${feed.name}: Apify credits/usage limit reached on your token — top up your Apify account or wait for the monthly reset.`)
      qc.invalidateQueries({ queryKey: ['feeds'] })
      return
    }
    if (data.error_kind) {
      toast.error(`${feed.name}: ${data.reason || 'feed run failed'}`)
      qc.invalidateQueries({ queryKey: ['feeds'] })
      return
    }
    const tk = data.tokens_used
    let msg = `${feed.name}: ${data.jobs_found} found, ${data.jobs_added} added`
    if (tk) msg += ` · ⚡ ${tk < 1000 ? tk : (tk / 1000).toFixed(1) + 'K'} · ₹${(data.cost_inr || 0).toFixed(2)}`
    if (data.apify_runs) msg += ` · Apify ${data.apify_runs} runs $${(data.apify_cost || 0).toFixed(2)}`
    toast.success(msg)
    qc.invalidateQueries({ queryKey: ['feeds'] })
  }

  const handleScan = async () => {
    setScanning(true)
    setScanMsg('')
    try {
      await triggerScan()
      setScanMsg('Scan queued — check status below for progress')
      setTimeout(() => refetchScans(), 3000)
    } catch (e) {
      setScanMsg('Failed to trigger scan: ' + (e.response?.data?.detail || e.message))
    } finally {
      setScanning(false)
    }
  }

  const handleRemoveCompany = async (id) => {
    await removeTargetCompany(id)
    qc.invalidateQueries({ queryKey: ['companies'] })
  }

  return (
    <div>
      {/* Heading omitted — Settings already labels this tab "Feeds & Scanning" */}
      <div className="flex items-center justify-end mb-5">
        <Button onClick={handleScan} loading={scanning}>
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
          </svg>
          Run scan now
        </Button>
      </div>

      {scanMsg && (
        <div className="bg-emerald-50 border border-emerald-200 rounded-xl px-4 py-3 text-sm text-emerald-700 mb-5">
          {scanMsg}
        </div>
      )}

      {/* Tabs */}
      <div className="flex gap-1 bg-gray-100 p-1 rounded-lg w-fit mb-6">
        {[
          { key: 'feeds', label: 'RSS & Apify Feeds' },
          { key: 'companies', label: 'Target Companies' },
          { key: 'history', label: 'Scan History' },
        ].map((t) => (
          <button key={t.key} onClick={() => setTab(t.key)}
            className={`px-4 py-1.5 rounded-md text-sm font-medium transition-colors whitespace-nowrap ${
              tab === t.key ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500 hover:text-gray-700'
            }`}>
            {t.label}
          </button>
        ))}
      </div>

      {/* ── Feeds tab ── */}
      {tab === 'feeds' && (
        <div>
          {/* Platform feeds */}
          <div className="mb-5">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-sm font-semibold text-gray-700">Platform feeds</h2>
              <span className="text-xs text-gray-400">{platformFeeds.filter(f => f.is_active).length} active</span>
            </div>
            <div className="bg-white rounded-xl border border-gray-200 divide-y divide-gray-50">
              {feedsLoading ? (
                <div className="flex justify-center py-6"><Spinner /></div>
              ) : platformFeeds.map((feed) => (
                <FeedRow key={feed.id} feed={feed} onToggle={handleToggle} onEdit={setEditFeed} onRun={handleRunFeed} canDelete={false} />
              ))}
            </div>
          </div>

          {/* Domain CV Profiles (auto-generated) */}
          {autoFeeds.length > 0 && (
            <div className="mb-5">
              <div className="flex items-center justify-between mb-3">
                <h2 className="text-sm font-semibold text-gray-700">Domain CV Profiles</h2>
                <span className="text-xs text-gray-400">auto-generated from your domain CVs</span>
              </div>
              <div className="bg-white rounded-xl border border-emerald-100 divide-y divide-gray-50">
                {autoFeeds.map((feed) => (
                  <FeedRow key={feed.id} feed={feed} onToggle={handleToggle} onEdit={setEditFeed}
                    onDelete={handleDelete} onRun={handleRunFeed} canDelete
                    autoBadge chip={domainCVChip(feed.domain_cv_id)} />
                ))}
              </div>
            </div>
          )}

          {/* Custom feeds */}
          <div>
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-sm font-semibold text-gray-700">Custom feeds</h2>
              <Button size="sm" variant="secondary" onClick={() => setShowAddFeed(true)}>
                + Add feed
              </Button>
            </div>
            {customFeeds.length === 0 ? (
              <div className="bg-white rounded-xl border border-gray-200 p-8 text-center">
                <p className="text-sm text-gray-400 mb-3">No custom feeds yet</p>
                <Button size="sm" variant="secondary" onClick={() => setShowAddFeed(true)}>
                  Add RSS or Apify feed
                </Button>
              </div>
            ) : (
              <div className="bg-white rounded-xl border border-gray-200 divide-y divide-gray-50">
                {customFeeds.map((feed) => (
                  <FeedRow key={feed.id} feed={feed} onToggle={handleToggle} onEdit={setEditFeed}
                    onDelete={handleDelete} onRun={handleRunFeed} canDelete
                    chip={feed.domain_cv_id ? domainCVChip(feed.domain_cv_id) : null} />
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── Companies tab ── */}
      {tab === 'companies' && (
        <div>
          <div className="flex items-center justify-between mb-3">
            <p className="text-sm text-gray-600">{companies.length} companies tracked</p>
            <Button size="sm" variant="secondary" onClick={() => setShowAddCompany(true)}>
              + Add company
            </Button>
          </div>
          <div className="grid grid-cols-2 gap-3">
            {companies.map((co) => (
              <div key={co.id} className="bg-white rounded-xl border border-gray-200 px-4 py-3 flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-gray-900">{co.company_name}</p>
                  <div className="flex items-center gap-2 mt-0.5">
                    {co.market && (
                      <span className="text-[10px] bg-gray-100 text-gray-500 px-1.5 py-0.5 rounded-full">{co.market}</span>
                    )}
                    {co.career_page_url && (
                      <a href={co.career_page_url} target="_blank" rel="noreferrer"
                        className="text-[10px] text-emerald-600 hover:underline">
                        Careers →
                      </a>
                    )}
                  </div>
                </div>
                {!co.is_platform && (
                  <button onClick={() => handleRemoveCompany(co.id)}
                    className="text-gray-300 hover:text-red-400 transition-colors ml-2">
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                    </svg>
                  </button>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── History tab ── */}
      {tab === 'history' && (
        <div>
          {scans.length === 0 ? (
            <div className="bg-white rounded-2xl border border-gray-200 p-10 text-center">
              <p className="text-sm text-gray-400">No scans run yet</p>
              <p className="text-xs text-gray-400 mt-1">Click "Run scan now" to start</p>
            </div>
          ) : (
            <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
              <table className="w-full">
                <thead className="border-b border-gray-100">
                  <tr>
                    {['Started', 'Status', 'Found', 'Added', 'Duration', 'Error'].map((h) => (
                      <th key={h} className="px-4 py-2.5 text-left text-xs font-medium text-gray-500">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-50">
                  {scansPg.slice.map((scan) => <ScanHistoryRow key={scan.id} scan={scan} />)}
                </tbody>
              </table>
              <div className="px-4 pb-3">
                <Pagination currentPage={scansPg.page} totalPages={scansPg.totalPages} totalItems={scansPg.total} itemsPerPage={10} onPageChange={scansPg.setPage} label="scans" />
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── Add feed modal ── */}
      {showAddFeed && (
        <AddFeedModal
          onClose={() => setShowAddFeed(false)}
          onSuccess={() => { qc.invalidateQueries({ queryKey: ['feeds'] }); setShowAddFeed(false) }}
        />
      )}

      {/* ── Add company modal ── */}
      {showAddCompany && (
        <AddCompanyModal
          onClose={() => setShowAddCompany(false)}
          onSuccess={() => { qc.invalidateQueries({ queryKey: ['companies'] }); setShowAddCompany(false) }}
        />
      )}

      {/* ── Edit feed modal ── */}
      {editFeed && (
        <EditFeedModal
          feed={editFeed}
          domainCVs={domainCVs}
          onClose={() => setEditFeed(null)}
          onSuccess={() => { qc.invalidateQueries({ queryKey: ['feeds'] }); setEditFeed(null) }}
        />
      )}
    </div>
  )
}

function ScanHistoryRow({ scan }) {
  const [open, setOpen] = useState(false)
  const feeds = scan.details?.feeds_summary || []
  const u = scan.details?.usage_summary
  const dur = scan.completed_at && scan.started_at
    ? `${Math.round((new Date(scan.completed_at) - new Date(scan.started_at)) / 1000)}s`
    : (scan.duration_seconds != null ? `${Math.round(scan.duration_seconds)}s` : scan.status === 'running' ? 'Running…' : '—')
  return (
    <>
      <tr className={feeds.length ? 'cursor-pointer hover:bg-gray-50' : ''}
        onClick={() => feeds.length && setOpen((o) => !o)}>
        <td className="px-4 py-3 text-xs text-gray-600">
          {scan.started_at ? format(new Date(scan.started_at), 'MMM d HH:mm') : '—'}
          {feeds.length > 0 && <span className="ml-1 text-gray-400">{open ? '▲' : '▼'}</span>}
        </td>
        <td className="px-4 py-3">
          <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${
            scan.status === 'success' ? 'bg-emerald-100 text-emerald-700' :
            scan.status === 'error' ? 'bg-red-100 text-red-600' :
            scan.status === 'running' ? 'bg-blue-100 text-blue-600' :
            'bg-yellow-100 text-yellow-700'
          }`}>
            {scan.status}
          </span>
        </td>
        <td className="px-4 py-3 text-sm text-gray-700">{scan.jobs_found ?? '—'}</td>
        <td className="px-4 py-3 text-sm font-medium text-emerald-600">{scan.jobs_added ?? '—'}</td>
        <td className="px-4 py-3 text-xs text-gray-400">{dur}</td>
        <td className="px-4 py-3 text-xs text-red-400 max-w-[200px] truncate">{scan.error || '—'}</td>
      </tr>
      {open && feeds.length > 0 && (
        <tr>
          <td colSpan={6} className="px-4 py-3 bg-gray-50/50 border-t border-gray-100">
            {u && (u.anthropic_tokens > 0 || u.apify_runs > 0) && (
              <p className="text-[11px] text-gray-500 mb-2">
                ⚡ Anthropic: {u.anthropic_tokens >= 1000 ? (u.anthropic_tokens / 1000).toFixed(1) + 'K' : u.anthropic_tokens} tokens · ₹{(u.anthropic_inr || 0).toFixed(2)}
                {u.apify_runs > 0 && ` | Apify: ${u.apify_runs} runs · $${(u.apify_usd || 0).toFixed(2)}`}
              </p>
            )}
            <div className="space-y-3">
              {feeds.map((f, i) => <ScanFeedBreakdown key={i} f={f} />)}
            </div>
          </td>
        </tr>
      )}
    </>
  )
}

function FeedRow({ feed, onToggle, onEdit, onDelete, onRun, canDelete, chip, autoBadge }) {
  const [running, setRunning] = useState(false)
  const handleRun = async () => {
    setRunning(true)
    try { await onRun(feed) } catch (e) { toast.error('Run failed: ' + (e.response?.data?.detail || e.message)) }
    finally { setRunning(false) }
  }
  return (
    <div className="flex items-center justify-between px-4 py-3">
      <div className="flex items-center gap-3 flex-1 min-w-0">
        <button onClick={() => onToggle(feed.id)}
          className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors shrink-0 ${
            feed.is_active ? 'bg-emerald-500' : 'bg-gray-200'
          }`}>
          <span className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white transition-transform ${
            feed.is_active ? 'translate-x-4' : 'translate-x-0.5'
          }`} />
        </button>
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <p className="text-sm font-medium text-gray-900 truncate">{feed.name}</p>
            <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium ${
              feed.feed_type === 'rss' ? 'bg-orange-100 text-orange-600' : 'bg-purple-100 text-purple-600'
            }`}>
              {feed.feed_type.toUpperCase()}
            </span>
            {autoBadge && (
              <span className="text-[10px] bg-emerald-100 text-emerald-700 px-1.5 py-0.5 rounded-full font-medium">
                Auto-generated from domain CV
              </span>
            )}
            {chip && (
              <span className="text-[10px] bg-emerald-50 text-emerald-700 border border-emerald-100 px-1.5 py-0.5 rounded-full font-medium">
                {chip}
              </span>
            )}
          </div>
          <p className="text-xs text-gray-400 truncate">{feed.url_or_actor}</p>
        </div>
      </div>
      <div className="flex items-center gap-1 ml-3 shrink-0">
        {onRun && (
          <button onClick={handleRun} disabled={running} title="Run this feed now"
            className="text-xs px-2 py-1 rounded-lg border border-emerald-200 text-emerald-700 bg-emerald-50 hover:bg-emerald-100 disabled:opacity-60 font-medium inline-flex items-center gap-1 mr-1">
            {running && (
              <svg className="w-3 h-3 animate-spin" viewBox="0 0 24 24" fill="none">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
              </svg>
            )}
            {running ? 'Running…' : 'Run'}
          </button>
        )}
        {onEdit && (
          <button onClick={() => onEdit(feed)} title="Edit feed"
            className="text-gray-300 hover:text-emerald-500 transition-colors p-1">
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
            </svg>
          </button>
        )}
        {canDelete && (
          <button onClick={() => onDelete(feed.id)} title="Delete feed"
            className="text-gray-300 hover:text-red-400 transition-colors p-1">
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
            </svg>
          </button>
        )}
      </div>
    </div>
  )
}

function EditFeedModal({ feed, domainCVs, onClose, onSuccess }) {
  const isPlatform = feed.is_platform
  const isAuto = feed.is_auto_generated

  const [name, setName] = useState(feed.name || '')
  const [url, setUrl] = useState(feed.url_or_actor || '')
  const [keywords, setKeywords] = useState(feed.search_keywords || feed.keywords || '')
  const [location, setLocation] = useState(feed.location || '')
  const [domainCvId, setDomainCvId] = useState(feed.domain_cv_id || '')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const inputCls = 'w-full px-3 py-2 border border-gray-200 rounded-lg text-sm outline-none focus:border-emerald-400 bg-white'
  const cvLabel = (cv) =>
    `${cv.industry_label || 'Industry'} × ${cv.function_label || 'Function'} × ${cv.country_name || cv.country_code}`

  const handleSave = async () => {
    if (!name.trim()) { setError('Feed name is required'); return }
    setSaving(true); setError('')
    try {
      const payload = {
        name,
        keywords,
        search_keywords: keywords,
        location: location || null,
        domain_cv_id: domainCvId || null,
      }
      if (!isPlatform) payload.url_or_actor = url   // platform URL is managed
      await updateFeed(feed.id, payload)
      onSuccess()
    } catch (e) {
      setError(e.response?.data?.detail || 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md p-6 max-h-[90vh] overflow-y-auto">
        <div className="flex items-center gap-2 mb-4">
          <h2 className="text-base font-semibold text-gray-900">Edit feed</h2>
          {isAuto && (
            <span className="text-[10px] bg-emerald-100 text-emerald-700 px-1.5 py-0.5 rounded-full font-medium">
              Auto-generated from domain CV
            </span>
          )}
          {isPlatform && (
            <span className="text-[10px] bg-gray-100 text-gray-500 px-1.5 py-0.5 rounded-full font-medium">
              Platform feed
            </span>
          )}
        </div>

        <div className="space-y-3">
          <Input label="Feed name" value={name} onChange={(e) => setName(e.target.value)} />

          {/* URL / Actor — read-only for platform feeds */}
          <div>
            <label className="text-sm font-medium text-gray-700 block mb-1.5">
              {feed.feed_type === 'rss' ? 'RSS URL' : 'Apify actor ID'}
              {isPlatform && <span className="text-xs text-gray-400 font-normal"> — platform-managed (read-only)</span>}
            </label>
            <input
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              disabled={isPlatform}
              className={`${inputCls} ${isPlatform ? 'bg-gray-50 text-gray-400 cursor-not-allowed' : ''}`}
            />
          </div>

          <Input label="Keywords" value={keywords} onChange={(e) => setKeywords(e.target.value)}
            placeholder="head of product ai machine learning" />
          <Input label="Location" value={location} onChange={(e) => setLocation(e.target.value)}
            placeholder="Netherlands" />

          {/* Domain CV association */}
          <div>
            <label className="text-sm font-medium text-gray-700 block mb-1.5">Domain CV association</label>
            <select value={domainCvId} onChange={(e) => setDomainCvId(e.target.value)} className={inputCls}>
              <option value="">Not linked</option>
              {domainCVs.map((cv) => (
                <option key={cv.id} value={cv.id}>{cvLabel(cv)}</option>
              ))}
            </select>
          </div>

          {error && <p className="text-sm text-red-500">{error}</p>}
        </div>

        <div className="flex justify-between mt-5">
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button onClick={handleSave} loading={saving}>Save</Button>
        </div>
      </div>
    </div>
  )
}

function AddFeedModal({ onClose, onSuccess }) {
  const { data: domainData, isLoading: cvsLoading } = useQuery({
    queryKey: ['domain-cvs'],
    queryFn: getDomainCVs,
  })
  const domainCVs = domainData?.data || []

  const [domainCvId, setDomainCvId] = useState('')
  const [generating, setGenerating] = useState(false)
  const [loaded, setLoaded] = useState(false)

  const [feedName, setFeedName] = useState('')
  const [keywords, setKeywords] = useState('')
  const [keywordUsage, setKeywordUsage] = useState(null)
  const [feedType, setFeedType] = useState('rss')

  const [rssBoards, setRssBoards] = useState([])         // [{name, url, url_template}]
  const [boardIdx, setBoardIdx] = useState(0)
  const [url, setUrl] = useState('')

  const [actorId, setActorId] = useState('')             // Apify actor id (from Store search)
  const [actorName, setActorName] = useState('')         // human-readable actor name (for scanner matching)

  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const selectedCV = domainCVs.find((c) => c.id === domainCvId)
  const cvLabel = (cv) =>
    `${cv.industry_label || 'Industry'} × ${cv.function_label || 'Function'} × ${cv.country_name || cv.country_code}`

  const buildUrl = (template, kw) =>
    (template || '').replace('{keywords}', (kw || '').trim().replace(/\s+/g, '+'))

  const handleSelectDomain = async (id) => {
    setDomainCvId(id)
    setLoaded(false)
    setError('')
    if (!id) return
    setGenerating(true)
    try {
      const { data } = await suggestFeed(id)
      setFeedName(data.feed_name)
      setKeywords(data.search_keywords)
      setKeywordUsage(data.tokens_used ? { tokens: data.tokens_used, cost_inr: data.cost_inr } : null)
      setRssBoards(data.rss_boards || [])
      setBoardIdx(0)
      setUrl(data.rss_boards?.[0]?.url || '')
      setActorId('')   // Apify actor chosen via the live Store search below
      setActorName('')
      setLoaded(true)
    } catch (e) {
      setError('Could not generate keywords: ' + (e.response?.data?.detail || e.message))
    } finally {
      setGenerating(false)
    }
  }

  const handleSelectBoard = (idx) => {
    setBoardIdx(idx)
    const b = rssBoards[idx]
    if (b) setUrl(buildUrl(b.url_template, keywords))
  }

  const regenUrlFromKeywords = () => {
    const b = rssBoards[boardIdx]
    if (b) setUrl(buildUrl(b.url_template, keywords))
  }

  const handleSave = async () => {
    if (!domainCvId) { setError('Select a domain CV first'); return }
    const urlOrActor = feedType === 'rss' ? url : actorId
    if (!urlOrActor) { setError(feedType === 'rss' ? 'RSS URL is required' : 'Select an Apify actor'); return }
    setSaving(true)
    setError('')
    try {
      await createFeed({
        feed_type: feedType,
        name: feedName || 'Domain CV feed',
        url_or_actor: urlOrActor,
        actor_name: feedType === 'apify' ? actorName : null,
        keywords,
        search_keywords: keywords,
        domain_cv_id: domainCvId,
        location: selectedCV?.country_name || null,
      })
      onSuccess()
    } catch (e) {
      setError(e.response?.data?.detail || 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  const selectCls = 'w-full px-3 py-2 border border-gray-200 rounded-lg text-sm outline-none focus:border-emerald-400 bg-white'

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md p-6 max-h-[90vh] overflow-y-auto">
        <h2 className="text-base font-semibold text-gray-900 mb-1">Add feed</h2>
        <p className="text-xs text-gray-500 mb-4">
          Feeds are built from a domain CV — keywords are generated automatically.
        </p>

        <div className="space-y-3">
          {/* 1. Domain CV picker */}
          <div>
            <label className="text-sm font-medium text-gray-700 block mb-1.5">
              Which domain CV is this feed for?
            </label>
            {cvsLoading ? (
              <div className="flex justify-center py-3"><Spinner /></div>
            ) : domainCVs.length === 0 ? (
              <p className="text-xs text-gray-400 bg-gray-50 border border-gray-100 rounded-lg px-3 py-2">
                No domain CVs yet — generate and apply one first.
              </p>
            ) : (
              <select
                value={domainCvId}
                onChange={(e) => handleSelectDomain(e.target.value)}
                className={selectCls}
              >
                <option value="">Select a domain CV…</option>
                {domainCVs.map((cv) => (
                  <option key={cv.id} value={cv.id}>{cvLabel(cv)}</option>
                ))}
              </select>
            )}
          </div>

          {/* Generating state */}
          {generating && (
            <div className="flex items-center gap-2 text-sm text-gray-500 py-2">
              <Spinner /> Generating keywords from your domain CV…
            </div>
          )}

          {/* 2. Suggestion-driven config */}
          {loaded && !generating && (
            <>
              <Input
                label="Feed name"
                value={feedName}
                onChange={(e) => setFeedName(e.target.value)}
                placeholder="AI & Data Product Leadership — NL"
              />

              {/* Editable generated keywords */}
              <div>
                <label className="text-sm font-medium text-gray-700 block mb-1.5 flex items-center gap-2">
                  Search keywords <span className="text-emerald-600 text-xs font-normal">✨ generated</span>
                  {keywordUsage && <TokenBadge tokens={keywordUsage.tokens} cost_inr={keywordUsage.cost_inr} />}
                </label>
                <input
                  value={keywords}
                  onChange={(e) => setKeywords(e.target.value)}
                  className={selectCls}
                  placeholder="head of product ai machine learning"
                />
              </div>

              {/* Feed type */}
              <div>
                <label className="text-sm font-medium text-gray-700 block mb-1.5">Feed type</label>
                <div className="flex gap-2">
                  {['rss', 'apify'].map((t) => (
                    <button key={t} type="button" onClick={() => setFeedType(t)}
                      className={`px-4 py-1.5 rounded-lg text-sm font-medium border transition-colors uppercase ${
                        feedType === t ? 'bg-emerald-50 text-emerald-700 border-emerald-200' : 'bg-white text-gray-600 border-gray-200 hover:bg-gray-50'
                      }`}>
                      {t}
                    </button>
                  ))}
                </div>
              </div>

              {/* RSS: board picker + editable pre-filled URL */}
              {feedType === 'rss' && (
                <>
                  <div>
                    <label className="text-sm font-medium text-gray-700 block mb-1.5">Job board</label>
                    <select value={boardIdx} onChange={(e) => handleSelectBoard(Number(e.target.value))} className={selectCls}>
                      {rssBoards.map((b, i) => (
                        <option key={i} value={i}>{b.name}</option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <div className="flex items-center justify-between mb-1.5">
                      <label className="text-sm font-medium text-gray-700">RSS URL</label>
                      <button type="button" onClick={regenUrlFromKeywords}
                        className="text-[11px] text-emerald-600 hover:text-emerald-700 font-medium">
                        ↻ rebuild from keywords
                      </button>
                    </div>
                    <input value={url} onChange={(e) => setUrl(e.target.value)} className={selectCls}
                      placeholder="https://nl.indeed.com/rss?q=..." />
                  </div>
                </>
              )}

              {/* Apify: live Apify Store search (no free text) */}
              {feedType === 'apify' && (
                <ApifyActorPicker
                  value={actorId}
                  onChange={(id, name) => { setActorId(id); setActorName(name) }}
                />
              )}
            </>
          )}

          {error && <p className="text-sm text-red-500">{error}</p>}
        </div>

        <div className="flex justify-between mt-5">
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button onClick={handleSave} loading={saving} disabled={!loaded || generating}>Add feed</Button>
        </div>
      </div>
    </div>
  )
}

function ApifyActorPicker({ value, onChange }) {
  const [searchInput, setSearchInput] = useState('jobs scraper')
  const [search, setSearch] = useState('jobs scraper')

  // Debounce typing → backend re-query of the Apify Store
  useEffect(() => {
    const t = setTimeout(() => setSearch(searchInput.trim() || 'jobs scraper'), 400)
    return () => clearTimeout(t)
  }, [searchInput])

  const { data, isFetching, error } = useQuery({
    queryKey: ['apify-actors', search],
    queryFn: () => searchApifyActors(search),
    retry: false,
  })

  const actors = data?.data || []
  const noToken = error?.response?.status === 400
  const errMsg = error?.response?.data?.detail || 'Apify search failed'
  const inputCls = 'w-full px-3 py-2 border border-gray-200 rounded-lg text-sm outline-none focus:border-emerald-400 bg-white'

  return (
    <div>
      <label className="text-sm font-medium text-gray-700 block mb-1.5">
        Apify actor <span className="text-emerald-600 text-xs font-normal">⚡ Apify Store</span>
      </label>

      {noToken ? (
        <p className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
          Add your Apify token in Settings → Plan &amp; Keys first
        </p>
      ) : (
        <>
          <input
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            placeholder="Search actors — e.g. linkedin, glassdoor"
            className={inputCls}
          />
          <div className="mt-2 border border-gray-200 rounded-lg divide-y divide-gray-50 max-h-52 overflow-y-auto">
            {error ? (
              <p className="text-xs text-red-500 px-3 py-3">{errMsg}</p>
            ) : isFetching && actors.length === 0 ? (
              <div className="flex justify-center py-4"><Spinner /></div>
            ) : actors.length === 0 ? (
              <p className="text-xs text-gray-400 px-3 py-3">No actors found for "{search}"</p>
            ) : (
              actors.map((a) => (
                <button key={a.id} type="button" onClick={() => onChange(a.id, a.name)}
                  className={`w-full text-left px-3 py-2 transition-colors ${
                    value === a.id ? 'bg-emerald-50' : 'hover:bg-gray-50'
                  }`}>
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-sm font-medium text-gray-900 truncate">{a.name}</span>
                    <span className="text-[10px] text-gray-400 shrink-0">{(a.runs || 0).toLocaleString()} runs</span>
                  </div>
                  {a.description && <p className="text-xs text-gray-400 truncate mt-0.5">{a.description}</p>}
                  <p className="text-[10px] text-gray-300 truncate">{a.id}</p>
                </button>
              ))
            )}
          </div>
          {value && <p className="text-[11px] text-emerald-600 mt-1.5">Selected: {value}</p>}
        </>
      )}
    </div>
  )
}

function AddCompanyModal({ onClose, onSuccess }) {
  const [name, setName] = useState('')
  const [url, setUrl] = useState('')
  const [market, setMarket] = useState('')
  const [saving, setSaving] = useState(false)

  const handleSave = async () => {
    if (!name) return
    setSaving(true)
    try {
      await addTargetCompany({ company_name: name, career_page_url: url || null, market: market || null })
      onSuccess()
    } catch (e) { console.error(e) }
    finally { setSaving(false) }
  }

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md p-6">
        <h2 className="text-base font-semibold text-gray-900 mb-4">Add target company</h2>
        <div className="space-y-3">
          <Input label="Company name *" value={name} onChange={(e) => setName(e.target.value)} placeholder="Adyen" />
          <Input label="Careers page URL" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://careers.adyen.com" />
          <div>
            <label className="text-sm font-medium text-gray-700 block mb-1.5">Market</label>
            <select value={market} onChange={(e) => setMarket(e.target.value)}
              className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm outline-none focus:border-emerald-400">
              <option value="">Unknown</option>
              <option value="NL">Netherlands</option>
              <option value="EU">EU</option>
              <option value="Dubai">Dubai</option>
              <option value="SG">Singapore</option>
              <option value="IN">India</option>
            </select>
          </div>
        </div>
        <div className="flex justify-between mt-5">
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button onClick={handleSave} loading={saving} disabled={!name}>Add company</Button>
        </div>
      </div>
    </div>
  )
}
