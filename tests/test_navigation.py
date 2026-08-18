import json

import pytest

from groundnut.adapters.navigation import (
    FullInjectionNavigator,
    HANDLE_TREE_SURFACE_SCHEMA,
    LexicalStructureNavigator,
    TREE_SURFACE_SCHEMA,
    SELECTABLE_HANDLE_TREE_SURFACE_SCHEMA,
    SelectableTreeHandleNavigator,
    TreeDexStyleNavigator,
    TreeHandleNavigator,
    _tree_surface,
    _short_handle_map,
)
from groundnut.navigation import (
    NavigationIndex,
    NavigationNode,
    fetch_selected_nodes,
)
from groundnut.navigation_cases import (
    NavigationCase,
    build_navigation_case,
    build_navigation_pack,
    load_navigation_pack,
    paragraph_navigation_index,
)
from groundnut.navigation_eval import (
    run_navigation_evaluation,
    validate_navigation_evaluation,
)
from groundnut.provenance import sha256_text
from groundnut.support_cases import CaseProvenance
from groundnut.support_seeds import AttestedSpanSeed


def _source():
    return (
        "MASTER SERVICES AGREEMENT\n\n"
        "1. Definitions. Services means the hosted platform.\n\n"
        "2. Delivery. The supplier shall deliver within thirty days.\n\n"
        "3. Liability. Liability is capped at one million pounds."
    )


def _seed(source_text=None, *, seed_id="seed-1"):
    source_text = source_text or _source()
    target = "The supplier shall deliver within thirty days."
    start = source_text.index(target)
    return AttestedSpanSeed(
        seed_id=seed_id,
        source_id="cuad/agreement.txt",
        source_sha256=sha256_text(source_text),
        original_start=start,
        original_end=start + len(target),
        original_text=target,
        question="What is the delivery obligation?",
        provenance=CaseProvenance(
            kind="attested",
            source="legalbenchrag",
            source_record_id=seed_id,
            method="expert span; generated query",
        ),
    )


def test_navigation_index_is_content_bound_and_fetches_exact_nodes():
    source = _source()
    first = paragraph_navigation_index("cuad/agreement.txt", source)
    second = paragraph_navigation_index("cuad/agreement.txt", source)
    assert first.sha256 == second.sha256
    assert all(len(node.node_id) == 24 for node in first.nodes)
    assert sum(node.selectable for node in first.nodes) == 4

    selection = LexicalStructureNavigator(max_nodes=1).select(
        first, "What is the delivery obligation?"
    )
    context, receipt = fetch_selected_nodes(first, selection, source)
    assert selection.status == "selected"
    assert selection.to_dict()["sha256"] == selection.sha256
    assert "deliver within thirty days" in context
    assert receipt.context_sha256 == sha256_text(context)
    assert receipt.selected_nodes[0]["node_id"] == selection.selected_node_ids[0]

    with pytest.raises(ValueError, match="source hash mismatch"):
        fetch_selected_nodes(first, selection, source + " changed")


def test_navigation_index_rejects_tampered_self_hash():
    value = paragraph_navigation_index("cuad/agreement.txt", _source()).to_dict()
    value["nodes"][0]["title"] = "Changed"
    with pytest.raises(ValueError, match="self-hash mismatch"):
        NavigationIndex.from_mapping(value)


def test_navigation_requires_summary_provenance_and_parent_containment():
    source = _source()
    index = paragraph_navigation_index("cuad/agreement.txt", source)
    child = next(node for node in index.nodes if node.selectable)
    with pytest.raises(ValueError, match="summary requires explicit provenance"):
        NavigationNode(**{**child.__dict__, "summary": "Derived heading"})

    root = next(node for node in index.nodes if not node.selectable)
    escaped = NavigationNode(
        **{
            **child.__dict__,
            "source_start": root.source_end - 1,
            "source_end": root.source_end + 1,
        }
    )
    with pytest.raises(ValueError, match="root source envelope"):
        NavigationIndex(
            source_id=index.source_id,
            source_sha256=index.source_sha256,
            indexer_key=index.indexer_key,
            indexer_version=index.indexer_version,
            nodes=(root, escaped, *(node for node in index.nodes if node not in {root, child})),
        )


