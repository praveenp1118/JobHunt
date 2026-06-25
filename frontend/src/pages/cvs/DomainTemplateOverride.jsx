import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getDomainOverride, updateDomainOverride, deleteDomainOverride, getFonts, getCVTemplate } from '../../api/templates'
import Button from '../../components/ui/Button'
import CVPreview from '../../components/cv/CVPreview'
import { mergeTemplate } from '../../utils/template'
import { toast } from '../../store/toast'

// Collapsible per-domain-CV template override (+ live preview modal). null fields = "use global".
export default function DomainTemplateOverride({ domainCvId, label, contentMd }) {
  const [open, setOpen] = useState(false)
  const [ov, setOv] = useState(null)
  const [saving, setSaving] = useState(false)
  const [previewOpen, setPreviewOpen] = useState(false)
  const [effective, setEffective] = useState(null)
  const { data: fontsData } = useQuery({ queryKey: ['cv-fonts'], queryFn: getFonts })
  const { data: globalTpl } = useQuery({ queryKey: ['cv-template'], queryFn: getCVTemplate })
  const fonts = fontsData?.data?.fonts || []

  const openPreview = async () => {
    let override = ov
    if (override === null) {
      try { const r = await getDomainOverride(domainCvId); override = r.data.override || {} } catch { override = {} }
    }
    setEffective(mergeTemplate(globalTpl?.data, override))
    setPreviewOpen(true)
  }

  const load = async () => {
    if (!open && ov === null) {
      try { const r = await getDomainOverride(domainCvId); setOv(r.data.override || {}) }
      catch { setOv({}) }
    }
    setOpen((o) => !o)
  }
  const set = (k, v) => setOv((p) => ({ ...p, [k]: v }))

  const save = async () => {
    setSaving(true)
    try {
      // Only send non-null fields (null = use global).
      const payload = {}
      ;['max_pages', 'font_family', 'never_modify_sections'].forEach((k) => {
        if (ov[k] != null && ov[k] !== '') payload[k] = ov[k]
      })
      await updateDomainOverride(domainCvId, payload)
      toast.success('Overrides saved')
    } catch (e) { toast.error(e.response?.data?.detail || 'Save failed') }
    finally { setSaving(false) }
  }
  const remove = async () => {
    setSaving(true)
    try { await deleteDomainOverride(domainCvId); setOv({}); toast.success('Reverted to global template') }
    catch (e) { toast.error('Failed') } finally { setSaving(false) }
  }

  return (
    <div className="mt-3 border-t border-gray-100 pt-2">
      <div className="flex items-center gap-4">
        <button onClick={load} className="text-xs text-gray-500 hover:text-gray-700 font-medium">
          {open ? '▾' : '▸'} Template overrides
        </button>
        <button onClick={openPreview} className="text-xs text-emerald-600 hover:text-emerald-700 font-medium">
          👁 Live preview
        </button>
      </div>
      {open && ov && (
        <div className="mt-2 bg-gray-50 rounded-lg p-3 space-y-2">
          <p className="text-[11px] text-gray-400">Overrides for {label} — leave on “Use global” to inherit.</p>
          <Row label="Max pages">
            <select value={ov.max_pages ?? ''} onChange={(e) => set('max_pages', e.target.value ? Number(e.target.value) : null)}
              className="text-xs border border-gray-200 rounded-md px-2 py-1 bg-white">
              <option value="">Use global</option>{[1, 2, 3].map((p) => <option key={p} value={p}>{p}</option>)}
            </select>
          </Row>
          <Row label="Font">
            <select value={ov.font_family ?? ''} onChange={(e) => set('font_family', e.target.value || null)}
              className="text-xs border border-gray-200 rounded-md px-2 py-1 bg-white">
              <option value="">Use global</option>{fonts.map((f) => <option key={f.value} value={f.value}>{f.value}</option>)}
            </select>
          </Row>
          <Row label="Never modify">
            <div className="flex flex-wrap gap-1 justify-end">
              {ov.never_modify_sections == null ? (
                <button onClick={() => set('never_modify_sections', ['EDUCATION', 'CERTIFICATIONS'])}
                  className="text-[11px] px-2 py-0.5 rounded-full border bg-white text-gray-500 border-gray-200">Use global · customise</button>
              ) : (
                <>
                  {['SUMMARY', 'EXPERIENCE', 'EDUCATION', 'CERTIFICATIONS', 'SKILLS'].map((s) => {
                    const on = ov.never_modify_sections.includes(s)
                    return <button key={s} onClick={() => set('never_modify_sections', on ? ov.never_modify_sections.filter((x) => x !== s) : [...ov.never_modify_sections, s])}
                      className={`text-[11px] px-2 py-0.5 rounded-full border ${on ? 'bg-amber-100 text-amber-800 border-amber-300' : 'bg-white text-gray-500 border-gray-200'}`}>{s}</button>
                  })}
                  <button onClick={() => set('never_modify_sections', null)} className="text-[11px] text-gray-400 px-1">↩ global</button>
                </>
              )}
            </div>
          </Row>
          <div className="flex gap-2 pt-1">
            <Button size="sm" loading={saving} onClick={save}>Save overrides</Button>
            <Button size="sm" variant="ghost" onClick={remove}>Remove overrides</Button>
          </div>
        </div>
      )}

      {/* Live preview modal — rendered domain CV with the effective (global + override) template */}
      {previewOpen && (
        <div className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4" onClick={() => setPreviewOpen(false)}>
          <div className="bg-white rounded-2xl shadow-xl max-w-2xl w-full max-h-[88vh] flex flex-col" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between px-5 py-3 border-b border-gray-100">
              <div>
                <p className="text-sm font-semibold text-gray-900">Live preview — {label}</p>
                <p className="text-[11px] text-gray-400">Effective template: {effective?.font_family} · {effective?.max_pages} page{effective?.max_pages > 1 ? 's' : ''} · {ov && Object.values(ov).some((v) => v != null) ? 'with overrides' : 'inheriting global'}</p>
              </div>
              <button onClick={() => setPreviewOpen(false)} className="text-gray-400 hover:text-gray-600 text-xl leading-none">×</button>
            </div>
            <div className="overflow-y-auto p-5 bg-gray-50">
              {contentMd ? (
                <div className="bg-white rounded-lg shadow-sm border border-gray-100 mx-auto" style={{ maxWidth: 640 }}>
                  <CVPreview contentMd={contentMd} template={effective} />
                </div>
              ) : (
                <p className="text-sm text-gray-400 text-center py-8">This domain CV has no content yet — apply changes first.</p>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function Row({ label, children }) {
  return (
    <div className="flex items-center justify-between gap-2">
      <span className="text-xs text-gray-600">{label}</span>
      {children}
    </div>
  )
}
