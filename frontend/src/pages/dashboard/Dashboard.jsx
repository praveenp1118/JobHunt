import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { formatDistanceToNow } from 'date-fns'
import { getJobStats, getJobs, pollGmail } from '../../api/jobs'
import { StatusBadge, MarketBadge } from '../../components/ui/Badge'
import { ThreeScores } from '../../components/ui/ScorePill'
import Button from '../../components/ui/Button'
import Spinner from '../../components/ui/Spinner'
import { toast } from '../../store/toast'
import {
  PieChart, Pie, Cell, ResponsiveContainer, Tooltip,
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
} from 'recharts'

const PIPELINE_ITEMS = [
  { key: 'total',          label: 'Total',      color: 'text-gray-700',    bg: 'bg-gray-50' },
  { key: 'applied',        label: 'Applied',    color: 'text-indigo-600',  bg: 'bg-indigo-50' },
  { key: 'screening',      label: 'Screening',  color: 'text-yellow-700',  bg: 'bg-yellow-50' },
  { key: 'interview_r1',   label: 'Interview',  color: 'text-amber-700',   bg: 'bg-amber-50' },
  { key: 'offer_received', label: 'Offer',      color: 'text-emerald-700', bg: 'bg-emerald-50' },
  { key: 'rejected',       label: 'Rejected',   color: 'text-red-600',     bg: 'bg-red-50' },
]

const PIE_COLORS = ['#6366f1', '#f59e0b', '#10b981', '#ef4444', '#6b7280', '#3b82f6', '#8b5cf6']

const SCORE_COLORS = {
  excellent: '#10b981',
  good: '#f59e0b',
  fair: '#f97316',
  low: '#ef4444',
}

