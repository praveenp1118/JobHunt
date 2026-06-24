import { clsx } from 'clsx'

function getScoreColor(score) {
  if (score === null || score === undefined) return 'bg-gray-100 text-gray-400'
  if (score >= 85) return 'bg-emerald-100 text-emerald-700'
  if (score >= 70) return 'bg-yellow-100 text-yellow-700'
  if (score >= 55) return 'bg-orange-100 text-orange-700'
  return 'bg-red-100 text-red-600'
}

function getS3Color(score) {
  if (score === null || score === undefined) return 'bg-gray-100 text-gray-400'
  if (score >= 90) return 'bg-emerald-100 text-emerald-700'
  if (score >= 85) return 'bg-yellow-100 text-yellow-700'
  return 'bg-red-100 text-red-600'
}

export function ScorePill({ score, label, type = 'fit', className = '' }) {
  const colorClass = type === 's3' ? getS3Color(score) : getScoreColor(score)
  const display = score !== null && score !== undefined ? Math.round(score) : 'NA'

  return (
    <div className={clsx('inline-flex flex-col items-center', className)}>
      {label && <span className="text-[10px] text-gray-400 font-medium mb-0.5">{label}</span>}
      <span className={clsx('px-2 py-0.5 rounded-full text-xs font-semibold tabular-nums', colorClass)}>
        {display === 'NA' ? 'NA' : `${display}`}
      </span>
    </div>
  )
}

export function ThreeScores({ s1, s2, s3Master }) {
  return (
    <div className="flex items-center gap-1.5">
      <ScorePill score={s1} label="B" />
      <ScorePill score={s2} label="T" />
      <ScorePill score={s3Master} label="F" type="s3" />
    </div>
  )
}

export default ScorePill
