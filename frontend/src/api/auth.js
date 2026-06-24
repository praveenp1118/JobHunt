import client from './client'

export const login = (email, password, rememberMe = false) =>
  client.post('/auth/login', { email, password, remember_me: rememberMe })

export const register = (email, password, name) =>
  client.post('/auth/register', { email, password, name })

export const forgotPassword = (email) =>
  client.post('/auth/forgot-password', { email })

export const resetPassword = (token, password) =>
  client.post('/auth/reset-password', { token, password })

export const getMe = () =>
  client.get('/auth/me')

export const updateProfile = (data) =>
  client.patch('/auth/me/profile', data)

export const getCredentials = () =>
  client.get('/auth/me/credentials')

export const updateCredentials = (data) =>
  client.put('/auth/me/credentials', data)

export const getPreferences = () =>
  client.get('/auth/me/preferences')

export const updatePreferences = (data) =>
  client.patch('/auth/me/preferences', data)

// Where outgoing application email actually goes (test → notification address; prod → recruiter).
export const getSettingsMode = () =>
  client.get('/settings/mode')
