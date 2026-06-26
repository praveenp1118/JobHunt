import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { formatDistanceToNow, format } from 'date-fns'
import { getAlertActivity, getSystemActivity, pollGmailNow, runScanNow } from '../../api/activity'
import client from '../../api/client'
import Spinner from '../../components/ui/Spinner'
import ScanFeedBreakdown from '../../components/ui/ScanFeedBreakdown'
import Pagination, { usePagination } from '../../components/ui/Pagination'
import { toast } from '../../store/toast'

const REFRESH = 60000

function RunButton({ label, running, onClick, className = '' }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={running}
      className={`text-xs px-2.5 py-1 rounded-lg border font-medium shrink-0 inline-flex items-center gap-1.5 transition-colors
        border-emerald-200 text-emerald-700 bg-emerald-50 hover:bg-emerald-100 disabled:opacity-60 disabled:cursor-not-allowed ${className}`}
    >
      {running && (
        <svg className="w-3 h-3 animate-spin" viewBox="0 0 24 24" fill="none">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
        </svg>
      )}
      {running ? 'Running…' : label}
    </button>
  )
}

function domainOf(sender) {
  if (!sender) return '—'
  const m = sender.match(/@([^>\s]+)/)
  return m ? m[1].toLowerCase() : sender
}

function timeAgo(dt) {
  if (!dt) return '—'
  try { return formatDistanceToNow(new Date(dt), { addSuffix: true }) } catch { return '—' }
}

const STATUS_CLASSES = {
  success: 'bg-emerald-100 text-emerald-700',
  error: 'bg-red-100 text-red-600',
  partial: 'bg-yellow-100 text-yellow-700',
  running: 'bg-blue-100 text-blue-600 animate-pulse',
}

