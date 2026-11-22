"""Chat with a model that can call tools (OpenAI-compatible API: OpenRouter, Ollama, ...).

Unlike the client of task 2 (one prompt -> one structured answer), the agent sends the whole conversation
(system, user, assistant, tool messages) together with the list of tools, and the model answers either with text
or with tool calls. One call of `chat` = one step of the agent."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Protocol

import openai
from openai import OpenAI
from tenacity import Retrying, retry_if_exception_type, stop_after_attempt, wait_exponential

RETRYABLE = (openai.APIConnectionError, openai.RateLimitError, openai.InternalServerError)   # timeouts are APIConnectionError


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: str          # raw JSON text as the model wrote it (validated by the tool registry, not here)


@dataclass
class ChatResult:
    content: str | None                                    # text of the model (the final answer when there are no tool calls)
    tool_calls: list[ToolCall] = field(default_factory=list)
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    latency_s: float = 0.0
    attempts: int = 1
    finish_reason: str | None = None
    error: str | None = None                               # set when the call failed after all retries

    def assistant_message(self) -> dict:
        """The message to append to the conversation (the API needs the tool calls repeated back)."""
        msg = {"role": "assistant", "content": self.content}
        if self.tool_calls:
            msg["tool_calls"] = [{"id": c.id, "type": "function", "function": {"name": c.name, "arguments": c.arguments}}
                                 for c in self.tool_calls]
        return msg


class ChatModel(Protocol):
    name: str

    def chat(self, messages: list[dict], tools: list[dict], timeout_s: float | None = None) -> ChatResult: ...


class OpenAIChat:
    """Any model behind an OpenAI-compatible chat API with tool calling."""

    def __init__(self, model: str, base_url: str, api_key: str, timeout_s: float = 60, max_retries: int = 3,
                 max_tokens: int = 1024, temperature: float = 0.0, price_per_1m: dict | None = None,
                 extra_body: dict | None = None):
        self.name = model
        self.timeout_s, self.max_retries, self.max_tokens, self.temperature = timeout_s, max_retries, max_tokens, temperature
        self.price = price_per_1m or {}
        self.extra_body = extra_body
        self._client = OpenAI(base_url=base_url, api_key=api_key, timeout=timeout_s, max_retries=0)   # our retries only

    def _cost(self, usage, tin: int, tout: int) -> float:
        reported = (usage.model_extra or {}).get("cost") if usage is not None else None
        if reported is not None:
            return float(reported)
        return (tin * self.price.get("input", 0) + tout * self.price.get("output", 0)) / 1e6

    def chat(self, messages: list[dict], tools: list[dict], timeout_s: float | None = None) -> ChatResult:
        timeout = min(self.timeout_s, timeout_s) if timeout_s else self.timeout_s
        attempts = 0

        def call():
            nonlocal attempts
            attempts += 1
            kw = dict(model=self.name, messages=messages, temperature=self.temperature, max_tokens=self.max_tokens,
                      extra_body=self.extra_body)
            if tools:
                kw["tools"] = tools
            return self._client.with_options(timeout=timeout).chat.completions.create(**kw)

        start = time.perf_counter()
        try:
            resp = Retrying(retry=retry_if_exception_type(RETRYABLE), stop=stop_after_attempt(self.max_retries),
                            wait=wait_exponential(multiplier=1, max=20), reraise=True)(call)
        except Exception as e:
            return ChatResult(None, latency_s=time.perf_counter() - start, attempts=attempts, error=f"{type(e).__name__}: {e}")
        latency = time.perf_counter() - start
        usage = resp.usage
        tin = usage.prompt_tokens if usage else 0
        tout = usage.completion_tokens if usage else 0
        res = ChatResult(None, tokens_in=tin, tokens_out=tout, cost_usd=self._cost(usage, tin, tout), latency_s=latency,
                         attempts=attempts)
        provider_error = (resp.model_extra or {}).get("error")
        if provider_error:
            res.error = f"provider error: {json.dumps(provider_error, ensure_ascii=False)}"
            return res
        if not resp.choices:
            res.error = "empty response: no choices"
            return res
        choice = resp.choices[0]
        res.finish_reason = choice.finish_reason
        res.content = choice.message.content
        res.tool_calls = [ToolCall(c.id, c.function.name, c.function.arguments or "{}") for c in (choice.message.tool_calls or [])]
        if choice.finish_reason == "length" and not res.tool_calls:
            res.error = "truncated: max_tokens reached"
        elif not res.content and not res.tool_calls:
            res.error = f"empty answer (finish_reason={choice.finish_reason})"
        return res


def make_model(cfg: dict, api_key: str) -> OpenAIChat:
    m = cfg["model"]
    return OpenAIChat(m["model"], m["base_url"], api_key, m.get("timeout_s", 60), m.get("max_retries", 3),
                      m.get("max_tokens", 1024), m.get("temperature", 0.0), m.get("price_per_1m"), m.get("extra_body"))
