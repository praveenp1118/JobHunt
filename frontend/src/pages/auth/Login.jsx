import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import AuthLayout from '../../components/layout/AuthLayout'
import Button from '../../components/ui/Button'
import Input from '../../components/ui/Input'
import useAuthStore from '../../store/auth'
import { login } from '../../api/auth'
import { getMasterCV } from '../../api/cvs'
import { getLegalUrls } from '../../api/legal'

export default function Login() {
  const navigate = useNavigate()
  const { login: storeLogin } = useAuthStore()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [rememberMe, setRememberMe] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const { data: legalData } = useQuery({ queryKey: ['legal-urls'], queryFn: getLegalUrls, staleTime: Infinity, retry: false })
  const legal = legalData?.data || {}

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!email || !password) return

    setLoading(true)
    setError('')

    try {
      const { data } = await login(email, password, rememberMe)
      storeLogin(data.user, data.access_token)

      // Check if onboarding needed (no master CV yet)
      try {
        const cvRes = await getMasterCV()
        if (!cvRes.data) {
          navigate('/onboarding')
        } else {
          navigate('/dashboard')
        }
      } catch {
        navigate('/onboarding')
      }
    } catch (err) {
      setError(
        err.response?.data?.detail || 'Incorrect email or password'
      )
    } finally {
      setLoading(false)
    }
  }

  return (
    <AuthLayout>
      <h1 className="text-xl font-semibold text-gray-900 mb-1">Sign in</h1>
      <p className="text-sm text-gray-500 mb-6">Welcome back</p>

      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        <Input
          label="Email"
          type="email"
          placeholder="you@example.com"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          autoFocus
          required
        />

        <Input
          label="Password"
          type="password"
          placeholder="••••••••"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />

        {error && (
          <div className="bg-red-50 border border-red-200 rounded-lg px-3 py-2 text-sm text-red-600">
            {error}
          </div>
        )}

        <div className="flex items-center justify-between">
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={rememberMe}
              onChange={(e) => setRememberMe(e.target.checked)}
              className="w-4 h-4 rounded border-gray-300 text-emerald-600 focus:ring-emerald-500"
            />
            <span className="text-sm text-gray-600">Remember me for 30 days</span>
          </label>
          <Link
            to="/forgot-password"
            className="text-sm text-emerald-600 hover:text-emerald-700 font-medium"
          >
            Forgot password?
          </Link>
        </div>

        <Button type="submit" fullWidth loading={loading} size="lg">
          Sign in
        </Button>

        <div className="relative my-1">
          <div className="absolute inset-0 flex items-center">
            <div className="w-full border-t border-gray-200" />
          </div>
          <div className="relative flex justify-center text-xs">
            <span className="bg-white px-3 text-gray-400">or</span>
          </div>
        </div>

        <a
          href="/api/auth/google/authorize"
          className="w-full flex items-center justify-center gap-3 px-4 py-2.5 border border-gray-200 rounded-lg text-sm font-medium text-gray-700 hover:bg-gray-50 transition-colors"
        >
          <svg className="w-5 h-5" viewBox="0 0 24 24">
            <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
            <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
            <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
            <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
          </svg>
          Continue with Google
        </a>
      </form>

      <p className="text-center text-sm text-gray-500 mt-6">
        Don't have an account?{' '}
        <Link to="/register" className="text-emerald-600 hover:text-emerald-700 font-medium">
          Sign up
        </Link>
      </p>

      <nav className="flex items-center justify-center gap-3 mt-6 text-xs text-gray-400">
        <a href={legal.privacy_url} target="_blank" rel="noreferrer" className="hover:text-emerald-600">Privacy Policy</a>
        <span>·</span>
        <a href={legal.terms_url} target="_blank" rel="noreferrer" className="hover:text-emerald-600">Terms</a>
        <span>·</span>
        <a href={legal.cookies_url} target="_blank" rel="noreferrer" className="hover:text-emerald-600">Cookies</a>
      </nav>
    </AuthLayout>
  )
}
