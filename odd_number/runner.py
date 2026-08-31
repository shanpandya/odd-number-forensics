"""Batch runner: models x conditions x n samples -> results JSONL.

Usage:
  .venv/bin/python -m odd_number.runner --models qwen/qwen3-32b \\
      --conditions base,no_function,no_conflict --n 25
  .venv/bin/python -m odd_number.runner --list-models qwen   # id lookup
"""

import argparse
import asyncio
import datetime
import json
from pathlib import Path

import httpx

from .client import load_api_key, make_client, sample
from .conditions import CONDITIONS

RESULTS_DIR = Path(__file__).resolve().parent.parent / "results"
CONCURRENCY = 20


async def run_matrix(models, condition_ids, n, out_path, temperature, max_tokens=None):
    client = make_client()
    sem = asyncio.Semaphore(CONCURRENCY)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    lock = asyncio.Lock()
    done = 0
    total = len(models) * len(condition_ids) * n

    async def one(model, cond_id, idx):
        nonlocal done
        messages = CONDITIONS[cond_id].build()
        kwargs = {}
        if temperature is not None:
            kwargs["temperature"] = temperature
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        async with sem:
            result = await sample(client, model, messages, **kwargs)
        record = {
            "model": model,
            "condition": cond_id,
            "sample_idx": idx,
            "messages": messages,
            "timestamp": datetime.datetime.now(
                datetime.timezone.utc
            ).isoformat(),
            **result,
        }
        async with lock:
            with out_path.open("a") as f:
                f.write(json.dumps(record) + "\n")
            done += 1
            if done % 20 == 0 or done == total:
                print(f"  {done}/{total} samples done")
        return record

    tasks = [
        one(m, c, i)
        for m in models
        for c in condition_ids
        for i in range(n)
    ]
    records = await asyncio.gather(*tasks)
    errs = [r for r in records if r["error"]]
    print(f"Finished: {len(records)} samples, {len(errs)} errors -> {out_path}")
    if errs:
        for e in errs[:5]:
            print(f"  ERROR [{e['model']}/{e['condition']}]: {e['error']}")


def list_models(substring: str):
    key = load_api_key()
    resp = httpx.get(
        "https://openrouter.ai/api/v1/models",
        headers={"Authorization": f"Bearer {key}"},
        timeout=30,
    )
    resp.raise_for_status()
    for m in sorted(resp.json()["data"], key=lambda x: x["id"]):
        if substring.lower() in m["id"].lower():
            print(m["id"])


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--models", help="comma-separated OpenRouter model ids")
    p.add_argument(
        "--conditions",
        default="base,no_function,no_conflict",
        help=f"comma-separated ids from: {','.join(CONDITIONS)}",
    )
    p.add_argument("--n", type=int, default=25, help="samples per cell")
    p.add_argument("--temperature", type=float, default=None)
    p.add_argument("--max-tokens", type=int, default=None)
    p.add_argument("--out", default=None, help="output JSONL path")
    p.add_argument("--list-models", metavar="SUBSTRING")
    args = p.parse_args()

    if args.list_models is not None:
        list_models(args.list_models)
        return

    if not args.models:
        p.error("--models is required (or use --list-models)")
    models = [m.strip() for m in args.models.split(",") if m.strip()]
    cond_ids = [c.strip() for c in args.conditions.split(",") if c.strip()]
    unknown = [c for c in cond_ids if c not in CONDITIONS]
    if unknown:
        p.error(f"unknown conditions: {unknown}. Known: {list(CONDITIONS)}")

    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = (
        Path(args.out) if args.out else RESULTS_DIR / f"run_{stamp}.jsonl"
    )
    asyncio.run(run_matrix(models, cond_ids, args.n, out_path, args.temperature, args.max_tokens))


if __name__ == "__main__":
    main()
