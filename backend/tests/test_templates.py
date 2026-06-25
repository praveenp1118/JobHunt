"""CV Template tests — defaults, save, override merge, content-rules prompt, overflow, trim priority."""
from types import SimpleNamespace

import pytest

from app.utils.cv_template import (
    get_effective_template, build_content_rules_prompt, check_overflow, compute_max_words, DEFAULTS,
)


# ── Pure utility ──
def test_effective_template_merges_override():
    ov = SimpleNamespace(font_family="Arial", max_pages=1, max_words=300,
                         font_size=None, overflow_action=None,
                         never_modify_sections=None, section_order=None)
    eff = get_effective_template(None, ov)
    assert eff["font_family"] == "Arial"   # override wins
    assert eff["max_words"] == 300         # override wins
    assert eff["font_size"] == DEFAULTS["font_size"]  # null override → keep global default


def test_content_rules_prompt_includes_max_words():
    eff = get_effective_template(None)  # defaults: 2 pages, 600 words
    prompt = build_content_rules_prompt(eff)
    assert "600 words" in prompt
    assert "2 pages maximum" in prompt
    assert "EDUCATION" in prompt  # never_modify
    assert compute_max_words(3) == 900


def test_overflow_check_detects_excess():
    eff = get_effective_template(None)  # 600 words
    ok = check_overflow(" ".join(["w"] * 500), eff)
    assert ok["overflow"] is False
    over = check_overflow(" ".join(["w"] * 750), eff)
    assert over["overflow"] is True
    assert over["excess_words"] == 150
    assert over["current_pages"] == 2.5


def test_trim_removes_lowest_impact_first():
    from app.routers.tailor import _TRIM_PRIORITY
    # reorder is removed before keyword_injection before rephrase; deselect never removed.
    assert _TRIM_PRIORITY == ["reorder", "keyword_injection", "rephrase"]
    assert "deselect" not in _TRIM_PRIORITY


# ── Endpoints ──
async def test_get_template_returns_defaults_when_none(client, user_creds):
    r = await client.get("/api/templates/cv", headers=user_creds["headers"])
    assert r.status_code == 200
    d = r.json()
    assert d["font_family"] == "Calibri"
    assert d["max_words"] == 600 and d["max_pages"] == 2
    assert d["never_modify_sections"] == ["EDUCATION", "CERTIFICATIONS"]


async def test_update_template_saves_correctly(client, user_creds):
    r = await client.put("/api/templates/cv",
                         json={"max_pages": 3, "font_family": "Garamond", "accent_color": "#0a66c2"},
                         headers=user_creds["headers"])
    assert r.status_code == 200
    d = r.json()
    assert d["max_words"] == 900          # recomputed from max_pages
    assert d["font_family"] == "Garamond"
    assert d["accent_color"] == "#0a66c2"
    # persisted
    g = await client.get("/api/templates/cv", headers=user_creds["headers"])
    assert g.json()["max_words"] == 900
