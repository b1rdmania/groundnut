import os

from .stub import StubBackend
from .openai_compat import OpenAICompatBackend
from .agent import AgentBackend
from .ollama_native import OllamaNativeBackend


def get_backend(name=None):
    name = name or os.environ.get("DD_BACKEND")
    if not name:
        name = "openai_compat" if os.environ.get("DD_BASE_URL") else "agent"
    if name == "stub":
        return StubBackend()
    if name == "openai_compat":
        return OpenAICompatBackend()
    if name == "ollama_native":
        return OllamaNativeBackend()
    if name == "agent":
        return AgentBackend()
    raise ValueError("unsupported backend name: " + name)
