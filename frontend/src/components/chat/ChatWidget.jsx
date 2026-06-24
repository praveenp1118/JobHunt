import { useState, useEffect, useRef } from 'react'
import {
  getPresence, createConversation, getConversation, sendChatMessage,
  createTicket, uploadAttachment, chatWsUrl,
} from '../../api/chat'
import useAuthStore from '../../store/auth'
import { toast } from '../../store/toast'

const CID_KEY = 'jobhunt-chat-cid'

export default function ChatWidget() {
  const token = useAuthStore((s) => s.token)
  const user = useAuthStore((s) => s.user)
  const isLoggedIn = !!token

  const [open, setOpen] = useState(false)
  const [adminOnline, setAdminOnline] = useState(false)
  const [conversationId, setConversationId] = useState(() => localStorage.getItem(CID_KEY) || null)
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [guestName, setGuestName] = useState('')
  const [guestEmail, setGuestEmail] = useState('')
  const [started, setStarted] = useState(false)
  const [sending, setSending] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [lastBot, setLastBot] = useState(null)   // {content, links, no_match}
  const [unread, setUnread] = useState(0)

  const wsRef = useRef(null)
  const fileRef = useRef(null)
  const bottomRef = useRef(null)

  // Once we know whether the user is logged in (or already has a thread), skip the guest form.
  useEffect(() => {
    if (isLoggedIn || conversationId) setStarted(true)
  }, [isLoggedIn, conversationId])

  // Poll admin presence every 30s for the online indicator.
  useEffect(() => {
    let active = true
    const poll = () => getPresence().then((r) => active && setAdminOnline(!!r.data.is_online)).catch(() => {})
    poll()
    const t = setInterval(poll, 30000)
    return () => { active = false; clearInterval(t) }
  }, [])

  // Load existing conversation when first opened.
  useEffect(() => {
    if (open && conversationId && messages.length === 0) {
      getConversation(conversationId)
        .then((r) => setMessages(r.data.messages || []))
        .catch(() => { localStorage.removeItem(CID_KEY); setConversationId(null) })
    }
  }, [open, conversationId]) // eslint-disable-line

  // WebSocket — receive admin/bot messages in real time.
  useEffect(() => {
    if (!conversationId) return
    let ws
    try {
      ws = new WebSocket(chatWsUrl(conversationId))
      wsRef.current = ws
      ws.onmessage = (e) => {
        try {
          const evt = JSON.parse(e.data)
          if (evt.type === 'message' && evt.data) {
            setMessages((prev) => (prev.some((m) => m.id === evt.data.id) ? prev : [...prev, evt.data]))
            const fromOther = !['user', 'guest'].includes(evt.data.sender_type)
            if (fromOther) setUnread((u) => (open ? 0 : u + 1))
          }
        } catch (_) {}
      }
    } catch (_) {}
    return () => { try { ws && ws.close() } catch (_) {} }
  }, [conversationId]) // eslint-disable-line

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages, open, lastBot])
  useEffect(() => { if (open) setUnread(0) }, [open])

  const persistCid = (id) => { localStorage.setItem(CID_KEY, id); setConversationId(id) }

  const handleSend = async (content, attachment) => {
    const text = (content ?? input).trim()
    if (!text && !attachment) return
    setSending(true)
    setLastBot(null)
    try {
      if (!conversationId) {
        const res = await createConversation({
          guest_name: isLoggedIn ? undefined : guestName,
          guest_email: isLoggedIn ? undefined : guestEmail,
          first_message: text || (attachment ? `📎 ${attachment.name}` : ''),
        })
        persistCid(res.data.conversation_id)
        const conv = await getConversation(res.data.conversation_id)
        setMessages(conv.data.messages || [])
        setLastBot(res.data.bot_response || null)
      } else {
        const res = await sendChatMessage(conversationId, {
          content: text,
          message_type: attachment ? (attachment.type?.startsWith('image/') ? 'image' : 'file') : 'text',
          attachment_url: attachment?.url,
          attachment_name: attachment?.name,
          attachment_size: attachment?.size,
        })
        // Append our message immediately (WS dedupes by id if it echoes back).
        setMessages((prev) => (prev.some((m) => m.id === res.data.message.id) ? prev : [...prev, res.data.message]))
        setLastBot(res.data.bot_response || null)
        if (res.data.bot_response) {
          // bot reply arrives via WS; if WS is slow, reload to be safe
          setTimeout(() => getConversation(conversationId).then((r) => setMessages(r.data.messages || [])).catch(() => {}), 400)
        }
      }
      setInput('')
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Could not send message')
    } finally {
      setSending(false)
    }
  }

  const handleFile = async (e) => {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    if (file.size > 5 * 1024 * 1024) { toast.error('File too large (max 5 MB)'); return }
    setUploading(true)
    try {
      const fd = new FormData()
      fd.append('file', file)
      const res = await uploadAttachment(fd)
      await handleSend(input, res.data)
    } catch (e2) {
      toast.error(e2.response?.data?.detail || 'Upload failed')
    } finally {
      setUploading(false)
    }
  }

  const handleCreateTicket = async () => {
    if (!conversationId) return
    try {
      const res = await createTicket({ conversation_id: conversationId, priority: 'medium' })
      setLastBot(null)
      toast.success(`Ticket ${res.data.ticket_number} created — we'll respond within 24h`)
      getConversation(conversationId).then((r) => setMessages(r.data.messages || [])).catch(() => {})
    } catch (e) {
      toast.error('Could not create ticket')
    }
  }

  // ── Bubble (closed) ──
  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="fixed bottom-5 right-5 z-50 w-14 h-14 rounded-full bg-emerald-600 hover:bg-emerald-700 shadow-lg flex items-center justify-center text-white transition-colors"
        aria-label="Open support chat"
      >
        <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.86 9.86 0 01-4-.8L3 20l1.3-3.9A7.96 7.96 0 013 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
        </svg>
        <span className={`absolute bottom-1 right-1 w-3 h-3 rounded-full border-2 border-white ${adminOnline ? 'bg-green-400' : 'bg-gray-400'}`} />
        {unread > 0 && (
          <span className="absolute -top-1 -right-1 min-w-5 h-5 px-1 rounded-full bg-red-500 text-white text-[10px] font-bold flex items-center justify-center">{unread}</span>
        )}
      </button>
    )
  }

  // ── Open panel ──
  return (
    <div className="fixed bottom-5 right-5 z-50 w-[350px] h-[500px] bg-white rounded-2xl shadow-2xl border border-gray-200 flex flex-col overflow-hidden">
      {/* Header */}
      <div className="px-4 py-3 bg-slate-800 text-white flex items-center justify-between shrink-0">
        <div>
          <p className="text-sm font-semibold">💬 JobHunt Support</p>
          <p className="text-[11px] text-slate-300 flex items-center gap-1.5 mt-0.5">
            <span className={`w-2 h-2 rounded-full ${adminOnline ? 'bg-green-400' : 'bg-gray-400'}`} />
            {adminOnline ? 'We’re online' : 'We’re offline — FAQ bot will help'}
          </p>
        </div>
        <button onClick={() => setOpen(false)} className="text-slate-300 hover:text-white text-lg leading-none">×</button>
      </div>

      {/* Guest gate */}
      {!started ? (
        <div className="flex-1 p-5 space-y-3">
          <p className="text-sm text-gray-600">Hi! Tell us who you are and we'll help.</p>
          <input value={guestName} onChange={(e) => setGuestName(e.target.value)} placeholder="Your name"
            className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm outline-none focus:border-emerald-400" />
          <input value={guestEmail} onChange={(e) => setGuestEmail(e.target.value)} placeholder="Your email" type="email"
            className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm outline-none focus:border-emerald-400" />
          <button onClick={() => setStarted(true)} disabled={!guestName || !guestEmail}
            className="w-full py-2 rounded-lg bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white text-sm font-medium">
            Start chat
          </button>
        </div>
      ) : (
        <>
          {/* Messages */}
          <div className="flex-1 overflow-y-auto px-3 py-3 space-y-2 bg-gray-50">
            {messages.length === 0 && (
              <p className="text-xs text-gray-400 text-center py-4">
                Ask me anything about JobHunt and I'll try to help.
              </p>
            )}
            {messages.map((m) => <MessageBubble key={m.id} m={m} />)}

            {/* FAQ links + helpful / ticket prompt for the latest bot reply */}
            {lastBot && !lastBot.no_match && (
              <div className="space-y-2">
                {(lastBot.links || []).map((l) => (
                  <a key={l.url} href={l.url} target="_blank" rel="noreferrer"
                    className="block text-center text-xs font-medium text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-lg px-3 py-1.5 hover:bg-emerald-100">
                    {l.text} →
                  </a>
                ))}
                <div className="flex items-center justify-center gap-2 text-[11px] text-gray-500">
                  Was this helpful?
                  <button onClick={() => setLastBot(null)} className="px-2 py-0.5 rounded border border-gray-200 hover:bg-gray-100">👍 Yes</button>
                  <button onClick={handleCreateTicket} className="px-2 py-0.5 rounded border border-gray-200 hover:bg-gray-100">👎 No</button>
                </div>
              </div>
            )}
            {lastBot && lastBot.no_match && (
              <div className="flex flex-col gap-1.5">
                <button onClick={handleCreateTicket} className="text-xs font-medium text-white bg-emerald-600 hover:bg-emerald-700 rounded-lg px-3 py-1.5">📝 Create support ticket</button>
                <button onClick={() => setLastBot(null)} className="text-xs font-medium text-gray-700 bg-white border border-gray-200 hover:bg-gray-50 rounded-lg px-3 py-1.5">💬 Leave a message for admin</button>
              </div>
            )}
            <div ref={bottomRef} />
          </div>

          {/* Composer */}
          <div className="px-3 py-2.5 border-t border-gray-200 bg-white shrink-0">
            <div className="flex items-center gap-2">
              <input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter' && !sending) handleSend() }}
                placeholder="Type a message..."
                className="flex-1 px-3 py-2 border border-gray-200 rounded-lg text-sm outline-none focus:border-emerald-400"
              />
              <input ref={fileRef} type="file" hidden accept="image/*,.pdf,.doc,.docx" onChange={handleFile} />
              <button onClick={() => fileRef.current?.click()} disabled={uploading} title="Attach a file"
                className="text-gray-400 hover:text-gray-600 disabled:opacity-50 text-lg">📎</button>
              <button onClick={() => handleSend()} disabled={sending || (!input.trim())}
                className="w-8 h-8 rounded-lg bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white flex items-center justify-center">→</button>
            </div>
            {uploading && <p className="text-[10px] text-gray-400 mt-1">Uploading…</p>}
          </div>
        </>
      )}
    </div>
  )
}