export default function Dashboard() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [tab, setTab] = useState('overview')
  const [polling, setPolling] = useState(false)

  const { data: statsData, isLoading: statsLoading } = useQuery({
    queryKey: ['job-stats'],
    queryFn: () => getJobStats(),
    refetchInterval: 30000,
  })

  const { data: hitlData } = useQuery({
    queryKey: ['hitl-jobs'],
    queryFn: () => getJobs({ needs_hitl: true, limit: 5 }),
    refetchInterval: 30000,
  })

  const { data: recentData, isLoading: recentLoading } = useQuery({
    queryKey: ['recent-jobs'],
    queryFn: () => getJobs({ limit: 10 }),
    refetchInterval: 30000,
  })

  const stats = statsData?.data || {}
  const byStatus = stats.by_status || {}
  const hitlJobs = hitlData?.data || []
  const recentJobs = recentData?.data || []

  const handlePollNow = async () => {
    setPolling(true)
    try {
      await pollGmail(2)
      toast.success('Gmail polled — new emails classified')
      qc.invalidateQueries({ queryKey: ['recent-jobs'] })
      qc.invalidateQueries({ queryKey: ['hitl-jobs'] })
    } catch {
      toast.error('Gmail poll failed — check Gmail settings')
    } finally {
      setPolling(false)
    }
  }

  // Chart data
  const pieData = Object.entries(byStatus)
    .filter(([, v]) => v > 0)
    .map(([name, value]) => ({ name: name.replace(/_/g, ' '), value }))

  const scoreData = stats.score_distribution
    ? [
        { label: '85+', value: stats.score_distribution.excellent, fill: SCORE_COLORS.excellent },
        { label: '70–84', value: stats.score_distribution.good, fill: SCORE_COLORS.good },
        { label: '55–69', value: stats.score_distribution.fair, fill: SCORE_COLORS.fair },
        { label: '<55', value: stats.score_distribution.low, fill: SCORE_COLORS.low },
      ]
    : []

  const domainData = stats.by_domain_cv || []

  return (
    <div className="p-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-semibold text-gray-900">Dashboard</h1>
          <p className="text-sm text-gray-500 mt-0.5">Your job search at a glance</p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="secondary" size="sm" onClick={handlePollNow} loading={polling}>
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
            Pull now
          </Button>
          <Button size="sm" onClick={() => navigate('/jobs')}>+ Add job</Button>
        </div>
      </div>

      {/* Action Needed alert */}
      {hitlJobs.length > 0 && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-4 mb-6">
          <div className="flex items-center gap-2 mb-3">
            <div className="w-2 h-2 rounded-full bg-red-500 animate-pulse" />
            <h3 className="text-sm font-semibold text-red-700">
              Action needed — {hitlJobs.length} recruiter {hitlJobs.length === 1 ? 'reply' : 'replies'}
            </h3>
          </div>
          <div className="space-y-2">
            {hitlJobs.map((job) => (
              <div key={job.id}
                className="flex items-center justify-between bg-white rounded-lg px-3 py-2 border border-red-100 cursor-pointer hover:border-red-300 transition-colors"
                onClick={() => navigate(`/jobs?id=${job.id}`)}>
                <div>
                  <span className="text-sm font-medium text-gray-900">{job.company}</span>
                  <span className="text-sm text-gray-500 mx-1.5">·</span>
                  <span className="text-sm text-gray-600">{job.role}</span>
                </div>
                <Button size="sm" variant="danger">Reply now →</Button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Tabs */}
      <div className="flex gap-1 bg-gray-100 p-1 rounded-lg w-fit mb-6">
        {['overview', 'analytics'].map((t) => (
          <button key={t} onClick={() => setTab(t)}
            className={`px-4 py-1.5 rounded-md text-sm font-medium transition-colors capitalize ${
              tab === t ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500 hover:text-gray-700'
            }`}>
            {t}
          </button>
        ))}
      </div>

      {/* ── Overview ── */}
      {tab === 'overview' && (
        <div>
          {statsLoading ? (
            <div className="flex justify-center py-8"><Spinner /></div>
          ) : (
            <>
              {/* Pipeline stats */}
              <div className="grid grid-cols-3 lg:grid-cols-6 gap-3 mb-4">
                {PIPELINE_ITEMS.map(({ key, label, color, bg }) => (
                  <div key={key} className={`${bg} rounded-xl p-4 border border-gray-100`}>
                    <p className="text-xs text-gray-500 font-medium mb-1">{label}</p>
                    <p className={`text-2xl font-bold ${color}`}>
                      {key === 'total' ? (stats.total || 0) : (byStatus[key] || 0)}
                    </p>
                  </div>
                ))}
              </div>

              {/* Scan summary row */}
              {stats.from_scan > 0 && (
                <div className="flex items-center gap-4 bg-emerald-50 border border-emerald-200 rounded-xl px-4 py-3 mb-4 text-sm">
                  <span className="text-emerald-700">
                    📡 <strong>{stats.from_scan}</strong> jobs found via feed scans
                  </span>
                  {stats.avg_s1 && (
                    <span className="text-emerald-600">
                      · avg S1: <strong>{stats.avg_s1}</strong>
                    </span>
                  )}
                  <button onClick={() => navigate('/feeds')} className="text-emerald-600 hover:underline ml-auto text-xs font-medium">
                    View feeds →
                  </button>
                </div>
              )}
            </>
          )}

          {/* Recent jobs */}
          <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
            <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100">
              <h3 className="text-sm font-semibold text-gray-900">Recent jobs</h3>
              <button onClick={() => navigate('/jobs')} className="text-xs text-emerald-600 hover:text-emerald-700 font-medium">
                View all →
              </button>
            </div>
            {recentLoading ? (
              <div className="flex justify-center py-8"><Spinner /></div>
            ) : recentJobs.length === 0 ? (
              <div className="text-center py-12">
                <p className="text-sm text-gray-500 mb-3">No jobs yet</p>
                <Button size="sm" onClick={() => navigate('/jobs')}>Add your first job →</Button>
              </div>
            ) : (
              <table className="w-full">
                <thead>
                  <tr className="border-b border-gray-100">
                    {['Company', 'Role', 'Market', 'Scores', 'Status', 'Added'].map((h) => (
                      <th key={h} className="px-4 py-2.5 text-left text-xs font-medium text-gray-500">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-50">
                  {recentJobs.map((job) => (
                    <tr key={job.id}
                      className={`hover:bg-gray-50 cursor-pointer transition-colors ${job.needs_hitl ? 'border-l-2 border-l-red-400' : ''}`}
                      onClick={() => navigate(`/jobs?id=${job.id}`)}>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          {job.needs_hitl && <div className="w-1.5 h-1.5 rounded-full bg-red-500 shrink-0" />}
                          <span className="text-sm font-medium text-gray-900">{job.company}</span>
                        </div>
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-600 max-w-[180px] truncate">{job.role}</td>
                      <td className="px-4 py-3">
                        {job.market ? <MarketBadge market={job.market} /> : <span className="text-gray-300">—</span>}
                      </td>
                      <td className="px-4 py-3">
                        <ThreeScores s1={job.s1} s2={job.s2} s3Master={job.s3_master} />
                      </td>
                      <td className="px-4 py-3"><StatusBadge status={job.status} /></td>
                      <td className="px-4 py-3 text-xs text-gray-400">
                        {job.created_at ? formatDistanceToNow(new Date(job.created_at), { addSuffix: true }) : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      )}

      {/* ── Analytics ── */}
      {tab === 'analytics' && (
        <div className="grid grid-cols-2 gap-5">
          {/* Status distribution */}
          <div className="bg-white rounded-xl border border-gray-200 p-4">
            <h3 className="text-sm font-semibold text-gray-900 mb-4">Status distribution</h3>
            {pieData.length === 0 ? (
              <p className="text-sm text-gray-400 text-center py-8">No data yet</p>
            ) : (
              <>
                <ResponsiveContainer width="100%" height={200}>
                  <PieChart>
                    <Pie data={pieData} cx="50%" cy="50%" innerRadius={50} outerRadius={80}
                      paddingAngle={3} dataKey="value">
                      {pieData.map((_, i) => <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />)}
                    </Pie>
                    <Tooltip formatter={(v, n) => [v, n]} />
                  </PieChart>
                </ResponsiveContainer>
                <div className="flex flex-wrap gap-2 mt-2">
                  {pieData.map((entry, i) => (
                    <div key={entry.name} className="flex items-center gap-1.5 text-xs text-gray-600">
                      <div className="w-2.5 h-2.5 rounded-full" style={{ background: PIE_COLORS[i % PIE_COLORS.length] }} />
                      <span className="capitalize">{entry.name}</span>
                      <span className="font-medium text-gray-900">({entry.value})</span>
                    </div>
                  ))}
                </div>
              </>
            )}
          </div>

          {/* S1 score distribution */}
          <div className="bg-white rounded-xl border border-gray-200 p-4">
            <h3 className="text-sm font-semibold text-gray-900 mb-1">S1 score distribution</h3>
            {stats.avg_s1 && (
              <p className="text-xs text-gray-400 mb-4">Average: <strong className="text-gray-700">{stats.avg_s1}</strong></p>
            )}
            {scoreData.length === 0 || scoreData.every(d => d.value === 0) ? (
              <p className="text-sm text-gray-400 text-center py-8">No scores yet</p>
            ) : (
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={scoreData} barSize={40}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f0f0f0" />
                  <XAxis dataKey="label" tick={{ fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 11 }} />
                  <Tooltip />
                  <Bar dataKey="value" name="Jobs" radius={[4, 4, 0, 0]}>
                    {scoreData.map((entry, i) => <Cell key={i} fill={entry.fill} />)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>

          {/* Domain CV breakdown */}
          <div className="bg-white rounded-xl border border-gray-200 p-4">
            <h3 className="text-sm font-semibold text-gray-900 mb-4">Jobs by domain CV</h3>
            {domainData.length === 0 ? (
              <p className="text-sm text-gray-400 text-center py-6">No domain-matched jobs yet</p>
            ) : (
              <div className="space-y-3">
                {domainData.map((d) => {
                  const maxCount = Math.max(...domainData.map(x => x.count))
                  const pct = Math.round((d.count / maxCount) * 100)
                  return (
                    <div key={d.domain_cv_id}>
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-xs text-gray-700 truncate max-w-[70%]">{d.label}</span>
                        <span className="text-xs font-semibold text-gray-900">{d.count}</span>
                      </div>
                      <div className="w-full bg-gray-100 rounded-full h-1.5">
                        <div className="bg-emerald-500 h-1.5 rounded-full transition-all" style={{ width: `${pct}%` }} />
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </div>

          {/* Source breakdown */}
          <div className="bg-white rounded-xl border border-gray-200 p-4">
            <h3 className="text-sm font-semibold text-gray-900 mb-4">Jobs by source</h3>
            {!stats.by_source || Object.values(stats.by_source).every(v => v === 0) ? (
              <p className="text-sm text-gray-400 text-center py-6">No data yet</p>
            ) : (
              <div className="space-y-3">
                {Object.entries(stats.by_source || {})
                  .filter(([, v]) => v > 0)
                  .sort(([, a], [, b]) => b - a)
                  .map(([source, count]) => {
                    const total = Object.values(stats.by_source).reduce((a, b) => a + b, 0)
                    const pct = Math.round((count / total) * 100)
                    return (
                      <div key={source}>
                        <div className="flex items-center justify-between mb-1">
                          <span className="text-xs text-gray-700 capitalize">{source}</span>
                          <div className="flex items-center gap-2">
                            <span className="text-xs text-gray-400">{pct}%</span>
                            <span className="text-xs font-semibold text-gray-900">{count}</span>
                          </div>
                        </div>
                        <div className="w-full bg-gray-100 rounded-full h-1.5">
                          <div className="bg-indigo-500 h-1.5 rounded-full transition-all" style={{ width: `${pct}%` }} />
                        </div>
                      </div>
                    )
                  })}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
