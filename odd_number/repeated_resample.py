"""Repeated resampling (Macar et al. style): prevent a class of sentences
during generation and measure the effect on the final answer's parity.

Two arms, both generated sentence-by-sentence via the completions channel
(R1-0528 @ SiliconFlow):
  - baseline: chunked generation, accept every sentence (controls for the
    chunked-generation procedure itself)
  - filtered: reject-and-resample any sentence naming the reward/grader
    authority (keyword class), up to MAX_TRIES; if all tries match, accept
    the last candidate and count a leak.

Usage:
  .venv/bin/python -m odd_number.repeated_resample --n 25 \
      --out results/repeated_resample.jsonl
"""

import argparse
import asyncio
import json
import re
from pathlib import Path

import httpx

from .analyze import extract_number
from .client import load_api_key
from .conditions import CONDITIONS
from .resample import build_raw_prompt

ROOT = Path(__file__).resolve().parent.parent
MODEL = "deepseek/deepseek-r1-0528"
PROVIDER = "SiliconFlow"
CONCURRENCY = 8
MAX_TRIES = 8
MAX_STEPS = 45
MAX_CHARS = 30000
TARGET = re.compile(r"reward|grader|grading|scor(e|ing)|benchmark|ground truth"
                    r"|evaluat", re.I)
SENT_END = re.compile(r"[.!?](?=\s|$)")


async def chunk(client, key, raw_prompt, max_tokens=420):
    for attempt in range(4):
        try:
            r = await client.post(
                "https://openrouter.ai/api/v1/completions",
                headers={"Authorization": f"Bearer {key}"},
                json={"model": MODEL, "prompt": raw_prompt,
                      "provider": {"order": [PROVIDER],
                                   "allow_fallbacks": False},
                      "max_tokens": max_tokens},
                timeout=180)
            d = r.json()
            if "error" in d:
                raise RuntimeError(str(d["error"])[:150])
            return d["choices"][0]["text"], d["choices"][0].get("finish_reason")
        except Exception:
            if attempt == 3:
                return None, None
            await asyncio.sleep(2 ** attempt)


def first_sentence(text):
    """(sentence, done) - done=True if a think-end or hard stop appears first."""
    if "</think>" in text.split(".")[0]:
        return text, True
    m = SENT_END.search(text)
    if m:
        return text[: m.end()], False
    return text, False  # no boundary in chunk; take it all


async def one_rollout(client, key, prompt, arm, idx, out_path, lock):
    prefix, rejected, leaks, steps = "", 0, 0, 0
    while steps < MAX_STEPS and len(prefix) < MAX_CHARS:
        steps += 1
        accepted = None
        for t in range(MAX_TRIES if arm == "filtered" else 1):
            text, fin = await chunk(client, key,
                                    build_raw_prompt(prompt, prefix))
            if text is None:
                continue
            if "</think>" in text:
                accepted = text  # closing: take the whole remainder
                break
            # take up to the LAST sentence boundary in the chunk
            ms = list(SENT_END.finditer(text))
            sent = text[: ms[-1].end()] if ms else text
            if arm == "filtered" and TARGET.search(sent):
                # try to salvage the clean leading sentences of the chunk
                clean = ""
                for m in ms:
                    cand = text[: m.end()]
                    if TARGET.search(cand):
                        break
                    clean = cand
                if clean:
                    accepted = clean
                    break
                rejected += 1
                accepted = sent  # provisional; try again
                continue
            accepted = sent
            break
        else:
            if arm == "filtered" and accepted is not None:
                leaks += 1  # all tries matched; accept last candidate
        if accepted is None:
            break
        sep = "" if (not prefix or prefix.endswith(("\n", " "))
                     or accepted.startswith(("\n", " "))) else " "
        prefix += sep + accepted
        if "</think>" in accepted:
            break
    # final answer: continue past think-close if not present yet
    if "</think>" not in prefix:
        tail, _ = await chunk(client, key,
                              build_raw_prompt(prompt, prefix + "\n</think>\n"),
                              max_tokens=100)
        answer_text = tail or ""
    else:
        answer_text = prefix.split("</think>", 1)[1]
        if not extract_number(answer_text):
            tail, _ = await chunk(client, key,
                                  build_raw_prompt(prompt, prefix),
                                  max_tokens=100)
            answer_text = (answer_text or "") + (tail or "")
    num = extract_number(answer_text)
    rec = {"arm": arm, "idx": idx, "steps": steps, "rejected": rejected,
           "leaks": leaks, "trace": prefix, "answer_text": answer_text[:200],
           "answer": num,
           "parity": ("unparsed" if num is None
                      else ("odd" if num % 2 else "even"))}
    async with lock:
        with open(out_path, "a") as f:
            f.write(json.dumps(rec) + "\n")
        print(f"  {arm}#{idx}: {rec['parity']} "
              f"(steps={steps}, rejected={rejected}, leaks={leaks})",
              flush=True)


async def run(n, out_path):
    key = load_api_key()
    prompt = CONDITIONS["base"].build()[-1]["content"]
    sem = asyncio.Semaphore(CONCURRENCY)
    lock = asyncio.Lock()

    async def guarded(arm, i):
        async with sem:
            async with httpx.AsyncClient() as client:
                await one_rollout(client, key, prompt, arm, i, out_path, lock)

    await asyncio.gather(*[guarded(arm, i)
                           for arm in ("baseline", "filtered")
                           for i in range(n)])


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--n", type=int, default=25)
    p.add_argument("--out", required=True)
    args = p.parse_args()
    asyncio.run(run(args.n, ROOT / args.out))
    recs = [json.loads(l) for l in open(ROOT / args.out)]
    from collections import Counter
    for arm in ("baseline", "filtered"):
        sub = [r for r in recs if r["arm"] == arm]
        print(arm, dict(Counter(r["parity"] for r in sub)),
              "| mean rejected:",
              round(sum(r["rejected"] for r in sub) / max(1, len(sub)), 1))


if __name__ == "__main__":
    main()
