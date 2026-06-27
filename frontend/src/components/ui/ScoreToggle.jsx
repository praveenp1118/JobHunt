// Compact segmented control: ATS / Pursuit / Combined.
const OPTIONS = [
  { value: 'ats', label: 'ATS' },
  { value: 'pursuit', label: 'Pursuit' },
  { value: 'combined', label: 'Combined' },
]

export default function ScoreToggle({ value = 'pursuit', onChange, size = 'md', options = OPTIONS }) {
  const pad = size === 'sm' ? 'px-2 py-0.5 text-[11px]' : 'px-2.5 py-1 text-xs'
  return (
    <div className="inline-flex items-center gap-0.5 rounded-lg bg-slate-100 p-0.5">
      {options.map((o) => (
        <button key={o.value} onClick={() => onChange?.(o.value)}
          className={`rounded-md font-medium transition-colors ${pad} ${
            value === o.value ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-700'
          }`}>
          {o.label}
        </button>
      ))}
    </div>
  )
}
