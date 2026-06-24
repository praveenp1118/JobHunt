"""
RSS feed reader — fetches and parses RSS/Atom job feeds.
Returns normalised job dicts (same format as Apify output).
"""
import asyncio
from datetime import datetime, timezone
from typing import Optional
import httpx
import xml.etree.ElementTree as ET
import re


RSS_NAMESPACES = {
    "dc": "http://purl.org/dc/elements/1.1/",
    "content": "http://purl.org/rss/1.0/modules/content/",
    "atom": "http://www.w3.org/2005/Atom",
}


async def fetch_rss_feed(url: str, max_items: int = 30) -> list[dict]:
    """
    Fetch and parse an RSS or Atom feed.
    Returns list of normalised job dicts.
    """
    headers = {
        "User-Agent": "JobHunt RSS Scanner/1.0",
        "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml",
    }

    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        try:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            content = response.text
        except Exception as e:
            raise ValueError(f"RSS fetch failed for {url}: {e}")

    jobs = _parse_feed(content, max_items)
    print(f"📡 RSS {url[:60]}: {len(jobs)} items")
    return jobs


def _parse_feed(content: str, max_items: int) -> list[dict]:
    """Parse RSS or Atom XML content."""
    try:
        root = ET.fromstring(content)
    except ET.ParseError as e:
        raise ValueError(f"XML parse error: {e}")

    # Detect RSS vs Atom
    tag = root.tag.lower()
    if "feed" in tag:
        return _parse_atom(root, max_items)
    else:
        return _parse_rss(root, max_items)


def _parse_rss(root: ET.Element, max_items: int) -> list[dict]:
    """Parse RSS 2.0 format."""
    jobs = []
    channel = root.find("channel")
    if channel is None:
        return []

    items = channel.findall("item")[:max_items]
    for item in items:
        try:
            job = _rss_item_to_job(item)
            if job:
                jobs.append(job)
        except Exception:
            continue
    return jobs


def _parse_atom(root: ET.Element, max_items: int) -> list[dict]:
    """Parse Atom format."""
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    jobs = []
    entries = root.findall("atom:entry", ns) or root.findall("entry")
    for entry in entries[:max_items]:
        try:
            job = _atom_entry_to_job(entry, ns)
            if job:
                jobs.append(job)
        except Exception:
            continue
    return jobs


def _rss_item_to_job(item: ET.Element) -> Optional[dict]:
    """Convert RSS item to job dict."""
    title = _get_text(item, "title") or ""
    link = _get_text(item, "link") or ""
    description = _get_text(item, "description") or ""
    pub_date = _get_text(item, "pubDate") or ""

    # Parse role from title; resolve company via the fallback chain.
    role, company_from_title = _parse_title(title)
    if not role:
        return None

    # Prefer the full JD in <content:encoded>; fall back to the short <description>.
    full = _find_local(item, "encoded") or description
    clean_desc = _strip_html(full)[:20000]
    company = _extract_company(item, company_from_title, clean_desc)

    return {
        "role": role,
        "company": company or "Unknown",
        "location": _find_local(item, "location") or _extract_location(clean_desc, title),
        "description": clean_desc,
        "url": link,
        "salary": "",
        "posted_at": pub_date,
        "source": "rss",
    }


def _atom_entry_to_job(entry: ET.Element, ns: dict) -> Optional[dict]:
    """Convert Atom entry to job dict."""
    title = _get_text(entry, "title") or _get_ns_text(entry, "atom:title", ns) or ""
    link_el = entry.find("atom:link", ns) or entry.find("link")
    link = link_el.get("href", "") if link_el is not None else ""
    summary = _get_text(entry, "summary") or _get_ns_text(entry, "atom:summary", ns) or ""
    published = _get_text(entry, "published") or _get_ns_text(entry, "atom:published", ns) or ""

    role, company_from_title = _parse_title(title)
    if not role:
        return None

    full = _find_local(entry, "encoded") or _find_local(entry, "content") or summary
    clean_desc = _strip_html(full)[:20000]
    company = _extract_company(entry, company_from_title, clean_desc)
    return {
        "role": role,
        "company": company or "Unknown",
        "location": _find_local(entry, "location") or _extract_location(clean_desc, title),
        "description": clean_desc,
        "url": link,
        "salary": "",
        "posted_at": published,
        "source": "rss",
    }


