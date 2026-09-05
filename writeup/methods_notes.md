# Methods notes: the channel-debugging chain (for the write-up)

Chronology of Thursday night / Friday morning. This is write-up gold for the
"truth-seeking / sanity checks" criterion - the calibration check at cut-0
caught a broken measurement channel before any conclusions were drawn from it.

1. **Built resampling on DeepSeek v4 Flash** (hand-built chat template via
   completions endpoint). Instrument validation passed (19/19 forcing each way).
   Overnight run: 536 cut-points, 0 API errors.
2. **Sanity check caught the problem**: cut-0 (prompt-only) P(odd) = 0.09, but
   the chat-endpoint base rate was 0.50. Same prompt, 5x discrepancy.
3. **Diagnosis 1 - provider heterogeneity**: the original chat replication was
   served by TEN different providers (OpenRouter routing); the completions
   endpoint routed only to Together. Per-provider base rates differ wildly
   (chat@Together alone: ~70% odd vs 50% for the mixture). The "50% base rate"
   of v1 was an average over a heterogeneous serving mixture. [Methodological
   finding in its own right: provider serving stack materially changes this
   behaviour - quantization/template/sampling defaults are uncontrolled
   confounds in API-based research.]
4. **Diagnosis 2 - template archaeology**: v4-Flash's official encoder
   (encoding_dsv4.py in the HF repo) prepends a reasoning-effort prompt in
   thinking mode. My hand template omitted it (= effort "low").
   **Single-variable result: effort=low -> 5% odd; effort=high -> 80% odd**
   (n=20 each, same prompt/provider/endpoint). The effort preamble alone is a
   massive causal lever on grader-following. [Secondary finding for write-up;
   v4-Flash, Together, n=20/cell.]
5. **Diagnosis 3 - hidden reasoning**: completions responses returned ~1-char
   texts, but usage showed 457-3347 completion tokens: providers generate the
   thinking and strip it from completions responses. The channel continues
   prefixes genuinely; the continued reasoning is just not returned (fine for
   P(odd|prefix), which needs only the answer).
6. **Pivot to R1-0528 @ SiliconFlow** (single pinned provider, standard R1
   template, no effort-prompt complication; the forensics paper's own
   resampling subject). Channel checks: forcing 20/20 both directions
   (results/instrument_validation_r1.json); chat base rate on-channel 27/40
   odd = 68%, matching the cross-model screen's 68% exactly; empty-prefix
   completions parity consistent within noise.
7. **Final design**: 40 chat rollouts (visible reasoning) -> 20 balanced
   (10 odd / 10 even) -> completions resampling, 8 resamples per sentence cut,
   max 30 cuts/trace, all pinned SiliconFlow.

Artifacts: results/commitment_v1.jsonl (v4-flash, broken-channel; appendix
robustness only), results/effort_test.log, results/provider_sweep.log,
results/r1_sweep.log, results/instrument_validation{,_r1}.json,
results/r1_base_chat.jsonl, results/commitment_r1.jsonl (headline).

Caveats to carry: temperature left at provider default (not pinned) in all
runs; sentence split is regex-based; curves measure the SiliconFlow serving
of R1, one prompt, one environment.

## Pre-registered prediction (logged BEFORE injection data collected)
Curves show even-commitment is early/sticky, odd-commitment late/unstable.
Prediction for the 15%-cut injection test: inject_user pins p_odd near 0
(sticky attractor); inject_grader shifts p_odd up but does NOT pin near 1
(unstable state) - i.e. |effect of user-sentence| > |effect of grader-sentence|
relative to control. Logged 2026-09-04 before results/injection.jsonl existed.

## Repeated resampling: attempted, infeasible via API (documented negative)
Built the Macar-style suppression pipeline (chunked generation + keyword
rejection of grader-authority sentences, with a chunked-baseline control arm).
Smoke tests revealed a hard blocker: every completions provider that honors
prefill correctly (SiliconFlow, DeepInfra, StreamLake, Together) STRIPS the
generated thinking from responses - the loop cannot see the sentences it
needs to filter. Providers that do return reasoning continuations via chat
prefill (Parasail, Baidu, Novita) fail the forcing validation (prefill not
honored: even-committed prefixes yield odd answers). Conclusion: suppression
interventions need visible incremental thinking + faithful prefill, which no
current API serving offers together; feasible only with local weights (vLLM).
Named as future work; necessity-side evidence comes from the commitment
curves, sufficiency-side from the injection test.
