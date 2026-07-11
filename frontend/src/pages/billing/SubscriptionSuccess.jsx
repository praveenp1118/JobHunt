import { useEffect, useState } from 'react'
import { useSearchParams, useNavigate } from 'react-router-dom'
import { verifySession } from '../../api/billing'
import Spinner from '../../components/ui/Spinner'
import Button from '../../components/ui/Button'

export default function SubscriptionSuccess() {
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const [state, setState] = useState('loading') // loading | success | error
  const sessionId = params.get('session_id')

  useEffect(() => {
    if (!sessionId) {
      setState('error')
      return
    }
    verifySession(sessionId)
      .then((r) => setState(r.data?.success ? 'success' : 'error'))
      .catch(() => setState('error'))
  }, [sessionId])

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 p-6">
      <div className="bg-white rounded-2xl border border-gray-200 p-10 max-w-md w-full text-center">
        {state === 'loading' && (
          <>
            <div className="flex justify-center"><Spinner /></div>
            <p className="text-sm text-gray-500 mt-4">Confirming your subscription…</p>
          </>
        )}
        {state === 'success' && (
          <>
            <div className="text-5xl mb-3">✅</div>
            <h1 className="text-xl font-semibold text-gray-900">You're subscribed to AIJobsHunt Pro!</h1>
            <p className="text-sm text-gray-500 mt-2">Your job search just got smarter.</p>
            <Button className="mt-6" onClick={() => navigate('/dashboard')}>Go to Dashboard →</Button>
          </>
        )}
        {state === 'error' && (
          <>
            <div className="text-5xl mb-3">⚠️</div>
            <h1 className="text-lg font-semibold text-gray-900">Something went wrong</h1>
            <p className="text-sm text-gray-500 mt-2">
              We couldn't confirm your payment. If you were charged, contact support — or check your plan in Settings.
            </p>
            <Button variant="secondary" className="mt-6" onClick={() => navigate('/settings#plan')}>Go to Settings</Button>
          </>
        )}
      </div>
    </div>
  )
}
