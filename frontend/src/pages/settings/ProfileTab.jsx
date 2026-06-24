import { useState, useEffect } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import useAuthStore from '../../store/auth'
import { getMe, updateProfile } from '../../api/auth'
import Button from '../../components/ui/Button'
import Input from '../../components/ui/Input'
import { toast } from '../../store/toast'

export default function ProfileTab() {
  const { user, updateUser } = useAuthStore()
  const qc = useQueryClient()
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState('')

  const [name, setName] = useState(user?.name || '')
  const [linkedinUrl, setLinkedinUrl] = useState(user?.linkedin_url || '')
  const [phone, setPhone] = useState(user?.phone || '')
  const [currentLocation, setCurrentLocation] = useState(user?.current_location || '')
  const [salaryExpectation, setSalaryExpectation] = useState(user?.salary_expectation || '')
  const [showPasswordForm, setShowPasswordForm] = useState(false)
  const [currentPw, setCurrentPw] = useState('')
  const [newPw, setNewPw] = useState('')
  const [changingPw, setChangingPw] = useState(false)
  const [pwError, setPwError] = useState('')
  const [pwSaved, setPwSaved] = useState(false)

  useEffect(() => {
    setName(user?.name || '')
    setLinkedinUrl(user?.linkedin_url || '')
    setPhone(user?.phone || '')
    setCurrentLocation(user?.current_location || '')
    setSalaryExpectation(user?.salary_expectation || '')
  }, [user])

  const handleSave = async () => {
    setSaving(true)
    setError('')
    setSaved(false)
    try {
      const { data } = await updateProfile({
        name,
        linkedin_url: linkedinUrl,
        phone,
        current_location: currentLocation,
        salary_expectation: salaryExpectation,
      })
      updateUser(data)
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
      toast.success('Profile saved')
    } catch (e) {
      const msg = e.response?.data?.detail || 'Save failed'
      setError(msg)
      toast.error(msg)
    } finally {
      setSaving(false)
    }
  }

  const handleChangePassword = async () => {
    if (!currentPw || !newPw) return
    if (newPw.length < 8) { setPwError('New password must be at least 8 characters'); return }
    setChangingPw(true)
    setPwError('')
    try {
      const client = (await import('../../api/client')).default
      await client.post('/auth/change-password', { current_password: currentPw, new_password: newPw })
      setCurrentPw('')
      setNewPw('')
      setShowPasswordForm(false)
      setPwSaved(true)
      setTimeout(() => setPwSaved(false), 3000)
    } catch (e) {
      setPwError(e.response?.data?.detail || 'Password change failed')
    } finally {
      setChangingPw(false)
    }
  }

  return (
    <div className="space-y-6">
      {/* Profile card */}
      <div className="bg-white rounded-2xl border border-gray-200 p-6">
        <h2 className="text-sm font-semibold text-gray-900 mb-4">Profile</h2>

        <div className="flex items-center gap-4 mb-5 pb-5 border-b border-gray-100">
          <div className="w-14 h-14 rounded-full bg-emerald-600 flex items-center justify-center text-white font-semibold text-lg shrink-0">
            {user?.name?.split(' ').map((n) => n[0]).join('').slice(0, 2).toUpperCase() || 'U'}
          </div>
          <div>
            <p className="text-sm font-medium text-gray-900">{user?.name || 'Your name'}</p>
            <p className="text-xs text-gray-500">{user?.email}</p>
            <div className="flex gap-2 mt-1">
              <span className="text-[10px] bg-slate-100 text-slate-600 px-2 py-0.5 rounded-full capitalize">{user?.role}</span>
              <span className="text-[10px] bg-slate-100 text-slate-600 px-2 py-0.5 rounded-full capitalize">{user?.plan} plan</span>
            </div>
          </div>
        </div>

        <div className="space-y-4">
          <Input
            label="Display name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Your full name"
          />
          <Input
            label="Email"
            value={user?.email || ''}
            disabled
            hint="Email cannot be changed"
          />
          <Input
            label="LinkedIn URL"
            value={linkedinUrl}
            onChange={(e) => setLinkedinUrl(e.target.value)}
            placeholder="https://linkedin.com/in/your-handle"
          />
          <Input
            label="Phone"
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
            placeholder="+31 6 1234 5678"
          />
          <Input
            label="Current location"
            value={currentLocation}
            onChange={(e) => setCurrentLocation(e.target.value)}
            placeholder="Amsterdam, Netherlands"
          />
          <Input
            label="Salary expectation"
            value={salaryExpectation}
            onChange={(e) => setSalaryExpectation(e.target.value)}
            placeholder="e.g. €120k–150k"
          />
        </div>

        {error && <p className="text-sm text-red-500 mt-3">{error}</p>}
        {saved && <p className="text-sm text-emerald-600 mt-3">✓ Profile saved</p>}

        <div className="flex justify-end mt-4">
          <Button onClick={handleSave} loading={saving} size="sm">Save profile</Button>
        </div>
      </div>

      {/* Password card */}
      <div className="bg-white rounded-2xl border border-gray-200 p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-semibold text-gray-900">Password</h2>
          {!showPasswordForm && (
            <Button size="sm" variant="secondary" onClick={() => setShowPasswordForm(true)}>
              Change password
            </Button>
          )}
        </div>

        {pwSaved && <p className="text-sm text-emerald-600 mb-3">✓ Password changed successfully</p>}

        {showPasswordForm && (
          <div className="space-y-3">
            <Input label="Current password" type="password" value={currentPw} onChange={(e) => setCurrentPw(e.target.value)} />
            <Input label="New password" type="password" value={newPw} onChange={(e) => setNewPw(e.target.value)} hint="Minimum 8 characters" />
            {pwError && <p className="text-sm text-red-500">{pwError}</p>}
            <div className="flex gap-2">
              <Button size="sm" onClick={handleChangePassword} loading={changingPw}>Update password</Button>
              <Button size="sm" variant="ghost" onClick={() => { setShowPasswordForm(false); setPwError('') }}>Cancel</Button>
            </div>
          </div>
        )}

        {!showPasswordForm && !pwSaved && (
          <p className="text-sm text-gray-400">••••••••••••</p>
        )}
      </div>
    </div>
  )
}
