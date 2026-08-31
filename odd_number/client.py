"""Async OpenRouter client with retries and reasoning capture."""

import asyncio
import os
from pathlib import Path

from openai import AsyncOpenAI, APIError, APITimeoutError, RateLimitError

OPENROUTER_BASE = "https://openrouter.ai/api/v1"


def load_api_key() -> str:
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        env_path = Path(__file__).resolve().parent.parent / ".env"
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                line = line.strip()
                if line.startswith("OPENROUTER_API_KEY="):
                    key = line.split("=", 1)[1].strip().strip('"').strip("'")
    if not key:
        raise SystemExit(
            "No OpenRouter key found. Set OPENROUTER_API_KEY or put "
            "OPENROUTER_API_KEY=sk-or-... in .env at the project root."
        )
    return key


def make_client() -> AsyncOpenAI:
    return AsyncOpenAI(
        base_url=OPENROUTER_BASE, api_key=load_api_key(), timeout=300.0
    )


async def sample(
    client: AsyncOpenAI,
    model: str,
    messages: list[dict],
    max_retries: int = 4,
    **kwargs,
) -> dict:
    """One completion. Returns dict with text, reasoning, meta, or error."""
    last_err = None
    for attempt in range(max_retries):
        try:
            resp = await client.chat.completions.create(
                model=model,
                messages=messages,
                extra_body={"reasoning": {"enabled": True}},
                **kwargs,
            )
            choice = resp.choices[0]
            msg = choice.message.model_dump()
            return {
                "text": msg.get("content") or "",
                # OpenRouter normalizes reasoning; some providers use
                # reasoning_content
                "reasoning": msg.get("reasoning")
                or msg.get("reasoning_content")
                or "",
                "finish_reason": choice.finish_reason,
                "provider": getattr(resp, "provider", None),
                "usage": resp.usage.model_dump() if resp.usage else None,
                "error": None,
            }
        except (APIError, APITimeoutError, RateLimitError, Exception) as e:
            last_err = e
            await asyncio.sleep(2**attempt)
    return {
        "text": "",
        "reasoning": "",
        "finish_reason": None,
        "provider": None,
        "usage": None,
        "error": f"{type(last_err).__name__}: {last_err}",
    }