def test_treedex_style_selection_is_strict_and_never_answers():
    index = paragraph_navigation_index("cuad/agreement.txt", _source())
    assert _tree_surface(index)["schema"] == TREE_SURFACE_SCHEMA
    selectable = [node.node_id for node in index.nodes if node.selectable]

    valid = TreeDexStyleNavigator(
        lambda prompt: {"node_ids": [selectable[1]], "reasoning": "Delivery section."},
        model="mock-model",
        revision="fixture",
        package_version="1",
        max_nodes=2,
    ).select(index, "What is the delivery obligation?")
    assert valid.status == "selected"
    assert valid.selected_node_ids == (selectable[1],)
    assert valid.prompt_sha256

    abstained = TreeDexStyleNavigator(
        lambda prompt: {"node_ids": [], "reasoning": "No suitable node."},
        model="mock-model",
        revision="fixture",
        package_version="1",
    ).select(index, "What is the renewal price?")
    assert abstained.status == "abstained"

    invalid = TreeDexStyleNavigator(
        lambda prompt: {"node_ids": ["invented"], "reasoning": "Guess."},
        model="mock-model",
        revision="fixture",
        package_version="1",
    ).select(index, "What is the delivery obligation?")
    assert invalid.status == "failed"
    assert invalid.raw_output["invalid_node_ids"] == ["invented"]


def test_treedex_style_selector_errors_and_duplicates_fail_closed():
    index = paragraph_navigation_index("cuad/agreement.txt", _source())
    node_id = next(node.node_id for node in index.nodes if node.selectable)

    failed = TreeDexStyleNavigator(
        lambda prompt: (_ for _ in ()).throw(RuntimeError("offline")),
        model="mock-model",
        revision="fixture",
        package_version="1",
    ).select(index, "Question?")
    assert failed.status == "failed"
    assert "RuntimeError" in failed.reason

    duplicate = TreeDexStyleNavigator(
        lambda prompt: {"node_ids": [node_id, node_id]},
        model="mock-model",
        revision="fixture",
        package_version="1",
    ).select(index, "Question?")
    assert duplicate.status == "failed"

    over_budget = TreeDexStyleNavigator(
        lambda prompt: pytest.fail("selector must not run over budget"),
        model="mock-model",
        revision="fixture",
        package_version="1",
        max_prompt_characters=1,
    ).select(index, "Question?")
    assert over_budget.status == "abstained"
    assert "prompt budget" in over_budget.reason

    output_over_budget = TreeDexStyleNavigator(
        lambda prompt: {
            "node_ids": [node_id],
            "input_tokens": 10,
            "output_tokens": 11,
        },
        model="mock-model",
        revision="fixture",
        package_version="1",
        max_output_tokens=10,
    ).select(index, "Question?")
    assert output_over_budget.status == "failed"
    assert "output-token budget" in output_over_budget.reason


def test_short_handles_resolve_strictly_to_content_addressed_nodes():
    index = paragraph_navigation_index("cuad/agreement.txt", _source())
    handle_map = _short_handle_map(index)
    handle_by_id = {node_id: handle for handle, node_id in handle_map.items()}
    selectable = next(node for node in index.nodes if node.selectable)
    selected_handle = handle_by_id[selectable.node_id]
    prompts = []

    navigator = TreeHandleNavigator(
        lambda prompt: prompts.append(prompt) or {"node_handles": [selected_handle]},
        model="mock-model",
        revision="fixture",
        package_version="1",
        max_nodes=2,
    )
    result = navigator.select(index, "What is the delivery obligation?")
    assert result.status == "selected"
    assert result.selected_node_ids == (selectable.node_id,)
    assert result.raw_output["node_handles"] == [selected_handle]
    assert result.raw_output["resolved_node_ids"] == [selectable.node_id]
    assert selectable.node_id not in prompts[0]
    assert HANDLE_TREE_SURFACE_SCHEMA in prompts[0]

    repeated = _short_handle_map(index)
    assert repeated == handle_map
    assert list(handle_map) == sorted(handle_map)

    unknown = TreeHandleNavigator(
        lambda prompt: {"node_handles": ["n9999"]},
        model="mock-model",
        revision="fixture",
        package_version="1",
    ).select(index, "Question?")
    assert unknown.status == "failed"
    assert unknown.raw_output["invalid_node_handles"] == ["n9999"]

    root = next(node for node in index.nodes if not node.selectable)
    root_handle = handle_by_id[root.node_id]
    nonselectable = TreeHandleNavigator(
        lambda prompt: {"node_handles": [root_handle]},
        model="mock-model",
        revision="fixture",
        package_version="1",
    ).select(index, "Question?")
    assert nonselectable.status == "failed"


