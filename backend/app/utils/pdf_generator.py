"""
PDF generator — converts markdown CV and cover letter to PDF via Playwright.
Chromium is already installed in the Docker image.
"""
import markdown as md_lib
from typing import Optional


# ── CV HTML template ──────────────────────────────────────────────────────────

CV_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
    font-family: 'Segoe UI', Arial, Helvetica, sans-serif;
    font-size: 10.5pt;
    line-height: 1.55;
    color: #1a1a2e;
    background: white;
}
.page { max-width: 760px; margin: 0 auto; padding: 28px 32px; }

/* Name / header */
h1 {
    font-size: 20pt;
    font-weight: 700;
    color: #1a1a2e;
    margin-bottom: 2px;
    letter-spacing: -0.3px;
}

/* Section headers (##) */
h2 {
    font-size: 10pt;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 1.2px;
    color: #1d9e75;
    margin-top: 18px;
    margin-bottom: 6px;
    padding-bottom: 3px;
    border-bottom: 1.5px solid #e5f7f1;
}

/* Role headers (###) */
h3 {
    font-size: 10.5pt;
    font-weight: 600;
    color: #1a1a2e;
    margin-top: 8px;
    margin-bottom: 1px;
}

p {
    margin-bottom: 4px;
    color: #2d2d44;
}

/* Contact line (first paragraph after h1) */
h1 + p {
    font-size: 9.5pt;
    color: #5a5a72;
    margin-bottom: 8px;
}

/* Tagline (second paragraph) */
h1 + p + p {
    font-size: 10pt;
    color: #3d3d5c;
    font-style: italic;
    margin-bottom: 0;
}

ul {
    margin: 3px 0 6px 0;
    padding-left: 16px;
}

li {
    margin-bottom: 2px;
    font-size: 10pt;
    color: #2d2d44;
    line-height: 1.5;
}

strong {
    font-weight: 600;
    color: #1a1a2e;
}

/* Horizontal rule between sections */
hr {
    border: none;
    border-top: 1px solid #f0f0f0;
    margin: 10px 0;
}

/* Skills section — inline */
h2:last-of-type + ul,
h2:last-of-type + p {
    font-size: 10pt;
}

@page {
    margin: 15mm 12mm;
    size: A4;
}
"""

CV_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width">
<style>{css}</style>
</head>
<body>
<div class="page">
{content}
</div>
</body>
</html>"""


# ── Cover Letter HTML template ────────────────────────────────────────────────

CL_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
    font-family: 'Segoe UI', Arial, Helvetica, sans-serif;
    font-size: 11pt;
    line-height: 1.7;
    color: #1a1a2e;
    background: white;
}
.page { max-width: 680px; margin: 0 auto; padding: 40px 36px; }

.header {
    border-bottom: 2px solid #1d9e75;
    padding-bottom: 12px;
    margin-bottom: 28px;
}
.name { font-size: 16pt; font-weight: 700; color: #1a1a2e; }
.contact { font-size: 9.5pt; color: #5a5a72; margin-top: 3px; }
.date { font-size: 10pt; color: #5a5a72; margin-bottom: 20px; }

.body p {
    margin-bottom: 14px;
    font-size: 11pt;
    color: #2d2d44;
    text-align: justify;
}

.signature {
    margin-top: 28px;
    font-size: 11pt;
    color: #1a1a2e;
}
.sig-name { font-weight: 600; font-size: 12pt; margin-top: 4px; }

@page { margin: 20mm 15mm; size: A4; }
"""

CL_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<style>{css}</style>
</head>
<body>
<div class="page">
  <div class="header">
    <div class="name">{name}</div>
    <div class="contact">{contact}</div>
  </div>
  <div class="date">{date}</div>
  <div class="body">{content}</div>
  <div class="signature">
    <div>Yours sincerely,</div>
    <div class="sig-name">{name}</div>
  </div>
</div>
</body>
</html>"""


# ── Core generator ────────────────────────────────────────────────────────────

async def _html_to_pdf(html: str) -> bytes:
    """Run Playwright in a thread (to avoid blocking asyncio event loop)."""
    import asyncio
    return await asyncio.to_thread(_sync_html_to_pdf, html)


def _sync_html_to_pdf(html: str) -> bytes:
    """Synchronous Playwright call — runs in thread pool."""
    import subprocess, tempfile, os

    # Use playwright CLI to avoid async event loop issues
    with tempfile.NamedTemporaryFile(suffix='.html', delete=False, mode='w', encoding='utf-8') as f:
        f.write(html)
        html_path = f.name

    pdf_path = html_path.replace('.html', '.pdf')

    try:
        result = subprocess.run(
            ['python', '-m', 'playwright', 'pdf', html_path, pdf_path],
            capture_output=True,
            timeout=30,
        )
        if result.returncode != 0:
            # Fallback: use direct Playwright Python API
            return _playwright_api_pdf(html)

        with open(pdf_path, 'rb') as f:
            return f.read()
    except Exception:
        return _playwright_api_pdf(html)
    finally:
        for p in [html_path, pdf_path]:
            if os.path.exists(p):
                os.unlink(p)


def _playwright_api_pdf(html: str) -> bytes:
    """Direct Playwright Python API PDF generation."""
    import asyncio

    async def _generate():
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            browser = await p.chromium.launch(args=['--no-sandbox', '--disable-dev-shm-usage'])
            page = await browser.new_page()
            await page.set_content(html, wait_until='domcontentloaded')
            pdf_bytes = await page.pdf(
                format='A4',
                margin={'top': '12mm', 'bottom': '12mm', 'left': '10mm', 'right': '10mm'},
                print_background=True,
            )
            await browser.close()
            return pdf_bytes

    # Run in new event loop since we're in a thread
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_generate())
    finally:
        loop.close()


async def cv_md_to_pdf(content_md: str) -> bytes:
    """Convert markdown CV to PDF bytes."""
    # Convert markdown to HTML
    html_body = md_lib.markdown(
        content_md,
        extensions=['tables', 'extra', 'nl2br'],
    )
    full_html = CV_TEMPLATE.format(css=CV_CSS, content=html_body)
    return await _html_to_pdf(full_html)


async def cl_md_to_pdf(
    content_md: str,
    user_name: str = "Candidate",
    user_contact: str = "",
) -> bytes:
    """Convert markdown cover letter to PDF bytes."""
    from datetime import date

    # Convert paragraphs
    paragraphs = [p.strip() for p in content_md.strip().split('\n\n') if p.strip()]
    html_body = ''.join(f'<p>{p.replace(chr(10), " ")}</p>' for p in paragraphs)

    full_html = CL_TEMPLATE.format(
        css=CL_CSS,
        name=user_name,
        contact=user_contact,
        date=date.today().strftime('%B %d, %Y'),
        content=html_body,
    )
    return await _html_to_pdf(full_html)
