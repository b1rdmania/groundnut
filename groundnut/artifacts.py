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
from .verification import Claim


_LINK = re.compile(r'\[([^\]]+)\]\((https?://[^\s)"]+)(?:\s+"([^"]*)")?\)')
_BLOCK_END = re.compile(
    r"</(?:p|div|li|h[1-6]|td|th|tr|section|article|header|footer|blockquote)>",
    re.I,
)
_TAG = re.compile(r"<[^>]+>")


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
    evidence_comment_prefix: str = "groundnut-source"
    declared_analysis_classes: tuple[str, ...] = ("groundnut-declared-analysis",)
    ignored_container_classes: tuple[str, ...] = ("groundnut-references",)

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "declared_analysis_classes", tuple(self.declared_analysis_classes)
        )
        object.__setattr__(
            self, "ignored_container_classes", tuple(self.ignored_container_classes)
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
            self.evidence_comment_prefix,
        )
        if not all(value.strip() for value in values):
            raise ValueError("artifact profile fields must not be empty")
        if any(not value.strip() for value in self.declared_analysis_classes):
            raise ValueError("declared-analysis classes must not be empty")
        if any(not value.strip() for value in self.ignored_container_classes):
            raise ValueError("ignored-container classes must not be empty")

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
            },
            "html": {
                "evidence_comment_prefix": self.evidence_comment_prefix,
                "declared_analysis_classes": list(self.declared_analysis_classes),
                "ignored_container_classes": list(self.ignored_container_classes),
            },
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
            evidence_comment_prefix=str(
                html.get("evidence_comment_prefix", "groundnut-source")
            ),
            declared_analysis_classes=tuple(
                str(item)
                for item in html.get(
                    "declared_analysis_classes", ("groundnut-declared-analysis",)
                )
            ),
            ignored_container_classes=tuple(
                str(item)
                for item in html.get(
                    "ignored_container_classes", ("groundnut-references",)
                )
            ),
        )


DEFAULT_ARTIFACT_PROFILE = ArtifactProfile(key="groundnut-default", version="1")


@dataclass(frozen=True)
class ArtifactExtraction:
    kind: str
    input_sha256: str
    profile_key: str
    profile_sha256: str
    claims: tuple[Claim, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "groundnut-artifact-extraction/v1",
            "kind": self.kind,
            "input_sha256": self.input_sha256,
            "profile": {"key": self.profile_key, "sha256": self.profile_sha256},
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
                location=f"{profile.claims_key}[{index}]",
            )
        )
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
                    location=f"line {line_number}",
                )
            )
    return claims


def _html_claims(raw: str, profile: ArtifactProfile) -> list[Claim]:
    prepared = raw
    for class_name in profile.ignored_container_classes:
        prepared = re.sub(
            rf"<([a-z][a-z0-9]*)\b[^>]*class=[\"'][^\"']*\b{re.escape(class_name)}\b[^\"']*[\"'][^>]*>[\s\S]*?</\1>",
            " ",
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
                        location=f"line {line_number}",
                    )
                )
        elif declared and reading:
            claims.append(
                Claim(
                    claim_id=f"c{len(claims) + 1}",
                    text=reading,
                    declared_analysis=True,
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
    value = re.sub(r"__GROUNDNUT_(?:DECLARED_ANALYSIS|EVIDENCE_(?:QUOTE|LOCATOR)_[^\s]+)__", "", value)
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


def _encode(value: str) -> str:
    return value.encode().hex()


def _decode(value: str) -> str:
    return bytes.fromhex(value).decode()
