import { useState } from 'react'
import { Outlet, useNavigate, useLocation } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { format } from 'date-fns'
import Sidebar from './Sidebar'
import { getJobs } from '../../api/jobs'
import { getSubscription } from '../../api/billing'
import { getLegalUrls, recordConsent } from '../../api/legal'
import useAuthStore from '../../store/auth'

export default function AppLayout() {
  const navigate = useNavigate()
  const location = useLocation()
  const user = useAuthStore((s) => s.user)
  const updateUser = useAuthStore((s) => s.updateUser)
  const [consenting, setConsenting] = useState(false)

  const { data: legalData } = useQuery({ queryKey: ['legal-urls'], queryFn: getLegalUrls, staleTime: Infinity, retry: false })
  const legal = legalData?.data || {}

  const needsConsent = !!user && !user.gdpr_consent_at
  const agree = async () => {
    setConsenting(true)
    try {
      const res = await recordConsent()
      updateUser({ gdpr_consent_at: res.data.gdpr_consent_at })
    } catch (_) { /* non-blocking */ } finally { setConsenting(false) }
  }

  const { data: hitlData } = useQuery({
    queryKey: ['hitl-count'],
    queryFn: () => getJobs({ needs_hitl: true, limit: 1 }),
    refetchInterval: 60000,
    retry: false,
  })
  const hitlCount = hitlData?.data?.total_count || 0

  const { data: subData } = useQuery({
    queryKey: ['subscription'],
    queryFn: getSubscription,
    refetchInterval: 300000,
    retry: false,
  })
  const sub = subData?.data

  // Hide the banner on the pages where the user manages their plan, and for admins
  // (who bypass the subscription gate entirely).
  const onPlanPage = location.pathname.startsWith('/settings') || location.pathname.startsWith('/billing')
  const isAdmin = user?.role === 'admin'

  let banner = null
  if (sub && !sub.is_active && !onPlanPage && !isAdmin) {
    const end = sub.subscription_end ? format(new Date(sub.subscription_end), 'MMM d') : null
    if (sub.status === 'past_due') {
      banner = {
        cls: 'bg-red-50 border-red-200 text-red-700',
        text: '🔴 Payment failed. Update your payment method to restore full access.',
        btn: 'Update payment →',
      }
    } else if (sub.status === 'cancelled') {
      banner = {
        cls: 'bg-yellow-50 border-yellow-200 text-yellow-800',
        text: `🟡 Subscription cancelled.${end ? ` Access until ${end}.` : ''} Resubscribe to keep your job search going.`,
        btn: 'Resubscribe →',
      }
    } else {
      banner = {
        cls: 'bg-amber-50 border-amber-200 text-amber-800',
        text: '⚠️ Your subscription is inactive. Subscribe to unlock CV tailoring, scanning, and application sending.',
        btn: 'Subscribe →',
      }
    }
  }

  return (
    <div className="flex h-screen bg-gray-50 overflow-hidden">
      <Sidebar hitlCount={hitlCount} />
      <main className="flex-1 overflow-y-auto min-w-0 flex flex-col">
        {needsConsent && (
          <div className="flex items-center justify-between gap-4 px-5 py-2.5 border-b bg-slate-800 text-slate-100">
            <p className="text-sm">
              We’ve updated our terms. By continuing you agree to our{' '}
              <a href={legal.privacy_url} target="_blank" rel="noreferrer" className="underline">Privacy Policy</a> and{' '}
              <a href={legal.terms_url} target="_blank" rel="noreferrer" className="underline">Terms of Service</a>.
            </p>
            <button onClick={agree} disabled={consenting}
              className="text-sm font-semibold whitespace-nowrap bg-emerald-500 hover:bg-emerald-600 text-white px-3 py-1 rounded-md disabled:opacity-50">
              {consenting ? '…' : 'I agree →'}
            </button>
          </div>
        )}
        {banner && (
          <div className={`flex items-center justify-between gap-4 px-5 py-2.5 border-b ${banner.cls}`}>
            <p className="text-sm font-medium">{banner.text}</p>
            <button
              onClick={() => navigate('/settings#plan')}
              className="text-sm font-semibold whitespace-nowrap hover:underline"
            >
              {banner.btn}
            </button>
          </div>
        )}
        <div className="flex-1"><Outlet /></div>
        <footer className="border-t border-gray-200 px-5 py-3 text-xs text-gray-400 flex items-center justify-between gap-3 shrink-0">
          <span>© 2026 JobHunt · Praveen Prakash</span>
          <nav className="flex items-center gap-3">
            <a href={legal.privacy_url} target="_blank" rel="noreferrer" className="hover:text-emerald-600">Privacy Policy</a>
            <a href={legal.terms_url} target="_blank" rel="noreferrer" className="hover:text-emerald-600">Terms</a>
            <a href={legal.cookies_url} target="_blank" rel="noreferrer" className="hover:text-emerald-600">Cookies</a>
          </nav>
        </footer>
      </main>
    </div>
  )
}
