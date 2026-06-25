import { lazy, Suspense } from 'react'
import { Routes, Route, Navigate, useLocation } from 'react-router-dom'
import useAuthStore from './store/auth'
import AppLayout from './components/layout/AppLayout'

// Support chat — mounted app-wide (incl. /login, /register) so guests can reach
// support before signing up. Lazy so it stays off the critical path.
const ChatWidget = lazy(() => import('./components/chat/ChatWidget'))

// Auth pages
import Login from './pages/auth/Login'
import Register from './pages/auth/Register'
import ForgotPassword from './pages/auth/ForgotPassword'

// Onboarding
import Onboarding from './pages/onboarding/Onboarding'

// App pages
import Dashboard from './pages/dashboard/Dashboard'
import JobsPage from './pages/jobs/JobsPage'
import TailorPage from './pages/jobs/TailorPage'
import SubscriptionSuccess from './pages/billing/SubscriptionSuccess'
import CVsPage from './pages/cvs/CVsPage'
import SettingsPage from './pages/settings/SettingsPage'
import ActivityPage from './pages/activity/ActivityPage'
import WalletPage from './pages/wallet/WalletPage'
import ToastContainer from './components/ui/Toast'
import AdminPage from './pages/admin/AdminPage'
import ChatPage from './pages/admin/ChatPage'
import ContributionsPage from './pages/community/ContributionsPage'
import CareerPage from './pages/career/CareerPage'

// Placeholder for pages not yet built
const Placeholder = ({ name }) => (
  <div className="p-6 flex items-center justify-center min-h-96">
    <div className="bg-white rounded-xl p-8 text-center shadow-sm border border-gray-200 max-w-sm w-full">
      <div className="w-10 h-10 bg-emerald-100 rounded-lg flex items-center justify-center mx-auto mb-4">
        <span className="text-emerald-600 font-bold text-sm">JH</span>
      </div>
      <h2 className="font-semibold text-gray-900 mb-1">{name}</h2>
      <p className="text-sm text-gray-500">Coming in the next build phase</p>
    </div>
  </div>
)

// Auth guard
function RequireAuth({ children }) {
  const { isAuthenticated } = useAuthStore()
  if (!isAuthenticated) return <Navigate to="/login" replace />
  return children
}

// Redirect if already logged in
function PublicOnly({ children }) {
  const { isAuthenticated } = useAuthStore()
  if (isAuthenticated) return <Navigate to="/dashboard" replace />
  return children
}

export default function App() {
  const location = useLocation()
  return (
    <>
    <ToastContainer />
    <Routes>
      {/* Public routes */}
      <Route path="/login" element={<PublicOnly><Login /></PublicOnly>} />
      <Route path="/register" element={<PublicOnly><Register /></PublicOnly>} />
      <Route path="/forgot-password" element={<ForgotPassword />} />

      {/* Onboarding */}
      <Route path="/onboarding" element={<RequireAuth><Onboarding /></RequireAuth>} />

      {/* Full-screen tailor experience (no app sidebar — maximum space) */}
      <Route path="/jobs/:jobId/tailor" element={<RequireAuth><TailorPage /></RequireAuth>} />

      {/* Post-checkout landing */}
      <Route path="/billing/success" element={<RequireAuth><SubscriptionSuccess /></RequireAuth>} />

      {/* Protected app routes — all use AppLayout */}
      <Route element={<RequireAuth><AppLayout /></RequireAuth>}>
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/activity" element={<ActivityPage />} />
        <Route path="/career" element={<CareerPage />} />
        <Route path="/jobs" element={<JobsPage />} />
        <Route path="/cvs" element={<CVsPage />} />
        <Route path="/wallet" element={<WalletPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="/community/contributions" element={<ContributionsPage />} />
        <Route path="/admin" element={<AdminPage />} />
        <Route path="/admin/chat" element={<ChatPage />} />
      </Route>

      {/* Default */}
      <Route path="/" element={<Navigate to="/dashboard" replace />} />
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
    {/* Support chat on every page except the admin chat console itself. */}
    {!location.pathname.startsWith('/admin/chat') && (
      <Suspense fallback={null}><ChatWidget /></Suspense>
    )}
  </>
  )
}
