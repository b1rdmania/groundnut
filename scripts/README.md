# Experimental operations

These scripts prepare, run and inspect active experiment lanes. They are
reproducible operational surfaces, not stable product CLIs.

- `*_support_*`: semantic-support case preparation, review, bake-off and admission
- `*_navigation_*`: structured-navigation packs and evaluations
- `*_relevance_*`: verification-question relevance experiments
- `compare_segmenters.py`: controlled segmentation comparison
- `compose_shadow_receipt.py`: non-canonical decision/abstention exploration
- `fetch_corpus.py`: compatibility-corpus reconstruction from its public manifest

The current product orchestration is `python3 -m groundnut.ic_loop`; its
contract is documented in [`docs/LEDGER.md`](../docs/LEDGER.md).
