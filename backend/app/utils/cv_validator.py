"""Lightweight anti-hallucination check — every metric in the tailored CV must
appear in the master CV (defence-in-depth alongside the S3 integrity score)."""
import re

# $1.2M, 4.5M+, 40%, 15+, 1,200, 10x
_NUM_RE = re.compile(r"\$[\d,.]+\s*[KMB+]?|\b\d[\d,.]*\s*[%xX]?\s*[KMB+]?\b")


def extract_numbers(text: str) -> set:
    """All numeric metrics in `text`, normalised (whitespace + trailing punctuation stripped)."""
    out = set()
    for m in _NUM_RE.findall(text or ""):
        norm = re.sub(r"\s+", "", m).rstrip(".,;:").upper()
        # Ignore bare single/standalone digits with no unit (years, counts in prose).
        if norm and not re.fullmatch(r"\d", norm):
            out.add(norm)
    return out


def validate_no_hallucination(tailored_cv_md: str, master_cv_md: str) -> dict:
    """Returns {valid, violations:[{type, value, message}]}. A violation = a metric in
    the tailored CV that is NOT present in the master CV."""
    master_nums = extract_numbers(master_cv_md)
    tailored_nums = extract_numbers(tailored_cv_md)
    invented = sorted(tailored_nums - master_nums)
    violations = [
        {"type": "invented_metric", "value": num, "message": f"{num} not found in master CV"}
        for num in invented
    ]
    return {"valid": len(violations) == 0, "violations": violations}