def test_selectable_handles_leave_structural_nodes_unaddressable():
    index = paragraph_navigation_index("cuad/agreement.txt", _source())
    handle_map = _short_handle_map(index, selectable_only=True)
    assert len(handle_map) == sum(node.selectable for node in index.nodes)
    root = next(node for node in index.nodes if not node.selectable)
    assert root.node_id not in set(handle_map.values())

    captured = []
    navigator = SelectableTreeHandleNavigator(
        lambda prompt: captured.append(prompt) or {"node_handles": ["n0001"]},
        model="mock-model",
        revision="fixture",
        package_version="1",
    )
    result = navigator.select(index, "Question?")
    assert result.status == "selected"
    assert result.selected_node_ids == (handle_map["n0001"],)
    assert SELECTABLE_HANDLE_TREE_SURFACE_SCHEMA in captured[0]
    surface = json.loads(captured[0].split("Structured index:\n", 1)[1])
    assert surface["roots"][0][0] is None
    assert surface["roots"][0][5] is False


def test_legalbench_offsets_map_to_gold_navigation_nodes(tmp_path):
    source = _source()
    case = build_navigation_case(_seed(source), source, max_node_characters=256)
    assert len(case.gold_node_ids) == 1
    gold = case.index.by_id[case.gold_node_ids[0]]
    assert gold.source_start <= case.gold_start < case.gold_end <= gold.source_end

    corpus = tmp_path / "corpus" / "cuad"
    corpus.mkdir(parents=True)
    (corpus / "agreement.txt").write_text(source)
    pack = build_navigation_pack(
        (_seed(source),),
        tmp_path / "corpus",
        count=1,
        sampling_seed=991,
        max_node_characters=256,
    )
    path = tmp_path / "pack.json"
    path.write_text(json.dumps(pack))
    [restored] = load_navigation_pack(path)
    assert restored.gold_node_ids == case.gold_node_ids


def test_navigation_evaluation_scores_selection_without_answering(tmp_path):
    source = _source()
    source_path = tmp_path / "cuad"
    source_path.mkdir()
    (source_path / "agreement.txt").write_text(source)
    case = build_navigation_case(_seed(source), source)
    result = run_navigation_evaluation(
        (case,),
        tmp_path,
        (FullInjectionNavigator(), LexicalStructureNavigator(max_nodes=1)),
        workers=2,
    )
    validate_navigation_evaluation(result)
    assert result["eligible_for_admission"] is False
    assert len(result["rows"]) == 2
    by_adapter = {
        row["navigator"]["adapter"]: row for row in result["summaries"]
    }
    assert by_adapter["groundnut.navigation.full-injection"][
        "exact_gold_coverage_rate"
    ] == 1.0
    assert by_adapter["groundnut.navigation.full-injection"]["selected_cases"] == 1
    assert by_adapter["groundnut.navigation.full-injection"][
        "selection_status_counts"
    ] == {"selected": 1}
    assert by_adapter["groundnut.navigation.lexical-structure"][
        "mean_context_ratio"
    ] < 1.0


def test_navigation_pack_rejects_source_escape(tmp_path):
    source = _source()
    seed = _seed(source)
    escaped = AttestedSpanSeed(**{**seed.__dict__, "source_id": "../escape.txt"})
    (tmp_path / "escape.txt").write_text(source)
    with pytest.raises(ValueError, match="escapes corpus root"):
        build_navigation_pack(
            (escaped,), tmp_path / "corpus", count=1, sampling_seed=991
        )