export default function ActivityPage() {
  const [tab, setTab] = useState('alerts')

  return (
    <div className="p-6 max-w-4xl mx-auto">
      <div className="mb-5">
        <h1 className="text-xl font-semibold text-gray-900">Activity</h1>
        <p className="text-sm text-gray-500 mt-0.5">What the job-alert parser and background tasks have been doing</p>
      </div>

      <div className="flex gap-1 bg-gray-100 p-1 rounded-lg w-fit mb-6">
        {[{ key: 'alerts', label: 'Job Alerts' }, { key: 'system', label: 'System' }].map((t) => (
          <button key={t.key} onClick={() => setTab(t.key)}
            className={`px-4 py-1.5 rounded-md text-sm font-medium transition-colors ${
              tab === t.key ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500 hover:text-gray-700'
            }`}>
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'alerts' ? <AlertsTab /> : <SystemTab />}
    </div>
  )
}

// ── Tab 1: Job Alerts ─────────────────────────────────────────────────────────
function AlertsTab() {
  const qc = useQueryClient()
  const [polling, setPolling] = useState(false)
  const { data, isLoading } = useQuery({
    queryKey: ['activity-alerts'],
    queryFn: () => getAlertActivity(7),
    refetchInterval: REFRESH,
  })
  const alerts = data?.data || []
  const pg = usePagination(alerts, 10)

  const totals = alerts.reduce(
    (a, r) => ({ links: a.links + (r.links_found || 0), saved: a.saved + (r.jobs_saved || 0) }),
    { links: 0, saved: 0 }
  )

  const handlePoll = async () => {
    setPolling(true)
    try {
      await pollGmailNow()
      toast.success('Gmail polled — refreshing shortly')
    } catch (e) {
      toast.error('Poll failed: ' + (e.response?.data?.detail || e.message))
    }
    setTimeout(() => { qc.invalidateQueries({ queryKey: ['activity-alerts'] }); setPolling(false) }, 10000)
  }

  if (isLoading) return <div className="flex justify-center py-10"><Spinner /></div>

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <div className="bg-emerald-50 border border-emerald-100 rounded-xl px-4 py-3 text-sm text-emerald-800 flex-1">
          <span className="font-medium">Last 7 days</span> · {alerts.length} emails · {totals.links} links found · {totals.saved} jobs saved
        </div>
        <RunButton label="Poll Gmail now" running={polling} onClick={handlePoll} className="px-3 py-2" />
      </div>

      {alerts.length === 0 ? (
        <div className="bg-white rounded-2xl border border-gray-200 p-10 text-center">
          <p className="text-sm text-gray-400">No alert emails processed yet</p>
          <p className="text-xs text-gray-400 mt-1">Job-alert digests will appear here after the next Gmail poll</p>
        </div>
      ) : (
        <div className="space-y-3">
          {pg.slice.map((a) => <AlertRow key={a.id} alert={a} />)}
          <Pagination currentPage={pg.page} totalPages={pg.totalPages} totalItems={pg.total} itemsPerPage={10} onPageChange={pg.setPage} label="alert emails" />
        </div>
      )}
    </div>
  )
}

function AlertRow({ alert }) {
  const [open, setOpen] = useState(false)
  const [showAllReasons, setShowAllReasons] = useState(false)
  const allGated = alert.links_public === 0 && alert.links_gated > 0
  const noLinks = alert.jobs_saved === 0 && alert.links_found === 0
  const reasons = alert.skip_reasons || []
  const shownReasons = showAllReasons ? reasons : reasons.slice(0, 5)
  const auto = alert.auto_application  // {action, company, role} when an external application was auto-detected

  // Auto-detected application — render a compact green card instead of the link funnel.
  if (auto) {
    return (
      <div className="bg-white rounded-xl border border-emerald-200 px-4 py-3">
        <p className="text-sm font-medium text-emerald-700">
          ✅ Auto-detected: Applied to {auto.company}
          {auto.action === 'created' && <span className="text-[10px] text-emerald-600 ml-1.5">(new job added)</span>}
        </p>
        <div className="flex items-center flex-wrap gap-x-2 gap-y-1 mt-1 text-xs text-gray-400">
          {auto.role && auto.role !== 'Unknown role' && <span className="text-gray-500">{auto.role}</span>}
          {auto.role && auto.role !== 'Unknown role' && <span>·</span>}
          <span className="truncate max-w-[260px]">📧 {alert.email_subject || '(no subject)'}</span>
          <span>·</span>
          <span>{timeAgo(alert.received_at || alert.created_at)}</span>
        </div>
      </div>
    )
  }

  return (
    <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
      <button onClick={() => setOpen((o) => !o)} className="w-full text-left px-4 py-3 hover:bg-gray-50 transition-colors">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <p className="text-sm font-medium text-gray-900 truncate">📧 {alert.email_subject || '(no subject)'}</p>
            <div className="flex items-center flex-wrap gap-x-2 gap-y-1 mt-1 text-xs text-gray-400">
              <span>{domainOf(alert.sender)}</span>
              <span>·</span>
              <span>{timeAgo(alert.received_at || alert.created_at)}</span>
            </div>
          </div>
          <div className="flex flex-col items-end gap-1 shrink-0">
            {alert.jobs_saved > 0 && (
              <span className="text-[10px] bg-emerald-100 text-emerald-700 px-2 py-0.5 rounded-full font-medium">
                {alert.jobs_saved} job{alert.jobs_saved > 1 ? 's' : ''} saved
              </span>
            )}
            {noLinks && (
              <span className="text-[10px] bg-gray-100 text-gray-500 px-2 py-0.5 rounded-full font-medium">No job links found</span>
            )}
            {alert.jobs_saved === 0 && allGated && (
              <span className="text-[10px] bg-amber-100 text-amber-700 px-2 py-0.5 rounded-full font-medium">All links login-gated</span>
            )}
          </div>
        </div>

        <div className="flex items-center gap-1.5 mt-2 flex-wrap">
          <Pill>{alert.links_found} links</Pill>
          {alert.links_gated > 0 && <Pill className="bg-amber-50 text-amber-700">{alert.links_gated} gated</Pill>}
          {alert.links_public > 0 && <Pill className="bg-blue-50 text-blue-600">{alert.links_public} public</Pill>}
          {alert.jobs_saved > 0 && <Pill className="bg-emerald-50 text-emerald-700">{alert.jobs_saved} saved</Pill>}
        </div>
      </button>

      {open && reasons.length > 0 && (
        <div className="px-4 py-3 border-t border-gray-100 bg-gray-50/50 space-y-1.5">
          {shownReasons.map((r, i) => <ReasonLine key={i} r={r} />)}
          {reasons.length > 5 && (
            <button onClick={() => setShowAllReasons((s) => !s)}
              className="text-xs text-emerald-600 hover:underline font-medium pt-1">
              {showAllReasons ? 'Show less' : `+ Show ${reasons.length - 5} more`}
            </button>
          )}
        </div>
      )}
      {open && reasons.length === 0 && (
        <div className="px-4 py-3 border-t border-gray-100 bg-gray-50/50 text-xs text-gray-400">
          No per-link detail recorded.
        </div>
      )}
    </div>
  )
}

function ReasonLine({ r }) {
  const label = (r.company || r.role)
    ? `${r.company || ''}${r.company && r.role ? ' · ' : ''}${r.role || ''}`
    : (r.url || '')
  if (r.reason === 'saved') {
    return (
      <p className="text-xs text-emerald-700 truncate">
        ✓ saved: <span className="font-medium">{label}</span>{r.s1 != null && <span className="text-gray-400"> · S1: {r.s1}</span>}
      </p>
    )
  }
  const map = {
    below_threshold: ['✗ below threshold', 'text-amber-600'],
    duplicate: ['✗ duplicate: already in tracker', 'text-gray-400'],
    title_skip: ['✗ title didn’t match target roles', 'text-gray-400'],
    fetch_failed: ['✗ couldn’t fetch (login-gated?)', 'text-gray-400'],
    error: ['✗ error processing', 'text-red-400'],
  }
  const [txt, cls] = map[r.reason] || [`✗ ${r.reason}`, 'text-gray-400']
  return (
    <p className={`text-xs truncate ${cls}`}>
      {txt}{label && r.reason === 'below_threshold' ? `: ${label}` : ''}
      {r.s1 != null && <span className="text-gray-400"> (S1: {r.s1})</span>}
      {!label && r.url ? <span className="text-gray-300"> {r.url.slice(0, 60)}</span> : ''}
    </p>
  )
}

const Pill = ({ children, className = 'bg-gray-100 text-gray-500' }) => (
  <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${className}`}>{children}</span>
)

// ── Tab 2: System ─────────────────────────────────────────────────────────────
function SystemTab() {
  const qc = useQueryClient()
  const { data, isLoading } = useQuery({
    queryKey: ['activity-system'],
    queryFn: () => getSystemActivity(7),
    refetchInterval: REFRESH,
  })
  const sys = data?.data || {}
  const scanPg = usePagination(sys.scanner_runs || [], 10)
  const pollPg = usePagination(sys.gmail_polls || [], 10)
  const ghostPg = usePagination(sys.ghosted_checks || [], 10)
  const nightPg = usePagination(sys.night_batches || [], 10)
  const errPg = usePagination(sys.recent_errors || [], 10)

  const handleResolve = async (id) => {
    try {
      await client.patch(`/auth/admin/error-logs/${id}/resolve`)
      qc.invalidateQueries({ queryKey: ['activity-system'] })
      toast.success('Error marked resolved')
    } catch {
      toast.error('Could not resolve')
    }
  }

  if (isLoading) return <div className="flex justify-center py-10"><Spinner /></div>

  return (
    <div className="space-y-4">
      <CollapsibleSection title="Weekly Scanner" runs={sys.scanner_runs} empty="No scans run yet">
        {scanPg.slice.map((r) => <ScannerCard key={r.id} run={r} />)}
        <Pagination currentPage={scanPg.page} totalPages={scanPg.totalPages} totalItems={scanPg.total} itemsPerPage={10} onPageChange={scanPg.setPage} label="runs" />
      </CollapsibleSection>

      <CollapsibleSection title="Gmail Polls" runs={sys.gmail_polls} empty="No Gmail polls run yet">
        {pollPg.slice.map((r) => <PollCard key={r.id} run={r} />)}
        <Pagination currentPage={pollPg.page} totalPages={pollPg.totalPages} totalItems={pollPg.total} itemsPerPage={10} onPageChange={pollPg.setPage} label="polls" />
      </CollapsibleSection>

      <CollapsibleSection title="Ghosted Check" runs={sys.ghosted_checks} empty="No ghosted checks run yet">
        {ghostPg.slice.map((r) => <GhostedCard key={r.id} run={r} />)}
        <Pagination currentPage={ghostPg.page} totalPages={ghostPg.totalPages} totalItems={ghostPg.total} itemsPerPage={10} onPageChange={ghostPg.setPage} label="checks" />
      </CollapsibleSection>

      <CollapsibleSection title="Night Batch" runs={sys.night_batches} empty="No night-batch scoring runs yet">
        {nightPg.slice.map((r) => <NightBatchCard key={r.id} run={r} />)}
        <Pagination currentPage={nightPg.page} totalPages={nightPg.totalPages} totalItems={nightPg.total} itemsPerPage={10} onPageChange={nightPg.setPage} label="runs" />
      </CollapsibleSection>

      <div>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-semibold text-gray-700">Recent Errors</h2>
          <Link to="/settings" className="text-xs text-emerald-600 hover:underline">View all errors →</Link>
        </div>
        {(!sys.recent_errors || sys.recent_errors.length === 0) ? (
          <div className="bg-white rounded-xl border border-gray-200 p-6 text-center text-sm text-gray-400">
            No errors {sys.error_count > 0 ? '' : 'in the last 7 days'} 🎉
          </div>
        ) : (
          <div className="bg-white rounded-xl border border-gray-200 divide-y divide-gray-50">
            {errPg.slice.map((e) => (
              <div key={e.id} className="flex items-center justify-between px-4 py-3 gap-3">
                <div className="min-w-0">
                  <p className="text-sm text-gray-900 truncate"><span className="font-medium">{e.action}</span> — {e.error_message}</p>
                  <p className="text-xs text-gray-400">{timeAgo(e.created_at)}</p>
                </div>
                {!e.is_resolved && (
                  <button onClick={() => handleResolve(e.id)}
                    className="text-xs text-emerald-600 hover:text-emerald-700 font-medium shrink-0">
                    Resolve
                  </button>
                )}
              </div>
            ))}
            <div className="px-4 py-1">
              <Pagination currentPage={errPg.page} totalPages={errPg.totalPages} totalItems={errPg.total} itemsPerPage={10} onPageChange={errPg.setPage} label="errors" />
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

function CollapsibleSection({ title, runs, empty, children }) {
  const [open, setOpen] = useState(false)
  const list = runs || []
  const last = list[0]  // backend orders by started_at desc
  return (
    <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
      <button onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between gap-3 px-4 py-3 hover:bg-gray-50 transition-colors text-left">
        <h2 className="text-sm font-semibold text-gray-700 flex items-center gap-2">
          <span className="text-gray-400 text-xs">{open ? '▼' : '▶'}</span> {title}
        </h2>
        <span className="text-xs text-gray-400 truncate">
          {list.length} run{list.length !== 1 ? 's' : ''}
          {last && ` · last: ${format(new Date(last.started_at), 'MMM d HH:mm')} · ${last.status}`}
        </span>
      </button>
      {open && (
        <div className="px-3 pb-3 pt-1 border-t border-gray-100 bg-gray-50/30">
          {list.length === 0 ? (
            <p className="text-sm text-gray-400 text-center py-4">{empty}</p>
          ) : (
            <div className="space-y-3">{children}</div>
          )}
        </div>
      )}
    </div>
  )
}

function GhostedCard({ run }) {
  const d = run.details || {}
  const dur = run.duration_seconds != null ? `${Math.round(run.duration_seconds)}s`
    : (run.completed_at && run.started_at ? `${Math.round((new Date(run.completed_at) - new Date(run.started_at)) / 1000)}s` : '—')
  return (
    <div className="bg-white rounded-xl border border-gray-200 px-4 py-3">
      <RunHeader run={run} />
      <p className="text-sm text-gray-700 mt-2">
        {d.checked ?? run.jobs_found ?? 0} applied jobs checked · <span className="text-amber-600 font-medium">{d.ghosted ?? run.jobs_added ?? 0} ghosted</span>
      </p>
      {run.error_message && <p className="text-xs text-red-400 mt-1 truncate">{run.error_message}</p>}
    </div>
  )
}

function NightBatchCard({ run }) {
  const d = run.details || {}
  return (
    <div className="bg-white rounded-xl border border-gray-200 px-4 py-3">
      <RunHeader run={run} />
      <p className="text-sm text-gray-700 mt-2">
        <span className="text-emerald-600 font-medium">{d.jobs_scored ?? run.jobs_added ?? 0} jobs scored</span>
        {d.users != null && <span className="text-xs text-gray-400"> · {d.users} user{d.users === 1 ? '' : 's'}</span>}
      </p>
      {(d.cost_inr != null || d.tokens != null) && (
        <p className="text-[11px] text-gray-400 mt-1">⚡ {(d.tokens || 0) >= 1000 ? (d.tokens / 1000).toFixed(1) + 'K' : (d.tokens ?? 0)} tokens · ₹{d.cost_inr ?? 0}</p>
      )}
      {run.error_message && <p className="text-xs text-red-400 mt-1 truncate">{run.error_message}</p>}
    </div>
  )
}

function RunHeader({ run }) {
  const dur = (run.completed_at && run.started_at)
    ? `${Math.round((new Date(run.completed_at) - new Date(run.started_at)) / 1000)}s`
    : (run.duration_seconds != null ? `${Math.round(run.duration_seconds)}s` : '—')
  return (
    <div className="flex items-center justify-between gap-3">
      <span className={`text-[10px] font-medium px-2 py-0.5 rounded-full ${STATUS_CLASSES[run.status] || 'bg-gray-100 text-gray-500'}`}>
        {run.status}
      </span>
      <span className="text-xs text-gray-400">{run.started_at ? format(new Date(run.started_at), 'MMM d HH:mm') : '—'} · {dur}</span>
    </div>
  )
}

function ScannerCard({ run }) {
  const qc = useQueryClient()
  const [open, setOpen] = useState(false)
  const [running, setRunning] = useState(false)
  const feeds = run.details?.feeds_summary || []
  const u = run.details?.usage_summary
  const rag = run.details?.rag_stats
  const fmtK = (n) => (n >= 1000 ? (n / 1000).toFixed(1) + 'K' : String(n ?? 0))

  const handleScan = async (e) => {
    e.stopPropagation()
    setRunning(true)
    try { await runScanNow(); toast.success('Scan queued') }
    catch (err) { toast.error('Scan failed: ' + (err.response?.data?.detail || err.message)) }
    setTimeout(() => { qc.invalidateQueries({ queryKey: ['activity-system'] }); setRunning(false) }, 5000)
  }

  return (
    <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
      <div onClick={() => setOpen((o) => !o)} className="cursor-pointer px-4 py-3 hover:bg-gray-50 transition-colors">
        <div className="flex items-start justify-between gap-2">
          <div className="flex-1 min-w-0"><RunHeader run={run} /></div>
          <RunButton label="Scan now" running={running} onClick={handleScan} />
        </div>
        <p className="text-sm text-gray-700 mt-2">
          {run.jobs_found} found · <span className="text-emerald-600 font-medium">{run.jobs_added} added</span>
          {feeds.length > 0 && <span className="text-xs text-gray-400"> · {feeds.length} feed{feeds.length > 1 ? 's' : ''} {open ? '▲' : '▼ Details'}</span>}
        </p>
        {u && (u.anthropic_tokens > 0 || u.apify_runs > 0) && (
          <p className="text-[11px] text-gray-400 mt-1">
            ⚡ Anthropic: {fmtK(u.anthropic_tokens)} tokens · ₹{(u.anthropic_inr || 0).toFixed(2)}
            {u.apify_runs > 0 && ` | Apify: ${u.apify_runs} runs · $${(u.apify_usd || 0).toFixed(2)}`}
          </p>
        )}
        {rag && rag.cost_inr != null && (
          <p className="text-[11px] text-emerald-600 mt-1">
            ⚡ ₹{rag.cost_inr} · 💡 Saved ₹{Math.max(0, ((rag.estimated_unoptimized_cost || 0) - (rag.cost_inr || 0))).toFixed(0)} vs unoptimized ({rag.savings_pct}%)
          </p>
        )}
        {run.error_message && <p className="text-xs text-red-400 mt-1 truncate">{run.error_message}</p>}
      </div>
      {open && (feeds.length > 0 || rag) && (
        <div className="px-4 py-3 border-t border-gray-100 bg-gray-50/50 space-y-3">
          {rag && (
            <div className="bg-white rounded-lg border border-gray-100 p-3">
              <p className="text-xs font-semibold text-gray-700 mb-1">RAG Pipeline</p>
              <p className="text-[11px] text-gray-500 leading-relaxed">
                {rag.total} total → <strong>{rag.stage1_rejected}</strong> Stage 1 rejected (free)
                → <strong>{rag.stage2_rejected}</strong> Stage 2 rejected (Haiku)
                → <strong>{rag.stage2_saved}</strong> saved at Stage 2 + <strong>{rag.stage3_scored}</strong> Stage 3 scored (Sonnet)
              </p>
              <p className="text-[11px] text-gray-400 mt-1">
                Tokens — Stage 2: {fmtK(rag.tokens_stage2)} · Stage 3: {fmtK(rag.tokens_stage3)} · cost ₹{rag.cost_inr}
              </p>
            </div>
          )}
          {feeds.map((f, i) => <ScanFeedBreakdown key={i} f={f} />)}
        </div>
      )}
    </div>
  )
}

function PollCard({ run }) {
  const qc = useQueryClient()
  const [running, setRunning] = useState(false)
  const d = run.details || {}

  const handlePoll = async () => {
    setRunning(true)
    try { await pollGmailNow(); toast.success('Gmail polled') }
    catch (err) { toast.error('Poll failed: ' + (err.response?.data?.detail || err.message)) }
    setTimeout(() => { qc.invalidateQueries({ queryKey: ['activity-system'] }); setRunning(false) }, 5000)
  }

  return (
    <div className="bg-white rounded-xl border border-gray-200 px-4 py-3">
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0"><RunHeader run={run} /></div>
        <RunButton label="Poll now" running={running} onClick={handlePoll} />
      </div>
      <p className="text-sm text-gray-700 mt-2">
        {d.emails_checked ?? run.jobs_found ?? 0} emails checked · <span className="text-emerald-600 font-medium">{run.jobs_added} jobs saved</span>
        {d.hitl_flagged ? <span className="text-red-500"> · {d.hitl_flagged} HITL</span> : ''}
      </p>
      {run.error_message && <p className="text-xs text-red-400 mt-1 truncate">{run.error_message}</p>}
    </div>
  )
}
