import time

import anthropic
from pydantic import BaseModel
from tenacity import Retrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from .base import GenResult, ModelClient

RETRYABLE = (
    anthropic.APIConnectionError,   # includes timeouts
    anthropic.RateLimitError,
    anthropic.InternalServerError,
)


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

    def generate(self, prompt: str, response_model: type[BaseModel], sampling: dict) -> GenResult:
        params = {"temperature": sampling["temperature"]}
        if self.use_top_p:
            params["top_p"] = sampling["top_p"]

        attempts = 0

        def call():
            nonlocal attempts
            attempts += 1
            return self._client.messages.parse(
                model=self.model,
                max_tokens=self.max_tokens,
                messages=[{"role": "user", "content": prompt}],
                output_format=response_model,   # schema goes in output_config, not in the prompt
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
        if resp.parsed_output is None:
            return GenResult(None, latency, *usage, attempts,
                             f"no parsed output (stop_reason={resp.stop_reason})")
        return GenResult(resp.parsed_output.model_dump_json(), latency, *usage, attempts)
