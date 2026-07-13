import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { format } from 'date-fns'
import { getUsageLogs, exportUsageCSV } from '../../api/usage'
import { toast } from '../../store/toast'
import Pagination, { usePagination } from '../../components/ui/Pagination'

// 10-step token badge colour scale (per spec).
function tokenColor(n) {
  if (n == null) return '#9ca3af'
  if (n < 1000) return '#10b981'
  if (n < 2000) return '#34d399'
  if (n < 3000) return '#6ee7b7'
  if (n < 5000) return '#a3e635'
  if (n < 8000) return '#fbbf24'
  if (n < 12000) return '#f59e0b'
  if (n < 18000) return '#f97316'
  if (n < 25000) return '#ef4444'
  if (n < 40000) return '#dc2626'
  return '#991b1b'
}

function fmtTokens(n) {
  if (n == null) return '—'
  return n < 1000 ? String(n) : (n / 1000).toFixed(1) + 'K'
}

const CAT_PILLS = [
  { key: 'all', label: 'All' },
  { key: 'tailoring', label: 'Tailoring' },
  { key: 'scoring', label: 'Scoring' },
  { key: 'domain_cv', label: 'Domain CVs' },
  { key: 'scanner', label: 'Scanner' },
  { key: 'gmail', label: 'Gmail' },
  { key: 'career', label: 'Career' },
]
const APIFY_PILLS = [
  { key: 'all', label: 'All' },
  { key: 'linkedin', label: 'LinkedIn' },
  { key: 'google', label: 'Google Jobs' },
  { key: 'other', label: 'Other' },
]
const CAT_COLORS = {
  tailoring: '#6366f1', scoring: '#10b981', domain_cv: '#f59e0b',
  scanner: '#3b82f6', gmail: '#ec4899', career: '#8b5cf6', other: '#9ca3af',
}

function TokenBadge({ n }) {
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold text-white tabular-nums"
      style={{ backgroundColor: tokenColor(n) }}>
      ⚡ {fmtTokens(n)}
    </span>
  )
}

