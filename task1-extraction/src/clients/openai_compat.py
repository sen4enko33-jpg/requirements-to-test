import copy
import time

import openai
from openai import OpenAI
from pydantic import BaseModel
from tenacity import Retrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from .base import GenResult, ModelClient

RETRYABLE = (
    openai.APIConnectionError,   # includes timeouts
    openai.RateLimitError,
    openai.InternalServerError,
)


def strict_schema(model: type[BaseModel]) -> dict:
    """JSON schema in the form strict structured output accepts: $ref inlined,
    every object closed (additionalProperties: false), every property required,
    no `default` keywords. Field descriptions are kept."""
    schema = model.model_json_schema()
    defs = schema.pop("$defs", {})

    def fix(node):
        if isinstance(node, list):
            return [fix(v) for v in node]
        if not isinstance(node, dict):
            return node
        if "$ref" in node:  # inline, so sibling keywords such as `description` stay valid
            target = copy.deepcopy(defs[node["$ref"].rsplit("/", 1)[-1]])
            node = {**target, **{k: v for k, v in node.items() if k != "$ref"}}
        out = {}
        for k, v in node.items():
            if k == "default":
                continue
            if k == "properties":
                out[k] = {name: fix(sub) for name, sub in v.items()}
            else:
                out[k] = fix(v)
        if out.get("type") == "object" and "properties" in out:
            out["additionalProperties"] = False
            out["required"] = list(out["properties"])
        return out

    return fix(schema)


class OpenAICompatClient(ModelClient):
    """Any model behind an OpenAI-compatible chat API (OpenRouter, Ollama, ...)."""

    def __init__(self, model: str, base_url: str, api_key: str, timeout_s: float,
                 max_retries: int, max_tokens: int = 8192, extra_body: dict | None = None,
                 schema_limits: dict | None = None):
        self.name = model
        self.model = model
        self.max_tokens = max_tokens
        self.max_retries = max_retries
        self.extra_body = extra_body  # provider-specific request options from config.yaml
        # {field: max number of items} for array fields; added as maxItems to the schema of the REQUEST only
        # (stops runaway lists of a local model), the Pydantic schema and the validation stay as they are
        self.schema_limits = schema_limits
        # our own retry loop (tenacity) is the only one: SDK retries are switched off
        self._client = OpenAI(base_url=base_url, api_key=api_key, timeout=timeout_s, max_retries=0)

    def generate(self, prompt: str, response_model: type[BaseModel], sampling: dict) -> GenResult:
        schema = strict_schema(response_model)
        for field, limit in (self.schema_limits or {}).items():
            schema["properties"][field]["maxItems"] = limit
        response_format = {
            "type": "json_schema",
            "json_schema": {"name": response_model.__name__, "strict": True, "schema": schema},
        }
        attempts = 0

        def call():
            nonlocal attempts
            attempts += 1
            return self._client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                response_format=response_format,    # schema goes here, not in the prompt text
                temperature=sampling["temperature"],
                top_p=sampling["top_p"],
                max_tokens=self.max_tokens,
                extra_body=self.extra_body,
            )

        retrying = Retrying(
            retry=retry_if_exception_type(RETRYABLE),
            stop=stop_after_attempt(self.max_retries),
            wait=wait_exponential(multiplier=1, max=20),
            reraise=True,
        )
        start = time.perf_counter()
        try:
            resp = retrying(call)
        except Exception as e:
            return GenResult(None, time.perf_counter() - start, None, None,
                             attempts, f"{type(e).__name__}: {e}")
        latency = time.perf_counter() - start

        usage = resp.usage
        tin = usage.prompt_tokens if usage else None
        tout = usage.completion_tokens if usage else None
        cost = (usage.model_extra or {}).get("cost") if usage else None

        def result(text, error=None):
            return GenResult(text, latency, tin, tout, attempts, error, cost)

        provider_error = (resp.model_extra or {}).get("error")
        if provider_error:
            return result(None, f"provider error: {provider_error}")
        if not resp.choices:
            return result(None, "empty response: no choices")
        choice = resp.choices[0]
        if choice.finish_reason == "length":
            return result(None, "truncated: max_tokens reached")
        if getattr(choice.message, "refusal", None):
            return result(None, f"refusal: {choice.message.refusal}")
        if not choice.message.content:
            return result(None, f"empty content (finish_reason={choice.finish_reason})")
        return result(choice.message.content)
