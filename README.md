# Odd Number Environment: a model forensics investigation

Why do models answer "odd" when asked for an even number, if the prompt
contains a reward function that pays for odd? An investigation of whether
this is reward hacking, following the protocol of
[Singh & Kroiz et al. (2026)](https://arxiv.org/abs/2606.26071).

**Write-up: [Google Doc](https://docs.google.com/document/d/1jMmEoWHumrOM6iWF-UUPaFwF9xJZUEt8BUFXGpanNCs/edit) (submitted version) or [`writeup/final.md`](writeup/final.md)** (figures in `writeup/figs/`).

Submitted for the Model Forensics SPAR take-home, August 2026.

Overall verdict: It isn't reward hacking. The models fully understand conflict and
are inferring the pass condition of the prompt. The behaviour survives stripping all reward language, and collapses when the reward is made real (a training signal) or the user disowns the
function.

## Layout
- `odd_number/` - harness: `conditions.py` (all prompt variants),
  `runner.py` (async OpenRouter batch runner), `analyze.py` (rates + Wilson
  CIs), `render.py` (JSONL -> readable transcripts), `judge.py` (LLM-judge
  classification of reasoning traces).
- `results/` - raw results, one JSON record per sample, reasoning included.
- `transcripts_md/` - the same data, more readable.
- `writeup/` - the write-up, figures, and appendix sources.

## Reproduce
```
uv venv && uv pip install openai httpx matplotlib
echo "OPENROUTER_API_KEY=sk-or-..." > .env
python -m odd_number.runner --models deepseek/deepseek-v4-flash-0731 --conditions base,no_function,no_conflict --n 25
python -m odd_number.analyze results/*.jsonl
python -m odd_number.render results/*.jsonl
```
