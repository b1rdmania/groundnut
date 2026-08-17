"""Self-contained, offline reviewer for a frozen support-pilot batch."""

from __future__ import annotations

import json

from .support_review import PilotReviewManifest


def render_support_review_html(manifest: PilotReviewManifest) -> str:
    payload = {
        "manifest_sha256": manifest.sha256,
        "target_group_count": manifest.target_group_count,
        "max_context_characters": manifest.max_context_characters,
        "lexical_overlap_min": manifest.lexical_overlap_min,
        "lexical_overlap_max": manifest.lexical_overlap_max,
        "rows": [row.canonical_payload() for row in manifest.rows],
    }
    encoded = json.dumps(payload, sort_keys=True).replace("</", "<\\/")
    return _DOCUMENT.replace("__GROUNDNUT_DATA__", encoded)


_DOCUMENT = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Groundnut support-pilot review</title>
<style>
:root { color-scheme: light dark; font-family: ui-sans-serif, system-ui, sans-serif; }
body { margin: 0; background: #11150f; color: #edf3e8; }
header { position: sticky; top: 0; z-index: 2; padding: 14px 20px; background: #1b2417; border-bottom: 1px solid #526148; }
main { max-width: 1100px; margin: auto; padding: 20px; }
.bar { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
.card { border: 1px solid #526148; border-radius: 10px; padding: 16px; margin: 16px 0; background: #182015; }
.grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
label { display: block; font-size: 13px; color: #bdd0b3; margin: 8px 0 4px; }
textarea, input, select { box-sizing: border-box; width: 100%; padding: 9px; background: #0e120c; color: #edf3e8; border: 1px solid #526148; border-radius: 6px; }
textarea { min-height: 90px; resize: vertical; }
#context { min-height: 230px; font-family: ui-monospace, monospace; font-size: 12px; }
button { padding: 9px 14px; border: 1px solid #8eaa7e; border-radius: 6px; background: #304628; color: white; cursor: pointer; }
button:hover { background: #405c35; }
.warning { color: #ffd27a; }
.small { font-size: 12px; color: #9fb096; }
@media (max-width: 760px) { .grid { grid-template-columns: 1fr; } }
</style>
</head>
<body>
<header>
  <div class="bar">
    <strong>Groundnut support-pilot review</strong>
    <span id="position"></span><span id="progress" class="warning"></span>
    <button id="previous">Previous</button><button id="next">Save & next</button>
    <button id="download">Download reviewed TSV</button>
  </div>
  <div class="small" id="manifest"></div>
</header>
<main>
  <div class="card">
    <div class="grid">
      <div><label>Default human reviewer ID</label><input id="defaultReviewer" placeholder="human:name"></div>
      <div><label>Source</label><input id="source" readonly></div>
    </div>
    <label>Question</label><textarea id="question" readonly></textarea>
    <div class="grid">
      <div><label>Attested answer span</label><textarea id="attested" readonly></textarea></div>
      <div><label>Present candidate span</label><textarea id="present" readonly></textarea></div>
    </div>
    <label id="contextLabel">Exact detector context</label><textarea id="context" readonly></textarea>
  </div>

  <div class="card">
    <h3>1. Present-but-irrelevant ruling</h3>
    <p class="small">Does the present candidate fail to answer the question? Accept only when it is genuinely irrelevant.</p>
    <div class="grid"><div><label>Decision</label><select id="irrelevantDecision"></select></div><div><label>Reviewer ID</label><input id="irrelevantReviewer"></div></div>
    <label>Note</label><textarea id="irrelevantNote"></textarea>
  </div>

  <div class="card">
    <h3>2. Supported paraphrase</h3>
    <p class="small">Write an accurate restatement that is absent from the source. Keep it neither trivially copied nor unrelated.</p>
    <label>Paraphrase <span id="overlap" class="warning"></span></label><textarea id="paraphraseText"></textarea>
    <div class="grid"><div><label>Author kind</label><select id="paraphraseAuthorKind"><option value=""></option><option>human</option><option>agent</option></select></div><div><label>Immutable author ID</label><input id="paraphraseAuthorId"></div></div>
    <div class="grid"><div><label>Decision</label><select id="paraphraseDecision"></select></div><div><label>Human reviewer ID</label><input id="paraphraseReviewer"></div></div>
    <label>Note</label><textarea id="paraphraseNote"></textarea>
  </div>

  <div class="card">
    <h3>3. Contradiction proposal</h3>
    <p class="small">Check that the deterministic polarity flip truly contradicts the attested span and remains grammatical.</p>
    <label>Frozen proposal</label><textarea id="contradiction" readonly></textarea>
    <div class="grid"><div><label>Decision</label><select id="contradictionDecision"></select></div><div><label>Reviewer ID</label><input id="contradictionReviewer"></div></div>
    <label>Note</label><textarea id="contradictionNote"></textarea>
  </div>
</main>
<script>
const data = __GROUNDNUT_DATA__;
const decisions = ['pending', 'accepted', 'rejected', 'ambiguous'];
for (const id of ['irrelevantDecision','paraphraseDecision','contradictionDecision']) {
  const select = document.getElementById(id);
  for (const value of decisions) select.add(new Option(value, value));
}
let index = 0;
const state = data.rows.map(row => ({
  input_sha256: row.input_sha256,
  source_id: row.candidate.source_id,
  question: row.candidate.question,
  attested_text: row.candidate.original_text,
  present_candidate_text: row.candidate.claim_text,
  context_text: row.context.text,
  irrelevant_decision: row.irrelevance_review.decision,
  irrelevant_reviewer_id: row.irrelevance_review.reviewer_id || '',
  irrelevant_note: row.irrelevance_review.note || '',
  paraphrase_text: row.paraphrase.text || '',
  paraphrase_author_kind: row.paraphrase.author.kind || '',
  paraphrase_author_id: row.paraphrase.author.id || '',
  paraphrase_decision: row.paraphrase.review.decision,
  paraphrase_reviewer_id: row.paraphrase.review.reviewer_id || '',
  paraphrase_note: row.paraphrase.review.note || '',
  contradiction_proposal: row.contradiction_proposal.text,
  contradiction_decision: row.contradiction_review.decision,
  contradiction_reviewer_id: row.contradiction_review.reviewer_id || '',
  contradiction_note: row.contradiction_review.note || ''
}));
const ids = {
  source:'source_id', question:'question', attested:'attested_text', present:'present_candidate_text', context:'context_text',
  irrelevantDecision:'irrelevant_decision', irrelevantReviewer:'irrelevant_reviewer_id', irrelevantNote:'irrelevant_note',
  paraphraseText:'paraphrase_text', paraphraseAuthorKind:'paraphrase_author_kind', paraphraseAuthorId:'paraphrase_author_id',
  paraphraseDecision:'paraphrase_decision', paraphraseReviewer:'paraphrase_reviewer_id', paraphraseNote:'paraphrase_note',
  contradiction:'contradiction_proposal', contradictionDecision:'contradiction_decision', contradictionReviewer:'contradiction_reviewer_id', contradictionNote:'contradiction_note'
};
function save() {
  const row = state[index];
  for (const [id,key] of Object.entries(ids)) if (!['source','question','attested','present','context','contradiction'].includes(id)) row[key] = document.getElementById(id).value;
  const reviewer = document.getElementById('defaultReviewer').value.trim();
  if (reviewer) {
    for (const key of ['irrelevant_reviewer_id','paraphrase_reviewer_id','contradiction_reviewer_id']) if (!row[key]) row[key] = reviewer;
  }
}
function load() {
  const row = state[index];
  for (const [id,key] of Object.entries(ids)) document.getElementById(id).value = row[key];
  document.getElementById('position').textContent = `Row ${index + 1} of ${state.length}`;
  const ready = state.filter(r => r.irrelevant_decision === 'accepted' && r.paraphrase_decision === 'accepted' && r.contradiction_decision === 'accepted').length;
  document.getElementById('progress').textContent = `${ready}/${data.target_group_count} fully accepted`;
  updateOverlap();
}
function tokens(text) { return new Set((text.toLocaleLowerCase().match(/[\p{L}\p{N}_]+/gu) || [])); }
function updateOverlap() {
  const left = tokens(state[index].attested_text), right = tokens(document.getElementById('paraphraseText').value);
  const union = new Set([...left, ...right]); let shared = 0; for (const token of left) if (right.has(token)) shared++;
  const score = union.size ? shared / union.size : 1;
  const valid = score >= data.lexical_overlap_min && score <= data.lexical_overlap_max;
  document.getElementById('overlap').textContent = `overlap ${score.toFixed(3)} — frozen band ${data.lexical_overlap_min}–${data.lexical_overlap_max} ${valid ? '✓' : '✗'}`;
}
document.getElementById('paraphraseText').addEventListener('input', updateOverlap);
function move(delta) { save(); index = Math.max(0, Math.min(state.length - 1, index + delta)); load(); }
document.getElementById('previous').onclick = () => move(-1);
document.getElementById('next').onclick = () => move(1);
document.getElementById('manifest').textContent = `Frozen manifest ${data.manifest_sha256}`;
document.getElementById('contextLabel').textContent = `Exact ${data.max_context_characters.toLocaleString()}-character-or-shorter detector context`;
const headers = Object.keys(state[0]);
function quote(value) { const text = String(value ?? ''); return /[\t\r\n"]/.test(text) ? '"' + text.replaceAll('"','""') + '"' : text; }
document.getElementById('download').onclick = () => {
  save();
  const tsv = [headers.join('\t'), ...state.map(row => headers.map(key => quote(row[key])).join('\t'))].join('\r\n') + '\r\n';
  const link = document.createElement('a');
  link.href = URL.createObjectURL(new Blob([tsv], {type:'text/tab-separated-values'}));
  link.download = 'support-pilot-review.tsv'; link.click(); URL.revokeObjectURL(link.href);
};
load();
</script>
</body>
</html>
"""
