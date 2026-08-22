"""The registry of support detectors the canonical path may execute.

A detector enters this registry only after a `groundnut-support-admission/v1`
artifact with `passed: true` exists for it under a frozen plan. Editing this
file is the act of admission and must cite that artifact. Until the canonical
semantic-support gate is measured, the exact baseline is the only entry, so
the canonical path can emit `supported` and `insufficient` but never
`contradicted`.
"""

from __future__ import annotations

from typing import Callable, Mapping

from .support import DetectorIdentity, ExactSupportDetector, SupportDetector

# identity -> factory, with the admission artifact that justified the entry.
_ADMITTED: dict[DetectorIdentity, tuple[Callable[[], SupportDetector], str]] = {
    ExactSupportDetector.identity: (
        ExactSupportDetector,
        "baseline; admitted by definition, see GATES.md section 2",
    ),
}


def admitted_detector_identities() -> Mapping[DetectorIdentity, str]:
    """Every admitted identity and the admission reference behind it."""
    return {identity: reference for identity, (_, reference) in _ADMITTED.items()}


def build_admitted_detector(identity: DetectorIdentity) -> SupportDetector:
    """Return a detector for an admitted identity; fail closed otherwise."""
    try:
        factory, _ = _ADMITTED[identity]
    except KeyError:
        admitted = ", ".join(
            f"{key.adapter}/{key.model}@{key.revision}" for key in _ADMITTED
        )
        raise ValueError(
            f"support detector {identity.adapter}/{identity.model}@{identity.revision} "
            f"is not admitted to the canonical path; admitted: {admitted}"
        ) from None
    return factory()
