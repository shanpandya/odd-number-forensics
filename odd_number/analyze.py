"""Analysis: parse answers, compute odd-rates with Wilson 95% CIs.

Usage:
  .venv/bin/python -m odd_number.analyze results/run_*.jsonl
"""

import argparse
import glob
import json
import math
import re
from collections import defaultdict

NUM_RE = re.compile(r"-?\d[\d,]*")


def extract_number(text: str) -> int | None:
    """Last integer in the text (models often explain, then answer)."""
    matches = NUM_RE.findall(text or "")
    if not matches:
        return None
    try:
        return int(matches[-1].replace(",", ""))
    except ValueError:
        return None


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    denom = 1 + z**2 / n
    center = (p + z**2 / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / denom
    return (max(0.0, center - half), min(1.0, center + half))


def classify(record: dict) -> str:
    """-> 'odd' | 'even' | 'unparsed' | 'error'"""
    if record.get("error"):
        return "error"
    num = extract_number(record.get("text", ""))
    if num is None:
        return "unparsed"
    return "odd" if num % 2 else "even"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("paths", nargs="+", help="JSONL files or globs")
    args = p.parse_args()

    files = []
    for path in args.paths:
        files.extend(glob.glob(path))
    cells = defaultdict(list)
    for fp in files:
        with open(fp) as f:
            for line in f:
                r = json.loads(line)
                cells[(r["model"], r["condition"])].append(classify(r))

    print(
        f"{'model':<42} {'condition':<22} {'n':>4} {'odd':>4} "
        f"{'odd%':>6} {'95% CI':>16} {'unparsed':>8} {'err':>4}"
    )
    for (model, cond), outcomes in sorted(cells.items()):
        valid = [o for o in outcomes if o in ("odd", "even")]
        k = sum(1 for o in valid if o == "odd")
        n = len(valid)
        lo, hi = wilson(k, n)
        rate = f"{100 * k / n:5.1f}%" if n else "   n/a"
        print(
            f"{model:<42} {cond:<22} {n:>4} {k:>4} {rate:>6} "
            f"[{100 * lo:5.1f}%,{100 * hi:5.1f}%] "
            f"{sum(1 for o in outcomes if o == 'unparsed'):>8} "
            f"{sum(1 for o in outcomes if o == 'error'):>4}"
        )


if __name__ == "__main__":
    main()
