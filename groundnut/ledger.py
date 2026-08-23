"""Claim ledger: every claim in a report, in one of three honest buckets.

This is the IC-facing output of a canonical run. It answers the question a
reader of a diligence report actually has: for each thing the report asserts,
is it quoted from a source we could check, did the quote drift from that
source, or is it the report's own reasoning?

Buckets:

- ``cited_verified``  — the cited excerpt was found verbatim in the snapshot.
- ``cited_drifted``   — a citation exists but the excerpt was not found,
  was ambiguous, had no excerpt to anchor, or the source was unavailable.
- ``own_reasoning``   — no citation, or the claim is declared analysis.

"Verified" means the quotation is in the source. It does not mean the claim is
true, and it does not mean the source supports the claim; the semantic support
status is carried alongside and is ``insufficient`` for every claim until a
support detector is admitted.

Own reasoning is split mechanically: ``numeric`` when the unit carries a
number, percentage, currency, or multiplier (the usual shape of LLM
extrapolation in a diligence report), ``declared`` when the author marked it
as analysis, ``narrative`` otherwise. The split is a reading aid, not a
judgement.

Every count here depends on the segmenter. Its identity is hashed into the
ledger so two ledgers are only comparable when the segmenter matches.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, Mapping, Sequence

from .artifacts import ArtifactProfile, DEFAULT_ARTIFACT_PROFILE, _LINK  # noqa: F401

LEDGER_SCHEMA = "groundnut-claim-ledger/v1"
BUCKETS = ("cited_verified", "cited_drifted", "own_reasoning")
DRIFT_REASONS = ("quote_not_found", "quote_ambiguous", "no_excerpt", "source_unavailable")
OWN_KINDS = ("declared", "numeric", "narrative")

_NUMERIC = re.compile(r"(?<![\w/])(?:[£$€]\s?\d|\d+(?:\.\d+)?\s?(?:%|x\b|×|m\b|bn\b|k\b)|\b\d{1,3}(?:,\d{3})+\b|\b\d+(?:\.\d+)?\b)")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"'(\[])")
_HEADING = re.compile(r"^\s{0,3}#{1,6}\s")
_HR = re.compile(r"^\s{0,3}([-*_])(?:\s*\1){2,}\s*$")
_TABLE = re.compile(r"^\s*\|")
_LIST = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
_COMMENT = re.compile(r"<!--[\s\S]*?-->")
_MD_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_INLINE = re.compile(r"[*_`]+")
MIN_WORDS = 8


@dataclass(frozen=True)
class LedgerSegmenter:
    key: str = "groundnut.ledger-prose-segmenter"
    version: str = "2"
    min_words: int = MIN_WORDS

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "version": self.version,
            "min_words": self.min_words,
            "rules": [
                "frontmatter, headings, horizontal rules, table rows, and fenced code are not claims",
                                "prose lines split into sentences; a sentence with a citation is one cited unit per citation; list items are one unit each",
                f"units under {self.min_words} words are dropped",
                "HTML comments and inline markdown are stripped before counting words",
            ],
        }

    @property
    def sha256(self) -> str:
        return _sha256(self.canonical_payload())


@dataclass(frozen=True)
class LedgerRow:
    unit_id: str
    line: int
    text: str
    bucket: str
    detail: str
    claim_id: str | None = None
    source_uri: str | None = None
    support_status: str | None = None
    anchor_score: float | None = None

    def __post_init__(self) -> None:
        if self.bucket not in BUCKETS:
            raise ValueError(f"unknown ledger bucket: {self.bucket}")
        if self.bucket == "cited_drifted" and self.detail not in DRIFT_REASONS:
            raise ValueError(f"unknown drift reason: {self.detail}")
        if self.bucket == "own_reasoning" and self.detail not in OWN_KINDS:
            raise ValueError(f"unknown own-reasoning kind: {self.detail}")
        if self.bucket.startswith("cited") and not (self.claim_id and self.source_uri):
            raise ValueError("cited ledger rows need a claim id and source")

    def to_dict(self) -> dict[str, Any]:
        return {
            "unit_id": self.unit_id,
            "line": self.line,
            "text": self.text,
            "bucket": self.bucket,
            "detail": self.detail,
            "claim_id": self.claim_id,
            "source_uri": self.source_uri,
            "support_status": self.support_status,
            "anchor_score": self.anchor_score,
        }


@dataclass(frozen=True)
class ClaimLedger:
    run_sha256: str
    artifact_sha256: str
    segmenter: LedgerSegmenter
    rows: tuple[LedgerRow, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "rows", tuple(self.rows))
        ids = [row.unit_id for row in self.rows]
        if len(ids) != len(set(ids)):
            raise ValueError("ledger unit ids must be unique")

    @property
    def counts(self) -> dict[str, Any]:
        by_bucket = {bucket: 0 for bucket in BUCKETS}
        detail: dict[str, int] = {}
        for row in self.rows:
            by_bucket[row.bucket] += 1
            key = f"{row.bucket}:{row.detail}"
            detail[key] = detail.get(key, 0) + 1
        return {
            "units": len(self.rows),
            "by_bucket": by_bucket,
            "by_detail": dict(sorted(detail.items())),
        }

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "schema": LEDGER_SCHEMA,
            "run_sha256": self.run_sha256,
            "artifact_sha256": self.artifact_sha256,
            "segmenter": {**self.segmenter.canonical_payload(), "sha256": self.segmenter.sha256},
            "counts": self.counts,
            "rows": [row.to_dict() for row in self.rows],
            "disclosure": (
                "cited_verified means the quotation was found in the snapshot; "
                "it is not a truth or support claim. support_status is insufficient "
                "for every claim until a support detector is admitted."
            ),
        }

    @property
    def sha256(self) -> str:
        return _sha256(self.canonical_payload())

    def to_dict(self) -> dict[str, Any]:
        return {**self.canonical_payload(), "sha256": self.sha256}


def build_claim_ledger(
    execution: Mapping[str, Any],
    artifact_text: str,
    *,
    profile: ArtifactProfile = DEFAULT_ARTIFACT_PROFILE,
    segmenter: LedgerSegmenter = LedgerSegmenter(),
) -> ClaimLedger:
    """Join a canonical execution's accounts to every prose unit of the report."""

    run = _run_from_execution(execution)
    artifact_sha256 = hashlib.sha256(artifact_text.encode()).hexdigest()
    _require_artifact_match(run, artifact_sha256)
    accounts = _accounts_by_location(run)
    rows: list[LedgerRow] = []
    counter = 0
    for line_number, line in _prose_lines(artifact_text):
        location = f"line {line_number}"
        citation_index = 0
        for raw_sentence in _raw_sentences(line):
            links = list(_LINK.finditer(raw_sentence))
            if links:
                for _ in links:
                    key = (location, citation_index)
                    if key not in accounts:
                        raise ValueError(
                            f"run has no account for citation {citation_index + 1} on "
                            f"{location}; run and artifact were produced with different "
                            "segmenters"
                        )
                    citation_index += 1
                    counter += 1
                    rows.append(
                        _cited_row(
                            f"u{counter}", line_number, raw_sentence, accounts.pop(key), profile
                        )
                    )
                continue
            for sentence in _sentences(raw_sentence, segmenter):
                counter += 1
                rows.append(_own_row(f"u{counter}", line_number, sentence, line, profile))
    if accounts:
        leftover = sorted(f"{loc}#{idx + 1}" for loc, idx in accounts)
        raise ValueError(f"run accounts not found in artifact: {leftover[:5]}")
    return ClaimLedger(
        run_sha256=run["sha256"],
        artifact_sha256=artifact_sha256,
        segmenter=segmenter,
        rows=tuple(rows),
    )


