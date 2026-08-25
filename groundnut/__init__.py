"""Internal convenience exports for Groundnut's checking contracts.

``pipeline`` remains the compatibility CLI used by the original CUAD eval.
The stable integration boundary is the versioned JSON emitted by the canonical
CLIs. Experimental objects remain importable here for repository work, but a
package-root export alone does not make them an admitted product API.
"""

from ._version import __version__

from .domain import Category, DocumentType, DomainEvidence, DomainPack
from .artifacts import (
    ArtifactExtraction,
    ArtifactProfile,
    DEFAULT_ARTIFACT_PROFILE,
    DEFAULT_SEGMENTER,
    SegmenterIdentity,
    extract_artifact,
)
from .metrics import MetricEnvelope
from .navigation import (
    NavigationIndex,
    NavigationNode,
    NavigationReceipt,
    NavigationSelection,
    NavigatorIdentity,
    fetch_selected_nodes,
)
from .navigation_cases import NavigationCase
from .signals import (
    COMPONENT_SIGNAL_SCHEMA,
    SIGNAL_BUNDLE_SCHEMA,
    SIGNAL_ROLES,
    ComponentLicence,
    ComponentSignal,
    SignalBundle,
    component_input_sha256,
)
from .rendering import (
    RENDER_RECEIPT_SCHEMA,
    RenderReceipt,
    RendererIdentity,
    compare_rendered_artifacts,
)
from .engine import AnalysisResult, analyse_text
from .coverage import CheckCoverage, CoverageManifest
from .authority import (
    AUTHORITY_KINDS,
    AuthorityAssessment,
    AuthorityDeclaration,
    AuthorityPolicy,
    ClaimEvidenceAccount,
    ClaimEvidenceReport,
    account_for_claim_check,
    assess_evidence_authority,
)
from .provenance import SourceAnchor, SourceRecord, anchor_quote
from .sources import (
    EvidenceWindow,
    FileResolver,
    HttpResolver,
    ResolvedSource,
    SnapshotStore,
    SnapshotFirstResolver,
    SourceAcquisition,
    SourceReference,
    SourceResolution,
)
from .arena import (
    ArenaPolicy,
    ArenaReport,
    ArenaTask,
    Attack,
    Ruling,
    adjudicate,
)
from .arena_emission import (
    ArenaEmissionProfile,
    ArenaTaskEmission,
    DEFAULT_ARENA_EMISSION_PROFILE,
    emit_arena_tasks,
)
from .registry import DomainRegistry
from .parity import ParityComparison, compare_analysis, semantic_projection
from .support import (
    ClaimAssessment,
    DetectorDecision,
    DetectorIdentity,
    ExactSupportDetector,
    SupportAssessment,
    SupportPolicy,
    SupportSpan,
    assess_claim_support,
)
from .support_eval import SupportGold, score_support
from .support_cases import CaseProvenance, SupportCase, SupportProbe
from .support_seeds import (
    AttestedSpanSeed,
    PresentIrrelevantCandidate,
    SeedImport,
    build_present_irrelevant_candidates,
    import_legalbenchrag,
    load_support_seeds,
    sample_present_irrelevant_candidates,
)
from .annotations import AnnotationBundle, EvidenceAnnotation
from .probe_plan import SupportProbePlan
from .support_admission import (
    RecordedProbeRun,
    SupportAdmissionReport,
    evaluate_support_admission,
)
from .support_bakeoff import SupportBakeoff, run_support_bakeoff
from .support_review import (
    PilotReviewManifest,
    PilotReviewRow,
    apply_review_decisions_tsv,
    build_pilot_probe,
    prepare_review_manifest,
    propose_negation_flip,
    review_decisions_tsv,
)
from .support_review_html import render_support_review_html
from .support_agent_screen import (
    AgentSuggestion,
    AgentSupportScreen,
    screen_agent_suggestions,
)
from .support_exploration import (
    COMPARISON_SCHEMA,
    EXPLORATION_SCHEMA,
    compare_agent_explorations,
    run_agent_exploration,
)
from .run_manifest import (
    ArtifactDigest,
    DomainDigest,
    EngineIdentity,
    PolicyDigest,
    RunManifest,
    RuntimeComponent,
    SourceDigest,
    source_tree_sha256,
)
from .checker import ClaimCheckReport, check_claims
from .runner import (
    CanonicalExecution,
    CanonicalRun,
    execute_canonical_check,
    run_canonical_check,
)
from .adapters import (
    AlignScoreAdapter,
    LettuceDetectAdapter,
    MiniCheckAdapter,
    SummaCAdapter,
)
from .support_runner import ProbeContextDigest, SupportProbeRun, run_support_probe
from .verification import (
    ANALYTICAL_PROVENANCE_SCHEMA,
    ANALYST_PROVENANCE_CLASSES,
    CALCULATION_LINEAGE_SCHEMA,
    CLAIM_PROVENANCE_CLASSES,
    CalculationInput,
    CalculationLineage,
    Claim,
    MatchOutcome,
    VerifiedClaim,
    anchor_excerpt,
    verification_metrics,
    verify_claim,
)

