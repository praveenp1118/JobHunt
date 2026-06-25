import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { getPrivacySummary, getRateLimits, exportMyData, requestDeletion, cancelDeletion } from '../../api/privacy'
import { getLegalUrls } from '../../api/legal'
import Button from '../../components/ui/Button'
import Spinner from '../../components/ui/Spinner'
import { toast } from '../../store/toast'

const RL_LABELS = {
  tailor_generate: 'CV tailoring', domain_generate: 'Domain CV', career_analyse: 'Career analysis',
  jd_parse: 'JD parsing', gmail_poll_manual: 'Gmail poll', scanner_run_manual: 'Feed scan',
}

function Card({ title, children }) {
  return (
    <div className="bg-white rounded-2xl border border-gray-200 p-5 mb-4">
      <h3 className="text-sm font-semibold text-gray-900 mb-3">{title}</h3>
      {children}
    </div>
  )
}

export default function PrivacyTab() {
  const qc = useQueryClient()
  const [exporting, setExporting] = useState(false)
  const [busy, setBusy] = useState(false)
  const [showDelete, setShowDelete] = useState(false)
  const [confirmText, setConfirmText] = useState('')

  const { data: sumData, isLoading } = useQuery({ queryKey: ['privacy-summary'], queryFn: getPrivacySummary })
  const { data: rlData } = useQuery({ queryKey: ['privacy-rate-limits'], queryFn: getRateLimits })
  const { data: legalData } = useQuery({ queryKey: ['legal-urls'], queryFn: getLegalUrls, staleTime: Infinity, retry: false })
  const s = sumData?.data || {}
  const rl = rlData?.data || {}
  const legal = legalData?.data || {}
  const deletionScheduled = s.data_deletion_scheduled

  const exportData = async () => {
    setExporting(true)
    try {
      const res = await exportMyData()
      const url = URL.createObjectURL(new Blob([res.data], { type: 'application/zip' }))
      const a = document.createElement('a')
      a.href = url; a.download = 'jobhunt_export.zip'; a.click()
      URL.revokeObjectURL(url)
      toast.success('Export downloaded')
    } catch (e) { toast.error('Export failed') } finally { setExporting(false) }
  }

  const doDelete = async () => {
    setBusy(true)
    try {
      const res = await requestDeletion()
      toast.success(`Account deletion scheduled for ${new Date(res.data.scheduled_at).toLocaleDateString()}`)
      setShowDelete(false); setConfirmText('')
      qc.invalidateQueries({ queryKey: ['privacy-summary'] })
    } catch (e) { toast.error(e.response?.data?.detail || 'Failed') } finally { setBusy(false) }
  }

  const undoDelete = async () => {
    setBusy(true)
    try {
      await cancelDeletion()
      toast.success('Deletion cancelled — your account is safe')
      qc.invalidateQueries({ queryKey: ['privacy-summary'] })
    } catch (e) { toast.error('Failed') } finally { setBusy(false) }
  }

  if (isLoading) return <div className="flex justify-center py-12"><Spinner /></div>

  return (
    <div className="max-w-2xl">
      {/* 1. Data summary */}
      <Card title="What we store about you">
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 text-sm">
          {[['Master CVs', s.master_cvs], ['Domain CVs', s.domain_cvs], ['Jobs', s.jobs],
            ['Tailored CVs', s.tailored_cvs], ['Chat messages', s.chat_messages], ['Usage logs', s.usage_logs]].map(([k, v]) => (
            <div key={k} className="bg-gray-50 rounded-lg px-3 py-2">
              <p className="text-lg font-bold text-gray-900">{v ?? 0}</p>
              <p className="text-xs text-gray-500">{k}</p>
            </div>
          ))}
        </div>
        {s.account_created && <p className="text-xs text-gray-400 mt-3">Account created {new Date(s.account_created).toLocaleDateString()}</p>}
      </Card>

      {/* 2. Export */}
      <Card title="Export your data">
        <p className="text-xs text-gray-500 mb-3">A ZIP with your profile, CVs, jobs, applications, and usage log (JSON + markdown).</p>
        <Button size="sm" loading={exporting} onClick={exportData}>↓ Export my data</Button>
      </Card>

      {/* 3. Legal */}
      <Card title="Legal documents">
        <div className="space-y-1.5 text-sm">
          {[['Privacy Policy', legal.privacy_url], ['Terms of Service', legal.terms_url], ['Cookie Policy', legal.cookies_url]].map(([k, u]) => (
            <div key={k} className="flex items-center justify-between">
              <span className="text-gray-700">{k}</span>
              <a href={u} target="_blank" rel="noreferrer" className="text-emerald-600 hover:underline text-xs font-medium">View →</a>
            </div>
          ))}
        </div>
      </Card>

      {/* 4. Rate limits */}
      <Card title="Your usage limits today">
        <div className="space-y-1.5">
          {Object.entries(rl).map(([action, info]) => (
            <div key={action} className="flex items-center justify-between text-sm">
              <span className="text-gray-600">{RL_LABELS[action] || action}</span>
              <span className="text-gray-500"><strong className="text-gray-800">{info.remaining}</strong> of {info.limit} left</span>
            </div>
          ))}
        </div>
        <p className="text-[11px] text-gray-400 mt-2">Daily limits reset on a rolling 24-hour window.</p>
      </Card>

      {/* 5. Danger zone */}
      <Card title="Danger zone">
        {deletionScheduled ? (
          <div className="bg-red-50 border border-red-200 rounded-lg p-3">
            <p className="text-sm text-red-700 font-medium">Deletion scheduled for {new Date(deletionScheduled).toLocaleDateString()}</p>
            <p className="text-xs text-red-500 mt-1 mb-2">Your data will be permanently purged on this date. You can still cancel.</p>
            <Button size="sm" variant="secondary" loading={busy} onClick={undoDelete}>Cancel deletion</Button>
          </div>
        ) : (
          <div>
            <p className="text-xs text-gray-500 mb-1">Deleting your account will, after a <strong>30-day grace period</strong>:</p>
            <ul className="text-xs text-gray-500 list-disc pl-5 mb-3 space-y-0.5">
              <li>Permanently delete all CVs, jobs, applications, and chat history</li>
              <li>Cancel your subscription and delete your Stripe customer record</li>
              <li>Remove your encrypted API keys</li>
            </ul>
            <Button size="sm" variant="danger" onClick={() => setShowDelete(true)}>Delete my account →</Button>
          </div>
        )}
      </Card>

      {showDelete && (
        <div className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-xl max-w-md w-full p-6">
            <h2 className="text-lg font-semibold text-gray-900">Delete account?</h2>
            <p className="text-sm text-gray-600 mt-2">This schedules permanent deletion in 30 days. Type <strong>DELETE</strong> to confirm.</p>
            <input value={confirmText} onChange={(e) => setConfirmText(e.target.value)} placeholder="DELETE"
              className="mt-3 w-full border border-gray-200 rounded-lg px-3 py-2 text-sm outline-none focus:border-red-400" />
            <div className="flex justify-end gap-2 mt-4">
              <Button size="sm" variant="ghost" onClick={() => { setShowDelete(false); setConfirmText('') }}>Cancel</Button>
              <Button size="sm" variant="danger" loading={busy} disabled={confirmText !== 'DELETE'} onClick={doDelete}>Delete my account</Button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
