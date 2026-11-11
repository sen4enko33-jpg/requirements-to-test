from abc import ABC, abstractmethod
from dataclasses import dataclass

from pydantic import BaseModel


@dataclass
class GenResult:
    text: str | None        # JSON string of the extraction (None on failure)
    latency_s: float        # wall time of the whole call, including retries
    tokens_in: int | None
    tokens_out: int | None
    attempts: int           # how many API attempts were needed
    error: str | None = None
    cost_usd: float | None = None   # cost of the successful attempt as reported by the provider


class ModelClient(ABC):
    name: str

    @abstractmethod
    def generate(self, prompt: str, response_model: type[BaseModel], sampling: dict) -> GenResult:
        """Send the prompt and ask the model for output matching `response_model`.

        The schema reaches the model through the provider's structured-output
        mechanism, not through the prompt text.
        """
