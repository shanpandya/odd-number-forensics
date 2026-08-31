"""Generate write-up figures from results JSONL files.

Usage: .venv/bin/python writeup/figures.py
"""

import glob
import json
import sys
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from odd_number.analyze import classify, wilson  # noqa: E402

FIGS = Path(__file__).resolve().parent / "figs"
RESULTS = Path(__file__).resolve().parent.parent / "results"

SHORT = {
    "deepseek/deepseek-v4-flash-0731": "DeepSeek v4 Flash",
    "qwen/qwen3.5-27b": "Qwen3.5 27B",
    "qwen/qwen3.5-122b-a10b": "Qwen3.5 122B",
    "openai/gpt-oss-120b": "GPT-OSS 120B",
}

COND_ORDER = [
    ("base", "base\n(reward fn)"),
    ("plain_note", "plain note\n(grader: odd correct)"),
    ("user_owned", "user-owned\n(user gets bonus)"),
    ("training_consequence", "training signal\n(real RL reward)"),
    ("inert_metadata", "inert metadata\n(unused stub)"),
    ("no_consequence", "no consequence\n(logged only)"),
    ("deauthorized", "de-authorized\n(user: buggy, ignore)"),
    ("no_function", "no function\n(control)"),
    ("no_conflict", "no conflict\n(control)"),
]


def load(paths):
    cells = defaultdict(list)
    for pat in paths:
        for fp in glob.glob(str(pat)):
            with open(fp) as f:
                for line in f:
                    r = json.loads(line)
                    cells[(r["model"], r["condition"])].append(classify(r))
    return cells


def rate(outcomes):
    valid = [o for o in outcomes if o in ("odd", "even")]
    k = sum(1 for o in valid if o == "odd")
    n = len(valid)
    if n == 0:
        return None
    lo, hi = wilson(k, n)
    return 100 * k / n, 100 * lo, 100 * hi, n


def fig_conditions():
    """Odd-rate across conditions for the two deep-dive models."""
    cells = load([RESULTS / "replication_v1.jsonl", RESULTS / "matrix_v1.jsonl"])
    models = ["deepseek/deepseek-v4-flash-0731", "qwen/qwen3.5-27b"]
    fig, ax = plt.subplots(figsize=(10, 4.6))
    width = 0.38
    colors = ["#4053d3", "#dd9f40"]
    for mi, model in enumerate(models):
        xs, ys, err_lo, err_hi = [], [], [], []
        for ci, (cond, _) in enumerate(COND_ORDER):
            res = rate(cells.get((model, cond), []))
            if res is None:
                continue
            p, lo, hi, n = res
            xs.append(ci + (mi - 0.5) * width)
            ys.append(p)
            err_lo.append(p - lo)
            err_hi.append(hi - p)
        ax.bar(
            xs, ys, width, label=SHORT[model], color=colors[mi],
            yerr=[err_lo, err_hi], capsize=3, error_kw={"lw": 1},
        )
    ax.set_xticks(range(len(COND_ORDER)))
    ax.set_xticklabels([lbl for _, lbl in COND_ORDER], fontsize=8)
    ax.set_ylabel("Odd answer rate (%)")
    ax.set_title(
        "Odd-rate by condition (asked for an even number; n=25/cell, "
        "95% Wilson CIs)"
    )
    ax.legend(frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(FIGS / "conditions.png", dpi=200)
    print("wrote figs/conditions.png")


def fig_screen():
    """Cross-model base odd-rate (screen), sorted, grouped by developer."""
    path = RESULTS / "screen_v1.jsonl"
    if not path.exists():
        print("screen_v1.jsonl not ready; skipping fig_screen")
        return
    cells = load(
        [path, RESULTS / "replication_v1.jsonl",
         RESULTS / "screen_v1_kimi_fix.jsonl"]
    )
    rows = []
    for (model, cond), outcomes in cells.items():
        if cond != "base":
            continue
        res = rate(outcomes)
        if res:
            rows.append((model, *res))
    rows.sort(key=lambda r: r[1], reverse=True)
    fig, ax = plt.subplots(figsize=(9, 0.34 * len(rows) + 1.6))
    names = [r[0].split("/", 1)[1] for r in rows]
    vals = [r[1] for r in rows]
    errs = [[r[1] - r[2] for r in rows], [r[3] - r[1] for r in rows]]
    dev_color = {
        "openai": "#7a7a7a", "google": "#4053d3", "anthropic": "#b51d14",
        "deepseek": "#00b25d", "qwen": "#dd9f40", "moonshotai": "#8d5eb7",
    }
    colors = [dev_color.get(r[0].split("/")[0], "#333") for r in rows]
    ax.barh(
        range(len(rows)), vals, xerr=errs, color=colors, capsize=2,
        error_kw={"lw": 0.8},
    )
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels(names, fontsize=8)
    ax.invert_yaxis()
    ax.set_xlabel("Odd answer rate in base condition (%)")
    ax.set_title("Cross-model screen (n=25/model, 95% Wilson CIs)")
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(FIGS / "screen.png", dpi=200)
    print("wrote figs/screen.png")


if __name__ == "__main__":
    FIGS.mkdir(exist_ok=True)
    fig_conditions()
    fig_screen()