__all__ = [
    "AnalysisResult",
    "AlignScoreAdapter",
    "AgentSuggestion",
    "AgentSupportScreen",
    "ANALYTICAL_PROVENANCE_SCHEMA",
    "ANALYST_PROVENANCE_CLASSES",
    "AUTHORITY_KINDS",
    "AnnotationBundle",
    "ArtifactDigest",
    "ArtifactExtraction",
    "ArtifactProfile",
    "AuthorityAssessment",
    "AuthorityDeclaration",
    "AuthorityPolicy",
    "AttestedSpanSeed",
    "ArenaPolicy",
    "ArenaEmissionProfile",
    "ArenaReport",
    "ArenaTask",
    "ArenaTaskEmission",
    "Attack",
    "Category",
    "CanonicalRun",
    "CanonicalExecution",
    "CALCULATION_LINEAGE_SCHEMA",
    "CaseProvenance",
    "CalculationInput",
    "CalculationLineage",
    "Claim",
    "CLAIM_PROVENANCE_CLASSES",
    "ClaimAssessment",
    "ClaimCheckReport",
    "ClaimEvidenceAccount",
    "ClaimEvidenceReport",
    "CheckCoverage",
    "COMPARISON_SCHEMA",
    "COMPONENT_SIGNAL_SCHEMA",
    "ComponentLicence",
    "ComponentSignal",
    "CoverageManifest",
    "DocumentType",
    "DEFAULT_ARTIFACT_PROFILE",
    "DEFAULT_SEGMENTER",
    "DEFAULT_ARENA_EMISSION_PROFILE",
    "DomainDigest",
    "DetectorDecision",
    "DetectorIdentity",
    "DomainEvidence",
    "DomainPack",
    "DomainRegistry",
    "FileResolver",
    "ExactSupportDetector",
    "EngineIdentity",
    "EXPLORATION_SCHEMA",
    "EvidenceAnnotation",
    "HttpResolver",
    "MatchOutcome",
    "MetricEnvelope",
    "NavigationCase",
    "NavigationIndex",
    "NavigationNode",
    "NavigationReceipt",
    "NavigationSelection",
    "NavigatorIdentity",
    "MiniCheckAdapter",
    "ParityComparison",
    "PresentIrrelevantCandidate",
    "PolicyDigest",
    "EvidenceWindow",
    "PilotReviewManifest",
    "PilotReviewRow",
    "ProbeContextDigest",
    "ResolvedSource",
    "RecordedProbeRun",
    "RENDER_RECEIPT_SCHEMA",
    "RenderReceipt",
    "RendererIdentity",
    "Ruling",
    "RunManifest",
    "RuntimeComponent",
    "SnapshotStore",
    "SnapshotFirstResolver",
    "SourceAcquisition",
    "SourceAnchor",
    "SourceDigest",
    "source_tree_sha256",
    "SourceReference",
    "SourceRecord",
    "SourceResolution",
    "SeedImport",
    "SegmenterIdentity",
    "SIGNAL_BUNDLE_SCHEMA",
    "SIGNAL_ROLES",
    "SignalBundle",
    "SupportAssessment",
    "SupportAdmissionReport",
    "SupportBakeoff",
    "SupportCase",
    "SupportGold",
    "SupportPolicy",
    "SupportProbe",
    "SupportProbePlan",
    "SupportProbeRun",
    "SupportSpan",
    "SummaCAdapter",
    "VerifiedClaim",
    "LettuceDetectAdapter",
    "analyse_text",
    "account_for_claim_check",
    "adjudicate",
    "assess_claim_support",
    "assess_evidence_authority",
    "anchor_quote",
    "apply_review_decisions_tsv",
    "anchor_excerpt",
    "compare_analysis",
    "compare_agent_explorations",
    "compare_rendered_artifacts",
    "component_input_sha256",
    "check_claims",
    "build_present_irrelevant_candidates",
    "build_pilot_probe",
    "import_legalbenchrag",
    "evaluate_support_admission",
    "emit_arena_tasks",
    "execute_canonical_check",
    "extract_artifact",
    "load_support_seeds",
    "prepare_review_manifest",
    "propose_negation_flip",
    "review_decisions_tsv",
    "render_support_review_html",
    "run_support_bakeoff",
    "run_agent_exploration",
    "sample_present_irrelevant_candidates",
    "semantic_projection",
    "score_support",
    "screen_agent_suggestions",
    "run_support_probe",
    "run_canonical_check",
    "verification_metrics",
    "verify_claim",
    "fetch_selected_nodes",
]