export default function UsageTab() {
  const [days, setDays] = useState(30)
  const [subtab, setSubtab] = useState('anthropic')
  const [category, setCategory] = useState('all')
  const [apifyFilter, setApifyFilter] = useState('all')
  const [expanded, setExpanded] = useState(null)

  const { data, isLoading } = useQuery({
    queryKey: ['usage', subtab, category, days],
    queryFn: () => getUsageLogs(subtab, subtab === 'anthropic' ? category : 'all', days),
    refetchInterval: 60000,
  })
  const logs = data?.data?.logs || []
  const anth = data?.data?.summary?.anthropic || { total_tokens: 0, total_cost_usd: 0, total_cost_inr: 0, call_count: 0, by_category: {} }
  const apify = data?.data?.summary?.apify || { total_runs: 0, total_cost_usd: 0, total_cost_inr: 0, actor_count: 0 }
  const brightdata = data?.data?.summary?.brightdata || { total_runs: 0, jobs_saved: 0, sub_source_count: 0 }

  const handleExport = async () => {
    try {
      const res = await exportUsageCSV(days)
      const url = URL.createObjectURL(res.data)
      const a = document.createElement('a')
      a.href = url; a.download = `jobhunt_usage_${days}d.csv`; a.click()
      URL.revokeObjectURL(url)
    } catch { toast.error('Export failed') }
  }

  const apifyLogs = logs.filter((l) => {
    if (apifyFilter === 'all') return true
    const id = (l.actor_id || '').toLowerCase()
    if (apifyFilter === 'linkedin') return id.includes('linkedin')
    if (apifyFilter === 'google') return id.includes('google')
    return !id.includes('linkedin') && !id.includes('google')
  })

  const maxCat = Math.max(1, ...Object.values(anth.by_category).map((c) => c.tokens))

  return (
    <div className="space-y-5">
      {/* Window selector */}
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-gray-900">API Usage</h2>
        <select value={days} onChange={(e) => setDays(Number(e.target.value))}
          className="text-xs border border-gray-200 rounded-lg px-2 py-1 outline-none bg-white">
          <option value={7}>Last 7 days</option>
          <option value={30}>Last 30 days</option>
          <option value={90}>Last 90 days</option>
        </select>
      </div>

      {/* Summary panel */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-white rounded-2xl border border-gray-200 p-5">
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-sm font-semibold text-gray-900">Anthropic (Claude)</h3>
            <a href="https://console.anthropic.com/settings/usage" target="_blank" rel="noreferrer"
              className="text-xs text-emerald-600 hover:underline">Verify on Console →</a>
          </div>
          <p className="text-2xl font-bold text-gray-900">₹{anth.total_cost_inr.toFixed(2)}</p>
          <p className="text-xs text-gray-500 mt-0.5">
            {fmtTokens(anth.total_tokens)} tokens · {anth.call_count} calls · ${anth.total_cost_usd.toFixed(4)}
          </p>
          <div className="mt-3 space-y-1.5">
            {Object.entries(anth.by_category).sort((a, b) => b[1].tokens - a[1].tokens).map(([cat, c]) => (
              <div key={cat} className="flex items-center gap-2">
                <span className="text-[11px] text-gray-500 w-20 capitalize">{cat.replace('_', ' ')}</span>
                <div className="flex-1 h-3 bg-gray-100 rounded-full overflow-hidden">
                  <div className="h-full rounded-full" style={{ width: `${(c.tokens / maxCat) * 100}%`, backgroundColor: CAT_COLORS[cat] || '#9ca3af' }} />
                </div>
                <span className="text-[10px] text-gray-400 w-20 text-right tabular-nums">{fmtTokens(c.tokens)} · ₹{c.cost.toFixed(2)}</span>
              </div>
            ))}
            {Object.keys(anth.by_category).length === 0 && <p className="text-xs text-gray-400">No Claude usage in this window.</p>}
          </div>
          {anth.by_model && Object.keys(anth.by_model).length > 0 && (
            <div className="mt-3 pt-2 border-t border-gray-100 space-y-0.5">
              {Object.entries(anth.by_model).sort((a, b) => b[1].cost - a[1].cost).map(([tier, m]) => (
                <div key={tier} className="flex items-center justify-between text-[11px]">
                  <span className={tier === 'Haiku' ? 'text-emerald-600 font-medium' : 'text-gray-600'}>{tier} calls: {m.count}</span>
                  <span className="text-gray-400 tabular-nums">₹{m.cost.toFixed(2)}</span>
                </div>
              ))}
              <div className="flex items-center justify-between text-[11px] font-semibold text-gray-700 pt-0.5">
                <span>Total</span><span className="tabular-nums">₹{anth.total_cost_inr.toFixed(2)}</span>
              </div>
            </div>
          )}
        </div>

        <div className="bg-white rounded-2xl border border-gray-200 p-5">
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-sm font-semibold text-gray-900">Apify (Scanning)</h3>
            <a href="https://console.apify.com/billing" target="_blank" rel="noreferrer"
              className="text-xs text-emerald-600 hover:underline">Verify on Console →</a>
          </div>
          <p className="text-2xl font-bold text-gray-900">${apify.total_cost_usd.toFixed(3)}</p>
          <p className="text-xs text-gray-500 mt-0.5">
            {apify.total_runs} runs · {apify.actor_count} actor{apify.actor_count === 1 ? '' : 's'} · ₹{apify.total_cost_inr.toFixed(2)}
          </p>
          <p className="text-[11px] text-amber-600 mt-3">💡 These are estimates — cross-check exact spend on each provider's console. You pay providers directly with your own keys.</p>
        </div>

        <div className="bg-white rounded-2xl border border-gray-200 p-5">
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-sm font-semibold text-gray-900">Bright Data (Scanning)</h3>
            <a href="https://brightdata.com/cp/dashboard" target="_blank" rel="noreferrer"
              className="text-xs text-emerald-600 hover:underline">Verify on Dashboard →</a>
          </div>
          <p className="text-2xl font-bold text-gray-900">{brightdata.total_runs} <span className="text-sm font-medium text-gray-500">results</span></p>
          <p className="text-xs text-gray-500 mt-0.5">
            {brightdata.jobs_saved} saved · {brightdata.sub_source_count} source{brightdata.sub_source_count === 1 ? '' : 's'}
          </p>
          <p className="text-[11px] text-amber-600 mt-3">💡 Bright Data's API doesn't return per-call cost — check exact credit spend on your Bright Data dashboard.</p>
        </div>
      </div>

      {/* Sub-tabs */}
      <div className="flex gap-1 bg-gray-100 p-1 rounded-lg w-fit">
        {[{ k: 'anthropic', l: 'Anthropic Tokens' }, { k: 'apify', l: 'Apify Usage' }].map((t) => (
          <button key={t.k} onClick={() => { setSubtab(t.k); setExpanded(null) }}
            className={`px-3 py-1.5 rounded-md text-sm font-medium ${subtab === t.k ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500 hover:text-gray-700'}`}>{t.l}</button>
        ))}
      </div>

      {subtab === 'anthropic' ? (
        <div>
          <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
            <div className="flex gap-1.5 flex-wrap">
              {CAT_PILLS.map((p) => (
                <button key={p.key} onClick={() => setCategory(p.key)}
                  className={`px-2.5 py-1 rounded-full text-xs font-medium border ${category === p.key ? 'bg-slate-800 text-white border-slate-800' : 'bg-white text-gray-600 border-gray-200 hover:bg-gray-50'}`}>{p.label}</button>
              ))}
            </div>
            <button onClick={handleExport} className="text-xs font-medium px-3 py-1.5 rounded-lg border border-gray-200 hover:bg-gray-50">⭳ Export CSV</button>
          </div>
          <UsageTable logs={logs} isLoading={isLoading} expanded={expanded} setExpanded={setExpanded} kind="anthropic" />
        </div>
      ) : (
        <div>
          <div className="flex gap-1.5 flex-wrap mb-3">
            {APIFY_PILLS.map((p) => (
              <button key={p.key} onClick={() => setApifyFilter(p.key)}
                className={`px-2.5 py-1 rounded-full text-xs font-medium border ${apifyFilter === p.key ? 'bg-slate-800 text-white border-slate-800' : 'bg-white text-gray-600 border-gray-200 hover:bg-gray-50'}`}>{p.label}</button>
            ))}
          </div>
          <UsageTable logs={apifyLogs} isLoading={isLoading} expanded={expanded} setExpanded={setExpanded} kind="apify" />
        </div>
      )}
    </div>
  )
}

function UsageTable({ logs, isLoading, expanded, setExpanded, kind }) {
  const pg = usePagination(logs, 20)
  if (isLoading) return <p className="text-sm text-gray-400 text-center py-8">Loading…</p>
  if (!logs.length) return <p className="text-sm text-gray-400 text-center py-8 bg-white rounded-2xl border border-gray-200">No usage in this window.</p>

  return (
    <div className="bg-white rounded-2xl border border-gray-200 overflow-hidden">
      <table className="w-full">
        <thead className="border-b border-gray-100 bg-gray-50">
          <tr className="text-left text-[11px] text-gray-500">
            <th className="px-4 py-2 font-medium">Date</th>
            <th className="px-4 py-2 font-medium">{kind === 'apify' ? 'Actor' : 'Agent'}</th>
            <th className="px-4 py-2 font-medium">For</th>
            {kind === 'anthropic' && <th className="px-4 py-2 font-medium">Model</th>}
            <th className="px-4 py-2 font-medium text-right">{kind === 'apify' ? 'Runs' : 'Tokens'}</th>
            <th className="px-4 py-2 font-medium text-right">Cost</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-50">
          {pg.slice.map((l) => (
            <>
              <tr key={l.id} onClick={() => setExpanded(expanded === l.id ? null : l.id)}
                className="hover:bg-gray-50 cursor-pointer"
                title={kind === 'anthropic' ? `${l.agent_name}\nInput: ${l.input_tokens}\nOutput: ${l.output_tokens}\nTotal: ${l.total_tokens}\nModel: ${l.model}` : `${l.agent_name}\nRequested: ${l.runs_requested}\nReturned: ${l.runs_returned}\nSaved: ${l.jobs_saved}`}>
                <td className="px-4 py-2.5 text-xs text-gray-500 whitespace-nowrap">{l.created_at ? format(new Date(l.created_at), 'MMM d HH:mm') : '—'}</td>
                <td className="px-4 py-2.5 text-xs text-gray-700 font-mono truncate max-w-[160px]">{l.agent_name}</td>
                <td className="px-4 py-2.5 text-xs text-gray-600 truncate max-w-[200px]">{l.entity_label || '—'}</td>
                {kind === 'anthropic' && (
                  <td className="px-4 py-2.5">
                    {(() => {
                      const m = (l.model || '').toLowerCase()
                      const tier = m.includes('haiku') ? 'Haiku' : m.includes('sonnet') ? 'Sonnet' : m.includes('opus') ? 'Opus' : '—'
                      const cls = tier === 'Haiku' ? 'bg-emerald-50 text-emerald-600' : tier === 'Sonnet' ? 'bg-blue-50 text-blue-600' : tier === 'Opus' ? 'bg-purple-50 text-purple-600' : 'bg-gray-100 text-gray-400'
                      return <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded-full ${cls}`}>{tier}</span>
                    })()}
                  </td>
                )}
                <td className="px-4 py-2.5 text-right">
                  {kind === 'apify' ? <span className="text-xs tabular-nums text-gray-700">{l.runs_returned ?? '—'}</span> : <TokenBadge n={l.total_tokens} />}
                </td>
                <td className="px-4 py-2.5 text-right text-xs tabular-nums text-gray-700">
                  {kind === 'apify' ? `$${(l.estimated_cost_usd || 0).toFixed(3)}` : `₹${(l.estimated_cost_inr || 0).toFixed(2)}`}
                </td>
              </tr>
              {expanded === l.id && (
                <tr key={l.id + '-d'} className="bg-gray-50">
                  <td colSpan={kind === 'anthropic' ? 6 : 5} className="px-4 py-3">
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
                      <Detail label="Agent" value={l.agent_name} />
                      <Detail label="Category" value={l.category} />
                      <Detail label="Model" value={l.model || '—'} />
                      <Detail label="Entity" value={l.entity_label || l.entity_type || '—'} />
                      {kind === 'anthropic' ? (
                        <>
                          <Detail label="Input tokens" value={l.input_tokens?.toLocaleString() ?? '—'} />
                          <Detail label="Output tokens" value={l.output_tokens?.toLocaleString() ?? '—'} />
                          <Detail label="Total tokens" value={l.total_tokens?.toLocaleString() ?? '—'} />
                          <Detail label="Cost" value={`₹${(l.estimated_cost_inr || 0).toFixed(4)} ($${(l.estimated_cost_usd || 0).toFixed(6)})`} />
                          {l.result_summary && <Detail label="Result" value={l.result_summary} />}
                        </>
                      ) : (
                        <>
                          <Detail label="Runs requested" value={l.runs_requested ?? '—'} />
                          <Detail label="Runs returned" value={l.runs_returned ?? '—'} />
                          <Detail label="Jobs found" value={l.jobs_saved ?? '—'} />
                          <Detail label="Cost" value={`$${(l.estimated_cost_usd || 0).toFixed(4)} (₹${(l.estimated_cost_inr || 0).toFixed(2)})`} />
                        </>
                      )}
                    </div>
                  </td>
                </tr>
              )}
            </>
          ))}
        </tbody>
      </table>
      <div className="px-4 pb-3">
        <Pagination currentPage={pg.page} totalPages={pg.totalPages} totalItems={pg.total} itemsPerPage={20} onPageChange={pg.setPage} label="calls" />
      </div>
    </div>
  )
}

function Detail({ label, value }) {
  return (
    <div>
      <p className="text-[10px] uppercase tracking-wide text-gray-400">{label}</p>
      <p className="text-gray-800 break-words">{value}</p>
    </div>
  )
}
