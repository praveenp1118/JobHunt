import { useState, useEffect, useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import { formatDistanceToNow } from 'date-fns'
import {
  listConversations, getConversation, sendChatMessage, updateConversation,
  setPresence, createTicket, chatWsUrl,
} from '../../api/chat'
import useAuthStore from '../../store/auth'
import { toast } from '../../store/toast'

const CANNED = [
  'Thanks for reaching out! Let me check that for you.',
  'Could you share a screenshot of the issue?',
  'This has been fixed, please refresh and try again.',
]

export default function ChatPage() {
  const user = useAuthStore((s) => s.user)
  const [online, setOnline] = useState(false)
  const [filter, setFilter] = useState('open')
  const [selectedId, setSelectedId] = useState(null)
  const [messages, setMessages] = useState([])
  const [reply, setReply] = useState('')
  const [internalNote, setInternalNote] = useState(false)
  const [sending, setSending] = useState(false)
  const wsRef = useRef(null)
  const bottomRef = useRef(null)

  // Presence — online on mount, heartbeat 60s, offline on leave (Step 10).
  useEffect(() => {
    setPresence(true).then(() => setOnline(true)).catch(() => {})
    const hb = setInterval(() => setPresence(true).catch(() => {}), 60000)
    const off = () => { setPresence(false).catch(() => {}) }
    window.addEventListener('beforeunload', off)
    return () => {
      clearInterval(hb)
      window.removeEventListener('beforeunload', off)
      setPresence(false).catch(() => {})
    }
  }, [])

  const { data: convData, refetch } = useQuery({
    queryKey: ['admin-chats', filter],
    queryFn: () => listConversations(filter === 'all' ? {} : { status: 'open' }),
    refetchInterval: 15000,
  })
  const conversations = convData?.data?.conversations || []

  useEffect(() => {
    if (!selectedId) { setMessages([]); return }
    getConversation(selectedId).then((r) => setMessages(r.data.messages || [])).catch(() => {})
    let ws
    try {
      ws = new WebSocket(chatWsUrl(selectedId))
      wsRef.current = ws
      ws.onmessage = (e) => {
        try {
          const evt = JSON.parse(e.data)
          if (evt.type === 'message' && evt.data) {
            setMessages((prev) => (prev.some((m) => m.id === evt.data.id) ? prev : [...prev, evt.data]))
          }
        } catch (_) {}
      }
    } catch (_) {}
    return () => { try { ws && ws.close() } catch (_) {} }
  }, [selectedId])

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages])

  if (user?.role !== 'admin') {
    return <div className="p-6 text-sm text-gray-500">Admin access required</div>
  }

  const selected = conversations.find((c) => c.id === selectedId)

  const toggleOnline = async () => {
    const next = !online
    try { await setPresence(next); setOnline(next) } catch { toast.error('Failed to update presence') }
  }

  const handleReply = async (text) => {
    const content = (text ?? reply).trim()
    if (!content || !selectedId) return
    setSending(true)
    try {
      const res = await sendChatMessage(selectedId, { content, is_internal_note: internalNote })
      setMessages((prev) => (prev.some((m) => m.id === res.data.message.id) ? prev : [...prev, res.data.message]))
      setReply('')
      setInternalNote(false)
      refetch()
    } catch { toast.error('Failed to send') } finally { setSending(false) }
  }

  const handleStatus = async (status) => {
    try { await updateConversation(selectedId, { status }); toast.success(`Marked ${status}`); refetch() }
    catch { toast.error('Failed') }
  }

  const handleTicket = async () => {
    try {
      const res = await createTicket({ conversation_id: selectedId, priority: 'medium' })
      toast.success(`Ticket ${res.data.ticket_number} created`)
      getConversation(selectedId).then((r) => setMessages(r.data.messages || [])).catch(() => {})
    } catch { toast.error('Failed') }
  }

  const convTitle = (c) => c.guest_name || (c.user_id ? 'User' : 'Guest') + (c.guest_email ? ` · ${c.guest_email}` : '')

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="flex items-center justify-between mb-5">
        <div>
          <h1 className="text-xl font-semibold text-gray-900">Support Chat</h1>
          <p className="text-sm text-gray-500 mt-0.5">Rule-based FAQ + live admin replies</p>
        </div>
        <button onClick={toggleOnline}
          className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm font-medium border ${online ? 'bg-emerald-50 text-emerald-700 border-emerald-200' : 'bg-gray-50 text-gray-600 border-gray-200'}`}>
          <span className={`w-2 h-2 rounded-full ${online ? 'bg-green-400' : 'bg-gray-400'}`} />
          {online ? 'Online — click to go offline' : 'Offline — click to go online'}
        </button>
      </div>

      <div className="flex gap-4 h-[calc(100vh-200px)]">
        {/* Left — conversation list */}
        <div className="w-[320px] shrink-0 bg-white rounded-2xl border border-gray-200 flex flex-col overflow-hidden">
          <div className="flex gap-1 p-2 border-b border-gray-100">
            {['open', 'all'].map((f) => (
              <button key={f} onClick={() => setFilter(f)}
                className={`px-3 py-1 rounded-md text-xs font-medium capitalize ${filter === f ? 'bg-slate-800 text-white' : 'text-gray-500 hover:bg-gray-100'}`}>{f}</button>
            ))}
          </div>
          <div className="flex-1 overflow-y-auto">
            {conversations.length === 0 && <p className="text-xs text-gray-400 text-center py-8">No conversations</p>}
            {conversations.map((c) => (
              <button key={c.id} onClick={() => setSelectedId(c.id)}
                className={`w-full text-left px-3 py-2.5 border-b border-gray-50 hover:bg-gray-50 ${selectedId === c.id ? 'bg-emerald-50' : ''}`}>
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium text-gray-800 truncate">{convTitle(c)}</span>
                  {c.unread > 0 && <span className="ml-2 min-w-5 h-5 px-1 rounded-full bg-red-500 text-white text-[10px] font-bold flex items-center justify-center">{c.unread}</span>}
                </div>
                <p className="text-xs text-gray-400 truncate mt-0.5">{c.last_message?.content || '—'}</p>
                <div className="flex items-center gap-2 mt-1">
                  <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${c.status === 'open' ? 'bg-amber-100 text-amber-700' : c.status === 'resolved' ? 'bg-emerald-100 text-emerald-700' : 'bg-gray-100 text-gray-500'}`}>{c.status}</span>
                  {c.category && <span className="text-[10px] text-gray-400">{c.category}</span>}
                  <span className="text-[10px] text-gray-300 ml-auto">{c.updated_at ? formatDistanceToNow(new Date(c.updated_at), { addSuffix: true }) : ''}</span>
                </div>
              </button>
            ))}
          </div>
        </div>

        {/* Right — thread */}
        <div className="flex-1 bg-white rounded-2xl border border-gray-200 flex flex-col overflow-hidden">
          {!selected ? (
            <div className="flex-1 flex items-center justify-center text-sm text-gray-400">Select a conversation</div>
          ) : (
            <>
              <div className="px-4 py-3 border-b border-gray-100 flex items-center justify-between">
                <div>
                  <p className="text-sm font-semibold text-gray-900">{convTitle(selected)}</p>
                  <p className="text-xs text-gray-400">{selected.status} · {selected.category || 'general'}</p>
                </div>
                <div className="flex gap-1.5">
                  <button onClick={handleTicket} className="text-xs px-2 py-1 rounded border border-gray-200 hover:bg-gray-50">+ Ticket</button>
                  <button onClick={() => handleStatus('resolved')} className="text-xs px-2 py-1 rounded border border-emerald-200 text-emerald-700 hover:bg-emerald-50">✓ Resolve</button>
                  <button onClick={() => handleStatus('closed')} className="text-xs px-2 py-1 rounded border border-gray-200 text-gray-500 hover:bg-gray-50">Close</button>
                </div>
              </div>

              <div className="flex-1 overflow-y-auto px-4 py-3 space-y-2 bg-gray-50">
                {messages.map((m) => (
                  <div key={m.id} className={`max-w-[75%] ${['admin'].includes(m.sender_type) ? 'ml-auto' : ''}`}>
                    {m.is_internal_note ? (
                      <div className="rounded-lg px-3 py-2 text-sm bg-yellow-50 border border-yellow-200 text-yellow-800">
                        <span className="text-[10px] font-medium">🔒 Internal note</span>
                        <p className="whitespace-pre-wrap mt-0.5">{m.content}</p>
                      </div>
                    ) : m.sender_type === 'system' ? (
                      <p className="text-center text-[11px] text-gray-400 w-full">{m.content}</p>
                    ) : (
                      <div>
                        <p className="text-[10px] text-gray-400 mb-0.5">{m.sender_type === 'bot' ? '🤖 Bot' : m.sender_type === 'admin' ? 'You' : m.sender_type === 'guest' ? 'Guest' : 'User'}</p>
                        <div className={`rounded-2xl px-3 py-2 text-sm whitespace-pre-wrap ${m.sender_type === 'admin' ? 'bg-indigo-600 text-white' : m.sender_type === 'bot' ? 'bg-gray-100 text-gray-700' : 'bg-white border border-gray-200 text-gray-800'}`}>
                          {m.attachment_url && (m.message_type === 'image'
                            ? <img src={m.attachment_url} alt={m.attachment_name} className="max-w-full rounded mb-1" />
                            : <a href={m.attachment_url} target="_blank" rel="noreferrer" className="underline text-xs block mb-1">📎 {m.attachment_name}</a>)}
                          {m.content}
                        </div>
                      </div>
                    )}
                  </div>
                ))}
                <div ref={bottomRef} />
              </div>

              {/* Canned responses */}
              <div className="px-4 pt-2 flex flex-wrap gap-1.5">
                {CANNED.map((c) => (
                  <button key={c} onClick={() => setReply(c)} className="text-[11px] px-2 py-1 rounded-full bg-gray-100 text-gray-600 hover:bg-gray-200 truncate max-w-[180px]">{c}</button>
                ))}
              </div>

              <div className="px-4 py-3 border-t border-gray-100">
                <label className="flex items-center gap-1.5 text-[11px] text-gray-500 mb-1.5 cursor-pointer">
                  <input type="checkbox" checked={internalNote} onChange={(e) => setInternalNote(e.target.checked)} className="accent-yellow-500" />
                  🔒 Internal note (not shown to the user)
                </label>
                <div className="flex items-center gap-2">
                  <input value={reply} onChange={(e) => setReply(e.target.value)}
                    onKeyDown={(e) => { if (e.key === 'Enter' && !sending) handleReply() }}
                    placeholder={internalNote ? 'Add an internal note…' : 'Type a reply…'}
                    className={`flex-1 px-3 py-2 border rounded-lg text-sm outline-none focus:border-emerald-400 ${internalNote ? 'bg-yellow-50 border-yellow-200' : 'border-gray-200'}`} />
                  <button onClick={() => handleReply()} disabled={sending || !reply.trim()}
                    className="px-3 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white text-sm font-medium">Send</button>
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
