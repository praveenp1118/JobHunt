import client from './client'

// ── Invite keys (redemption) ──
export const redeemInvite = (code) =>
  client.post('/invites/redeem', { code })

// ── Extension requests (user) ──
export const requestExtension = () =>
  client.post('/extension-requests')
export const listMyExtensionRequests = () =>
  client.get('/extension-requests')

// ── Admin: invites ──
export const adminCreateInvites = (payload) =>
  client.post('/admin/invites', payload) // { count, grants_days, key_expires_at? }
export const adminListInvites = () =>
  client.get('/admin/invites')
export const adminRevokeInvite = (id) =>
  client.post(`/admin/invites/${id}/revoke`)
export const adminExtendInvite = (id, key_expires_at) =>
  client.patch(`/admin/invites/${id}/extend`, { key_expires_at })

// ── Admin: extension requests ──
export const adminListExtensionRequests = () =>
  client.get('/admin/extension-requests')
export const adminGrantExtension = (id, days = 30, admin_note) =>
  client.post(`/admin/extension-requests/${id}/grant`, { days, admin_note })
export const adminDenyExtension = (id, admin_note) =>
  client.post(`/admin/extension-requests/${id}/deny`, { admin_note })
export const adminExtendUserSubscription = (userId, days = 30) =>
  client.patch(`/admin/users/${userId}/extend-subscription`, { days })