function MessageBubble({ m }) {
  const isMine = ['user', 'guest'].includes(m.sender_type)
  if (m.sender_type === 'system') {
    return <p className="text-center text-[11px] text-gray-400 py-1">{m.content}</p>
  }
  const isBot = m.sender_type === 'bot'
  const isAdmin = m.sender_type === 'admin'
  const bubbleCls = isMine
    ? 'bg-emerald-600 text-white ml-auto'
    : isBot
      ? 'bg-gray-100 text-gray-800'
      : 'bg-indigo-50 text-indigo-900 border border-indigo-100'
  return (
    <div className={`max-w-[80%] ${isMine ? 'ml-auto' : ''}`}>
      {!isMine && (
        <p className="text-[10px] text-gray-400 mb-0.5 ml-1">{isBot ? '🤖 Assistant' : isAdmin ? '🧑‍💼 Support' : ''}</p>
      )}
      <div className={`rounded-2xl px-3 py-2 text-sm whitespace-pre-wrap ${bubbleCls}`}>
        {m.attachment_url && (
          m.message_type === 'image'
            ? <img src={m.attachment_url} alt={m.attachment_name} className="max-w-full rounded-lg mb-1" />
            : <a href={m.attachment_url} target="_blank" rel="noreferrer" className="underline text-xs block mb-1">📎 {m.attachment_name}</a>
        )}
        {m.content}
      </div>
    </div>
  )
}
