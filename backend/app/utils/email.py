"""
Email utility — used for password reset, verification, and notifications.
In development: logs to console.
In production: sends via Gmail SMTP.
"""
from app.config import settings


async def send_email(to: str, subject: str, body: str) -> None:
    """Send an email. Falls back to console log in development."""
    if settings.env == "development":
        print(f"\n{'='*60}")
        print(f"📧 EMAIL (dev mode — not actually sent)")
        print(f"To: {to}")
        print(f"Subject: {subject}")
        print(f"Body:\n{body}")
        print(f"{'='*60}\n")
        return

    # Production: send via Gmail SMTP
    if not settings.gmail_address or not settings.gmail_app_password:
        print(f"⚠️  Gmail not configured — email to {to} not sent")
        return

    try:
        import aiosmtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"JobHunt <{settings.gmail_address}>"
        msg["To"] = to
        msg.attach(MIMEText(body, "html"))

        await aiosmtplib.send(
            msg,
            hostname="smtp.gmail.com",
            port=587,
            start_tls=True,
            username=settings.gmail_address,
            password=settings.gmail_app_password,
        )
    except Exception as e:
        print(f"❌ Failed to send email to {to}: {e}")


async def send_password_reset_email(email: str, token: str) -> None:
    reset_url = f"{settings.frontend_url}/auth/reset-password?token={token}"
    subject = "JobHunt — Reset your password"
    body = f"""
    <h2>Reset your JobHunt password</h2>
    <p>Click the link below to reset your password. This link expires in 1 hour.</p>
    <p><a href="{reset_url}" style="background:#1D9E75;color:white;padding:10px 20px;border-radius:6px;text-decoration:none">Reset Password</a></p>
    <p>Or copy this URL: {reset_url}</p>
    <p>If you didn't request this, ignore this email.</p>
    <br>
    <p style="color:#9CA3AF;font-size:12px">JobHunt — AI-powered job search</p>
    """
    await send_email(email, subject, body)


async def send_verification_email(email: str, token: str) -> None:
    verify_url = f"{settings.frontend_url}/auth/verify?token={token}"
    subject = "JobHunt — Verify your email"
    body = f"""
    <h2>Verify your JobHunt email</h2>
    <p>Click the link below to verify your email address.</p>
    <p><a href="{verify_url}" style="background:#1D9E75;color:white;padding:10px 20px;border-radius:6px;text-decoration:none">Verify Email</a></p>
    <p>Or copy this URL: {verify_url}</p>
    <br>
    <p style="color:#9CA3AF;font-size:12px">JobHunt — AI-powered job search</p>
    """
    await send_email(email, subject, body)


async def send_notification_email(to: str, subject: str, message: str) -> None:
    """General notification email to personal address."""
    body = f"""
    <div style="font-family:Inter,sans-serif;max-width:500px;margin:0 auto">
      <h3 style="color:#1B2B4B">JobHunt Notification</h3>
      <p>{message}</p>
      <br>
      <p><a href="{settings.frontend_url}" style="color:#1D9E75">Open JobHunt →</a></p>
      <p style="color:#9CA3AF;font-size:12px">JobHunt — AI-powered job search</p>
    </div>
    """
    await send_email(to, subject, body)
