# Evidence annotation and adjudication

Groundnut can use OpenContracts as an annotation workbench without making that
application its semantic authority. LegalBench-RAG provides source-anchored
seeds; reviewers turn candidate transformations into accepted annotations;
Groundnut imports the resulting immutable records and runs the frozen gate.

```text
LegalBench-RAG -> attested span seeds -> OpenContracts review -> four-cell probe
                                      -> rejected/ambiguous candidates stay out
```

## LegalBench-RAG import

The importer reads the upstream benchmark and corpus directly:

```bash
python3 scripts/import_legalbenchrag.py \
  --benchmark /path/to/data/benchmarks/cuad.json \
  --corpus-root /path/to/data/corpus \
  --expected-safe-sources 271 \
  --expected-excluded-sources 191 \
  --output /tmp/groundnut-support-seeds.jsonl
```

It never copies source documents into Groundnut. Every source is hashed; any
hash assigned to Groundnut's holdout split is excluded before a seed exists.
The command prints both the safe source-pool hash and the complete exclusion-
pool hash for preregistration and writes them to a self-hashed manifest beside
the seed JSONL. The expected inventory flags make a dataset-edition or text-
normalization mismatch fail closed instead of silently weakening the holdout
exclusion.

### Verified downloaded edition

Groundnut downloaded and checked the upstream Dropbox edition on 17 August
2026. Its CUAD slice contains 4,042 queries, 6,247 non-empty in-bounds snippet
offsets, and 462 source documents. The Groundnut holdout hashes exclude 191
documents, leaving **271**, not 270, safe documents and 3,610 safe snippet
seeds. The importer intentionally fails if invoked with the earlier 270 count.

The downloaded `LegalBench-RAG.zip` archive SHA-256 is
`27431be37db9b1db23f8ab790a42d076adb1f72d7f9e7562e36a10573405f88d`.
The archive and extracted documents remain outside the repository; underlying
dataset usage terms apply independently of the LegalBench-RAG code licence.

For this edition the safe-pool hash is
`f089eb671b2dbc8bd7f6e4070066660abe82a82b7dace06ca1626a8afbfce7b4` and
the complete exclusion-pool hash is
`1e474fa294229e3832aef8c937c4fe7d436b021d8b1132f8f6eb1c9e1710d2e7`.
These are inventory facts, not semantic-support measurements.

Each imported row discloses that LegalBench-RAG's span/category relationship is
expert-derived while the category-to-query wording may be generated. The row
is a seed for `verbatim_supported`, not proof that any derived negative or
authored paraphrase is valid.

Build a bounded cross-query review batch from those seeds:

```bash
python3 scripts/sample_irrelevant_candidates.py \
  --seeds /tmp/groundnut-support-seeds.jsonl \
  --count 50 \
  --sampling-seed 991 \
  --max-span-envelope 4096 \
  --output /tmp/present-irrelevant-candidates.jsonl
```

The sampler rejects identical and overlapping spans mechanically. Disjointness
only proves that the two spans differ; it does not prove irrelevance. The
remaining rows are candidate judgments, and the default one-document-per-row
sampling reduces correlated evidence. A human must rule that the present span
does not answer the target query before it can become a case.

For the canonical 50-group pilot, generate the complete review package directly
from the safe seeds:

```bash
python3 scripts/prepare_support_pilot.py \
  --seeds /path/to/groundnut-support-seeds.jsonl \
  --seed-manifest /path/to/groundnut-support-seeds.jsonl.manifest.json \
  --corpus-root /path/to/data/corpus \
  --target-groups 50 \
  --reserve-groups 25 \
  --max-context-characters 4096 \
  --output /path/to/support-pilot-review.jsonl
```

This writes immutable JSONL, a self-hashed manifest, and an editable TSV. The
75 rows use distinct sources, fit both present spans inside the frozen context,
and have a deterministic negation-flip proposal. The first 50 fully accepted
rows in manifest order form the pilot; reserves replace rejected or ambiguous
rows without post-hoc cherry-picking.

For a less painful review than editing a large TSV directly, render the private
self-contained reviewer. It has no network dependency or telemetry and remains
outside the repository with the source data:

```bash
python3 scripts/render_support_review.py \
  --review-jsonl /path/to/support-pilot-review.jsonl \
  --manifest /path/to/support-pilot-review.jsonl.manifest.json \
  --output /path/to/support-pilot-review.html
```

The reviewer downloads a TSV in the exact format consumed below.

After review:

```bash
python3 scripts/apply_support_reviews.py \
  --review-jsonl /path/to/support-pilot-review.jsonl \
  --manifest /path/to/support-pilot-review.jsonl.manifest.json \
  --worksheet /path/to/support-pilot-review.tsv \
  --output /path/to/support-pilot-reviewed.jsonl

python3 scripts/build_support_probe.py \
  --reviewed-jsonl /path/to/support-pilot-reviewed.jsonl \
  --manifest /path/to/support-pilot-review.jsonl.manifest.json \
  --seeds /path/to/groundnut-support-seeds.jsonl \
  --corpus-root /path/to/data/corpus \
  --output /path/to/support-pilot-cases.jsonl
```

Pending rows fail closed. Accepted irrelevance, paraphrase, and contradiction
decisions each require a reviewer identity; agent-authored paraphrases retain
their immutable author identity and cannot promote themselves.

## OpenContracts interchange

`groundnut-evidence-annotation/v1` is newline-delimited JSON with these stable
fields:

```json
{
  "schema": "groundnut-evidence-annotation/v1",
  "annotation_id": "a-001",
  "source_id": "cuad/example.txt",
  "source_sha256": "<64 lowercase hex characters>",
  "start": 120,
  "end": 180,
  "text": "<exact source substring>",
  "label": "paraphrase_supported",
  "question": "What is the delivery obligation?",
  "creator": {"kind": "agent", "id": "paraphraser:model-revision"},
  "review": {"state": "accepted", "reviewer_ids": ["human:reviewer-1"]},
  "relationship_ids": ["a-000"]
}
```

OpenContracts can retain its native documents, labels, annotations,
relationships and review UI. An export adapter needs only to emit the shape
above. Groundnut validates the source hash, exact offsets, creator, review
state, relationships and reviewer before promotion. Candidate and rejected
rows remain review records and cannot enter a support probe.

## Authorship rules

- Expert-imported spans use `attested` provenance with the query-generation
  disclosure preserved.
- Present-but-irrelevant cases use `adjudicated` provenance and identify the
  Groundnut reviewer; missing upstream annotation is never a negative label.
- Negation and other deterministic mutations use `derived` provenance and name
  their parent cases and transform.
- Human paraphrases use `authored` provenance.
- Agent/model paraphrases use `model_authored` provenance, record immutable
  model/prompt identity, and require human review.
- Paraphrase lexical overlap is part of the canonical case payload. Its allowed
  range is frozen in the probe plan before any detector runs.

The annotation system records why a label was admitted. It does not turn an
annotation, citation, or reviewer vote into a claim that the underlying source
is true.
