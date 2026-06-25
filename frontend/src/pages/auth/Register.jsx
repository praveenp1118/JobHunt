import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import AuthLayout from '../../components/layout/AuthLayout'
import Button from '../../components/ui/Button'
import Input from '../../components/ui/Input'
import useAuthStore from '../../store/auth'
import { register, login } from '../../api/auth'
import { getLegalUrls, recordConsent } from '../../api/legal'

export default function Register() {
  const navigate = useNavigate()
  const { login: storeLogin, updateUser } = useAuthStore()

  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [agreed, setAgreed] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const { data: legalData } = useQuery({ queryKey: ['legal-urls'], queryFn: getLegalUrls, staleTime: Infinity, retry: false })
  const legal = legalData?.data || {}

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (password.length < 8) {
      setError('Password must be at least 8 characters')
      return
    }
    if (!agreed) {
      setError('Please agree to the Terms of Service and Privacy Policy')
      return
    }

    setLoading(true)
    setError('')

    try {
      await register(email, password, name)
      // Auto-login after register
      const { data } = await login(email, password)
      storeLogin(data.user, data.access_token)
      try { const c = await recordConsent(); updateUser({ gdpr_consent_at: c.data.gdpr_consent_at }) } catch (_) {}
      navigate('/onboarding')
    } catch (err) {
      setError(
        err.response?.data?.detail || 'Registration failed. Please try again.'
      )
    } finally {
      setLoading(false)
    }
  }

  return (
    <AuthLayout>
      <h1 className="text-xl font-semibold text-gray-900 mb-1">Create account</h1>
      <p className="text-sm text-gray-500 mb-6">Start your AI-powered job search</p>

      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        <Input
          label="Full name"
          placeholder="Praveen Prakash"
          value={name}
          onChange={(e) => setName(e.target.value)}
          autoFocus
          required
        />
        <Input
          label="Email"
          type="email"
          placeholder="you@example.com"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
        />
        <Input
          label="Password"
          type="password"
          placeholder="Min. 8 characters"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />

        <label className="flex items-start gap-2 text-sm text-gray-600">
          <input type="checkbox" checked={agreed} onChange={(e) => setAgreed(e.target.checked)}
            className="mt-0.5 w-4 h-4 rounded accent-emerald-500" />
          <span>
            I agree to the{' '}
            <a href={legal.terms_url} target="_blank" rel="noreferrer" className="text-emerald-600 hover:underline">Terms of Service</a> and{' '}
            <a href={legal.privacy_url} target="_blank" rel="noreferrer" className="text-emerald-600 hover:underline">Privacy Policy</a>.
          </span>
        </label>

        {error && (
          <div className="bg-red-50 border border-red-200 rounded-lg px-3 py-2 text-sm text-red-600">
            {error}
          </div>
        )}

        <Button type="submit" fullWidth loading={loading} size="lg" disabled={!agreed}>
          Create account
        </Button>
      </form>

      <p className="text-center text-sm text-gray-500 mt-6">
        Already have an account?{' '}
        <Link to="/login" className="text-emerald-600 hover:text-emerald-700 font-medium">
          Sign in
        </Link>
      </p>
    </AuthLayout>
  )
}
