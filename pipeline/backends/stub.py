import json
import re

from .base import Backend, log_usage, approx_tokens

# Deterministic canned extractor used only by the test suite: pulls a
# "Name (\"Short\")" style party definition out of the chunk, if present.
QUOTE_PATTERN = re.compile(r"([A-Z][A-Za-z0-9&.,' ]{3,60}\(\"[A-Za-z0-9 ]+\"\))")
TEXT_MARKER = re.compile(r"(?:^|\n)[A-Z][A-Z ]* TEXT:\n")


class StubBackend(Backend):
    name = "stub"
    model = "stub-deterministic"

    def complete(self, prompt, doc_id=None):
        markers = list(TEXT_MARKER.finditer(prompt))
        chunk = prompt[markers[-1].end():] if markers else prompt
        findings = {}
        m = QUOTE_PATTERN.search(chunk)
        if m:
            findings["Parties"] = [m.group(1)]
        text = json.dumps({"findings": findings})
        log_usage(self.name, self.model, approx_tokens(prompt), approx_tokens(text), doc_id)
        return text
