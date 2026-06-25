import { useState, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getCVTemplate, updateCVTemplate, getFonts } from '../../api/templates'
import Button from '../../components/ui/Button'
import Spinner from '../../components/ui/Spinner'
import { toast } from '../../store/toast'

const DEFAULTS = {
  font_family: 'Calibri', font_size: 11, heading_font_family: 'Calibri', heading_font_size: 14,
  heading_bold: true, margin_size: 'normal', line_spacing: 1.15, bullet_style: '•', accent_color: '#1a1a1a',
  max_pages: 2, overflow_action: 'warn',
  never_modify_sections: ['EDUCATION', 'CERTIFICATIONS'],
  section_order: ['SUMMARY', 'EXPERIENCE', 'EDUCATION', 'CERTIFICATIONS'],
}
const NEVER_OPTIONS = ['SUMMARY', 'EXPERIENCE', 'EDUCATION', 'CERTIFICATIONS', 'SKILLS', 'CONTACT']

function Field({ label, children }) {
  return (
    <div className="flex items-center justify-between gap-3 py-1.5">
      <label className="text-sm text-gray-600 w-36 shrink-0">{label}</label>
      <div className="flex-1 flex justify-end">{children}</div>
    </div>
  )
}
function Radio({ value, current, onChange, children }) {
  return (
    <button onClick={() => onChange(value)}
      className={`text-xs px-2.5 py-1 rounded-md border ${current === value ? 'bg-emerald-500 text-white border-emerald-500' : 'bg-white text-gray-600 border-gray-200 hover:bg-gray-50'}`}>
      {children}
    </button>
  )
}

export default function TemplateTab() {
  const [tpl, setTpl] = useState(null)
  const [saving, setSaving] = useState(false)
  const { data: tplData, isLoading } = useQuery({ queryKey: ['cv-template'], queryFn: getCVTemplate })
  const { data: fontsData } = useQuery({ queryKey: ['cv-fonts'], queryFn: getFonts })
  const fonts = fontsData?.data?.fonts || []

  useEffect(() => { if (tplData?.data) setTpl(tplData.data) }, [tplData])

  if (isLoading || !tpl) return <div className="flex justify-center py-12"><Spinner /></div>

  const set = (k, v) => setTpl((p) => ({ ...p, [k]: v }))
  const maxWords = tpl.max_pages * 300

  const toggleNever = (s) => {
    const cur = tpl.never_modify_sections || []
    set('never_modify_sections', cur.includes(s) ? cur.filter((x) => x !== s) : [...cur, s])
  }
  const moveSection = (i, dir) => {
    const arr = [...(tpl.section_order || [])]
    const j = i + dir
    if (j < 0 || j >= arr.length) return
    ;[arr[i], arr[j]] = [arr[j], arr[i]]
    set('section_order', arr)
  }

  const save = async () => {
    setSaving(true)
    try {
      const { created_at, updated_at, max_words, ...payload } = tpl
      const res = await updateCVTemplate(payload)
      setTpl(res.data)
      toast.success('Template saved')
    } catch (e) { toast.error(e.response?.data?.detail || 'Save failed') }
    finally { setSaving(false) }
  }
  const reset = () => { setTpl((p) => ({ ...DEFAULTS })); toast.success('Reset to defaults — click Save to apply') }

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      {/* LEFT — form */}
      <div className="space-y-5">
        <Section title="Look & feel">
          <Field label="Font family">
            <select value={tpl.font_family} onChange={(e) => set('font_family', e.target.value)} className="text-xs border border-gray-200 rounded-md px-2 py-1 bg-white">
              {fonts.map((f) => <option key={f.value} value={f.value}>{f.label}</option>)}
            </select>
          </Field>
          <Field label="Font size">
            <div className="flex gap-1">{[10, 11, 12].map((s) => <Radio key={s} value={s} current={tpl.font_size} onChange={(v) => set('font_size', v)}>{s}pt</Radio>)}</div>
          </Field>
          <Field label="Heading font">
            <select value={tpl.heading_font_family} onChange={(e) => set('heading_font_family', e.target.value)} className="text-xs border border-gray-200 rounded-md px-2 py-1 bg-white">
              {fonts.map((f) => <option key={f.value} value={f.value}>{f.label}</option>)}
            </select>
          </Field>
          <Field label="Heading size">
            <div className="flex gap-1">{[12, 14, 16].map((s) => <Radio key={s} value={s} current={tpl.heading_font_size} onChange={(v) => set('heading_font_size', v)}>{s}pt</Radio>)}</div>
          </Field>
          <Field label="Heading bold">
            <button onClick={() => set('heading_bold', !tpl.heading_bold)} className={`relative w-9 h-5 rounded-full transition-colors ${tpl.heading_bold ? 'bg-emerald-500' : 'bg-gray-300'}`}>
              <span className={`absolute top-0.5 left-0.5 w-4 h-4 bg-white rounded-full transition-transform ${tpl.heading_bold ? 'translate-x-4' : ''}`} />
            </button>
          </Field>
          <Field label="Margins">
            <div className="flex gap-1">{['narrow', 'normal', 'wide'].map((m) => <Radio key={m} value={m} current={tpl.margin_size} onChange={(v) => set('margin_size', v)}>{m}</Radio>)}</div>
          </Field>
          <Field label="Line spacing">
            <div className="flex gap-1">{[1.0, 1.15, 1.5].map((s) => <Radio key={s} value={s} current={tpl.line_spacing} onChange={(v) => set('line_spacing', v)}>{s}</Radio>)}</div>
          </Field>
          <Field label="Bullet style">
            <div className="flex gap-1">{['•', '–', '▪', 'none'].map((b) => <Radio key={b} value={b} current={tpl.bullet_style} onChange={(v) => set('bullet_style', v)}>{b}</Radio>)}</div>
          </Field>
          <Field label="Accent color">
            <div className="flex items-center gap-2">
              <input type="color" value={tpl.accent_color} onChange={(e) => set('accent_color', e.target.value)} className="w-7 h-7 rounded border border-gray-200" />
              <input type="text" value={tpl.accent_color} onChange={(e) => set('accent_color', e.target.value)} className="text-xs border border-gray-200 rounded-md px-2 py-1 w-20" />
            </div>
          </Field>
        </Section>

        <Section title="Page rules">
          <Field label="Max pages">
            <div className="flex gap-1">{[1, 2, 3].map((p) => <Radio key={p} value={p} current={tpl.max_pages} onChange={(v) => set('max_pages', v)}>{p}</Radio>)}</div>
          </Field>
          <Field label="Max words">
            <span className="text-xs text-gray-500">~{maxWords} words for {tpl.max_pages} page{tpl.max_pages > 1 ? 's' : ''}</span>
          </Field>
          <Field label="If CV exceeds limit">
            <div className="flex gap-1">
              <Radio value="warn" current={tpl.overflow_action} onChange={(v) => set('overflow_action', v)}>Warn me</Radio>
              <Radio value="auto_trim" current={tpl.overflow_action} onChange={(v) => set('overflow_action', v)}>Auto-trim</Radio>
            </div>
          </Field>
        </Section>

        <Section title="Content rules">
          <p className="text-xs text-gray-500 mb-1">Never modify these sections (the tailor agent will leave them untouched):</p>
          <div className="flex flex-wrap gap-1.5 mb-3">
            {NEVER_OPTIONS.map((s) => (
              <button key={s} onClick={() => toggleNever(s)}
                className={`text-[11px] px-2 py-0.5 rounded-full border ${(tpl.never_modify_sections || []).includes(s) ? 'bg-amber-100 text-amber-800 border-amber-300' : 'bg-white text-gray-500 border-gray-200'}`}>
                {(tpl.never_modify_sections || []).includes(s) ? '🔒 ' : ''}{s}
              </button>
            ))}
          </div>
          <p className="text-xs text-gray-500 mb-1">Section order (use ↑ ↓ to reorder):</p>
          <div className="space-y-1">
            {(tpl.section_order || []).map((s, i) => (
              <div key={s} className="flex items-center justify-between bg-gray-50 rounded-md px-2.5 py-1.5">
                <span className="text-xs text-gray-700">{s}</span>
                <div className="flex gap-1">
                  <button onClick={() => moveSection(i, -1)} disabled={i === 0} className="text-xs text-gray-400 hover:text-gray-700 disabled:opacity-30">↑</button>
                  <button onClick={() => moveSection(i, 1)} disabled={i === tpl.section_order.length - 1} className="text-xs text-gray-400 hover:text-gray-700 disabled:opacity-30">↓</button>
                </div>
              </div>
            ))}
          </div>
        </Section>

        <div className="flex gap-2">
          <Button loading={saving} onClick={save}>Save template</Button>
          <Button variant="secondary" onClick={reset}>Reset to defaults</Button>
        </div>
      </div>

      {/* RIGHT — live preview */}
      <div className="lg:sticky lg:top-4 self-start">
        <p className="text-xs font-medium text-gray-500 mb-2">Live preview</p>
        <Preview tpl={tpl} />
      </div>
    </div>
  )
}

