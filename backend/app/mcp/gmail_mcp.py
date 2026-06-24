"""
Gmail MCP — IMAP polling and SMTP sending.
Reuses BloomDirect pattern: IMAP for reading, SMTP for sending.

Test mode: all outgoing emails redirect to notification_email.
Prod mode: emails go to real recruiter addresses.
"""
import asyncio
import email as email_lib
import email.header
import email.utils
from datetime import datetime, timezone
from typing import Optional
import aiofiles

from app.config import settings


# ── Email data model ──────────────────────────────────────────────────────────

class EmailMessage:
    def __init__(self):
        self.uid: str = ""
        self.message_id: str = ""
        self.subject: str = ""
        self.from_email: str = ""
        self.from_name: str = ""
        self.to_email: str = ""
        self.body_text: str = ""
        self.body_html: str = ""
        self.received_at: Optional[datetime] = None
        self.has_attachments: bool = False
        self.in_reply_to: Optional[str] = None
        self.references: list[str] = []

    def body_preview(self, chars: int = 500) -> str:
        text = self.body_text or self.body_html or ""
        # Strip HTML tags for preview
        import re
        text = re.sub(r"<[^>]+>", " ", text)
        text = " ".join(text.split())
        return text[:chars]


# ── IMAP Client ───────────────────────────────────────────────────────────────

async def poll_inbox(
    gmail_address: str,
    app_password: str,
    since_dt: Optional[datetime] = None,
    max_emails: int = 50,
) -> list[EmailMessage]:
    """
    Poll Gmail inbox via IMAP.
    Returns list of unread EmailMessage objects since since_dt.
    Uses asyncio.to_thread to avoid blocking the event loop.
    """
    return await asyncio.to_thread(
        _poll_inbox_sync,
        gmail_address,
        app_password,
        since_dt,
        max_emails,
    )


def _poll_inbox_sync(
    gmail_address: str,
    app_password: str,
    since_dt: Optional[datetime],
    max_emails: int,
) -> list[EmailMessage]:
    """Synchronous IMAP poll — runs in thread pool."""
    import imaplib
    import re

    messages = []

    try:
        imap = imaplib.IMAP4_SSL("imap.gmail.com", 993)
        imap.login(gmail_address, app_password)
        imap.select("INBOX")

        # Build search criteria
        if since_dt:
            date_str = since_dt.strftime("%d-%b-%Y")
            status, uids = imap.uid("search", None, f"SINCE {date_str} UNSEEN")
        else:
            status, uids = imap.uid("search", None, "UNSEEN")

        if status != "OK" or not uids[0]:
            imap.logout()
            return []

        uid_list = uids[0].split()[-max_emails:]  # most recent first

        for uid in reversed(uid_list):
            try:
                status, data = imap.uid("fetch", uid, "(RFC822)")
                if status != "OK" or not data or data[0] is None:
                    continue

                raw = data[0][1]
                msg = _parse_raw_email(raw)
                msg.uid = uid.decode() if isinstance(uid, bytes) else uid
                messages.append(msg)

            except Exception as e:
                print(f"⚠️ Failed to fetch email UID {uid}: {e}")
                continue

        imap.logout()

    except imaplib.IMAP4.error as e:
        raise ConnectionError(f"Gmail IMAP error: {e}")
    except Exception as e:
        raise ConnectionError(f"Gmail connection failed: {e}")

    return messages


def _parse_raw_email(raw_bytes: bytes) -> EmailMessage:
    """Parse raw RFC822 bytes into EmailMessage."""
    msg_obj = email_lib.message_from_bytes(raw_bytes)
    result = EmailMessage()

    # Message-ID
    result.message_id = msg_obj.get("Message-ID", "").strip()

    # Subject (decode encoded headers)
    subject_raw = msg_obj.get("Subject", "")
    decoded_parts = email.header.decode_header(subject_raw)
    subject_parts = []
    for part, charset in decoded_parts:
        if isinstance(part, bytes):
            subject_parts.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            subject_parts.append(part)
    result.subject = "".join(subject_parts)

    # From
    from_raw = msg_obj.get("From", "")
    result.from_name, result.from_email = email.utils.parseaddr(from_raw)

    # To
    result.to_email = msg_obj.get("To", "")

    # Date
    date_raw = msg_obj.get("Date", "")
    try:
        result.received_at = email.utils.parsedate_to_datetime(date_raw)
    except Exception:
        result.received_at = datetime.now(timezone.utc)

    # Thread references
    result.in_reply_to = msg_obj.get("In-Reply-To", "").strip() or None
    refs = msg_obj.get("References", "")
    result.references = [r.strip() for r in refs.split() if r.strip()]

    # Body extraction
    if msg_obj.is_multipart():
        for part in msg_obj.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition", ""))

            if "attachment" in content_disposition:
                result.has_attachments = True
                continue

            charset = part.get_content_charset() or "utf-8"
            try:
                payload = part.get_payload(decode=True)
                if payload is None:
                    continue
                text = payload.decode(charset, errors="replace")
                if content_type == "text/plain" and not result.body_text:
                    result.body_text = text[:5000]
                elif content_type == "text/html" and not result.body_html:
                    # Keep a large window of HTML — job-alert digests put their
                    # links well past the first few KB (V3 link extraction needs them).
                    # Only body_preview (500 chars) is persisted, so this is in-memory only.
                    result.body_html = text[:200000]
            except Exception:
                pass
    else:
        charset = msg_obj.get_content_charset() or "utf-8"
        try:
            payload = msg_obj.get_payload(decode=True)
            if payload:
                result.body_text = payload.decode(charset, errors="replace")[:5000]
        except Exception:
            pass

    return result


