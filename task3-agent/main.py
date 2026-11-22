"""The agent of task 3 in one command:  python main.py "your question"

  python main.py "Hello, what can you do?"
  python main.py "Echo the text 'hi' with the echo tool" --max-steps 3

Needs OPENROUTER_API_KEY in .env (repository root or this folder). Every run writes its trace to traces/<run_id>.jsonl."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from agent.limits import Limits  # noqa: E402
from agent.llm import make_model  # noqa: E402
from agent.loop import run_agent  # noqa: E402
from agent.trace import Trace  # noqa: E402
from tools.echo import ECHO  # noqa: E402
from tools.registry import ToolRegistry  # noqa: E402


def load_config() -> dict:
    return yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))


def load_system_prompt(version: str) -> str:
    return (ROOT / "prompts" / f"system_{version}.md").read_text(encoding="utf-8").strip()


def build_tools() -> ToolRegistry:
    return ToolRegistry([ECHO])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("question", help="the question to the agent")
    ap.add_argument("--max-steps", type=int, help="override limits.max_steps of config.yaml")
    ap.add_argument("--max-cost", type=float, help="override limits.max_cost_usd of config.yaml")
    a = ap.parse_args()

    load_dotenv(ROOT / ".env"); load_dotenv(ROOT.parent / ".env")
    cfg = load_config()
    key = os.getenv(cfg["model"]["api_key_env"])
    if not key:
        sys.exit(f"no {cfg['model']['api_key_env']}: copy .env.example to .env (repository root) and put the key there")
    limits = Limits.from_config(cfg["limits"])
    if a.max_steps is not None:
        limits.max_steps = a.max_steps
    if a.max_cost is not None:
        limits.max_cost_usd = a.max_cost

    result = run_agent(a.question, make_model(cfg, key), build_tools(), limits, load_system_prompt(cfg["system_prompt"]),
                       Trace(ROOT / cfg["trace_dir"]))
    print(result.answer)
    u = result.usage
    print(f"\n[stop: {result.stop_reason} | steps {u['steps']} | tokens {u['tokens_in']}+{u['tokens_out']} | "
          f"${u['cost_usd']:.5f} | {u['elapsed_s']:.1f} s | tools: {[c['name'] for c in result.tool_calls] or '-'}]")
    print(f"[trace: {result.trace_path}]")
    return 0 if result.complete else 2


if __name__ == "__main__":
    sys.exit(main())
