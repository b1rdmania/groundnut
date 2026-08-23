# Domain packs

These JSON files are executable playbooks, not quality claims. They were
ported from the checklist-driven deployment to make the reusable method live
in Groundnut. All three currently declare `experimental` evidence status:

- `ma_dd` is the deployed 18-category playbook. It is not identical to the
  existing 41-category evaluation taxonomy and cannot inherit that score.
- `grant_compliance` and `trust_obligations` have demonstration corpora but no
  labelled evaluation or frozen acceptance bar.
- `ic_research` is the one-category shadow pack for investment-committee
  research reports, used by `python3 -m groundnut.ic_loop`. It carries no
  IC-domain quality claim.

Run a built-in pack with:

```bash
python3 -m pipeline.run --domain trust_obligations --in contracts --out results
```

Unknown keys fail; the canonical registry never silently substitutes M&A for a
misspelled or missing domain. Hosts that want a default must choose it
explicitly.
