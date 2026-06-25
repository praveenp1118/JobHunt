import client from './client'

export const getPrivacySummary = () => client.get('/privacy/summary')
export const getRateLimits = () => client.get('/privacy/rate-limits')
export const exportMyData = () => client.get('/privacy/export', { responseType: 'blob' })
export const requestDeletion = () => client.post('/privacy/delete-request', { confirm: true })
export const cancelDeletion = () => client.post('/privacy/cancel-deletion')

// Admin governance
export const getGovernance = () => client.get('/admin/governance')
export const adminCancelDeletion = (userId) => client.post(`/admin/governance/cancel-deletion/${userId}`)
