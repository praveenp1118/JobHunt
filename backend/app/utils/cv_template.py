"""
CV Template helpers — merge global + domain override, build the tailor content-rules
prompt, build PDF styles, and check page-budget overflow.
"""

FONTS = [
    {"value": "Calibri",         "label": "Calibri (recommended)"},
    {"value": "Arial",           "label": "Arial"},
    {"value": "Garamond",        "label": "Garamond"},
    {"value": "Georgia",         "label": "Georgia"},
    {"value": "Helvetica",       "label": "Helvetica"},
    {"value": "Times New Roman", "label": "Times New Roman"},
    {"value": "Lato",            "label": "Lato"},
    {"value": "Open Sans",       "label": "Open Sans"},
]

MARGIN_MAP = {
    "narrow": "0.5in",
    "normal": "1in",
    "wide":   "1.25in",
}

WORDS_PER_PAGE = 300

# Sensible defaults used when a user has no template row yet.
DEFAULTS = {
    "font_family": "Calibri", "font_size": 11,
    "heading_font_family": "Calibri", "heading_font_size": 14, "heading_bold": True,
    "margin_size": "normal", "line_spacing": 1.15, "bullet_style": "•", "accent_color": "#1a1a1a",
    "max_pages": 2, "overflow_action": "warn",
    "never_modify_sections": ["EDUCATION", "CERTIFICATIONS"],
    "section_order": ["SUMMARY", "EXPERIENCE", "EDUCATION", "CERTIFICATIONS"],
    "max_words": 600,
}


def compute_max_words(max_pages: int) -> int:
    return int(max_pages) * WORDS_PER_PAGE


def get_effective_template(global_template, domain_override=None) -> dict:
    """Merge the global template with a domain override (override wins where not null).
    `global_template` may be a CVTemplate row or None (→ DEFAULTS)."""
    if global_template is None:
        base = dict(DEFAULTS)
    else:
        base = {
            "font_family": global_template.font_family,
            "font_size": global_template.font_size,
            "heading_font_family": global_template.heading_font_family,
            "heading_font_size": global_template.heading_font_size,
            "heading_bold": global_template.heading_bold,
            "margin_size": global_template.margin_size,
            "line_spacing": global_template.line_spacing,
            "bullet_style": global_template.bullet_style,
            "accent_color": global_template.accent_color,
            "max_pages": global_template.max_pages,
            "overflow_action": global_template.overflow_action,
            "never_modify_sections": global_template.never_modify_sections,
            "section_order": global_template.section_order,
            "max_words": global_template.max_words,
        }

    if domain_override is not None:
        for field in ["font_family", "font_size", "max_pages", "overflow_action",
                      "never_modify_sections", "section_order", "max_words"]:
            val = getattr(domain_override, field, None)
            if val is not None:
                base[field] = val

    return base


def build_content_rules_prompt(template: dict) -> str:
    """The content-rules block injected into the tailor agent's system prompt."""
    never_modify = ", ".join(template.get("never_modify_sections") or [])
    section_order = " → ".join(template.get("section_order") or [])
    return f"""
TEMPLATE RULES — follow strictly:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Page budget: {template["max_pages"]} pages maximum (~{template["max_words"]} words total)
Never modify: {never_modify}
Section order must be preserved: {section_order}
Do NOT add new sections
Do NOT rename section headers
Bullet length: 1-2 lines maximum
Preserve ALL metrics and numbers exactly as written
Preserve the candidate's writing voice and style

If proposed changes exceed the word budget:
  → Prioritise the highest-impact changes
  → Exclude the lowest-impact changes to fit within budget
  → Never exceed {template["max_words"]} words total
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""


def build_pdf_styles(template: dict) -> dict:
    """CSS-variable values for the PDF generator."""
    return {
        "font_family": template["font_family"],
        "font_size": f"{template['font_size']}pt",
        "heading_font": template["heading_font_family"],
        "heading_size": f"{template['heading_font_size']}pt",
        "heading_bold": template["heading_bold"],
        "margin": MARGIN_MAP.get(template["margin_size"], "1in"),
        "line_height": template["line_spacing"],
        "bullet": template["bullet_style"],
        "accent_color": template["accent_color"],
    }


def count_words(text: str) -> int:
    return len((text or "").split())


def check_overflow(tailored_cv_md: str, template: dict) -> dict:
    """Does the tailored CV exceed the page budget? Returns overflow info for the frontend."""
    word_count = count_words(tailored_cv_md)
    max_words = template["max_words"]

    if word_count <= max_words:
        return {"overflow": False, "word_count": word_count, "max_words": max_words,
                "max_pages": template["max_pages"]}

    excess = word_count - max_words
    return {
        "overflow": True,
        "word_count": word_count,
        "max_words": max_words,
        "excess_words": excess,
        "excess_pages": round(excess / WORDS_PER_PAGE, 1),
        "current_pages": round(word_count / WORDS_PER_PAGE, 1),
        "max_pages": template["max_pages"],
    }
