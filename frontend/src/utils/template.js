// Mirror of backend get_effective_template — merge a global CV template with a
// per-domain override (override wins where not null).
export const TEMPLATE_DEFAULTS = {
  font_family: 'Calibri', font_size: 11, heading_font_family: 'Calibri', heading_font_size: 14,
  heading_bold: true, margin_size: 'normal', line_spacing: 1.15, bullet_style: '•', accent_color: '#1a1a1a',
  max_pages: 2, overflow_action: 'warn',
  never_modify_sections: ['EDUCATION', 'CERTIFICATIONS'],
  section_order: ['SUMMARY', 'EXPERIENCE', 'EDUCATION', 'CERTIFICATIONS'],
  max_words: 600,
}

const OVERRIDE_FIELDS = ['font_family', 'font_size', 'max_pages', 'overflow_action',
  'never_modify_sections', 'section_order', 'max_words']

export function mergeTemplate(global, override) {
  const base = { ...TEMPLATE_DEFAULTS, ...(global || {}) }
  if (override) {
    OVERRIDE_FIELDS.forEach((k) => { if (override[k] != null) base[k] = override[k] })
  }
  return base
}
