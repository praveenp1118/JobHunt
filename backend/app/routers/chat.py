"""
Support chat router — rule-based FAQ bot + human admin. NO Claude/AI.

REST endpoints for conversations, messages, tickets, and admin presence.
The WebSocket layer (real-time push) lives at the bottom of this file.
"""
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, UploadFile, File
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User, UserRole
from app.models.chat import ChatConversation, ChatMessage, ChatTicket, AdminPresence
from app.auth.dependencies import optional_user, require_admin
from app.utils.chat_faq import match_faq, get_no_match_response

router = APIRouter()

PRESENCE_TIMEOUT = timedelta(minutes=5)

MAX_UPLOAD = 5 * 1024 * 1024  # 5 MB
ATTACH_DIR = "chat_attachments"
ALLOWED_UPLOAD_TYPES = {
    "image/png", "image/jpeg", "image/jpg", "image/gif", "image/webp",
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ── Serialization helpers ─────────────────────────────────────────────────────
def _msg(m: ChatMessage) -> dict:
    return {
        "id": str(m.id),
        "conversation_id": str(m.conversation_id),
        "sender_id": str(m.sender_id) if m.sender_id else None,
        "sender_type": m.sender_type,
        "content": m.content,
        "message_type": m.message_type,
        "attachment_url": m.attachment_url,
        "attachment_name": m.attachment_name,
        "attachment_size": m.attachment_size,
        "is_internal_note": m.is_internal_note,
        "read_at": m.read_at.isoformat() if m.read_at else None,
        "created_at": m.created_at.isoformat() if m.created_at else None,
    }


def _conv(c: ChatConversation, messages=None, unread=0, last_message=None) -> dict:
    d = {
        "id": str(c.id),
        "user_id": str(c.user_id) if c.user_id else None,
        "guest_name": c.guest_name,
        "guest_email": c.guest_email,
        "status": c.status,
        "category": c.category,
        "assigned_to": str(c.assigned_to) if c.assigned_to else None,
        "is_guest": c.is_guest,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
        "unread": unread,
    }
    if messages is not None:
        d["messages"] = [_msg(m) for m in messages]
    if last_message is not None:
        d["last_message"] = last_message
    return d


def _ticket(t: ChatTicket) -> dict:
    return {
        "id": str(t.id),
        "conversation_id": str(t.conversation_id),
        "ticket_number": t.ticket_number,
        "title": t.title,
        "status": t.status,
        "priority": t.priority,
        "category": t.category,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "resolved_at": t.resolved_at.isoformat() if t.resolved_at else None,
    }


async def admin_online(session: AsyncSession):
    """Any admin online = is_online AND last_seen within PRESENCE_TIMEOUT.
    Returns (online: bool, last_seen: datetime|None)."""
    rows = (await session.execute(select(AdminPresence))).scalars().all()
    cutoff = _now() - PRESENCE_TIMEOUT
    online = any(p.is_online and p.last_seen and p.last_seen >= cutoff for p in rows)
    last_seen = max((p.last_seen for p in rows if p.last_seen), default=None)
    return online, last_seen


async def _next_ticket_number(session: AsyncSession) -> str:
    count = (await session.execute(select(func.count(ChatTicket.id)))).scalar() or 0
    return f"JH-{count + 1:03d}"


# ── Request bodies ────────────────────────────────────────────────────────────
class CreateConversation(BaseModel):
    guest_name: Optional[str] = None
    guest_email: Optional[str] = None
    first_message: str


class CreateMessage(BaseModel):
    content: str = ""
    message_type: str = "text"
    attachment_url: Optional[str] = None
    attachment_name: Optional[str] = None
    attachment_size: Optional[int] = None
    is_internal_note: bool = False


class CreateTicket(BaseModel):
    conversation_id: uuid.UUID
    title: Optional[str] = None
    priority: str = "medium"


class UpdateTicket(BaseModel):
    status: Optional[str] = None
    priority: Optional[str] = None


class PresenceUpdate(BaseModel):
    is_online: bool


# ── Conversations ─────────────────────────────────────────────────────────────
@router.post("/conversations")
async def create_conversation(
    body: CreateConversation,
    user: Optional[User] = Depends(optional_user),
    session: AsyncSession = Depends(get_db),
):
    """Start a conversation (guests allowed). Saves the first message and, if no admin
    is online, an automatic FAQ-bot reply."""
    is_guest = user is None
    conv = ChatConversation(
        user_id=(user.id if user else None),
        guest_name=(body.guest_name if is_guest else (user.name if user else None)),
        guest_email=(body.guest_email if is_guest else (user.email if user else None)),
        is_guest=is_guest,
        status="open",
    )
    session.add(conv)
    await session.flush()

    session.add(ChatMessage(
        conversation_id=conv.id, sender_id=(user.id if user else None),
        sender_type=("guest" if is_guest else "user"), content=body.first_message))

    online, _ = await admin_online(session)
    bot_response = None
    if not online:
        rule = match_faq(body.first_message)
        if rule:
            conv.category = rule["category"]
            session.add(ChatMessage(conversation_id=conv.id, sender_type="bot", content=rule["answer"]))
            bot_response = {"content": rule["answer"], "links": rule.get("links", [])}
        else:
            answer = get_no_match_response()
            session.add(ChatMessage(conversation_id=conv.id, sender_type="bot", content=answer))
            bot_response = {"content": answer, "no_match": True}

    await session.commit()
    return {"conversation_id": str(conv.id), "bot_response": bot_response, "admin_online": online}


@router.get("/conversations")
async def list_conversations(
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
):
    """Admin: all conversations with per-conversation unread counts (newest activity first)."""
    filters = []
    if status:
        filters.append(ChatConversation.status == status)
    convs = (await session.execute(
        select(ChatConversation).where(*filters)
        .order_by(ChatConversation.updated_at.desc()).offset(offset).limit(limit)
    )).scalars().all()

    out = []
    for c in convs:
        unread = (await session.execute(select(func.count(ChatMessage.id)).where(
            ChatMessage.conversation_id == c.id,
            ChatMessage.sender_type.in_(["user", "guest"]),
            ChatMessage.read_at.is_(None),
        ))).scalar() or 0
        last = (await session.execute(
            select(ChatMessage).where(ChatMessage.conversation_id == c.id)
            .order_by(ChatMessage.created_at.desc()).limit(1)
        )).scalars().first()
        out.append(_conv(c, unread=unread, last_message=(_msg(last) if last else None)))

    return {"conversations": out, "total_unread": sum(o["unread"] for o in out)}


async def _load_conversation(conversation_id, user, session):
    conv = (await session.execute(
        select(ChatConversation).where(ChatConversation.id == conversation_id)
    )).scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    is_admin = bool(user and user.role == UserRole.admin)
    is_owner = bool(user and conv.user_id == user.id)
    # Guests have only the conversation UUID, which is sufficient to access their own thread.
    if not (is_admin or is_owner or conv.is_guest):
        raise HTTPException(status_code=403, detail="Not your conversation")
    return conv, is_admin


@router.get("/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: uuid.UUID,
    user: Optional[User] = Depends(optional_user),
    session: AsyncSession = Depends(get_db),
):
    conv, is_admin = await _load_conversation(conversation_id, user, session)
    msgs = (await session.execute(
        select(ChatMessage).where(ChatMessage.conversation_id == conv.id)
        .order_by(ChatMessage.created_at)
    )).scalars().all()
    if not is_admin:
        msgs = [m for m in msgs if not m.is_internal_note]  # hide internal notes
    return _conv(conv, messages=msgs)


@router.post("/conversations/{conversation_id}/messages")
async def post_message(
    conversation_id: uuid.UUID,
    body: CreateMessage,
    user: Optional[User] = Depends(optional_user),
    session: AsyncSession = Depends(get_db),
):
    conv, is_admin = await _load_conversation(conversation_id, user, session)
    sender_type = "admin" if is_admin else ("user" if user else "guest")

    msg = ChatMessage(
        conversation_id=conv.id,
        sender_id=(user.id if user else None),
        sender_type=sender_type,
        content=body.content,
        message_type=body.message_type,
        attachment_url=body.attachment_url,
        attachment_name=body.attachment_name,
        attachment_size=body.attachment_size,
        is_internal_note=(body.is_internal_note if is_admin else False),
    )
    session.add(msg)
    conv.updated_at = _now()
    if is_admin and conv.status == "open":
        conv.status = "in_progress"
    await session.flush()

    # FAQ bot only for user/guest messages when no admin is online (and not file-only).
    bot_response = None
    bot_msg_obj = None
    if sender_type in ("user", "guest") and body.content.strip():
        online, _ = await admin_online(session)
        if not online:
            rule = match_faq(body.content)
            if rule:
                conv.category = conv.category or rule["category"]
                bot_msg_obj = ChatMessage(conversation_id=conv.id, sender_type="bot", content=rule["answer"])
                session.add(bot_msg_obj)
                bot_response = {"content": rule["answer"], "links": rule.get("links", [])}
            else:
                answer = get_no_match_response()
                bot_msg_obj = ChatMessage(conversation_id=conv.id, sender_type="bot", content=answer)
                session.add(bot_msg_obj)
                bot_response = {"content": answer, "no_match": True}

    await session.commit()
    await session.refresh(msg)
    # Real-time push to anyone watching this conversation (the other party).
    await manager.send_to_conversation(str(conversation_id), {"type": "message", "data": _msg(msg)})
    if bot_msg_obj is not None:
        await session.refresh(bot_msg_obj)
        await manager.send_to_conversation(str(conversation_id), {"type": "message", "data": _msg(bot_msg_obj)})

    # Email the user/guest when an admin replies (fallback notification for an offline user).
    if sender_type == "admin" and not msg.is_internal_note and conv.guest_email:
        try:
            from app.utils.email import send_chat_reply_email
            tk = (await session.execute(
                select(ChatTicket.ticket_number).where(ChatTicket.conversation_id == conv.id)
                .order_by(ChatTicket.created_at.desc()).limit(1))).scalars().first()
            await send_chat_reply_email(conv.guest_email, tk, body.content)
        except Exception as e:
            print(f"⚠️ chat reply email failed: {e}")

    return {"message": _msg(msg), "bot_response": bot_response}


@router.post("/conversations/{conversation_id}/messages/{message_id}/read")
async def mark_read(
    conversation_id: uuid.UUID,
    message_id: uuid.UUID,
    user: Optional[User] = Depends(optional_user),
    session: AsyncSession = Depends(get_db),
):
    await _load_conversation(conversation_id, user, session)
    msg = (await session.execute(
        select(ChatMessage).where(ChatMessage.id == message_id,
                                  ChatMessage.conversation_id == conversation_id)
    )).scalar_one_or_none()
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")
    if not msg.read_at:
        msg.read_at = _now()
        await session.commit()
    return {"status": "ok", "read_at": msg.read_at.isoformat() if msg.read_at else None}


class UpdateConversation(BaseModel):
    status: Optional[str] = None
    category: Optional[str] = None


@router.patch("/conversations/{conversation_id}")
async def update_conversation(
    conversation_id: uuid.UUID,
    body: UpdateConversation,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
):
    """Admin: update conversation status (resolve/close) / category."""
    conv = (await session.execute(
        select(ChatConversation).where(ChatConversation.id == conversation_id)
    )).scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if body.status:
        conv.status = body.status
    if body.category:
        conv.category = body.category
    conv.assigned_to = admin.id
    await session.commit()
    return _conv(conv)


# ── Tickets ───────────────────────────────────────────────────────────────────
@router.post("/tickets")
async def create_ticket(
    body: CreateTicket,
    user: Optional[User] = Depends(optional_user),
    session: AsyncSession = Depends(get_db),
):
    conv, _ = await _load_conversation(body.conversation_id, user, session)
    if body.title:
        title = body.title
    else:
        first = (await session.execute(
            select(ChatMessage).where(
                ChatMessage.conversation_id == conv.id,
                ChatMessage.sender_type.in_(["user", "guest"]),
            ).order_by(ChatMessage.created_at).limit(1)
        )).scalars().first()
        title = (first.content[:120] if first else "Support request")

    number = await _next_ticket_number(session)
    ticket = ChatTicket(
        conversation_id=conv.id, ticket_number=number, title=title,
        priority=body.priority, category=conv.category, status="open")
    session.add(ticket)
    session.add(ChatMessage(
        conversation_id=conv.id, sender_type="system", message_type="system",
        content=f"Ticket {number} created. We'll respond within 24 hours."))
    await session.commit()
    await session.refresh(ticket)
    try:
        from app.utils.email import send_chat_ticket_email
        await send_chat_ticket_email(number, title, conv.guest_name or "User", title)
    except Exception as e:
        print(f"⚠️ ticket email failed: {e}")
    return {"ticket_number": number, "ticket_id": str(ticket.id), "title": title}


@router.get("/tickets")
async def list_tickets(
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
):
    rows = (await session.execute(
        select(ChatTicket).order_by(ChatTicket.created_at.desc())
    )).scalars().all()
    return [_ticket(t) for t in rows]


@router.patch("/tickets/{ticket_id}")
async def update_ticket(
    ticket_id: uuid.UUID,
    body: UpdateTicket,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
):
    t = (await session.execute(select(ChatTicket).where(ChatTicket.id == ticket_id))).scalar_one_or_none()
    if not t:
        raise HTTPException(status_code=404, detail="Ticket not found")
    if body.status:
        t.status = body.status
        if body.status in ("resolved", "closed") and not t.resolved_at:
            t.resolved_at = _now()
    if body.priority:
        t.priority = body.priority
    await session.commit()
    await session.refresh(t)
    return _ticket(t)


# ── Presence ──────────────────────────────────────────────────────────────────
@router.post("/presence")
async def update_presence(
    body: PresenceUpdate,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
):
    p = (await session.execute(
        select(AdminPresence).where(AdminPresence.admin_id == admin.id)
    )).scalar_one_or_none()
    if not p:
        p = AdminPresence(admin_id=admin.id, is_online=body.is_online, last_seen=_now())
        session.add(p)
    else:
        p.is_online = body.is_online
        p.last_seen = _now()
    await session.commit()
    return {"is_online": body.is_online, "last_seen": _now().isoformat()}


@router.get("/presence")
async def get_presence(session: AsyncSession = Depends(get_db)):
    """Public — the chat widget polls this to show the online/offline indicator.
    Honours the 5-minute auto-timeout (a stale last_seen counts as offline)."""
    online, last_seen = await admin_online(session)
    return {"is_online": online, "last_seen": last_seen.isoformat() if last_seen else None}


# ── File upload ───────────────────────────────────────────────────────────────
@router.post("/upload")
async def upload_attachment(
    file: UploadFile = File(...),
    user: Optional[User] = Depends(optional_user),
):
    """Upload a chat attachment (guests allowed). Max 5 MB; images / PDF / doc / docx.
    Returns {url, name, size, type} — the url is passed back as the message attachment."""
    content = await file.read()
    if len(content) > MAX_UPLOAD:
        raise HTTPException(status_code=413, detail="File too large (max 5 MB)")
    ctype = (file.content_type or "").lower()
    if ctype not in ALLOWED_UPLOAD_TYPES:
        raise HTTPException(status_code=415, detail=f"Unsupported file type: {ctype or 'unknown'}")
    from app.utils.input_validator import validate_file_type, CHAT_ALLOWED_TYPES
    if not validate_file_type(file.filename or "", CHAT_ALLOWED_TYPES):
        raise HTTPException(status_code=415, detail="Unsupported file extension")

    import re as _re
    from app.utils.storage import save_binary_file
    safe_name = _re.sub(r"[^\w.\-]", "_", file.filename or "file")[:120]
    stored = f"{uuid.uuid4().hex}_{safe_name}"
    await save_binary_file(content, f"{ATTACH_DIR}/{stored}")
    return {
        "url": f"/api/chat/attachments/{stored}",
        "name": file.filename,
        "size": len(content),
        "type": ctype,
    }


@router.get("/attachments/{filename}")
async def get_attachment(filename: str):
    """Serve a chat attachment. The stored name is UUID-prefixed (unguessable)."""
    from pathlib import Path
    safe = Path(filename).name  # strip any path traversal
    full = Path("/app/storage") / ATTACH_DIR / safe
    if not full.exists():
        raise HTTPException(status_code=404, detail="Attachment not found")
    return FileResponse(str(full))


# ── WebSocket (real-time push) ────────────────────────────────────────────────
class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[str, list[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, conversation_id: str):
        await websocket.accept()
        self.active_connections.setdefault(conversation_id, []).append(websocket)

    def disconnect(self, websocket: WebSocket, conversation_id: str):
        conns = self.active_connections.get(conversation_id)
        if conns and websocket in conns:
            conns.remove(websocket)
        if conns is not None and not conns:
            self.active_connections.pop(conversation_id, None)

    async def send_to_conversation(self, conversation_id, message: dict):
        for ws in list(self.active_connections.get(str(conversation_id), [])):
            try:
                await ws.send_json(message)
            except Exception:
                pass

    async def broadcast_to_admins(self, message: dict):
        # No dedicated admin-socket registry — best-effort broadcast to all open sockets.
        for conns in list(self.active_connections.values()):
            for ws in list(conns):
                try:
                    await ws.send_json(message)
                except Exception:
                    pass


manager = ConnectionManager()


async def chat_websocket(websocket: WebSocket, conversation_id: str):
    """Real-time channel for one conversation. Relays client events (typing/read/…)
    to the other participants; REST message saves are pushed here by the router.
    Registered on the app at /ws/chat/{conversation_id} (see main.py)."""
    await manager.connect(websocket, conversation_id)
    try:
        while True:
            data = await websocket.receive_json()
            await manager.send_to_conversation(conversation_id, data)
    except WebSocketDisconnect:
        manager.disconnect(websocket, conversation_id)
    except Exception:
        manager.disconnect(websocket, conversation_id)
