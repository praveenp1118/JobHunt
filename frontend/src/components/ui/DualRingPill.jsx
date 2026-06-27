import { useState } from 'react'
import ScoreTooltip from './ScoreTooltip'

// Ring (filled-arc) colour by score band.
function ringColor(s) {
  if (s == null) return '#cbd5e1'
  if (s >= 90) return '#10b981'
  if (s >= 80) return '#34d399'
  if (s >= 70) return '#a3e635'
  if (s >= 65) return '#fbbf24'
  if (s >= 55) return '#f97316'
  return '#ef4444'
}
// Track (background-arc) colour — same hue, very light.
function trackColor(s) {
  if (s == null) return '#e5e7eb'
  if (s >= 80) return '#d1fae5'
  if (s >= 70) return '#ecfccb'
  if (s >= 65) return '#fef3c7'
  if (s >= 55) return '#ffedd5'
  return '#fee2e2'
}

const SIZES = { sm: 36, md: 40, lg: 52 }

function Arc({ cx, cy, r, score, color, track, sw }) {
  const c = 2 * Math.PI * r
  return (
    <>
      <circle cx={cx} cy={cy} r={r} fill="none" stroke={track} strokeWidth={sw} />
      {score != null && (
        <circle cx={cx} cy={cy} r={r} fill="none" stroke={color} strokeWidth={sw}
          strokeLinecap="round" strokeDasharray={c}
          strokeDashoffset={c * (1 - Math.max(0, Math.min(100, score)) / 100)}
          transform={`rotate(-90 ${cx} ${cy})`} />
      )}
    </>
  )
}

/**
 * Dual-ring score pill: outer ring = ATS, inner ring = Pursuit.
 * The centre number follows `defaultView` (ats | pursuit | combined).
 */
export default function DualRingPill({
  atsScore = null, pursuitScore = null, defaultView = 'pursuit',
  size = 'md', showTooltip = true, tooltipData = null, scoreLabel = null, style,
}) {
  const [hover, setHover] = useState(false)
  const px = SIZES[size] || SIZES.md
  const c = px / 2
  const outerR = c - 3
  const innerR = c - 9

  const shown = defaultView === 'ats' ? atsScore
    : defaultView === 'combined'
      ? (atsScore != null && pursuitScore != null ? Math.round(atsScore * 0.4 + pursuitScore * 0.6) : null)
      : pursuitScore
  const numColor = shown == null ? '#94a3b8' : '#0f172a'

  return (
    <span className="relative inline-flex flex-col items-center" style={style}
      onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)}>
      <svg width={px} height={px} viewBox={`0 0 ${px} ${px}`} className="block">
        <Arc cx={c} cy={c} r={outerR} score={atsScore} color={ringColor(atsScore)} track={trackColor(atsScore)} sw={3} />
        <circle cx={c} cy={c} r={innerR - 2.5} fill={trackColor(pursuitScore)} opacity="0.5" />
        <Arc cx={c} cy={c} r={innerR} score={pursuitScore} color={ringColor(pursuitScore)} track="transparent" sw={2.5} />
        <text x={c} y={c} textAnchor="middle" dominantBaseline="central"
          style={{ fontSize: px * 0.3, fontWeight: 700, fill: numColor }}>
          {shown == null ? '—' : Math.round(shown)}
        </text>
      </svg>
      {scoreLabel && <span className="text-[9px] text-gray-400 leading-none mt-0.5 whitespace-nowrap">{scoreLabel}</span>}
      {showTooltip && hover && tooltipData && (
        <ScoreTooltip {...tooltipData} ats={atsScore} pursuit={pursuitScore} />
      )}
    </span>
  )
}
