import json
import os
import urllib.request

from .base import Backend, log_usage, approx_tokens


class OpenAICompatBackend(Backend):
    name = "openai_compat"

    def __init__(self):
        self.base_url = os.environ["DD_BASE_URL"].rstrip("/")
        self.model = os.environ.get("DD_MODEL", "local-model")
        # Some local models (e.g. Qwen3) emit chain-of-thought tokens unless
        # told not to. That's a serving-side quirk of this endpoint, not a
        # pipeline concern, so the prefix (and its default) stay local here.
        self.prompt_prefix = os.environ.get("DD_PROMPT_PREFIX", "")
        self.api_key = os.environ.get("DD_API_KEY", "")
        self.max_tokens = int(os.environ.get("DD_MAX_TOKENS", "4000"))

    def complete(self, prompt, doc_id=None):
        full_prompt = (self.prompt_prefix + " " + prompt) if self.prompt_prefix else prompt
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": full_prompt}],
            "temperature": 0,
            "max_tokens": self.max_tokens,
        }
        if os.environ.get("DD_REASONING", "off") == "off":
            payload["reasoning"] = {"enabled": False}
        req = urllib.request.Request(
            self.base_url + "/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", **({"Authorization": "Bearer " + self.api_key} if self.api_key else {})},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=int(os.environ.get("DD_TIMEOUT_S", "600"))) as resp:
            body = json.loads(resp.read())
        text = body["choices"][0]["message"].get("content") or ""
        usage = body.get("usage", {})
        in_tok = usage.get("prompt_tokens", approx_tokens(full_prompt))
        out_tok = usage.get("completion_tokens", approx_tokens(text))
        log_usage(self.name, self.model, in_tok, out_tok, doc_id)
        return text
