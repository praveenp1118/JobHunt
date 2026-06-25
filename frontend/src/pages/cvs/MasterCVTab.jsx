import { useState, useRef } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { formatDistanceToNow, format } from 'date-fns'
import {
  getMasterCV, getMasterCVVersions,
  saveMasterCVText, updateMasterCV,
  uploadMasterCVFile, rollbackMasterCV,
} from '../../api/cvs'
import Button from '../../components/ui/Button'
import Spinner from '../../components/ui/Spinner'
import { toast } from '../../store/toast'

async function downloadPDF(url, filename) {
  const raw = localStorage.getItem('jobhunt-auth')
  let token = ''
  if (raw) { try { token = JSON.parse(raw).state?.token || '' } catch (_) {} }
  const res = await fetch(url, { headers: { Authorization: `Bearer ${token}` } })
  if (!res.ok) { alert('PDF generation failed'); return }
  const blob = await res.blob()
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = filename
  a.click()
}

export default function MasterCVTab() {
  const qc = useQueryClient()
  const fileRef = useRef()

  const [view, setView] = useState('show') // show | edit | versions
  const [editText, setEditText] = useState('')
  const [saving, setSaving] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  const { data: cvData, isLoading } = useQuery({
    queryKey: ['master-cv'],
    queryFn: getMasterCV,
  })

  const { data: versionsData } = useQuery({
    queryKey: ['master-cv-versions'],
    queryFn: getMasterCVVersions,
    enabled: view === 'versions',
  })

  const cv = cvData?.data
  const versions = versionsData?.data || []

  const startEdit = () => {
    setEditText(cv ? cv.content_md : '')
    setError('')
    setView('edit')
  }

  const saveCV = async () => {
    if (!editText.trim()) { setError('CV content cannot be empty'); return }
    setSaving(true)
    setError('')
    try {
      if (cv) {
        await updateMasterCV(editText, 'Inline edit')
      } else {
        await saveMasterCVText(editText, 'Initial upload')
      }
      qc.invalidateQueries({ queryKey: ['master-cv'] })
      qc.invalidateQueries({ queryKey: ['domain-cvs'] })
      setView('show')
      setSuccess('Saved!')
      toast.success('Master CV saved')
      setTimeout(() => setSuccess(''), 3000)
    } catch (e) {
      const msg = e?.response?.data?.detail || e?.message || 'Save failed'
    setError(msg)
    toast.error(msg)
    } finally {
      setSaving(false)
    }
  }

  const uploadFile = async (file) => {
    if (!file) return
    setUploading(true)
    setError('')
    try {
      const res = await uploadMasterCVFile(file)
      qc.invalidateQueries({ queryKey: ['master-cv'] })
      qc.invalidateQueries({ queryKey: ['domain-cvs'] })
      setView('show')
      setSuccess('CV uploaded!')
      const tk = res?.data?.tokens_used
      toast.success(tk ? `✅ CV saved · ⚡ ${tk < 1000 ? tk : (tk / 1000).toFixed(1) + 'K'} · ₹${(res.data.cost_inr || 0).toFixed(2)}` : '✅ CV saved')
      setTimeout(() => setSuccess(''), 3000)
    } catch (e) {
      setError(e?.response?.data?.detail || e?.message || 'Upload failed')
    } finally {
      setUploading(false)
    }
  }

  const rollback = async (version) => {
    try {
      await rollbackMasterCV(version)
      qc.invalidateQueries({ queryKey: ['master-cv'] })
      qc.invalidateQueries({ queryKey: ['domain-cvs'] })
      setView('show')
    } catch (e) {
      setError('Rollback failed')
    }
  }

  if (isLoading) return <div className="flex justify-center py-12"><Spinner /></div>

  return (
    <div>
      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg px-4 py-3 text-sm text-red-600 mb-4">
          {error}
        </div>
      )}
      {success && (
        <div className="bg-emerald-50 border border-emerald-200 rounded-lg px-4 py-3 text-sm text-emerald-700 mb-4">
          ✓ {success}
        </div>
      )}

      {/* ── EDIT VIEW ── */}
      {view === 'edit' && (
        <div className="bg-white rounded-2xl border border-gray-200 overflow-hidden">
          <div className="flex items-center justify-between px-5 py-3 border-b border-gray-100">
            <span className="text-sm font-semibold text-gray-900">
              {cv ? 'Edit master CV' : 'Paste your CV (markdown)'}
            </span>
            <div className="flex gap-2">
              <Button size="sm" variant="ghost" onClick={() => setView('show')}>Cancel</Button>
              <Button size="sm" onClick={saveCV} loading={saving}>Save</Button>
            </div>
          </div>
          <textarea
            value={editText}
            onChange={(e) => setEditText(e.target.value)}
            rows={35}
            autoFocus
            placeholder={`## PRAVEEN PRAKASH\nBengaluru, India | email@example.com\n\n## SUMMARY\nProduct leader...\n\n## EXPERIENCE\n### Company · Role · Dates\n- Achievement\n`}
            className="w-full px-5 py-4 text-sm font-mono text-gray-700 outline-none resize-none border-0"
            spellCheck={false}
          />
          {cv && (
            <div className="px-5 py-3 border-t border-gray-100 bg-amber-50">
              <p className="text-xs text-amber-600">Saving will flag all domain CVs as stale.</p>
            </div>
          )}
        </div>
      )}

      {/* ── VERSIONS VIEW ── */}
      {view === 'versions' && (
        <div className="bg-white rounded-2xl border border-gray-200 overflow-hidden">
          <div className="flex items-center justify-between px-5 py-3 border-b border-gray-100">
            <span className="text-sm font-semibold text-gray-900">Version history</span>
            <Button size="sm" variant="ghost" onClick={() => setView('show')}>Close</Button>
          </div>
          {versions.length === 0 ? (
            <p className="text-sm text-gray-400 text-center py-8">No previous versions</p>
          ) : (
            <div className="divide-y divide-gray-50">
              {versions.map((v) => (
                <div key={v.id} className="flex items-center justify-between px-5 py-3">
                  <div>
                    <span className="text-sm font-medium text-gray-700">v{v.version}</span>
                    {v.change_summary && <span className="text-xs text-gray-400 ml-2">{v.change_summary}</span>}
                    <p className="text-xs text-gray-400 mt-0.5">{format(new Date(v.created_at), 'MMM d, yyyy HH:mm')}</p>
                  </div>
                  <Button size="sm" variant="ghost" onClick={() => rollback(v.version)}>Restore</Button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ── SHOW VIEW (no CV) ── */}
      {view === 'show' && !cv && (
        <div className="bg-white rounded-2xl border border-gray-200 p-12 text-center">
          <div className="w-14 h-14 bg-gray-100 rounded-2xl flex items-center justify-center mx-auto mb-4">
            <svg className="w-7 h-7 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
          </div>
          <h3 className="font-semibold text-gray-900 mb-1">No master CV yet</h3>
          <p className="text-sm text-gray-500 mb-6">Upload your CV — everything else flows from this.</p>
          <div className="flex gap-3 justify-center">
            <Button onClick={startEdit}>Paste markdown</Button>
            <Button variant="secondary" loading={uploading} onClick={() => fileRef.current?.click()}>
              Upload PDF / DOCX
            </Button>
          </div>
          <input
            ref={fileRef}
            type="file"
            accept=".pdf,.docx,.doc,.md,.txt"
            className="hidden"
            onChange={(e) => uploadFile(e.target.files[0])}
          />
        </div>
      )}

      {/* ── SHOW VIEW (has CV) ── */}
      {view === 'show' && cv && (
        <div className="bg-white rounded-2xl border border-gray-200 overflow-hidden">
          <div className="flex items-center justify-between px-5 py-3 border-b border-gray-100">
            <div className="flex items-center gap-3">
              <span className="text-sm font-semibold text-gray-900">Master CV</span>
              <span className="text-xs bg-gray-100 text-gray-500 px-2 py-0.5 rounded-full">v{cv.version}</span>
              <span className="text-xs text-gray-400">
                {cv.word_count} words · {formatDistanceToNow(new Date(cv.updated_at), { addSuffix: true })}
              </span>
            </div>
            <div className="flex items-center gap-2">
              <Button size="sm" variant="ghost" onClick={() => setView('versions')}>History</Button>
              <Button size="sm" variant="ghost" onClick={() => downloadPDF('/api/pdfs/master-cv', 'CV_Master.pdf')}>
                ↓ PDF
              </Button>
              <Button size="sm" variant="secondary" loading={uploading} onClick={() => fileRef.current?.click()}>
                Upload new
              </Button>
              <Button size="sm" onClick={startEdit}>Edit</Button>
            </div>
          </div>
          <input
            ref={fileRef}
            type="file"
            accept=".pdf,.docx,.doc,.md,.txt"
            className="hidden"
            onChange={(e) => uploadFile(e.target.files[0])}
          />
          <pre className="px-6 py-5 text-sm text-gray-700 whitespace-pre-wrap leading-relaxed font-sans max-h-[65vh] overflow-y-auto">
            {cv.content_md}
          </pre>
        </div>
      )}
    </div>
  )
}
