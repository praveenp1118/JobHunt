import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { formatDistanceToNow, format } from 'date-fns'
import client from '../../api/client'
import Button from '../../components/ui/Button'
import Spinner from '../../components/ui/Spinner'
import { StatusBadge } from '../../components/ui/Badge'
import { toast } from '../../store/toast'
import useAuthStore from '../../store/auth'
import { useNavigate } from 'react-router-dom'
import { getGovernance, adminCancelDeletion } from '../../api/privacy'
import {
  adminCreateInvites, adminListInvites, adminRevokeInvite, adminExtendInvite,
  adminListExtensionRequests, adminGrantExtension, adminDenyExtension,
} from '../../api/access'
import Pagination, { usePagination } from '../../components/ui/Pagination'

export default function AdminPage() {
  const { user } = useAuthStore()
  const navigate = useNavigate()

  if (user?.role !== 'admin') {
    return (
      <div className="p-6 flex items-center justify-center min-h-96">
        <div className="text-center">
          <p className="text-sm text-gray-500">Admin access required</p>
          <Button size="sm" variant="ghost" className="mt-3" onClick={() => navigate('/dashboard')}>
            ← Back to dashboard
          </Button>
        </div>
      </div>
    )
  }

  return (
    <div className="p-6 max-w-6xl mx-auto">
      <div className="mb-6">
        <h1 className="text-xl font-semibold text-gray-900">Admin</h1>
        <p className="text-sm text-gray-500 mt-0.5">Platform management</p>
      </div>

      <div className="flex gap-1 bg-gray-100 p-1 rounded-lg w-fit mb-6">
        <TabContent />
      </div>
    </div>
  )
}

function TabContent() {
  const [tab, setTab] = useState('users')

  // Pending extension-request count → nav badge.
  const { data: extData } = useQuery({
    queryKey: ['admin-extensions'],
    queryFn: adminListExtensionRequests,
    refetchInterval: 60000,
  })
  const pendingExt = extData?.data?.pending_count || 0

  const tabs = [
    { key: 'users', label: 'Users' },
    { key: 'invites', label: 'Invites' },
    { key: 'extensions', label: 'Extension Requests', badge: pendingExt },
    { key: 'errors', label: 'Error Log' },
    { key: 'stats', label: 'Stats' },
    { key: 'governance', label: 'Governance' },
  ]

  return (
    <div className="w-full">
      <div className="flex gap-1 bg-gray-100 p-1 rounded-lg w-fit mb-6">
        {tabs.map((t) => (
          <button key={t.key} onClick={() => setTab(t.key)}
            className={`px-4 py-1.5 rounded-md text-sm font-medium transition-colors flex items-center gap-1.5 ${
              tab === t.key ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500 hover:text-gray-700'
            }`}>
            {t.label}
            {t.badge > 0 && (
              <span className="text-[10px] font-bold bg-amber-500 text-white rounded-full px-1.5 py-0.5 min-w-[18px] text-center">
                {t.badge}
              </span>
            )}
          </button>
        ))}
      </div>
      {tab === 'users' && <UsersTab />}
      {tab === 'invites' && <InvitesTab />}
      {tab === 'extensions' && <ExtensionsTab />}
      {tab === 'errors' && <ErrorsTab />}
      {tab === 'stats' && <StatsTab />}
      {tab === 'governance' && <GovernanceTab />}
    </div>
  )
}

// ── Invites tab (admin) ──
const KEY_STATUS_STYLE = {
  unredeemed: 'bg-emerald-100 text-emerald-700',
  redeemed: 'bg-gray-100 text-gray-500',
  revoked: 'bg-red-100 text-red-600',
  expired: 'bg-amber-100 text-amber-700',
}

