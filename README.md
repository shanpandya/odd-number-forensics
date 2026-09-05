# Odd Number Environment: a model forensics investigation

Why do models answer "odd" when asked for an even number, if the prompt
contains a reward function that pays for odd? An investigation of whether
this is reward hacking, following the protocol of
[Singh & Kroiz et al. (2026)](https://arxiv.org/abs/2606.26071) - and then
a causal audit of whether the chain-of-thought deliberation behind the
answer is real or post-hoc narration.

**Part 1** (Model Forensics SPAR take-home, August 2026):
[Google Doc](https://docs.google.com/document/d/1jMmEoWHumrOM6iWF-UUPaFwF9xJZUEt8BUFXGpanNCs/edit) (submitted version)
or [`writeup/final.md`](writeup/final.md).
Verdict: it isn't reward hacking. The models fully understand the conflict and
are inferring the pass condition of the prompt. The behaviour survives
stripping all reward language, and collapses when the reward is made real
(a training signal) or the user disowns the function.

**Part 2** (MATS application extension, September 2026):
[`writeup/mats_fullv2.md`](writeup/mats_fullv2.md).
Is the deliberation causally real? Commitment curves - cut each reasoning
trace at every sentence boundary and regenerate the rest - show the outcome
is open at the channel's base rate when reasoning begins, and a single
spliced sentence at the 15% mark still swings the answer in either
direction. The deliberation is where the decision happens, not a story
written after it.

## Layout
- `odd_number/` - harness: `conditions.py` (all prompt variants),
  `runner.py` (async OpenRouter batch runner), `analyze.py` (rates + Wilson
  CIs), `render.py` (JSONL -> readable transcripts), `judge.py` (LLM-judge
  classification of reasoning traces), `resample.py` (commitment curves via
  prefill on the completions endpoint), `inject.py` (single-sentence
  injection test), `novelty.py` (dual-judge sentence classification).
- `results/` - raw results, one JSON record per sample, reasoning included.
- `transcripts_md/` - the same data, more readable.
- `writeup/` - both write-ups, figures, appendix sources, and analysis
  scripts (`analyze_commitment.py`, `figures.py`).

## Reproduce
```
uv venv && uv pip install openai httpx matplotlib
echo "OPENROUTER_API_KEY=sk-or-..." > .env
# Part 1
python -m odd_number.runner --models deepseek/deepseek-v4-flash-0731 --conditions base,no_function,no_conflict --n 25
python -m odd_number.analyze results/*.jsonl
# Part 2 (commitment curves; pin the provider - base rates vary wildly across them)
python -m odd_number.resample --source results/r1_sel.jsonl --n-resamples 8 --out results/commitment_r1_all.jsonl
python -m odd_number.inject --out results/injection.jsonl
python writeup/analyze_commitment.py
```
