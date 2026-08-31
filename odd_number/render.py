"""Render results JSONL into readable markdown transcripts for hand-reading.

One file per model x condition, each sample annotated with its parity
classification so positives can be spot-checked against the metric.

Usage:
  .venv/bin/python -m odd_number.render results/run_*.jsonl
"""

import argparse
import glob
import json
from collections import defaultdict
from pathlib import Path

from .analyze import classify, extract_number

OUT_DIR = Path(__file__).resolve().parent.parent / "transcripts_md"


def safe(name: str) -> str:
    return name.replace("/", "__").replace(":", "_")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("paths", nargs="+")
    args = p.parse_args()

    files = []
    for path in args.paths:
        files.extend(glob.glob(path))
    groups = defaultdict(list)
    for fp in files:
        with open(fp) as f:
            for line in f:
                r = json.loads(line)
                groups[(r["model"], r["condition"])].append(r)

    OUT_DIR.mkdir(exist_ok=True)
    for (model, cond), records in sorted(groups.items()):
        records.sort(key=lambda r: r["sample_idx"])
        lines = [f"# {model} — `{cond}`\n"]
        prompt = records[0]["messages"][-1]["content"]
        lines.append(f"**Prompt:**\n\n```\n{prompt}\n```\n\n---\n")
        for r in records:
            tag = classify(r)
            num = extract_number(r.get("text", ""))
            lines.append(
                f"## sample {r['sample_idx']} — **{tag.upper()}**"
                f" (parsed: {num})\n"
            )
            if r.get("error"):
                lines.append(f"**ERROR:** {r['error']}\n")
                continue
            if r.get("reasoning"):
                lines.append(f"**CoT:**\n\n> {r['reasoning'][:20000]}\n")
            lines.append(f"**Answer:**\n\n{r['text']}\n\n---\n")
        out = OUT_DIR / f"{safe(model)}__{cond}.md"
        out.write_text("\n".join(lines))
        print(f"wrote {out} ({len(records)} samples)")


if __name__ == "__main__":
    main()
