import { useState, useMemo } from 'react'
import { useSearchParams, useNavigate } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { formatDistanceToNow } from 'date-fns'
import { getJobs } from '../../api/jobs'
import { getDomainCVs } from '../../api/cvs'
import { clsx } from 'clsx'
import { StatusBadge, MarketBadge, SourceBadge } from '../../components/ui/Badge'
import ScorePill from '../../components/ui/ScorePill'
import Button from '../../components/ui/Button'
import Spinner from '../../components/ui/Spinner'
import AddJobModal from './AddJobModal'
import { toast } from '../../store/toast'
import JobDetail from './JobDetail'
import TailorOverlay from './TailorOverlay'

const STATUS_FILTERS = [
  { value: null, label: 'All' },
  { value: 'new', label: 'New' },
  { value: 'bookmarked', label: 'Bookmarked' },
  { value: 'applied', label: 'Applied' },
  { value: 'screening', label: 'Screening' },
  { value: 'interview_r1', label: 'Interview' },
  { value: 'offer_received', label: 'Offer' },
  { value: 'rejected', label: 'Rejected' },
  { value: 'ghosted', label: 'Ghosted' },
]

const SOURCE_FILTERS = [
  { value: null, label: 'All' },
  { value: 'rss', label: 'RSS' },
  { value: 'apify', label: 'Apify' },
  { value: 'manual', label: 'Manual' },
  { value: 'gmail_alert', label: '📧 Alert' },
]

const SCORE_FILTERS = [
  { value: null, label: 'Any' },
  { value: '70', label: '≥70' },
  { value: '80', label: '≥80' },
  { value: '90', label: '≥90' },
]

// Sortable columns (T/F deliberately not sortable, per spec). key=null → label only.
const COLUMNS = [
  { label: 'Company', key: 'company' },
  { label: 'Role', key: 'role' },
  { label: 'Market', key: 'market' },
  { label: 'B', key: 's1' },
  { label: 'Best Fit', key: 'best_fit' },
  { label: 'T', key: null },
  { label: 'F', key: null },
  { label: 'Status', key: 'status' },
  { label: 'Source', key: 'source' },
  { label: 'Added', key: 'created_at' },
  { label: '', key: null },
]

