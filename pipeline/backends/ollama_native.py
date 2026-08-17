import json
import os
import urllib.request

from .base import Backend, log_usage, approx_tokens


class OllamaNativeBackend(Backend):
    """Ollama's native /api/chat. Exists because some served models emit
    hidden reasoning tokens through the OpenAI-compatible endpoint with no
    way to disable them there; the native API has an explicit think switch.
    Serving-side quirks stay in this file per the model-agnostic rule.
    """

    name = "ollama_native"

    def __init__(self):
        self.base_url = os.environ["DD_BASE_URL"].rstrip("/")
        if self.base_url.endswith("/v1"):
            self.base_url = self.base_url[:-3]
        self.model = os.environ.get("DD_MODEL", "local-model")
        self.max_tokens = int(os.environ.get("DD_MAX_TOKENS", "2500"))

    def complete(self, prompt, doc_id=None):
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "think": False,
            "options": {"temperature": 0, "num_predict": self.max_tokens},
        }
        req = urllib.request.Request(
            self.base_url + "/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        timeout = int(os.environ.get("DD_TIMEOUT_S", "900"))
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read())
        text = body.get("message", {}).get("content", "")
        in_tok = body.get("prompt_eval_count", approx_tokens(prompt))
        out_tok = body.get("eval_count", approx_tokens(text))
        log_usage(self.name, self.model, in_tok, out_tok, doc_id)
        return text
