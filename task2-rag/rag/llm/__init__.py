"""LLM client of the RAG part: an OpenAI-compatible chat client (OpenRouter, Ollama, ...).

base.py and openai_compat.py are a copy of task1-extraction/src/clients/, so that the two parts of the repository do not
depend on each other. A fix in one of the copies has to be made in the other as well."""
import os
import sys

from .base import GenResult, ModelClient
from .openai_compat import OpenAICompatClient

__all__ = ["GenResult", "ModelClient", "OpenAICompatClient", "make_client"]


def make_client(cfg: dict, model_key: str) -> OpenAICompatClient:
    """Client for models.<model_key> of config.yaml (the API key is read from the environment variable api_key_env)."""
    m = cfg["models"][model_key]
    key = m.get("api_key") or os.getenv(m.get("api_key_env", ""))
    if not key:
        sys.exit(f"no API key for models.{model_key}: set {m.get('api_key_env')} in .env (repository root or task2-rag)")
    return OpenAICompatClient(m["model"], m["base_url"], key, m.get("timeout_s", cfg["timeout_s"]),
                              m.get("max_retries", cfg["max_retries"]), m.get("max_tokens", cfg["max_tokens"]),
                              extra_body=m.get("extra_body"), schema_limits=m.get("schema_limits"))
