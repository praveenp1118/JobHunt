import { useId } from 'react'
import { TEMPLATE_DEFAULTS } from '../../utils/template'

// ── Tiny, dependency-free markdown → HTML for CV content (#/##/### headings,
//    **bold**, _italic_/*italic*, links, - bullets, --- rules). ──
function esc(s) {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}
function inline(s) {
  let t = esc(s)
  t = t.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
  t = t.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2">$1</a>')
  t = t.replace(/(^|[\s(])_(.+?)_(?=[\s).,;:]|$)/g, '$1<em>$2</em>')
  t = t.replace(/(^|[\s(])\*(?!\s)(.+?)\*(?=[\s).,;:]|$)/g, '$1<em>$2</em>')
  return t
}
function mdToHtml(md) {
  const out = []
  let inList = false
  const closeList = () => { if (inList) { out.push('</ul>'); inList = false } }
  for (const raw of (md || '').split('\n')) {
    const t = raw.trim()
    if (!t) { closeList(); continue }
    if (/^###\s+/.test(t)) { closeList(); out.push(`<h3>${inline(t.replace(/^###\s+/, ''))}</h3>`); continue }
    if (/^##\s+/.test(t)) { closeList(); out.push(`<h2>${inline(t.replace(/^##\s+/, ''))}</h2>`); continue }
    if (/^#\s+/.test(t)) { closeList(); out.push(`<h1>${inline(t.replace(/^#\s+/, ''))}</h1>`); continue }
    if (/^(-{3,}|\*{3,})$/.test(t)) { closeList(); out.push('<hr/>'); continue }
    if (/^[-*]\s+/.test(t)) { if (!inList) { out.push('<ul>'); inList = true } out.push(`<li>${inline(t.replace(/^[-*]\s+/, ''))}</li>`); continue }
    closeList(); out.push(`<p>${inline(t)}</p>`)
  }
  closeList()
  return out.join('\n')
}

// Live, styled preview of real CV markdown using a (merged) template.
export default function CVPreview({ contentMd, template, className = '' }) {
  const uid = useId().replace(/[:]/g, '')
  const cls = `cvp-${uid}`
  const t = { ...TEMPLATE_DEFAULTS, ...(template || {}) }
  const margin = { narrow: '18px', normal: '30px', wide: '44px' }[t.margin_size] || '30px'
  const accent = t.accent_color || '#1a1a1a'
  const headFont = t.heading_font_family || t.font_family
  const bullet = t.bullet_style || '•'

  let bulletCss = ''
  if (bullet === 'none') bulletCss = `.${cls} ul { list-style: none; padding-left: 0; }`
  else if (bullet !== '•') bulletCss = `.${cls} ul { list-style: none; padding-left: 18px; } .${cls} li::before { content: '${bullet} '; margin-left: -16px; color: ${accent}; }`

  const css = `
.${cls} { font-family: '${t.font_family}', Arial, Helvetica, sans-serif; font-size: ${t.font_size}pt; line-height: ${t.line_spacing}; color: #222; padding: ${margin}; background: #fff; }
.${cls} h1 { font-family: '${headFont}', Arial, sans-serif; font-size: ${(t.heading_font_size || 14) + 6}pt; font-weight: 700; color: ${accent}; margin: 0 0 2px; letter-spacing: -0.3px; }
.${cls} h2 { font-family: '${headFont}', Arial, sans-serif; font-size: ${t.heading_font_size}pt; font-weight: ${t.heading_bold ? 700 : 400}; color: ${accent}; text-transform: uppercase; letter-spacing: 0.6px; margin: 14px 0 5px; padding-bottom: 3px; border-bottom: 1.5px solid ${accent}33; }
.${cls} h3 { font-family: '${headFont}', Arial, sans-serif; font-size: ${(t.font_size || 11) + 0.5}pt; font-weight: 600; color: #1a1a1a; margin: 8px 0 1px; }
.${cls} p { margin: 4px 0; }
.${cls} ul { margin: 3px 0 6px; padding-left: 18px; }
.${cls} li { margin-bottom: 2px; }
.${cls} hr { border: none; border-top: 1px solid #eee; margin: 8px 0; }
.${cls} strong { font-weight: 600; color: #1a1a1a; }
.${cls} a { color: ${accent}; text-decoration: none; }
${bulletCss}
`
  return (
    <div className={className}>
      <style>{css}</style>
      <div className={cls} dangerouslySetInnerHTML={{ __html: mdToHtml(contentMd) }} />
    </div>
  )
}
