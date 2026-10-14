import json
import time

import anthropic
from tenacity import Retrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from .base import GenResult, ModelClient

RETRYABLE = (
    anthropic.APIConnectionError,   # includes timeouts
    anthropic.RateLimitError,
    anthropic.InternalServerError,
)
TOOL_NAME = "record_extraction"


class AnthropicClient(ModelClient):
    def __init__(self, model: str, timeout_s: float, max_retries: int,
                 max_tokens: int = 8192, use_top_p: bool = False):
        self.name = model
        self.model = model
        self.max_tokens = max_tokens
        self.use_top_p = use_top_p
        self.max_retries = max_retries
        # our own retry loop (tenacity) is the only one: SDK retries are switched off
        self._client = anthropic.Anthropic(timeout=timeout_s, max_retries=0)

    def generate(self, prompt: str, schema: dict, sampling: dict) -> GenResult:
        params = {"temperature": sampling["temperature"]}
        if self.use_top_p:
            params["top_p"] = sampling["top_p"]

        attempts = 0

        def call():
            nonlocal attempts
            attempts += 1
            return self._client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                messages=[{"role": "user", "content": prompt}],
                tools=[{"name": TOOL_NAME,
                        "description": "Record the extracted requirements",
                        "input_schema": schema}],
                tool_choice={"type": "tool", "name": TOOL_NAME},
                **params,
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

        usage = (resp.usage.input_tokens, resp.usage.output_tokens)
        if resp.stop_reason == "max_tokens":
            return GenResult(None, latency, *usage, attempts, "truncated: max_tokens reached")
        block = next((b for b in resp.content if b.type == "tool_use"), None)
        if block is None:
            return GenResult(None, latency, *usage, attempts, "no tool_use block in response")
        return GenResult(json.dumps(block.input, ensure_ascii=False), latency, *usage, attempts)
