import { clsx } from 'clsx'

const STATUS_CONFIG = {
  new:            { label: 'New',            classes: 'bg-gray-100 text-gray-600' },
  bookmarked:     { label: 'Bookmarked',     classes: 'bg-blue-50 text-blue-600' },
  applied:        { label: 'Applied',        classes: 'bg-indigo-50 text-indigo-600' },
  screening:      { label: 'Screening',      classes: 'bg-yellow-50 text-yellow-700' },
  interview_r1:   { label: 'Interview R1',   classes: 'bg-amber-50 text-amber-700' },
  interview_r2:   { label: 'Interview R2',   classes: 'bg-amber-50 text-amber-700' },
  offer_received: { label: 'Offer',          classes: 'bg-emerald-50 text-emerald-700' },
  offer_accepted: { label: 'Accepted',       classes: 'bg-emerald-100 text-emerald-800' },
  offer_declined: { label: 'Declined',       classes: 'bg-gray-100 text-gray-600' },
  rejected:       { label: 'Rejected',       classes: 'bg-red-50 text-red-600' },
  ghosted:        { label: 'Ghosted',        classes: 'bg-gray-100 text-gray-500' },
  withdrawn:      { label: 'Withdrawn',      classes: 'bg-gray-100 text-gray-500' },
  not_interested: { label: 'Not Interested', classes: 'bg-gray-100 text-gray-500' },
}

const SOURCE_CONFIG = {
  manual:        { label: 'Manual',   classes: 'bg-slate-100 text-slate-600' },
  url:           { label: 'URL',      classes: 'bg-slate-100 text-slate-600' },
  file:          { label: 'File',     classes: 'bg-slate-100 text-slate-600' },
  gmail:         { label: 'Gmail',    classes: 'bg-blue-50 text-blue-600' },
  apify:         { label: 'Apify',    classes: 'bg-purple-50 text-purple-600' },
  rss:           { label: 'RSS',      classes: 'bg-orange-50 text-orange-600' },
  gmail_alert:   { label: '📧 Alert', classes: 'bg-blue-50 text-blue-600' },
  email_to_jobhunt: { label: '📥 Email', classes: 'bg-blue-50 text-blue-700' },
}

const MARKET_CONFIG = {
  NL:     { label: '🇳🇱 NL',    classes: 'bg-blue-50 text-blue-700' },
  EU:     { label: '🇪🇺 EU',    classes: 'bg-blue-50 text-blue-700' },
  Dubai:  { label: '🇦🇪 Dubai', classes: 'bg-yellow-50 text-yellow-700' },
  SG:     { label: '🇸🇬 SG',    classes: 'bg-red-50 text-red-700' },
  IN:     { label: '🇮🇳 IN',    classes: 'bg-orange-50 text-orange-700' },
}

export function StatusBadge({ status, className = '' }) {
  const config = STATUS_CONFIG[status] || { label: status, classes: 'bg-gray-100 text-gray-600' }
  return (
    <span className={clsx('inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium', config.classes, className)}>
      {config.label}
    </span>
  )
}

export function SourceBadge({ source, className = '' }) {
  const config = SOURCE_CONFIG[source] || { label: source, classes: 'bg-gray-100 text-gray-600' }
  return (
    <span className={clsx('inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium', config.classes, className)}>
      {config.label}
    </span>
  )
}

export function MarketBadge({ market, className = '' }) {
  const config = MARKET_CONFIG[market] || { label: market, classes: 'bg-gray-100 text-gray-600' }
  return (
    <span className={clsx('inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium', config.classes, className)}>
      {config.label}
    </span>
  )
}

export default StatusBadge