def _parse_title(title: str) -> tuple[str, str]:
    """Extract role and company from title like 'Head of Product at Adyen'."""
    title = title.strip()
    if not title:
        return "", ""

    # Common separators (NOT en-dash — feeds like Jobicy use '–' inside the role
    # itself, e.g. 'Technical PM – AI Compute Platform'; their company is a field).
    for sep in [" at ", " | ", " @ ", " · "]:
        if sep in title:
            parts = title.split(sep, 1)
            return parts[0].strip(), parts[1].strip()

    # No separator found — assume whole title is role
    return title, ""


def _find_local(el: ET.Element, localname: str) -> Optional[str]:
    """Find a child element by local tag name, ignoring namespace.
    Handles feed-specific fields like Jobicy's <job_listing:company>."""
    for child in el:
        tag = child.tag.split("}")[-1].lower()  # strip {namespace}
        if tag == localname and child.text and child.text.strip():
            return child.text.strip()
    return None


def _clean_company(value: str) -> str:
    """Normalise a candidate company string; reject obvious non-companies."""
    if not value:
        return ""
    c = re.sub(r"\s+", " ", _strip_html(value)).strip(" -–|·,").strip()
    # Reject URLs, emails, or absurdly long strings (likely a sentence, not a name).
    if not c or len(c) > 80 or "http" in c.lower() or "@" in c:
        return ""
    return c


def _company_from_desc(desc: str) -> str:
    """Last resort — pull a company from the JD opening, e.g. 'About Nebius:'."""
    if not desc:
        return ""
    m = re.match(r"\s*About\s+([A-Z][\w&.\-' ]{1,40}?)[:,.]", desc)
    if m:
        return _clean_company(m.group(1))
    return ""


def _extract_company(item: ET.Element, company_from_title: str, clean_desc: str) -> str:
    """Resolve the employer name with a fallback chain:
    1. explicit feed fields (company / dc:creator / author / source)
    2. 'Role at Company' parsed from the title
    3. 'About <Company>:' in the JD opening."""
    for name in ("company", "creator", "author", "source"):
        c = _clean_company(_find_local(item, name) or "")
        if c:
            return c
    if company_from_title:
        c = _clean_company(company_from_title)
        if c:
            return c
    return _company_from_desc(clean_desc)


def _extract_location(description: str, title: str) -> str:
    """Simple location extraction from description."""
    combined = f"{description} {title}".lower()
    locations = [
        ("Netherlands", "NL"), ("Amsterdam", "NL"), ("Rotterdam", "NL"),
        ("Dubai", "Dubai"), ("UAE", "Dubai"),
        ("Singapore", "SG"),
        ("Bengaluru", "IN"), ("Bangalore", "IN"), ("Mumbai", "IN"), ("Delhi", "IN"),
        ("Berlin", "EU"), ("London", "EU"), ("Paris", "EU"),
    ]
    for location_name, _ in locations:
        if location_name.lower() in combined:
            return location_name
    return ""


def _get_text(el: ET.Element, tag: str) -> Optional[str]:
    child = el.find(tag)
    if child is not None and child.text:
        return child.text.strip()
    return None


def _get_ns_text(el: ET.Element, path: str, ns: dict) -> Optional[str]:
    child = el.find(path, ns)
    if child is not None and child.text:
        return child.text.strip()
    return None


def _strip_html(text: str) -> str:
    """Strip HTML tags and normalise whitespace."""
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()