def render_ledger_markdown(ledger: ClaimLedger, *, title: str = "Claim ledger") -> str:
    counts = ledger.counts
    total = counts["units"] or 1
    lines = [f"# {title}", ""]
    lines.append(f"{counts['units']} claim units · run `{ledger.run_sha256[:12]}` · artifact `{ledger.artifact_sha256[:12]}` · segmenter `{ledger.segmenter.sha256[:12]}`")
    lines.append("")
    lines.append("| Bucket | Units | Share |")
    lines.append("|---|---:|---:|")
    labels = {
        "cited_verified": "Cited, quotation found in source",
        "cited_drifted": "Cited, quotation not confirmed",
        "own_reasoning": "Report's own reasoning, no source",
    }
    for bucket in BUCKETS:
        n = counts["by_bucket"][bucket]
        lines.append(f"| {labels[bucket]} | {n} | {100 * n / total:.1f}% |")
    lines.append("")
    lines.append("| Detail | Units |")
    lines.append("|---|---:|")
    for key, n in counts["by_detail"].items():
        lines.append(f"| `{key}` | {n} |")
    lines.append("")
    lines.append("Verified means the quoted words are in the snapshot. It is not a statement that the claim is true or that the source supports it.")
    lines.append("")
    for bucket in BUCKETS:
        lines.append(f"## {labels[bucket]}")
        lines.append("")
        for row in ledger.rows:
            if row.bucket != bucket:
                continue
            src = f" — <{row.source_uri}>" if row.source_uri else ""
            score = f" ({row.anchor_score:.2f})" if row.anchor_score is not None else ""
            lines.append(f"- **{row.unit_id}** L{row.line} `{row.detail}`{score}: {row.text}{src}")
        lines.append("")
    return "\n".join(lines)


# --- internals ---------------------------------------------------------------


def _run_from_execution(execution: Mapping[str, Any]) -> Mapping[str, Any]:
    value = execution
    if value.get("schema") == "groundnut-canonical-response/v1":
        value = _mapping(value, "execution")
    if value.get("schema") != "groundnut-canonical-execution/v1":
        raise ValueError(f"unsupported canonical execution schema: {value.get('schema')}")
    run = _mapping(value, "run")
    if run.get("schema") != "groundnut-canonical-run/v1":
        raise ValueError(f"unsupported canonical run schema: {run.get('schema')}")
    if not isinstance(run.get("sha256"), str) or len(run["sha256"]) != 64:
        raise ValueError("canonical run has no sha256")
    return run


