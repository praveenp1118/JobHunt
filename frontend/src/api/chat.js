import client from './client'

// ── Public / user ──
export const getPresence = () => client.get('/chat/presence')
export const createConversation = (data) => client.post('/chat/conversations', data)
export const getConversation = (id) => client.get(`/chat/conversations/${id}`)
export const sendChatMessage = (id, data) => client.post(`/chat/conversations/${id}/messages`, data)
export const markChatRead = (id, msgId) => client.post(`/chat/conversations/${id}/messages/${msgId}/read`)
export const createTicket = (data) => client.post('/chat/tickets', data)
export const uploadAttachment = (formData, onUploadProgress) =>
  client.post('/chat/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    onUploadProgress,
  })

// ── Admin ──
export const listConversations = (params) => client.get('/chat/conversations', { params })
export const updateConversation = (id, data) => client.patch(`/chat/conversations/${id}`, data)
export const listTickets = () => client.get('/chat/tickets')
export const updateTicket = (id, data) => client.patch(`/chat/tickets/${id}`, data)
export const setPresence = (isOnline) => client.post('/chat/presence', { is_online: isOnline })

// WebSocket URL for a conversation (proxied by Vite in dev).
export const chatWsUrl = (conversationId) => {
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
  return `${proto}://${window.location.host}/ws/chat/${conversationId}`
}