export default function JobsPage() {
  const qc = useQueryClient()
  const navigate = useNavigate()
  const [sp, setSp] = useSearchParams()
  const [search, setSearch] = useState('')
  const [selectedJobId, setSelectedJobId] = useState(null)
  const [showAddModal, setShowAddModal] = useState(false)
  const [tailorJobId, setTailorJobId] = useState(null)

  // Filter + sort state lives in the URL so views are shareable/bookmarkable.
  const statusFilter = sp.get('status')
  const sourceFilter = sp.get('source')
  const scoreFilter = sp.get('score')
  const domainFilter = sp.get('domain')
  const needsHitl = sp.get('hitl') === '1'
  const [sortKey, sortDir] = sp.get('sort') ? sp.get('sort').split(':') : [null, null]

  const patchSp = (updates) => {
    const next = new URLSearchParams(sp)
    Object.entries(updates).forEach(([k, v]) => {
      if (v === null || v === undefined || v === '') next.delete(k)
      else next.set(k, v)
    })
    setSp(next, { replace: true })
  }

  const toggleSort = (key) => {
    if (sortKey !== key) patchSp({ sort: `${key}:asc` })
    else if (sortDir === 'asc') patchSp({ sort: `${key}:desc` })
    else patchSp({ sort: null })  // asc → desc → unsorted (default Added DESC)
  }

  // Server-side filters (status/source/search/hitl); score+domain are client-side.
  const params = {
    limit: 50,
    ...(statusFilter && { status: statusFilter }),
    ...(sourceFilter && { source: sourceFilter }),
    ...(search && { search }),
    ...(needsHitl && { needs_hitl: true }),
  }

  const { data, isLoading } = useQuery({
    queryKey: ['jobs', params],
    queryFn: () => getJobs(params),
    refetchInterval: 30000,
  })

  const { data: hitlData } = useQuery({
    queryKey: ['hitl-count'],
    queryFn: () => getJobs({ needs_hitl: true, limit: 5 }),
    refetchInterval: 30000,
    retry: false,
  })

  const { data: domainCVsData } = useQuery({
    queryKey: ['domain-cvs'],
    queryFn: getDomainCVs,
  })
  const domainCVOptions = (domainCVsData?.data || []).map((cv) => ({
    id: String(cv.id),
    label: `${cv.industry_label || 'Domain'} × ${cv.country_code || '—'}`,
  }))

  const jobs = data?.data || []
  const hitlCount = hitlData?.data?.length || 0

  // Client-side score (s1d when available, else s1) + domain (best_domain_cv_id) filters.
  const filtered = useMemo(() => jobs.filter((j) => {
    if (scoreFilter) {
      const s = j.s1d ?? j.s1
      if (s === null || s === undefined || s < Number(scoreFilter)) return false
    }
    if (domainFilter && String(j.best_domain_cv_id) !== domainFilter) return false
    return true
  }), [jobs, scoreFilter, domainFilter])

  // Client-side sort (default Added DESC when no column is chosen).
  const displayJobs = useMemo(() => {
    const key = sortKey || 'created_at'
    const dir = sortKey ? sortDir : 'desc'
    const val = (j) => {
      if (key === 'best_fit') return j.s1d ?? -1
      if (key === 's1') return j.s1 ?? -1
      if (key === 'created_at') return new Date(j.created_at).getTime()
      return (j[key] ?? '').toString().toLowerCase()
    }
    return [...filtered].sort((a, b) => {
      const va = val(a), vb = val(b)
      if (va < vb) return dir === 'asc' ? -1 : 1
      if (va > vb) return dir === 'asc' ? 1 : -1
      return 0
    })
  }, [filtered, sortKey, sortDir])

  const selectedJob = jobs.find((j) => j.id === selectedJobId)

  const onJobAdded = () => {
    qc.invalidateQueries({ queryKey: ['jobs'] })
    qc.invalidateQueries({ queryKey: ['job-stats'] })
    setShowAddModal(false)
    toast.success('Job added to tracker')
  }

  const onJobUpdated = () => {
    qc.invalidateQueries({ queryKey: ['jobs'] })
    qc.invalidateQueries({ queryKey: ['job-stats'] })
    qc.invalidateQueries({ queryKey: ['hitl-count'] })
  }

  return (
    <div className="flex h-full">
      {/* ── Left: list ── */}
      <div className={`flex flex-col ${selectedJobId ? 'w-[55%]' : 'flex-1'} border-r border-gray-200 overflow-hidden transition-all`}>
        {/* Header */}
        <div className="px-5 pt-5 pb-3 border-b border-gray-100 bg-white">
          <div className="flex items-center justify-between mb-3">
            <h1 className="text-lg font-semibold text-gray-900">Jobs</h1>
            <Button size="sm" onClick={() => setShowAddModal(true)}>
              + Add job
            </Button>
          </div>

          {/* Search */}
          <div className="relative mb-3">
            <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
            <input
              type="text"
              placeholder="Search company or role..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full pl-9 pr-3 py-2 border border-gray-200 rounded-lg text-sm outline-none focus:border-emerald-400 focus:ring-2 focus:ring-emerald-100"
            />
          </div>

          {/* Status filter pills */}
          <div className="flex items-center gap-1.5 flex-wrap">
            {hitlCount > 0 && (
              <button
                onClick={() => patchSp({ hitl: needsHitl ? null : '1', status: null })}
                className={`flex items-center gap-1 px-3 py-1 rounded-full text-xs font-medium border transition-colors ${
                  needsHitl
                    ? 'bg-red-500 text-white border-red-500'
                    : 'bg-red-50 text-red-600 border-red-200 hover:bg-red-100'
                }`}
              >
                <div className="w-1.5 h-1.5 rounded-full bg-current animate-pulse" />
                Needs reply ({hitlCount})
              </button>
            )}
            {STATUS_FILTERS.map((f) => (
              <button
                key={f.value ?? 'all'}
                onClick={() => patchSp({ status: f.value, hitl: null })}
                className={`px-3 py-1 rounded-full text-xs font-medium border transition-colors ${
                  statusFilter === f.value && !needsHitl
                    ? 'bg-slate-800 text-white border-slate-800'
                    : 'bg-white text-gray-600 border-gray-200 hover:bg-gray-50'
                }`}
              >
                {f.label}
              </button>
            ))}
          </div>

          {/* Source / Score / Domain filters (combinable, AND logic) */}
          <div className="flex items-center gap-x-4 gap-y-2 flex-wrap mt-2">
            <FilterGroup label="Source">
              {SOURCE_FILTERS.map((f) => (
                <FilterPill key={f.value ?? 'all'} active={(sourceFilter ?? null) === f.value}
                  onClick={() => patchSp({ source: f.value })}>{f.label}</FilterPill>
              ))}
            </FilterGroup>
            <FilterGroup label="Score">
              {SCORE_FILTERS.map((f) => (
                <FilterPill key={f.value ?? 'any'} active={(scoreFilter ?? null) === f.value}
                  onClick={() => patchSp({ score: f.value })}>{f.label}</FilterPill>
              ))}
            </FilterGroup>
            {domainCVOptions.length > 0 && (
              <FilterGroup label="Domain">
                <select
                  value={domainFilter || ''}
                  onChange={(e) => patchSp({ domain: e.target.value || null })}
                  className="text-xs border border-gray-200 rounded-lg px-2 py-1 outline-none focus:border-emerald-400 bg-white text-gray-700"
                >
                  <option value="">All domains</option>
                  {domainCVOptions.map((d) => (
                    <option key={d.id} value={d.id}>{d.label}</option>
                  ))}
                </select>
              </FilterGroup>
            )}
          </div>
        </div>

        {/* Table */}
        <div className="flex-1 overflow-y-auto bg-white">
          {isLoading ? (
            <div className="flex justify-center items-center h-40"><Spinner /></div>
          ) : displayJobs.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-64 text-center px-6">
              <div className="w-12 h-12 bg-gray-100 rounded-xl flex items-center justify-center mb-3">
                <svg className="w-6 h-6 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M21 13.255A23.931 23.931 0 0112 15c-3.183 0-6.22-.62-9-1.745M16 6V4a2 2 0 00-2-2h-4a2 2 0 00-2 2v2m4 6h.01M5 20h14a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                </svg>
              </div>
              <p className="text-sm font-medium text-gray-700 mb-1">No jobs found</p>
              <p className="text-xs text-gray-400 mb-4">
                {statusFilter || needsHitl || search || sourceFilter || scoreFilter || domainFilter ? 'Try clearing your filters' : 'Add your first job to get started'}
              </p>
              {!statusFilter && !needsHitl && !search && !sourceFilter && !scoreFilter && !domainFilter && (
                <Button size="sm" onClick={() => setShowAddModal(true)}>Add first job →</Button>
              )}
            </div>
          ) : (
            <table className="w-full">
              <thead className="sticky top-0 bg-white border-b border-gray-100 z-10">
                <tr>
                  {COLUMNS.map((col) => (
                    <th key={col.label || 'tailor'} className="px-4 py-2.5 text-left text-xs font-medium text-gray-500">
                      {col.key ? (
                        <button
                          onClick={() => toggleSort(col.key)}
                          className="flex items-center gap-1 hover:text-gray-700 transition-colors"
                        >
                          {col.label}
                          {sortKey === col.key && <span className="text-emerald-600">{sortDir === 'asc' ? '↑' : '↓'}</span>}
                        </button>
                      ) : col.label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {displayJobs.map((job) => (
                  <tr
                    key={job.id}
                    onClick={() => setSelectedJobId(job.id === selectedJobId ? null : job.id)}
                    className={`cursor-pointer transition-colors hover:bg-gray-50 ${
                      job.id === selectedJobId ? 'bg-emerald-50' : ''
                    } ${job.needs_hitl ? 'border-l-2 border-l-red-400' : ''}`}
                  >
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        {job.needs_hitl && <div className="w-1.5 h-1.5 rounded-full bg-red-500 shrink-0 animate-pulse" />}
                        <span className="text-sm font-medium text-gray-900 truncate max-w-[120px]">{job.company}</span>
                      </div>
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-600 max-w-[180px]">
                      <span className="truncate block">{job.role}</span>
                      {job.has_partial_jd && (
                        <span
                          title="Job details from alert email — click the portal URL for the full description before tailoring"
                          className="inline-block mt-0.5 text-[9px] bg-amber-50 text-amber-700 border border-amber-200 px-1.5 py-0.5 rounded-full font-medium"
                        >
                          Partial JD
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      {job.market ? <MarketBadge market={job.market} /> : <span className="text-gray-300 text-xs">—</span>}
                    </td>
                    <td className="px-4 py-3">
                      <ScorePill score={job.s1} />
                    </td>
                    <td className="px-4 py-3">
                      <BestFitCell job={job} />
                    </td>
                    <td className="px-4 py-3">
                      <ScorePill score={job.s2} />
                    </td>
                    <td className="px-4 py-3">
                      <ScorePill score={job.s3_master} type="s3" />
                    </td>
                    <td className="px-4 py-3">
                      <StatusBadge status={job.status} />
                    </td>
                    <td className="px-4 py-3">
                      {job.source ? <SourceBadge source={job.source} /> : <span className="text-gray-300 text-xs">—</span>}
                    </td>
                    <td className="px-4 py-3 text-xs text-gray-400 whitespace-nowrap">
                      {job.created_at ? formatDistanceToNow(new Date(job.created_at), { addSuffix: true }) : '—'}
                    </td>
                    <td className="px-4 py-3">
                      <button
                        onClick={(e) => { e.stopPropagation(); navigate(`/jobs/${job.id}/tailor`) }}
                        className="text-xs text-emerald-600 hover:text-emerald-700 font-medium px-2 py-1 rounded hover:bg-emerald-50 transition-colors whitespace-nowrap"
                      >
                        Tailor →
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {/* ── Right: detail panel ── */}
      {selectedJobId && (
        <div className="w-[45%] overflow-y-auto bg-white">
          <JobDetail
            jobId={selectedJobId}
            onClose={() => setSelectedJobId(null)}
            onUpdate={onJobUpdated}
            onTailor={(id) => navigate(`/jobs/${id}/tailor`)}
          />
        </div>
      )}

      {/* ── Add job modal ── */}
      {showAddModal && (
        <AddJobModal
          onClose={() => setShowAddModal(false)}
          onSuccess={onJobAdded}
        />
      )}

      {/* ── Tailor overlay ── */}
      {tailorJobId && (
        <TailorOverlay
          jobId={tailorJobId}
          onClose={() => setTailorJobId(null)}
          onSuccess={() => { setTailorJobId(null); onJobUpdated() }}
        />
      )}
    </div>
  )
}

function FilterGroup({ label, children }) {
  return (
    <div className="flex items-center gap-1.5">
      <span className="text-[10px] uppercase tracking-wide text-gray-400 font-medium">{label}</span>
      <div className="flex items-center gap-1">{children}</div>
    </div>
  )
}

function FilterPill({ active, onClick, children }) {
  return (
    <button
      onClick={onClick}
      className={clsx(
        'px-2 py-0.5 rounded-full text-xs font-medium border transition-colors',
        active ? 'bg-slate-800 text-white border-slate-800' : 'bg-white text-gray-600 border-gray-200 hover:bg-gray-50'
      )}
    >
      {children}
    </button>
  )
}

// Same thresholds as ScorePill's S1 colouring.
function scoreColor(score) {
  if (score === null || score === undefined) return 'bg-gray-100 text-gray-400'
  if (score >= 85) return 'bg-emerald-100 text-emerald-700'
  if (score >= 70) return 'bg-yellow-100 text-yellow-700'
  if (score >= 55) return 'bg-orange-100 text-orange-700'
  return 'bg-red-100 text-red-600'
}

// "Best Fit" cell — best domain CV label + score, expandable to all domain CV scores.
function BestFitCell({ job }) {
  const [open, setOpen] = useState(false)
  const scores = job.domain_cv_scores || {}
  const labels = job.domain_cv_labels || {}
  const entries = Object.entries(scores)
    .filter(([, v]) => v !== null && v !== undefined)
    .sort((a, b) => b[1] - a[1])

  if (!entries.length) return <span className="text-gray-300 text-xs">—</span>

  const bestId = job.best_domain_cv_id ? String(job.best_domain_cv_id) : entries[0][0]
  const bestScore = job.s1d !== null && job.s1d !== undefined ? job.s1d : scores[bestId]
  const bestLabel = labels[bestId] || 'Domain'

  return (
    <div className="relative inline-block">
      <button
        onClick={(e) => { e.stopPropagation(); setOpen((o) => !o) }}
        className="flex items-center gap-1"
        title={bestLabel}
      >
        <span className="text-[11px] text-gray-600 font-medium truncate max-w-[72px]">{bestLabel}</span>
        <span className={clsx('px-1.5 py-0.5 rounded-full text-xs font-semibold tabular-nums', scoreColor(bestScore))}>
          {Math.round(bestScore)}
        </span>
        {entries.length > 1 && <span className="text-gray-400 text-[9px]">{open ? '▲' : '▼'}</span>}
      </button>

      {open && (
        <>
          <div className="fixed inset-0 z-20" onClick={(e) => { e.stopPropagation(); setOpen(false) }} />
          <div
            className="absolute left-0 top-full mt-1 z-30 w-60 bg-white rounded-lg shadow-lg border border-gray-200 p-2"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="text-[10px] uppercase tracking-wide text-gray-400 font-medium px-1 pb-1">
              Domain CV fit
            </div>
            {entries.map(([id, score]) => {
              const isBest = id === bestId
              return (
                <div key={id} className={clsx('flex items-center gap-2 px-1.5 py-1 rounded', isBest && 'bg-emerald-50')}>
                  <span
                    className={clsx('text-xs flex-1 truncate', isBest ? 'text-emerald-800 font-medium' : 'text-gray-600')}
                    title={labels[id] || id}
                  >
                    {labels[id] || 'Domain'}
                  </span>
                  <div className="w-14 h-1.5 bg-gray-100 rounded-full overflow-hidden shrink-0">
                    <div
                      className={clsx('h-full rounded-full', isBest ? 'bg-emerald-500' : 'bg-gray-300')}
                      style={{ width: `${Math.max(0, Math.min(100, score))}%` }}
                    />
                  </div>
                  <span className={clsx('text-xs font-semibold tabular-nums w-6 text-right', isBest ? 'text-emerald-700' : 'text-gray-500')}>
                    {Math.round(score)}
                  </span>
                </div>
              )
            })}
          </div>
        </>
      )}
    </div>
  )
}
