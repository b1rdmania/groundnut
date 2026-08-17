"""Configuration-driven ingestion of claim-bearing artifacts.

This layer recovers claims and citation apparatus. It does not fetch sources,
anchor excerpts, assess support, or assign a downstream domain outcome.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from html import unescape
import json
from pathlib import Path
import re
from typing import Any, Mapping

from .provenance import sha256_text
from .sources import SourceReference
from .verification import (
    ANALYST_PROVENANCE_CLASSES,
    CLAIM_PROVENANCE_CLASSES,
    CalculationInput,
    CalculationLineage,
    Claim,
)


_LINK = re.compile(r'\[([^\]]+)\]\((https?://[^\s)"]+)(?:\s+"([^"]*)")?\)')
_BLOCK_END = re.compile(
    r"</(?:p|div|li|h[1-6]|td|th|tr|section|article|header|footer|blockquote)>",
    re.I,
)
_TAG = re.compile(r"<[^>]+>")


@dataclass(frozen=True)
class SegmenterIdentity:
    key: str
    version: str
    strategies: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "strategies", tuple(sorted(self.strategies)))
        if not self.key.strip() or not self.version.strip() or not self.strategies:
            raise ValueError("segmenter identity and strategies are required")
        if any(not kind.strip() or not rule.strip() for kind, rule in self.strategies):
            raise ValueError("segmenter strategies must not be empty")
        if len({kind for kind, _ in self.strategies}) != len(self.strategies):
            raise ValueError("segmenter strategy kinds must be unique")

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "schema": "groundnut-segmenter-identity/v1",
            "key": self.key,
            "version": self.version,
            "strategies": dict(self.strategies),
        }

    @property
    def sha256(self) -> str:
        encoded = json.dumps(
            self.canonical_payload(), sort_keys=True, separators=(",", ":")
        ).encode()
        return hashlib.sha256(encoded).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {**self.canonical_payload(), "configuration_sha256": self.sha256}

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "SegmenterIdentity":
        strategies = value.get("strategies", {})
        if not isinstance(strategies, Mapping):
            raise ValueError("segmenter strategies must be an object")
        return cls(
            key=str(value["key"]),
            version=str(value["version"]),
            strategies=tuple((str(kind), str(rule)) for kind, rule in strategies.items()),
        )


DEFAULT_SEGMENTER = SegmenterIdentity(
    key="groundnut.artifact-block-segmenter",
    version="1",
    strategies=(
        ("structured_json", "one claim per configured claims-array row"),
        ("markdown", "one claim per HTTP citation per physical line"),
        (
            "rendered_html",
            "one claim per HTTP citation per normalized block line; one claim per typed unsourced block",
        ),
    ),
)


DEFAULT_PROVENANCE_CLASS_MARKERS = (
    ("groundnut-external-evidence", "external_evidence"),
    ("groundnut-company-assertion", "company_assertion"),
    ("groundnut-analyst-calculation", "analyst_calculation"),
    ("groundnut-analyst-inference", "analyst_inference"),
    ("groundnut-recommendation", "recommendation"),
    ("groundnut-open-question", "open_question"),
)


@dataclass(frozen=True)
class ArtifactProfile:
    key: str
    version: str
    claims_key: str = "claims"
    claim_id_key: str = "claim_id"
    claim_text_key: str = "claim_text"
    source_uri_key: str = "source_url"
    excerpt_key: str = "source_excerpt"
    locator_key: str = "source_locator"
    declared_analysis_key: str = "declared_analysis"
    provenance_class_key: str = "provenance_class"
    calculation_key: str = "calculation"
    evidence_comment_prefix: str = "groundnut-source"
    declared_analysis_classes: tuple[str, ...] = ("groundnut-declared-analysis",)
    provenance_class_markers: tuple[tuple[str, str], ...] = DEFAULT_PROVENANCE_CLASS_MARKERS
    ignored_container_classes: tuple[str, ...] = ("groundnut-references",)
    segmenter: SegmenterIdentity = DEFAULT_SEGMENTER

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "declared_analysis_classes", tuple(self.declared_analysis_classes)
        )
        object.__setattr__(
            self, "ignored_container_classes", tuple(self.ignored_container_classes)
        )
        object.__setattr__(
            self,
            "provenance_class_markers",
            tuple(sorted(tuple(row) for row in self.provenance_class_markers)),
        )
        values = (
            self.key,
            self.version,
            self.claims_key,
            self.claim_id_key,
            self.claim_text_key,
            self.source_uri_key,
            self.excerpt_key,
            self.locator_key,
            self.declared_analysis_key,
            self.provenance_class_key,
            self.calculation_key,
            self.evidence_comment_prefix,
        )
        if not all(value.strip() for value in values):
            raise ValueError("artifact profile fields must not be empty")
        if any(not value.strip() for value in self.declared_analysis_classes):
            raise ValueError("declared-analysis classes must not be empty")
        if any(not value.strip() for value in self.ignored_container_classes):
            raise ValueError("ignored-container classes must not be empty")
        marker_classes = [marker for marker, _ in self.provenance_class_markers]
        if len(marker_classes) != len(set(marker_classes)):
            raise ValueError("provenance marker classes must be unique")
        if any(
            not marker.strip() or provenance not in CLAIM_PROVENANCE_CLASSES - {"unclassified"}
            for marker, provenance in self.provenance_class_markers
        ):
            raise ValueError("provenance markers require a canonical provenance class")

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "schema": "groundnut-artifact-profile/v1",
            "key": self.key,
            "version": self.version,
            "structured_fields": {
                "claims": self.claims_key,
                "claim_id": self.claim_id_key,
                "claim_text": self.claim_text_key,
                "source_uri": self.source_uri_key,
                "excerpt": self.excerpt_key,
                "locator": self.locator_key,
                "declared_analysis": self.declared_analysis_key,
                "provenance_class": self.provenance_class_key,
                "calculation": self.calculation_key,
            },
            "html": {
                "evidence_comment_prefix": self.evidence_comment_prefix,
                "declared_analysis_classes": list(self.declared_analysis_classes),
                "provenance_class_markers": dict(self.provenance_class_markers),
                "ignored_container_classes": list(self.ignored_container_classes),
            },
            "segmenter": self.segmenter.to_dict(),
        }

    @property
    def sha256(self) -> str:
        encoded = json.dumps(
            self.canonical_payload(), sort_keys=True, separators=(",", ":")
        ).encode()
        return hashlib.sha256(encoded).hexdigest()

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ArtifactProfile":
        schema = value.get("schema", "groundnut-artifact-profile/v1")
        if schema != "groundnut-artifact-profile/v1":
            raise ValueError(f"unsupported artifact profile schema: {schema}")
        structured = value.get("structured_fields", {})
        html = value.get("html", {})
        if not isinstance(structured, Mapping) or not isinstance(html, Mapping):
            raise ValueError("artifact profile sections must be objects")
        provenance_markers = html.get(
            "provenance_class_markers",
            dict(DEFAULT_PROVENANCE_CLASS_MARKERS),
        )
        if not isinstance(provenance_markers, Mapping):
            raise ValueError("provenance_class_markers must be an object")
        return cls(
            key=str(value["key"]),
            version=str(value["version"]),
            claims_key=str(structured.get("claims", "claims")),
            claim_id_key=str(structured.get("claim_id", "claim_id")),
            claim_text_key=str(structured.get("claim_text", "claim_text")),
            source_uri_key=str(structured.get("source_uri", "source_url")),
            excerpt_key=str(structured.get("excerpt", "source_excerpt")),
            locator_key=str(structured.get("locator", "source_locator")),
            declared_analysis_key=str(
                structured.get("declared_analysis", "declared_analysis")
            ),
            provenance_class_key=str(
                structured.get("provenance_class", "provenance_class")
            ),
            calculation_key=str(structured.get("calculation", "calculation")),
            evidence_comment_prefix=str(
                html.get("evidence_comment_prefix", "groundnut-source")
            ),
            declared_analysis_classes=tuple(
                str(item)
                for item in html.get(
                    "declared_analysis_classes", ("groundnut-declared-analysis",)
                )
            ),
            provenance_class_markers=tuple(
                (str(marker), str(provenance))
                for marker, provenance in provenance_markers.items()
            ),
            ignored_container_classes=tuple(
                str(item)
                for item in html.get(
                    "ignored_container_classes", ("groundnut-references",)
                )
            ),
            segmenter=(
                SegmenterIdentity.from_mapping(value["segmenter"])
                if isinstance(value.get("segmenter"), Mapping)
                else DEFAULT_SEGMENTER
            ),
        )


DEFAULT_ARTIFACT_PROFILE = ArtifactProfile(key="groundnut-default", version="1")


@dataclass(frozen=True)
class ArtifactExtraction:
    kind: str
    input_sha256: str
    profile_key: str
    profile_sha256: str
    segmenter: SegmenterIdentity
    claims: tuple[Claim, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "groundnut-artifact-extraction/v2",
            "kind": self.kind,
            "input_sha256": self.input_sha256,
            "profile": {"key": self.profile_key, "sha256": self.profile_sha256},
            "segmenter": self.segmenter.to_dict(),
            "claim_count": len(self.claims),
            "claims": [claim.to_dict() for claim in self.claims],
        }


def extract_artifact(
    path: str | Path, profile: ArtifactProfile = DEFAULT_ARTIFACT_PROFILE
) -> ArtifactExtraction:
    artifact = Path(path)
    raw = artifact.read_text()
    suffix = artifact.suffix.casefold()
    if suffix == ".json":
        kind = "structured_json"
        claims = _structured_claims(json.loads(raw), profile)
    elif suffix in {".html", ".htm"}:
        kind = "rendered_html"
        claims = _html_claims(raw, profile)
    elif suffix in {".md", ".markdown"}:
        kind = "markdown"
        claims = _markdown_claims(raw, profile)
    else:
        raise ValueError(f"unsupported artifact suffix: {suffix or '<none>'}")
    return ArtifactExtraction(
        kind=kind,
        input_sha256=sha256_text(raw),
        profile_key=profile.key,
        profile_sha256=profile.sha256,
        segmenter=profile.segmenter,
        claims=tuple(claims),
    )


def _structured_claims(value: Any, profile: ArtifactProfile) -> list[Claim]:
    if not isinstance(value, Mapping) or not isinstance(value.get(profile.claims_key), list):
        raise ValueError("structured artifact must contain a claims array")
    claims = []
    for index, row in enumerate(value[profile.claims_key]):
        if not isinstance(row, Mapping):
            raise ValueError(f"claims[{index}] must be an object")
        text = _required_string(row, profile.claim_text_key, index)
        uri = _optional_string(row.get(profile.source_uri_key), profile.source_uri_key)
        claims.append(
            Claim(
                claim_id=_optional_string(row.get(profile.claim_id_key), profile.claim_id_key)
                or f"c{index + 1}",
                text=text,
                source=_reference(uri) if uri else None,
                excerpt=_optional_string(row.get(profile.excerpt_key), profile.excerpt_key),
                locator=_optional_string(row.get(profile.locator_key), profile.locator_key),
                declared_analysis=_optional_bool(
                    row.get(profile.declared_analysis_key, False),
                    profile.declared_analysis_key,
                ),
                provenance_class=(
                    _optional_string(
                        row.get(profile.provenance_class_key),
                        profile.provenance_class_key,
                    )
                    or "unclassified"
                ),
                calculation_lineage=_calculation_lineage(
                    row.get(profile.calculation_key),
                    f"{profile.claims_key}[{index}].{profile.calculation_key}",
                ),
                location=f"{profile.claims_key}[{index}]",
            )
        )
    claim_ids = {claim.claim_id for claim in claims}
    if len(claim_ids) != len(claims):
        raise ValueError("structured artifact claim ids must be unique")
    for claim in claims:
        if claim.calculation_lineage is None:
            continue
        referenced = {
            claim_id
            for row in claim.calculation_lineage.inputs
            for claim_id in row.source_claim_ids
        }
        unknown = referenced - claim_ids
        if unknown:
            raise ValueError(
                f"calculation lineage references unknown claims: {sorted(unknown)}"
            )
        if claim.claim_id in referenced:
            raise ValueError("calculation lineage cannot reference its own claim")
    return claims


def _markdown_claims(raw: str, profile: ArtifactProfile) -> list[Claim]:
    claims = []
    comment = _comment_pattern(profile)
    for line_number, line in enumerate(raw.splitlines(), 1):
        for match in _LINK.finditer(line):
            evidence = comment.match(line[match.end() :])
            excerpt, locator = _citation_evidence(
                match.group(1), match.group(3), evidence.groups() if evidence else None
            )
            claims.append(
                Claim(
                    claim_id=f"c{len(claims) + 1}",
                    text=_reading_text(line, profile),
                    source=_reference(match.group(2)),
                    excerpt=excerpt,
                    locator=locator,
                    declared_analysis=_declared(line, profile),
                    provenance_class=_provenance_class(line, profile),
                    location=f"line {line_number}",
                )
            )
    return claims


def _html_claims(raw: str, profile: ArtifactProfile) -> list[Claim]:
    _validate_html_provenance_markers(raw, profile)
    prepared = raw
    for class_name in profile.ignored_container_classes:
        prepared = re.sub(
            rf"<([a-z][a-z0-9]*)\b[^>]*class=[\"'][^\"']*\b{re.escape(class_name)}\b[^\"']*[\"'][^>]*>[\s\S]*?</\1>",
            " ",
            prepared,
            flags=re.I,
        )
    for class_name, provenance_class in profile.provenance_class_markers:
        prepared = re.sub(
            rf"<([a-z][a-z0-9]*)\b[^>]*class=[\"'][^\"']*\b{re.escape(class_name)}\b[^\"']*[\"'][^>]*>([\s\S]*?)</\1>",
            lambda match: (
                f" {match.group(2)} "
                f"__GROUNDNUT_PROVENANCE_{provenance_class.upper()}__ "
            ),
            prepared,
            flags=re.I,
        )
    for class_name in profile.declared_analysis_classes:
        prepared = re.sub(
            rf"<([a-z][a-z0-9]*)\b[^>]*class=[\"'][^\"']*\b{re.escape(class_name)}\b[^\"']*[\"'][^>]*>[\s\S]*?</\1>",
            " __GROUNDNUT_DECLARED_ANALYSIS__ ",
            prepared,
            flags=re.I,
        )
    prepared = re.sub(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>", " ", prepared, flags=re.I)
    prepared = re.sub(
        r"<a\b([^>]*)>([\s\S]*?)</a>",
        lambda match: _anchor_marker(match.group(1), match.group(2)),
        prepared,
        flags=re.I,
    )
    comment = _comment_pattern(profile)
    prepared = comment.sub(
        lambda match: f" __GROUNDNUT_EVIDENCE_{match.group(1).upper()}_{_encode(match.group(2).strip())}__ ",
        prepared,
    )
    prepared = _BLOCK_END.sub("\n", prepared)
    prepared = re.sub(r"<(?:br|hr)\s*/?>", "\n", prepared, flags=re.I)
    prepared = unescape(_TAG.sub(" ", prepared))
    claims = []
    for line_number, line in enumerate(prepared.splitlines(), 1):
        line = " ".join(line.split())
        if not line:
            continue
        links = list(_LINK.finditer(line))
        declared = "__GROUNDNUT_DECLARED_ANALYSIS__" in line
        provenance_class = _provenance_class(line, profile)
        if declared and provenance_class == "unclassified":
            provenance_class = "analyst_inference"
        reading = _reading_text(line, profile)
        if links:
            for match in links:
                evidence = re.match(
                    r"\s*__GROUNDNUT_EVIDENCE_(QUOTE|LOCATOR)_([^\s]+)__",
                    line[match.end() :],
                )
                adjacent = (
                    (evidence.group(1).casefold(), _decode(evidence.group(2)))
                    if evidence
                    else None
                )
                excerpt, locator = _citation_evidence(
                    match.group(1), match.group(3), adjacent
                )
                claims.append(
                    Claim(
                        claim_id=f"c{len(claims) + 1}",
                        text=reading,
                        source=_reference(match.group(2)),
                        excerpt=excerpt,
                        locator=locator,
                        declared_analysis=declared,
                        provenance_class=provenance_class,
                        location=f"line {line_number}",
                    )
                )
        elif (declared or provenance_class != "unclassified") and reading:
            claims.append(
                Claim(
                    claim_id=f"c{len(claims) + 1}",
                    text=reading,
                    declared_analysis=(
                        declared or provenance_class in ANALYST_PROVENANCE_CLASSES
                    ),
                    provenance_class=provenance_class,
                    location=f"line {line_number}",
                )
            )
    return claims


def _anchor_marker(attributes: str, inner: str) -> str:
    uri = _html_attribute(attributes, "href")
    if not uri or not uri.startswith(("http://", "https://")):
        return _TAG.sub(" ", inner)
    text = " ".join(_TAG.sub(" ", inner).split()).replace("[", "").replace("]", "")
    title = _html_attribute(attributes, "title")
    suffix = f' "{title.replace(chr(34), "__GROUNDNUT_DQUOTE__")}"' if title else ""
    return f" [{text}]({uri}{suffix}) "


def _html_attribute(attributes: str, name: str) -> str | None:
    match = re.search(rf"\b{re.escape(name)}\s*=\s*([\"'])([\s\S]*?)\1", attributes, re.I)
    return unescape(match.group(2)) if match else None


def _reading_text(value: str, profile: ArtifactProfile) -> str:
    value = _LINK.sub(lambda match: match.group(1), value)
    value = _comment_pattern(profile).sub("", value)
    value = re.sub(
        r"__GROUNDNUT_(?:DECLARED_ANALYSIS|PROVENANCE_[A-Z_]+|EVIDENCE_(?:QUOTE|LOCATOR)_[^\s]+)__",
        "",
        value,
    )
    return " ".join(value.replace("#", " ").replace("*", " ").replace("`", " ").split())


def _citation_evidence(
    anchor: str, title: str | None, adjacent: tuple[str, str] | None
) -> tuple[str | None, str | None]:
    if adjacent:
        kind, value = adjacent
        return (value, None) if kind.casefold() == "quote" else (None, value)
    decoded_title = unescape(title or "").replace("__GROUNDNUT_DQUOTE__", '"')
    title_match = re.search(r"(?:^|\|)\s*quote:\s*(.+)$", decoded_title, re.I)
    value = title_match.group(1).strip() if title_match else anchor.strip()
    if value.startswith("[") and value.endswith("]"):
        return None, value[1:-1].strip()
    return value, None


def _comment_pattern(profile: ArtifactProfile) -> re.Pattern[str]:
    return re.compile(
        rf"\s*<!--\s*{re.escape(profile.evidence_comment_prefix)}-(quote|locator):\s*([\s\S]*?)\s*-->",
        re.I,
    )


def _declared(value: str, profile: ArtifactProfile) -> bool:
    return any(class_name in value for class_name in profile.declared_analysis_classes)


def _provenance_class(value: str, profile: ArtifactProfile) -> str:
    found = {
        provenance
        for marker, provenance in profile.provenance_class_markers
        if marker in value
        or f"__GROUNDNUT_PROVENANCE_{provenance.upper()}__" in value
    }
    if len(found) > 1:
        raise ValueError(f"claim block declares conflicting provenance classes: {sorted(found)}")
    return next(iter(found), "unclassified")


def _validate_html_provenance_markers(raw: str, profile: ArtifactProfile) -> None:
    """Reject contradictory provenance declarations before HTML is flattened."""

    for tag in re.finditer(r"<[a-z][a-z0-9]*\b([^>]*)>", raw, re.I):
        attributes = tag.group(1)
        classes = _html_attribute(attributes, "class")
        if classes is None:
            continue
        class_names = set(classes.split())
        found = {
            provenance
            for marker, provenance in profile.provenance_class_markers
            if marker in class_names
        }
        if len(found) > 1:
            raise ValueError(
                f"claim block declares conflicting provenance classes: {sorted(found)}"
            )
        declared = any(
            class_name in class_names for class_name in profile.declared_analysis_classes
        )
        if declared and found and not found <= ANALYST_PROVENANCE_CLASSES:
            raise ValueError(
                "claim block conflicts with legacy declared-analysis provenance"
            )


def _reference(uri: str) -> SourceReference:
    return SourceReference(source_id=f"url:{sha256_text(uri)[:16]}", uri=uri)


def _required_string(row: Mapping[str, Any], key: str, index: int) -> str:
    value = _optional_string(row.get(key), key)
    if value is None:
        raise ValueError(f"claims[{index}].{key} must be a non-empty string")
    return value


def _optional_string(value: Any, label: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a string or null")
    value = value.strip()
    return value or None


def _optional_bool(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{label} must be boolean")
    return value


def _calculation_lineage(value: Any, label: str) -> CalculationLineage | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object or null")
    formula = _optional_string(value.get("formula"), f"{label}.formula")
    rows = value.get("inputs")
    if formula is None or not isinstance(rows, list) or not rows:
        raise ValueError(f"{label} requires a formula and non-empty inputs array")
    inputs = []
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise ValueError(f"{label}.inputs[{index}] must be an object")
        name = _optional_string(row.get("name"), f"{label}.inputs[{index}].name")
        input_value = _optional_string(
            row.get("value"), f"{label}.inputs[{index}].value"
        )
        source_claim_ids = row.get("source_claim_ids", [])
        if not isinstance(source_claim_ids, list) or any(
            not isinstance(claim_id, str) for claim_id in source_claim_ids
        ):
            raise ValueError(
                f"{label}.inputs[{index}].source_claim_ids must be a string array"
            )
        if name is None or input_value is None:
            raise ValueError(f"{label}.inputs[{index}] requires name and value")
        inputs.append(
            CalculationInput(name, input_value, tuple(source_claim_ids))
        )
    return CalculationLineage(
        formula=formula,
        inputs=tuple(inputs),
        note=_optional_string(value.get("note"), f"{label}.note"),
    )


def _encode(value: str) -> str:
    return value.encode().hex()


def _decode(value: str) -> str:
    return bytes.fromhex(value).decode()
