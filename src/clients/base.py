from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class GenResult:
    text: str | None        # raw JSON string returned by the model (None on failure)
    latency_s: float        # wall time of the whole call, including retries
    tokens_in: int | None
    tokens_out: int | None
    attempts: int           # how many API attempts were needed
    error: str | None = None


class ModelClient(ABC):
    name: str

    @abstractmethod
    def generate(self, prompt: str, schema: dict, sampling: dict) -> GenResult:
        """Send the prompt, ask for JSON matching `schema`, return the raw result."""
