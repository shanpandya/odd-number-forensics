"""Commitment curves via prefix resampling.

For each selected base rollout: split its reasoning into sentences, and for
each cut point k (after sentence k), sample N fresh continuations of the
trace from that prefix via the raw completions endpoint (DeepSeek chat
template). The fraction of continuations ending in an odd number estimates
P(odd | prefix up to k) - the commitment curve.

Usage:
  .venv/bin/python -m odd_number.resample --n-resamples 10 \
      --out results/commitment_v1.jsonl
"""

import argparse
import asyncio
import json
import re
from pathlib import Path

import httpx

from .analyze import classify, extract_number
from .client import load_api_key

MODEL = "deepseek/deepseek-r1-0528"
ROOT = Path(__file__).resolve().parent.parent
CONCURRENCY = 12
MAX_CUTS = 30  # subsample evenly if a trace has more sentences

SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")


def split_sentences(text: str) -> list[str]:
    return [s for s in SENT_SPLIT.split(text.strip()) if s.strip()]


_ENC = None

def _encoder():
    global _ENC
    if _ENC is None:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "enc", ROOT / "results" / "encoding_dsv4.py")
        _ENC = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_ENC)
    return _ENC


def build_raw_prompt(user_prompt: str, prefix: str) -> str:
    # R1-0528 template: thinking opens immediately after the Assistant tag
    return (f"<｜begin▁of▁sentence｜><｜User｜>{user_prompt}"
            f"<｜Assistant｜><think>\n{prefix}")


async def sample_continuation(client, key, raw_prompt, max_tokens=12000,
                              retries=4):
    for attempt in range(retries):
        try:
            r = await client.post(
                "https://openrouter.ai/api/v1/completions",
                headers={"Authorization": f"Bearer {key}"},
                json={"model": MODEL, "prompt": raw_prompt,
                      "provider": {"order": ["SiliconFlow"],
                                   "allow_fallbacks": False},
                      "max_tokens": max_tokens},
                timeout=180,
            )
            d = r.json()
            if "error" in d:
                raise RuntimeError(str(d["error"])[:200])
            return d["choices"][0]["text"]
        except Exception:
            if attempt == retries - 1:
                return None
            await asyncio.sleep(2 ** attempt)


async def run(rollouts, n_resamples, out_path):
    key = load_api_key()
    sem = asyncio.Semaphore(CONCURRENCY)
    lock = asyncio.Lock()
    done = [0]
    async with httpx.AsyncClient() as client:

        async def one(rollout_id, user_prompt, cut_idx, n_cuts, prefix,
                      sentence):
            async with sem:
                texts = await asyncio.gather(*[
                    sample_continuation(client, key,
                                        build_raw_prompt(user_prompt, prefix))
                    for _ in range(n_resamples)
                ])
            answers, parities = [], []
            for t in texts:
                if t is None:
                    answers.append(None); parities.append("error"); continue
                num = extract_number(t)
                answers.append(num)
                parities.append("unparsed" if num is None
                                else ("odd" if num % 2 else "even"))
            rec = {
                "rollout_id": rollout_id, "cut_idx": cut_idx,
                "n_cuts": n_cuts, "sentence": sentence,
                "prefix_chars": len(prefix),
                "answers": answers, "parities": parities,
                "p_odd": (sum(1 for p in parities if p == "odd")
                          / max(1, sum(1 for p in parities
                                       if p in ("odd", "even")))),
            }
            async with lock:
                with out_path.open("a") as f:
                    f.write(json.dumps(rec) + "\n")
                done[0] += 1
                if done[0] % 10 == 0:
                    print(f"  {done[0]} cut-points done", flush=True)

        tasks = []
        for r in rollouts:
            sents = split_sentences(r["reasoning"])
            n = len(sents)
            if n > MAX_CUTS:
                idxs = sorted({round(i * (n - 1) / (MAX_CUTS - 1))
                               for i in range(MAX_CUTS)})
            else:
                idxs = list(range(n))
            # cut 0 = empty prefix (pure prompt); cut k = after sentence k
            user_prompt = r["messages"][-1]["content"]
            rid = f"{r['model'].split('/')[-1]}#{r['sample_idx']}"
            tasks.append(one(rid, user_prompt, 0, n, "", "<EMPTY - prompt only>"))
            for k in idxs:
                prefix = " ".join(sents[: k + 1])
                tasks.append(one(rid, user_prompt, k + 1, n, prefix, sents[k]))
        print(f"{len(tasks)} cut-points x {n_resamples} resamples "
              f"= {len(tasks) * n_resamples} calls")
        await asyncio.gather(*tasks)
    print(f"done -> {out_path}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--source", default="results/replication_v1.jsonl")
    p.add_argument("--model", default=MODEL)
    p.add_argument("--n-resamples", type=int, default=10)
    p.add_argument("--max-rollouts", type=int, default=0,
                   help="0 = all base rollouts of the model")
    p.add_argument("--out", required=True)
    args = p.parse_args()

    rollouts = []
    with open(ROOT / args.source) as f:
        for line in f:
            r = json.loads(line)
            if (r["model"] == args.model and r["condition"] == "base"
                    and r.get("reasoning")
                    and classify(r) in ("odd", "even")):
                r["final_parity"] = classify(r)
                rollouts.append(r)
    if args.max_rollouts:
        rollouts = rollouts[: args.max_rollouts]
    print(f"{len(rollouts)} rollouts "
          f"({sum(1 for r in rollouts if r['final_parity']=='odd')} odd, "
          f"{sum(1 for r in rollouts if r['final_parity']=='even')} even)")
    out_path = ROOT / args.out
    # index of rollout metadata for the analysis step
    meta_path = out_path.with_suffix(".meta.json")
    meta_path.write_text(json.dumps(
        [{"rollout_id": f"{r['model'].split('/')[-1]}#{r['sample_idx']}",
          "final_parity": r["final_parity"],
          "final_answer": extract_number(r["text"]),
          "n_sentences": len(split_sentences(r["reasoning"]))}
         for r in rollouts], indent=1))
    asyncio.run(run(rollouts, args.n_resamples, out_path))


if __name__ == "__main__":
    main()
