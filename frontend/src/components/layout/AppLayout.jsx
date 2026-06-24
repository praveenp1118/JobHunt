import { lazy, Suspense } from 'react'
import { Outlet, useNavigate, useLocation } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { format } from 'date-fns'
import Sidebar from './Sidebar'

// Lazy — only loads when first rendered, keeping it off the critical path.
const ChatWidget = lazy(() => import('../chat/ChatWidget'))
import { getJobs } from '../../api/jobs'
import { getSubscription } from '../../api/billing'
import useAuthStore from '../../store/auth'

export default function AppLayout() {
  const navigate = useNavigate()
  const location = useLocation()
  const user = useAuthStore((s) => s.user)

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
      <main className="flex-1 overflow-y-auto min-w-0">
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
        <Outlet />
      </main>
      {/* Support chat — on all app pages except the admin chat console itself. */}
      {!location.pathname.startsWith('/admin/chat') && (
        <Suspense fallback={null}><ChatWidget /></Suspense>
      )}
    </div>
  )
}