def _require_artifact_match(run: Mapping[str, Any], artifact_sha256: str) -> None:
    artifact = _mapping(run, "artifact")
    if artifact.get("input_sha256") != artifact_sha256:
        raise ValueError("artifact text does not match the artifact the run was produced from")
    if artifact.get("kind") != "markdown":
        raise ValueError("claim ledger currently reads markdown artifacts only")


def _accounts_by_location(run: Mapping[str, Any]) -> dict[tuple[str, int], Mapping[str, Any]]:
    evidence = _mapping(run, "evidence")
    accounts = evidence.get("accounts")
    if not isinstance(accounts, Sequence):
        raise ValueError("canonical run evidence has no accounts")
    by_location: dict[tuple[str, int], Mapping[str, Any]] = {}
    seen: dict[str, int] = {}
    for account in accounts:
        claim = _mapping(_mapping(_mapping(account, "assessment"), "verification"), "claim")
        location = claim.get("location")
        if not isinstance(location, str):
            raise ValueError("claim account has no location")
        index = seen.get(location, 0)
        seen[location] = index + 1
        by_location[(location, index)] = account
    return by_location


def _cited_row(
    unit_id: str, line_number: int, line: str, account: Mapping[str, Any], profile: ArtifactProfile
) -> LedgerRow:
    assessment = _mapping(account, "assessment")
    verification = _mapping(assessment, "verification")
    support = _mapping(assessment, "support")
    claim = _mapping(verification, "claim")
    anchor = verification.get("anchor")
    support_status = support.get("status")
    source = claim.get("source") or {}
    uri = source.get("uri") if isinstance(source, Mapping) else None
    score = verification.get("score")
    score = float(score) if isinstance(score, (int, float)) else None
    if support_status == "source_unavailable":
        bucket, detail = "cited_drifted", "source_unavailable"
    elif anchor == "found":
        bucket, detail = "cited_verified", "found"
    elif anchor == "ambiguous":
        bucket, detail = "cited_drifted", "quote_ambiguous"
    elif anchor == "not_found":
        bucket, detail = "cited_drifted", "quote_not_found"
    elif anchor is None:
        bucket, detail = "cited_drifted", "no_excerpt"
    else:
        raise ValueError(f"unknown anchor state: {anchor}")
    return LedgerRow(
        unit_id=unit_id,
        line=line_number,
        text=_clean(line),
        bucket=bucket,
        detail=detail,
        claim_id=str(claim.get("claim_id")),
        source_uri=str(uri) if uri else None,
        support_status=str(support_status) if support_status else None,
        anchor_score=score,
    )


def _own_row(
    unit_id: str, line_number: int, sentence: str, line: str, profile: ArtifactProfile
) -> LedgerRow:
    declared = any(marker in line for marker in profile.declared_analysis_classes)
    if declared:
        detail = "declared"
    elif _NUMERIC.search(sentence):
        detail = "numeric"
    else:
        detail = "narrative"
    return LedgerRow(
        unit_id=unit_id, line=line_number, text=sentence, bucket="own_reasoning", detail=detail
    )


def _prose_lines(text: str):
    lines = text.splitlines()
    start = 0
    if lines and lines[0].strip() == "---":
        for index in range(1, len(lines)):
            if lines[index].strip() == "---":
                start = index + 1
                break
    in_code = False
    for number, line in enumerate(lines[start:], start + 1):
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code = not in_code
            continue
        if in_code or not stripped:
            continue
        if _HEADING.match(line) or _HR.match(line) or _TABLE.match(line):
            continue
        yield number, line


def _raw_sentences(line: str) -> list[str]:
    """Split a line into sentences with links and comments left intact.

    Comments are masked so a full stop inside a quoted excerpt does not end a
    sentence; the split positions are then applied to the original text.
    """
    masked = _COMMENT.sub(lambda m: " " * len(m.group(0)), line)
    masked = _MD_LINK.sub(lambda m: "x" * len(m.group(0)), masked)
    if _LIST.match(line):
        return [line]
    pieces = []
    start = 0
    for match in _SENTENCE_END.finditer(masked):
        pieces.append(line[start : match.start()])
        start = match.end()
    pieces.append(line[start:])
    return [piece for piece in pieces if piece.strip()]


def _sentences(line: str, segmenter: LedgerSegmenter) -> list[str]:
    cleaned = _clean(line)
    if not cleaned:
        return []
    if _LIST.match(line):
        units = [cleaned]
    else:
        units = _SENTENCE_END.split(cleaned)
    return [unit.strip() for unit in units if len(unit.split()) >= segmenter.min_words]


def _clean(line: str) -> str:
    text = _COMMENT.sub("", line)
    text = _MD_LINK.sub(r"\1", text)
    text = _LIST.sub("", text)
    text = _INLINE.sub("", text)
    return re.sub(r"\s+", " ", text).strip()


def _mapping(value: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    item = value.get(key)
    if not isinstance(item, Mapping):
        raise ValueError(f"canonical run is missing object '{key}'")
    return item


def _sha256(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
