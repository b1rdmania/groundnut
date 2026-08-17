import json
import time
import uuid
from pathlib import Path

from .base import Backend, log_usage, approx_tokens

REPO = Path(__file__).resolve().parent.parent.parent
PENDING = REPO / "runs" / "tasks" / "pending"
DONE = REPO / "runs" / "tasks" / "done"
POLL_INTERVAL_S = 2
TIMEOUT_S = 1800


class AgentBackend(Backend):
    """Task-file protocol: writes a pending extraction task and blocks until
    the supervising agent drops a matching file in DONE."""

    name = "agent"
    model = "supervising-agent"

    def complete(self, prompt, doc_id=None):
        PENDING.mkdir(parents=True, exist_ok=True)
        DONE.mkdir(parents=True, exist_ok=True)
        task_id = uuid.uuid4().hex
        (PENDING / (task_id + ".json")).write_text(
            json.dumps({"id": task_id, "doc": doc_id, "prompt": prompt})
        )
        done_path = DONE / (task_id + ".json")
        deadline = time.time() + TIMEOUT_S
        while not done_path.exists():
            if time.time() > deadline:
                raise TimeoutError("agent backend timed out waiting for " + task_id)
            time.sleep(POLL_INTERVAL_S)
        result = json.loads(done_path.read_text())
        text = result.get("completion", "")
        log_usage(
            self.name,
            self.model,
            result.get("in_tokens", approx_tokens(prompt)),
            result.get("out_tokens", approx_tokens(text)),
            doc_id,
        )
        return text