function Section({ title, children }) {
  return (
    <div className="bg-white rounded-2xl border border-gray-200 p-5">
      <h3 className="text-sm font-semibold text-gray-900 mb-2">{title}</h3>
      {children}
    </div>
  )
}

function Preview({ tpl }) {
  const marginPad = { narrow: '16px', normal: '28px', wide: '40px' }[tpl.margin_size] || '28px'
  const bullet = tpl.bullet_style === 'none' ? '' : tpl.bullet_style
  return (
    <div className="bg-white border border-gray-200 rounded-lg shadow-sm overflow-hidden" style={{ aspectRatio: '0.72' }}>
      <div style={{ padding: marginPad, fontFamily: tpl.font_family, fontSize: `${tpl.font_size}px`, lineHeight: tpl.line_spacing, color: '#222' }}>
        <div style={{ fontFamily: tpl.heading_font_family, fontSize: `${tpl.heading_font_size + 6}px`, fontWeight: 700, color: tpl.accent_color }}>John Doe</div>
        <div style={{ fontSize: `${tpl.font_size}px`, color: '#666', fontStyle: 'italic' }}>Product Leader · Amsterdam</div>
        <hr style={{ margin: '8px 0', borderColor: '#eee' }} />
        {['SUMMARY', 'EXPERIENCE'].map((sec) => (
          <div key={sec} style={{ marginTop: 10 }}>
            <div style={{ fontFamily: tpl.heading_font_family, fontSize: `${tpl.heading_font_size}px`, fontWeight: tpl.heading_bold ? 700 : 400, color: tpl.accent_color, textTransform: 'uppercase', letterSpacing: 0.5 }}>{sec}</div>
            <p style={{ margin: '4px 0' }}>Sample line in the body font showing how paragraph text renders.</p>
            {['First achievement with a 42% metric', 'Second bullet, kept to 1–2 lines'].map((b, i) => (
              <div key={i} style={{ display: 'flex', gap: 6 }}>
                <span style={{ color: tpl.accent_color }}>{bullet}</span><span>{b}</span>
              </div>
            ))}
          </div>
        ))}
        <div style={{ marginTop: 10, fontSize: '10px', color: '#999' }}>~{tpl.max_pages * 300} word budget · {tpl.max_pages} page{tpl.max_pages > 1 ? 's' : ''}</div>
      </div>
    </div>
  )
}
