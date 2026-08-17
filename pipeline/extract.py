import json


def parse_response(text):
    """Tolerate stray prose around the JSON object; never raise."""
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        return {}
    try:
        obj = json.loads(text[start:end + 1])
    except Exception:
        return {}
    if not isinstance(obj, dict):
        return {}
    findings = obj.get("findings", obj)
    if not isinstance(findings, dict):
        return {}
    clean = {}
    for cat, spans in findings.items():
        if not isinstance(cat, str) or not isinstance(spans, list):
            continue
        clean[cat] = [s for s in spans if isinstance(s, str) and s.strip()]
    return clean


def filter_verbatim(findings, source_text):
    """Drop any span that is not an exact substring of the source it came from."""
    out = {}
    for cat, spans in findings.items():
        kept = [s for s in spans if s in source_text]
        if kept:
            out[cat] = kept
    return out


def merge_findings(chunk_findings_list, categories):
    """Union findings across chunks, deduping on normalized whitespace/case."""
    merged = {c: [] for c in categories}
    seen = {c: set() for c in categories}
    for cf in chunk_findings_list:
        for cat, spans in cf.items():
            if cat not in merged:
                merged[cat] = []
                seen[cat] = set()
            for s in spans:
                key = " ".join(s.split()).lower()
                if key in seen[cat]:
                    continue
                seen[cat].add(key)
                merged[cat].append(s)
    return {c: spans for c, spans in merged.items() if spans}
