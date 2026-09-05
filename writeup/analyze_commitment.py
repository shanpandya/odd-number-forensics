"""Analyze commitment curves: figures + commitment points + sentence scores.

Usage: .venv/bin/python writeup/analyze_commitment.py results/commitment_r1.jsonl
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
FIGS = ROOT / "writeup" / "figs"


def load(path):
    recs = [json.loads(l) for l in open(path)]
    meta = {m["rollout_id"]: m
            for m in json.load(open(str(path).replace(".jsonl", ".meta.json")))}
    by_roll = defaultdict(list)
    for r in recs:
        by_roll[r["rollout_id"]].append(r)
    for v in by_roll.values():
        v.sort(key=lambda r: r["cut_idx"])
    return by_roll, meta


def commitment_point(cuts, final_parity, hi=0.875, lo=0.125):
    """First cut position (fraction of trace) from which p_odd stays on the
    final answer's side of the threshold for the rest of the trace."""
    target = (lambda p: p >= hi) if final_parity == "odd" else (lambda p: p <= lo)
    n = len(cuts)
    for i in range(n):
        if all(target(c["p_odd"]) for c in cuts[i:]):
            return cuts[i]["cut_idx"] / max(1, cuts[-1]["cut_idx"])
    return None  # never commits by this definition


def main(path):
    by_roll, meta = load(path)
    FIGS.mkdir(exist_ok=True)

    # --- figure: all curves, colored by final parity ---
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.2), sharey=True)
    agg = {"odd": [], "even": []}
    cps = {"odd": [], "even": []}
    for rid, cuts in by_roll.items():
        fp = meta[rid]["final_parity"]
        xs = [c["cut_idx"] / max(1, cuts[-1]["cut_idx"]) for c in cuts]
        ys = [c["p_odd"] for c in cuts]
        ax = ax1 if fp == "odd" else ax2
        ax.plot(xs, ys, alpha=0.45, lw=1.2,
                color="#dd9f40" if fp == "odd" else "#4053d3")
        agg[fp].append((xs, ys))
        cp = commitment_point(cuts, fp)
        cps[fp].append(cp)
    for ax, fp, title in [(ax1, "odd", "rollouts that answered ODD"),
                          (ax2, "even", "rollouts that answered EVEN")]:
        ax.set_title(f"{title} (n={len(agg[fp])})", fontsize=10)
        ax.set_xlabel("position in reasoning trace (fraction)")
        ax.axhline(0.5, color="#999", lw=0.6, ls="--")
        ax.set_ylim(-0.03, 1.03)
        ax.spines[["top", "right"]].set_visible(False)
    ax1.set_ylabel("P(final answer is odd | prefix)")
    fig.suptitle("Commitment curves - DeepSeek R1-0528, Odd Number base prompt "
                 "(8 resamples per cut)", fontsize=11)
    fig.tight_layout()
    fig.savefig(FIGS / "commitment_curves.png", dpi=200)
    print(f"wrote {FIGS/'commitment_curves.png'}")

    # --- commitment point stats ---
    for fp in ("odd", "even"):
        vals = [c for c in cps[fp] if c is not None]
        never = sum(1 for c in cps[fp] if c is None)
        if vals:
            vals.sort()
            print(f"{fp}-final: commitment point median {vals[len(vals)//2]:.2f} "
                  f"of trace (range {vals[0]:.2f}-{vals[-1]:.2f}); "
                  f"{never} never lock in")
        else:
            print(f"{fp}-final: no rollout ever locks in ({never} total)")

    # cut-0 (prompt-only) base rate
    c0 = [cuts[0]["p_odd"] for cuts in by_roll.values() if cuts[0]["cut_idx"] == 0]
    print(f"cut-0 p_odd mean: {sum(c0)/len(c0):.2f} (channel base rate)")

    # --- sentence resampling scores: biggest |delta p_odd| steps ---
    steps = []
    for rid, cuts in by_roll.items():
        for a, b in zip(cuts, cuts[1:]):
            steps.append((b["p_odd"] - a["p_odd"], rid, b["cut_idx"],
                          b["sentence"][:110]))
    steps.sort(key=lambda s: -abs(s[0]))
    out = ROOT / "writeup" / "top_sentences.md"
    with open(out, "w") as f:
        f.write("# Top 40 sentences by |delta P(odd)| (resampling score)\n\n")
        for d, rid, ci, s in steps[:40]:
            f.write(f"- **{d:+.2f}** [{rid} cut {ci}] {s}\n")
    print(f"wrote {out}; top 5:")
    for d, rid, ci, s in steps[:5]:
        print(f"  {d:+.2f} [{rid}#{ci}] {s[:90]}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "results/commitment_r1.jsonl")
