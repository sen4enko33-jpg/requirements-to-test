"""A toy tool for checking the agent loop: it returns its text unchanged. It is replaced by the real tools
(search over the corpus and others) in the next sub-step."""
from pydantic import BaseModel, Field

from .registry import Tool


class EchoArgs(BaseModel):
    text: str = Field(min_length=1, max_length=500, description="The text to repeat.")


def echo(args: EchoArgs) -> dict:
    return {"echo": args.text}


ECHO = Tool(
    name="echo",
    description="Repeats the given text unchanged. Call it only when the user explicitly asks you to echo or repeat a text "
                "with the echo tool; never for anything else. Returns {\"echo\": <text>}.",
    args_model=EchoArgs,
    fn=echo,
)