function InvitesTab() {
  const qc = useQueryClient()
  const [count, setCount] = useState(5)
  const [grantsDays, setGrantsDays] = useState(30)
  const [deadline, setDeadline] = useState('')
  const [busy, setBusy] = useState(false)

  const { data, isLoading } = useQuery({ queryKey: ['admin-invites'], queryFn: adminListInvites })
  const invites = data?.data || []
  const pg = usePagination(invites, 15)

  const generate = async () => {
    setBusy(true)
    try {
      const payload = { count: Number(count), grants_days: Number(grantsDays) }
      if (deadline) payload.key_expires_at = new Date(deadline).toISOString()
      const res = await adminCreateInvites(payload)
      qc.invalidateQueries({ queryKey: ['admin-invites'] })
      const codes = (res.data.keys || []).map((k) => k.code).join('\n')
      if (codes) {
        try { await navigator.clipboard.writeText(codes) } catch { /* clipboard may be blocked */ }
        toast.success(`${res.data.created} key(s) generated + copied`)
      }
    } catch { toast.error('Failed to generate keys') } finally { setBusy(false) }
  }

  const copyOne = async (code) => {
    try { await navigator.clipboard.writeText(code); toast.success('Copied') } catch { toast.error('Copy failed') }
  }
  const revoke = async (id) => {
    try { await adminRevokeInvite(id); qc.invalidateQueries({ queryKey: ['admin-invites'] }); toast.success('Revoked') }
    catch { toast.error('Cannot revoke (already redeemed?)') }
  }
  const extend = async (id) => {
    const val = window.prompt('New redemption deadline (YYYY-MM-DD), or blank to clear:')
    if (val === null) return
    try {
      await adminExtendInvite(id, val ? new Date(val).toISOString() : null)
      qc.invalidateQueries({ queryKey: ['admin-invites'] }); toast.success('Deadline updated')
    } catch { toast.error('Failed to update deadline') }
  }

  return (
    <div className="space-y-5">
      <div className="bg-white rounded-2xl border border-gray-200 p-5">
        <h3 className="text-sm font-semibold text-gray-900 mb-3">Generate invitation keys</h3>
        <div className="flex flex-wrap items-end gap-3">
          <label className="text-xs text-gray-500">Count
            <input type="number" min="1" max="200" value={count} onChange={(e) => setCount(e.target.value)}
              className="block mt-1 w-24 border border-gray-200 rounded-lg px-2 py-1.5 text-sm outline-none" />
          </label>
          <label className="text-xs text-gray-500">Free days granted
            <input type="number" min="1" value={grantsDays} onChange={(e) => setGrantsDays(e.target.value)}
              className="block mt-1 w-32 border border-gray-200 rounded-lg px-2 py-1.5 text-sm outline-none" />
          </label>
          <label className="text-xs text-gray-500">Redemption deadline (optional)
            <input type="date" value={deadline} onChange={(e) => setDeadline(e.target.value)}
              className="block mt-1 border border-gray-200 rounded-lg px-2 py-1.5 text-sm outline-none" />
          </label>
          <Button size="sm" loading={busy} onClick={generate}>Generate</Button>
        </div>
        <p className="text-xs text-gray-400 mt-2">Generated keys are copied to your clipboard. Each key is single-use.</p>
      </div>

      <div className="bg-white rounded-2xl border border-gray-200 overflow-hidden">
        <div className="px-5 py-3 border-b border-gray-100">
          <p className="text-sm font-semibold text-gray-900">{invites.length} keys</p>
        </div>
        {isLoading ? <div className="flex justify-center py-8"><Spinner /></div> : (
          <table className="w-full">
            <thead className="border-b border-gray-100">
              <tr>{['Code', 'Status', 'Days', 'Deadline', 'Redeemed', 'Actions'].map((h) => (
                <th key={h} className="px-4 py-2.5 text-left text-xs font-medium text-gray-500">{h}</th>))}</tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {pg.slice.map((k) => (
                <tr key={k.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3 text-sm font-mono text-gray-900">{k.code}</td>
                  <td className="px-4 py-3">
                    <span className={`text-xs font-medium px-2 py-0.5 rounded-full capitalize ${KEY_STATUS_STYLE[k.status] || 'bg-gray-100 text-gray-500'}`}>{k.status}</span>
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-600">{k.grants_days}</td>
                  <td className="px-4 py-3 text-xs text-gray-400">{k.key_expires_at ? format(new Date(k.key_expires_at), 'MMM d, yyyy') : 'never'}</td>
                  <td className="px-4 py-3 text-xs text-gray-400">{k.redeemed_at ? format(new Date(k.redeemed_at), 'MMM d, yyyy') : '—'}</td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2.5 text-xs font-medium">
                      <button onClick={() => copyOne(k.code)} className="text-gray-500 hover:text-gray-700">Copy</button>
                      {k.status === 'unredeemed' && (
                        <>
                          <button onClick={() => extend(k.id)} className="text-blue-600 hover:underline">Deadline</button>
                          <button onClick={() => revoke(k.id)} className="text-red-600 hover:underline">Revoke</button>
                        </>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <div className="px-4 pb-3">
          <Pagination currentPage={pg.page} totalPages={pg.totalPages} totalItems={pg.total} itemsPerPage={15} onPageChange={pg.setPage} label="keys" />
        </div>
      </div>
    </div>
  )
}

// ── Extension Requests tab (admin) ──
function ExtensionsTab() {
  const qc = useQueryClient()
  const { data, isLoading } = useQuery({
    queryKey: ['admin-extensions'], queryFn: adminListExtensionRequests, refetchInterval: 60000,
  })
  const rows = data?.data?.requests || []
  const pg = usePagination(rows, 15)

  const grant = async (id) => {
    const val = window.prompt('Grant how many free days?', '30')
    if (val === null) return
    try {
      await adminGrantExtension(id, Number(val) || 30)
      qc.invalidateQueries({ queryKey: ['admin-extensions'] }); toast.success(`Granted ${val} days`)
    } catch { toast.error('Failed to grant') }
  }
  const deny = async (id) => {
    try { await adminDenyExtension(id); qc.invalidateQueries({ queryKey: ['admin-extensions'] }); toast.success('Denied') }
    catch { toast.error('Failed to deny') }
  }

  const STATUS = { pending: 'bg-amber-100 text-amber-700', granted: 'bg-emerald-100 text-emerald-700', denied: 'bg-gray-100 text-gray-500' }

  if (isLoading) return <div className="flex justify-center py-8"><Spinner /></div>
  if (rows.length === 0) return (
    <div className="bg-white rounded-2xl border border-gray-200 p-10 text-center">
      <p className="text-sm text-gray-400">No extension requests</p>
    </div>
  )

  return (
    <div className="bg-white rounded-2xl border border-gray-200 overflow-hidden">
      <table className="w-full">
        <thead className="border-b border-gray-100">
          <tr>{['User', 'Requested', 'Status', 'Access ends', 'Actions'].map((h) => (
            <th key={h} className="px-4 py-2.5 text-left text-xs font-medium text-gray-500">{h}</th>))}</tr>
        </thead>
        <tbody className="divide-y divide-gray-50">
          {pg.slice.map((r) => (
            <tr key={r.id} className="hover:bg-gray-50">
              <td className="px-4 py-3 text-sm text-gray-700">
                {r.user?.email || r.user_id.slice(0, 8)}
                {r.user?.entitlement_source && <span className="ml-1 text-[10px] text-gray-400">· {r.user.entitlement_source}</span>}
              </td>
              <td className="px-4 py-3 text-xs text-gray-400">{r.requested_at ? formatDistanceToNow(new Date(r.requested_at), { addSuffix: true }) : '—'}</td>
              <td className="px-4 py-3"><span className={`text-xs font-medium px-2 py-0.5 rounded-full capitalize ${STATUS[r.status] || ''}`}>{r.status}</span></td>
              <td className="px-4 py-3 text-xs text-gray-400">{r.user?.subscription_end ? format(new Date(r.user.subscription_end), 'MMM d, yyyy') : '—'}</td>
              <td className="px-4 py-3">
                {r.status === 'pending' ? (
                  <div className="flex items-center gap-2.5 text-xs font-medium">
                    <button onClick={() => grant(r.id)} className="text-emerald-600 hover:underline">Grant</button>
                    <button onClick={() => deny(r.id)} className="text-red-600 hover:underline">Deny</button>
                  </div>
                ) : <span className="text-xs text-gray-300">resolved</span>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="px-4 pb-3">
        <Pagination currentPage={pg.page} totalPages={pg.totalPages} totalItems={pg.total} itemsPerPage={15} onPageChange={pg.setPage} label="requests" />
      </div>
    </div>
  )
}

function UsersTab() {
  const qc = useQueryClient()

  const { data, isLoading } = useQuery({
    queryKey: ['admin-users'],
    queryFn: () => client.get('/auth/admin/users'),
  })

  const users = data?.data || []
  const pg = usePagination(users, 20)

  const handleRoleChange = async (userId, role) => {
    try {
      await client.patch(`/auth/admin/users/${userId}/role`, { role })
      qc.invalidateQueries({ queryKey: ['admin-users'] })
      toast.success('Role updated')
    } catch {
      toast.error('Failed to update role')
    }
  }

  const handleToggleActive = async (userId, isActive) => {
    try {
      await client.patch(`/auth/admin/users/${userId}/active`, { is_active: !isActive })
      qc.invalidateQueries({ queryKey: ['admin-users'] })
      toast.success(isActive ? 'User deactivated' : 'User activated')
    } catch {
      toast.error('Failed to update user')
    }
  }

  if (isLoading) return <div className="flex justify-center py-8"><Spinner /></div>

  return (
    <div className="bg-white rounded-2xl border border-gray-200 overflow-hidden">
      <div className="px-5 py-3 border-b border-gray-100 flex items-center justify-between">
        <p className="text-sm font-semibold text-gray-900">{users.length} users</p>
      </div>
      <table className="w-full">
        <thead className="border-b border-gray-100">
          <tr>
            {['Name', 'Email', 'Role', 'Plan', 'Joined', 'Status', 'Actions'].map((h) => (
              <th key={h} className="px-4 py-2.5 text-left text-xs font-medium text-gray-500">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-50">
          {pg.slice.map((u) => (
            <tr key={u.id} className="hover:bg-gray-50">
              <td className="px-4 py-3 text-sm font-medium text-gray-900">{u.name || '—'}</td>
              <td className="px-4 py-3 text-sm text-gray-600">{u.email}</td>
              <td className="px-4 py-3">
                <select
                  value={u.role}
                  onChange={(e) => handleRoleChange(u.id, e.target.value)}
                  className="text-xs border border-gray-200 rounded px-2 py-1 outline-none"
                >
                  <option value="user">user</option>
                  <option value="admin">admin</option>
                </select>
              </td>
              <td className="px-4 py-3">
                <span className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded-full capitalize">{u.plan}</span>
              </td>
              <td className="px-4 py-3 text-xs text-gray-400">
                {u.created_at ? format(new Date(u.created_at), 'MMM d, yyyy') : '—'}
              </td>
              <td className="px-4 py-3">
                <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${u.is_active ? 'bg-emerald-100 text-emerald-700' : 'bg-red-100 text-red-600'}`}>
                  {u.is_active ? 'Active' : 'Inactive'}
                </span>
              </td>
              <td className="px-4 py-3">
                <button
                  onClick={() => handleToggleActive(u.id, u.is_active)}
                  className="text-xs text-gray-500 hover:text-gray-700 font-medium"
                >
                  {u.is_active ? 'Deactivate' : 'Activate'}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="px-4 pb-3">
        <Pagination currentPage={pg.page} totalPages={pg.totalPages} totalItems={pg.total} itemsPerPage={20} onPageChange={pg.setPage} label="users" />
      </div>
    </div>
  )
}

function ErrorsTab() {
  const qc = useQueryClient()

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['admin-errors'],
    queryFn: () => client.get('/auth/admin/error-logs'),
  })

  const errors = data?.data || []
  const unresolved = errors.filter((e) => !e.is_resolved)
  const pg = usePagination(errors, 10)

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <p className="text-sm text-gray-600">
          {unresolved.length} unresolved · {errors.length} total
        </p>
        <Button size="sm" variant="ghost" onClick={() => refetch()}>Refresh</Button>
      </div>

      {isLoading ? (
        <div className="flex justify-center py-8"><Spinner /></div>
      ) : errors.length === 0 ? (
        <div className="bg-white rounded-2xl border border-gray-200 p-10 text-center">
          <p className="text-sm text-gray-400">No errors logged</p>
        </div>
      ) : (
        <div className="space-y-2">
          {pg.slice.map((err) => (
            <div key={err.id} className={`bg-white rounded-xl border p-4 ${err.is_resolved ? 'border-gray-100 opacity-60' : 'border-red-100'}`}>
              <div className="flex items-start justify-between gap-3">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-xs font-medium bg-red-50 text-red-600 px-2 py-0.5 rounded-full">{err.action}</span>
                    {err.is_resolved && <span className="text-[10px] text-emerald-600 font-medium">Resolved</span>}
                  </div>
                  <p className="text-sm text-gray-700">{err.error_message}</p>
                  <p className="text-xs text-gray-400 mt-1">
                    {formatDistanceToNow(new Date(err.created_at), { addSuffix: true })}
                  </p>
                </div>
                {!err.is_resolved && (
                  <Button size="sm" variant="secondary" onClick={async () => {
                    try {
                      await client.patch(`/auth/admin/error-logs/${err.id}/resolve`)
                      qc.invalidateQueries({ queryKey: ['admin-errors'] })
                      toast.success('Marked as resolved')
                    } catch { toast.error('Failed') }
                  }}>
                    Resolve
                  </Button>
                )}
              </div>
            </div>
          ))}
          <Pagination currentPage={pg.page} totalPages={pg.totalPages} totalItems={pg.total} itemsPerPage={10} onPageChange={pg.setPage} label="errors" />
        </div>
      )}
    </div>
  )
}

function StatsTab() {
  const { data, isLoading } = useQuery({
    queryKey: ['admin-stats'],
    queryFn: () => client.get('/admin/stats'),
  })

  const stats = data?.data || {}

  const statCards = [
    { label: 'Total users', value: stats.total_users ?? '—', color: 'text-gray-900' },
    { label: 'Active users', value: stats.active_users ?? '—', color: 'text-emerald-600' },
    { label: 'Total jobs', value: stats.total_jobs ?? '—', color: 'text-indigo-600' },
    { label: 'Applications sent', value: stats.total_applied ?? '—', color: 'text-blue-600' },
    { label: 'Domain CVs', value: stats.total_domain_cvs ?? '—', color: 'text-purple-600' },
    { label: 'Tailored CVs', value: stats.total_tailored ?? '—', color: 'text-amber-600' },
  ]

  if (isLoading) return <div className="flex justify-center py-8"><Spinner /></div>

  return (
    <div className="grid grid-cols-3 gap-4">
      {statCards.map(({ label, value, color }) => (
        <div key={label} className="bg-white rounded-xl border border-gray-200 p-5">
          <p className="text-xs text-gray-500 mb-1">{label}</p>
          <p className={`text-2xl font-bold ${color}`}>{value}</p>
        </div>
      ))}
    </div>
  )
}

// ── Governance tab (admin) ──
function GovernanceTab() {
  const qc = useQueryClient()
  const { data, isLoading } = useQuery({ queryKey: ['admin-governance'], queryFn: getGovernance, refetchInterval: 60000 })
  const g = data?.data
  const pg = usePagination(g?.audit_logs || [], 20)
  if (isLoading) return <div className="flex justify-center py-12"><Spinner /></div>
  if (!g) return null

  const stats = [
    ['Audit events today', g.audit_events_today],
    ['Rate-limit 429s', g.rate_limit_violations],
    ['Failed logins (24h)', g.failed_logins],
    ['Data exports today', g.data_exports_today],
    ['Hallucination flags (7d)', g.hallucination_violations],
    ['Pending deletions', (g.pending_deletions || []).length],
  ]

  const cancelDel = async (uid) => {
    try { await adminCancelDeletion(uid); toast.success('Deletion cancelled'); qc.invalidateQueries({ queryKey: ['admin-governance'] }) }
    catch { toast.error('Failed') }
  }

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
        {stats.map(([k, v]) => (
          <div key={k} className="bg-white rounded-xl border border-gray-200 p-4">
            <p className="text-2xl font-bold text-gray-900">{v ?? 0}</p>
            <p className="text-xs text-gray-500 mt-0.5">{k}</p>
          </div>
        ))}
      </div>

      {(g.pending_deletions || []).length > 0 && (
        <div className="bg-white rounded-xl border border-red-200 p-4">
          <h3 className="text-sm font-semibold text-red-700 mb-2">Pending account deletions</h3>
          {g.pending_deletions.map((p) => (
            <div key={p.user_id} className="flex items-center justify-between py-1.5 border-b border-gray-50 last:border-0">
              <span className="text-sm text-gray-700">{p.email} <span className="text-xs text-gray-400">· {p.scheduled_at ? new Date(p.scheduled_at).toLocaleDateString() : ''}</span></span>
              <button onClick={() => cancelDel(p.user_id)} className="text-xs text-emerald-600 hover:underline font-medium">Cancel deletion</button>
            </div>
          ))}
        </div>
      )}

      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        <h3 className="text-sm font-semibold text-gray-900 px-4 py-3 border-b border-gray-100">Audit log (last 100)</h3>
        <div className="max-h-[60vh] overflow-y-auto">
          <table className="w-full text-xs">
            <thead className="sticky top-0 bg-gray-50 text-gray-500">
              <tr><th className="text-left px-3 py-2">Time</th><th className="text-left px-3 py-2">Action</th><th className="text-left px-3 py-2">User</th><th className="text-left px-3 py-2">IP</th><th className="text-left px-3 py-2">Details</th></tr>
            </thead>
            <tbody>
              {pg.slice.map((l) => (
                <tr key={l.id} className="border-t border-gray-50">
                  <td className="px-3 py-1.5 text-gray-400 whitespace-nowrap">{l.created_at ? new Date(l.created_at).toLocaleString() : ''}</td>
                  <td className="px-3 py-1.5"><span className={`font-medium ${l.action.includes('fail') || l.action.includes('rate') || l.action.includes('hallucinat') ? 'text-amber-700' : 'text-gray-700'}`}>{l.action}</span></td>
                  <td className="px-3 py-1.5 text-gray-400 font-mono">{l.user_id ? l.user_id.slice(0, 8) : '—'}</td>
                  <td className="px-3 py-1.5 text-gray-400">{l.ip || '—'}</td>
                  <td className="px-3 py-1.5 text-gray-400 max-w-[200px] truncate">{l.details ? JSON.stringify(l.details) : ''}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="px-3 pb-3">
            <Pagination currentPage={pg.page} totalPages={pg.totalPages} totalItems={pg.total} itemsPerPage={20} onPageChange={pg.setPage} label="events" />
          </div>
        </div>
      </div>
    </div>
  )
}
