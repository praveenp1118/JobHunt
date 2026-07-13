import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { addFullJd, fetchJobJd } from '../../api/jobs'
import { toast } from '../../store/toast'
import Button from '../ui/Button'

// Shared paste-to-enrich affordance for partial-JD jobs (Gmail-alert / LinkedIn-gated).
// LinkedIn serves a login wall to bots and our Apify actor is a search scraper (can't
// fetch a single job by URL without burning credit), so the reliable, zero-cost path is
// manual paste: user opens the posting (already logged in), copies the full JD, pastes it.
// POST /jobs/{id}/add-full-jd → rescore_partial_job_from_text sets has_partial_jd=false.
// The optional "Try auto-fetch (free)" button calls POST /jobs/{id}/fetch-jd (web_fetch
// only, NO Apify) — helps public-ATS partials, predictably fails on LinkedIn.
export default function PartialJdPanel({ job, onEnriched, showAutoFetch = true, className = '' }) {
  const qc = useQueryClient()
  const [pastedJd, setPastedJd] = useState('')
  const [savingJd, setSavingJd] = useState(false)
  const [fetchingJd, setFetchingJd] = useState(false)
  const jobId = job.id

  // Background rescore lands a few seconds later — refresh the job + tracker as it does.
  const poll = (delays) =>
    delays.forEach((ms) =>
      setTimeout(() => {
        qc.invalidateQueries({ queryKey: ['job', jobId] })
        qc.invalidateQueries({ queryKey: ['jobs'] })
        onEnriched?.()
      }, ms)
    )

  const handleAddFullJd = async () => {
    if (pastedJd.trim().length < 100) {
      toast.error('Please paste the full job description (at least 100 characters)')
      return
    }
    setSavingJd(true)
    try {
      await addFullJd(jobId, pastedJd.trim())
      toast.success('JD saved — scoring in the background; tailoring unlocks shortly')
      setPastedJd('')
      poll([6000, 14000, 24000])
      setTimeout(() => setSavingJd(false), 25000)
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Could not save the JD')
      setSavingJd(false)
    }
  }

  const handleFetchJd = async () => {
    setFetchingJd(true)
    try {
      await fetchJobJd(jobId)
      toast.success('Trying to auto-fetch the full JD — scores update if it lands')
      poll([8000, 16000, 26000])
      setTimeout(() => setFetchingJd(false), 27000)
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Could not fetch the full JD')
      setFetchingJd(false)
    }
  }

  return (
    <div className={className}>
      {job.portal_url && (
        <a href={job.portal_url} target="_blank" rel="noreferrer"
           className="inline-flex items-center gap-1 text-xs font-medium text-emerald-600 hover:text-emerald-700">
          Open job posting ↗
        </a>
      )}
      <div className="mt-3">
        <label className="text-xs font-medium text-gray-600">Paste the full JD here</label>
        <textarea
          value={pastedJd}
          onChange={(e) => setPastedJd(e.target.value)}
          placeholder="Open the posting, copy the full job description, and paste it here. We'll score it (S1 + best domain fit) and unlock tailoring."
          rows={6}
          className="mt-1 w-full text-xs border border-gray-200 rounded-lg px-3 py-2 outline-none focus:border-emerald-400 resize-y"
        />
        <div className="mt-2 flex items-center gap-2">
          <Button size="sm" loading={savingJd} disabled={pastedJd.trim().length < 100} onClick={handleAddFullJd}>
            Save JD + tailor →
          </Button>
          {showAutoFetch && job.portal_url && (
            <Button size="sm" variant="secondary" loading={fetchingJd} onClick={handleFetchJd}>
              Try auto-fetch (free)
            </Button>
          )}
        </div>
        {showAutoFetch && (
          <p className="mt-1.5 text-[11px] text-gray-400">
            Auto-fetch works for some sites; LinkedIn needs manual paste (it requires a login).
          </p>
        )}
      </div>
    </div>
  )
}