async def test_imap_connection(gmail_address: str, app_password: str) -> dict:
    """Test IMAP connection. Returns {success, message}."""
    try:
        msgs = await poll_inbox(gmail_address, app_password, max_emails=1)
        return {"success": True, "message": "Connected successfully"}
    except Exception as e:
        return {"success": False, "message": str(e)}


# ── SMTP Client ───────────────────────────────────────────────────────────────

async def send_application_email(
    gmail_address: str,
    app_password: str,
    to_email: str,
    subject: str,
    body: str,
    cv_pdf_path: Optional[str] = None,
    cl_pdf_path: Optional[str] = None,
    test_mode: bool = True,
    test_email: Optional[str] = None,
) -> dict:
    """
    Send application email with CV and CL attachments.

    Test mode: redirects to test_email (safe).
    Prod mode: sends to real recruiter.

    Returns {success, message_id, sent_to}
    """
    import aiosmtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    from email.mime.application import MIMEApplication
    from email.utils import formatdate, make_msgid

    actual_recipient = test_email or settings.notification_email or gmail_address
    if not test_mode:
        actual_recipient = to_email

    msg = MIMEMultipart()
    msg["From"] = f"JobHunt <{gmail_address}>"
    msg["To"] = actual_recipient
    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid()

    if test_mode:
        # Add test mode notice to body
        test_notice = f"<p style='color:orange;font-size:12px'>⚠️ TEST MODE — Would have sent to: {to_email}</p><hr>"
        body = test_notice + body

    msg.attach(MIMEText(body, "html"))

    # Attach CV PDF
    if cv_pdf_path:
        try:
            async with aiofiles.open(f"/app/storage/{cv_pdf_path}", "rb") as f:
                pdf_bytes = await f.read()
            attachment = MIMEApplication(pdf_bytes, _subtype="pdf")
            attachment.add_header(
                "Content-Disposition", "attachment", filename="CV_Praveen_Prakash.pdf"
            )
            msg.attach(attachment)
        except Exception as e:
            print(f"⚠️ Could not attach CV: {e}")

    # Attach CL PDF
    if cl_pdf_path:
        try:
            async with aiofiles.open(f"/app/storage/{cl_pdf_path}", "rb") as f:
                pdf_bytes = await f.read()
            attachment = MIMEApplication(pdf_bytes, _subtype="pdf")
            attachment.add_header(
                "Content-Disposition", "attachment", filename="CoverLetter_Praveen_Prakash.pdf"
            )
            msg.attach(attachment)
        except Exception as e:
            print(f"⚠️ Could not attach cover letter: {e}")

    try:
        await aiosmtplib.send(
            msg,
            hostname="smtp.gmail.com",
            port=587,
            start_tls=True,
            username=gmail_address,
            password=app_password,
        )
        return {
            "success": True,
            "message_id": msg["Message-ID"],
            "sent_to": actual_recipient,
            "test_mode": test_mode,
        }
    except Exception as e:
        return {"success": False, "message_id": None, "error": str(e)}


async def send_reply_email(
    gmail_address: str,
    app_password: str,
    to_email: str,
    subject: str,
    body: str,
    in_reply_to: Optional[str] = None,
    test_mode: bool = True,
    test_email: Optional[str] = None,
) -> dict:
    """Send a reply to a recruiter email (HITL)."""
    import aiosmtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    from email.utils import formatdate, make_msgid

    actual_recipient = test_email or settings.notification_email or gmail_address
    if not test_mode:
        actual_recipient = to_email

    msg = MIMEMultipart()
    msg["From"] = f"{gmail_address}"
    msg["To"] = actual_recipient
    msg["Subject"] = subject if subject.startswith("Re:") else f"Re: {subject}"
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid()
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
        msg["References"] = in_reply_to

    msg.attach(MIMEText(body, "html"))

    try:
        await aiosmtplib.send(
            msg,
            hostname="smtp.gmail.com",
            port=587,
            start_tls=True,
            username=gmail_address,
            password=app_password,
        )
        return {
            "success": True,
            "message_id": msg["Message-ID"],
            "sent_to": actual_recipient,
            "test_mode": test_mode,
        }
    except Exception as e:
        return {"success": False, "message_id": None, "error": str(e)}
