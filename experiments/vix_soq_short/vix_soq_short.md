# VIX settlement (SOQ) pre-open SHORT — Phase 2 thesis

**Status**: Phase 2 complete 2026-05-28. **REJECT (one-window-wonder / holdout-decayed).**
**Verdict**: **9/12 mechanically, but REJECT for deploy.** The three failures (#2 W3-holdout mean, #3
all-regimes-positive, #7 bootstrap-lower) are precisely the deploy-binding ones — the edge is
**entirely pre-2023**: W1 **+5.21** / W2 **+13.57** / **W3 −0.43 bp (Sh −0.06)**; WF halves H1 **+9.52** /
H2 **+0.20**. Bootstrap 95% CI **[−1.37, +12.41]** straddles zero. Per lessons #16/#25/#31 (the W3
holdout is the binding deploy signal) and the btc_volbreak / retail_overshoot_fade precedent, a
one-window-wonder whose holdout is net-negative is **not deployable, period** — the nominal 9/12
"MARGINAL" label is overridden by the qualitative reading that the failures are the decay failures,
not sample-width misses (contrast a sample-width-only miss that still has a live-positive holdout). The Griffin-Shams post-publication + post-2022-0DTE decay red flag (#3 in
"why this might fail") fired exactly as written. **Forward-watch curiosity (NOT a deploy path):** the
last 8 events (Oct-2025→May-2026) rebounded to 7/8 wins (~+11 bp), implying 2023→mid-2025 was ~−3 bp
and a possible re-emergence — but using a post-hoc sub-slice to rescue the verdict is goalpost-moving
(barred per the no-regime-gate-overlay rule). Re-screen only if that rebound persists ≥1yr AND a fresh
pre-commit is locked first. **#77/#81-bug-immune** (fixed window) — the decay is real, not a geometry artifact.

## Phase 2 results table

| # | Criterion | Threshold | Observed | Pass? |
|---|---|---|---|---|
| 1 | Full mean net | ≥ +3.0 bp | **+4.86** | ✅ |
| 2 | W3 holdout mean net | ≥ +2.0 bp | **−0.43** | ❌ |
| 3 | All 3 regimes net positive | >0 | +5.2 / +13.6 / **−0.4** | ❌ |
| 4 | Annualized Sharpe (×√12) | ≥ +0.30 | **+0.51** | ✅ |
| 5 | PF (SHORT, lesson #55) | ≥ 1.3 | **1.75** | ✅ |
| 6 | MDD | ≤ −10% | **−1.57%** | ✅ |
| 7 | Bootstrap 95% CI lower | > 0 | **−1.37** | ❌ |
| 8 | Direction-gap | > +0.30 | **+1.33** | ✅ |
| 9 | Placebo SHORT mean | < +3 bp | **−0.61** | ✅ |
| 10 | Cost-stress @ 2× net | > 0 | **+3.36** | ✅ |
| 11 | Deflated Sharpe (n_trials=28) | ≥ 0.0 | **+0.23** | ✅ |
| 12 | WF halves both positive | >0 | H1 +9.5 / **H2 +0.2** | ✅* |

n=88 SPX500, 2019-2026. *#12 passes only because H2 is +0.20 (barely >0) — but that masks the
W3-within-H2 decay; #2/#3 capture it. Cost-zero gross +6.36 bp (Sh +0.66) → real signal eaten partly
by friction but mostly by **regime decay**, not by cost (lesson #26: cost-zero ≫ 0 yet W3-dead =
mechanism died, not friction-bound). NDX100 same-complex (sanity only, not load-bearing): full +8.22 bp
/ W3 +1.82 bp — NDX's holdout is positive but VIX is SPX-option-specific so this can't rescue SPX.

## Mechanistic interpretation

- **One-window-wonder.** W1 (2019-20) + W2 (2021-22) carry the entire full-sample edge; the 2023-2026
  holdout is flat-to-negative. This is the same shape as `btc_volbreak` (W2 carries everything) and
  `retail_overshoot_fade` (W2 +1.30 → W3 −1.07) — both REJECTED on the same holdout-binding logic.
- **Decay is consistent with the Griffin-Shams (2018) effect being arbed/regulated away.** The VIX
  settlement-manipulation pattern they documented (2008-2015 sample) was published in 2018 and drew
  Cboe/regulatory scrutiny; the pre-settlement SPX drift it implied is exactly what decayed to zero in
  the 2023-2026 window here. Academic-flow half-life (lesson #7) struck again.
- **Cost-zero diagnostic (lesson #26).** Gross Sh +0.66 with W3-dead is NOT a friction story — the
  full-sample positive comes from W1/W2, and no plausible cost change resurrects a net-negative W3.
- **Why this still mattered to run.** It was the best-cadence (~12/yr) and statistically strongest
  (t −1.81, MEDIUM tier) short candidate the v2 audit surfaced. Its rejection on holdout-decay tightens
  the short-side conclusion: even the strongest screen cell from the forced-flow family decays in the
  holdout — corroborating that the *durable* structural shorts in this book are the **quarter-aligned
  forced-rebalance** ones (`quarter_end_xau_short`, `triple_witch_close_short`), not the
  monthly-options-microstructure ones (this), which sit closest to the 0DTE-arbed complex.

Origin: short-side book-enhancement slate (2026-05-28), top fresh SHORT candidate.

> Origin: short-side book-enhancement slate (2026-05-28). Top fresh SHORT candidate surfaced by the
> v2 structural-flow audit ([structural_flow_audit_v2_results.csv](../structural_flow_audit/structural_flow_audit_v2_results.csv)):
> `vix_soq_settle SPX500 08:30-09:30 ET` MEDIUM tier — null-gap **−6.97 bp**, t **−1.81**, **n=88**,
> cost-headroom +5.5 bp. The **best-cadence structural short available** (~12/yr vs 4/yr for
> `quarter_end_xau_short` / `triple_witch_close_short`) → its bootstrap CI tightens an order of
> magnitude faster than the quarterly sparse shorts.

---

## Thesis (mechanism)

1. **VIX settles monthly via a Special Opening Quotation (SOQ).** The SOQ is computed from the
   opening prices of the strip of SPX options at the **09:30 ET market open on VIX-expiration
   Wednesday** (the Wednesday 30 days before the following month's 3rd-Friday SPX expiry;
   rule-approximated here as the Wednesday before the 3rd Friday — the screen's `gen_vix_soq_dates`).
2. **Settlement hedging exerts transient directional pressure on the SPX complex.** Griffin & Shams
   (2018) document that SPX-option volume spikes at the SOQ auction in patterns consistent with
   VIX-derivative holders trading SPX options to influence the settlement print, biasing OTM-put
   demand up into the open. The associated hedging/convergence flow shows up on the futures side as
   **downward pressure on SPX in the pre-settlement hour**.
3. **The pre-settlement window (08:30–09:30 ET) on the SPX500 CFD captures the futures-side shadow**
   of that flow. Screen: event mean **−6.36 bp** vs same-weekday non-event placebo **+0.61 bp**
   → gap **−6.97 bp**, t **−1.81**, n=88. SPX drifts DOWN into the SOQ; the placebo Wednesday drifts
   slightly up — the effect is settlement-specific, not generic pre-open beta.
4. **Forced-flow, not a directional macro view.** Dealer settlement hedging happens regardless of
   macro narrative → this is short-biased, **uncorrelated ballast** for a long-heavy book, not a bear
   bet (which lessons #34/#35/#36 tombstoned). Direction is SHORT, **pre-committed**; the dir-gap
   null-check (lesson #54) confirms it carries directional content rather than book-keeping artifact.
5. **Distinct driver from every existing component** (options-settlement microstructure vs ORB
   opening-impulse / lunch_fade basis-arb / event_calendar macro-anticipation) → low timing
   correlation by construction.

## Key reference

- Griffin, J. & Shams, A. (2018), "Manipulation in the VIX?", *Review of Financial Studies* 31(4).
- Cboe VIX SOQ methodology (settlement via SPX-option opening prices on expiration Wednesday).

## Signal math

```
universe : SPX500 (primary); NDX100 = same-complex sanity check (VIX is SPX-specific, so NDX is
           only a partial corroborator — NDX has its own VXN settlement)
trigger  : Wednesday before the 3rd Friday of each month (VIX-expiration Wednesday)  ~12/yr
window   : 08:30 -> 09:30 ET  (the hour BEFORE the 09:30 SOQ print)
direction: SHORT ; entry = 08:30 open, exit = 09:30 close (fixed window, no stops/levels)
cost     : SPX500 1.5 bp RT default (Eightcap Raw all-in), 2x stress
```

Like `triple_witch_close_short` / `quarter_end_xau_short`, this is
**#77/#81-bug-immune** — fixed forward window, no stops, no levels, no retest geometry, no same-bar
look-ahead (entry at the window-start open, exit at the window-end close).

## Why retail-accessible

One SHORT entry + exit per VIX-expiration Wednesday on a liquid Eightcap index CFD. ~12/yr.
Deployment analog: MES futures (short the 08:30–09:30 ET hour).

## Universe

SPX500 (primary). NDX100 reported as a same-complex sanity check only — **not** load-bearing
corroboration, because VIX settlement is SPX-option-specific (NDX has its own VXN complex with a
separate settlement). Do not promote on NDX corroboration alone.

## Expected performance

- ~12 events/yr; n≈88 over 2019-2026.
- Screen gross SHORT ≈ +6.4 bp/event; net (−1.5 bp cost) ≈ **+4.9 bp/event**.
- Target annualized Sharpe (×√12) **+0.3 to +0.6** research, pre-haircut.
- Sparse but the **highest-cadence structural short in the book** → fastest CI convergence.

## Fail conditions (pre-committed — FROZEN BEFORE THE PHASE-2 RUN)

Applied to **SHORT SPX500** primary at 1.5 bp default cost. SHORT asymmetric-payoff mechanism →
per **lesson #55** the WR>55% template is REPLACED by the **PF≥1.3 + Sh≥+0.30 + MDD≤10% trio**
(criteria 4/5/6). 12/12 = PASS; 8–11 = MARGINAL (watch-list); <8 = REJECT.

| # | Criterion | Threshold |
|---|---|---|
| 1 | Full mean net (SHORT) | ≥ +3.0 bp/event |
| 2 | W3 (2023-26) holdout mean net | ≥ +2.0 bp/event |
| 3 | All 3 regimes net positive | W1, W2, W3 > 0 |
| 4 | Annualized Sharpe (×√12) | ≥ +0.30 |
| 5 | PF (SHORT, lesson #55) | ≥ 1.3 |
| 6 | MDD (notional equity curve) | ≤ −10% |
| 7 | Bootstrap 95% CI lower | > 0 bp |
| 8 | Direction-gap (SHORT zc Sh − LONG zc Sh) | > +0.30 |
| 9 | Placebo SHORT mean (non-event same-weekday) | < +3.0 bp |
| 10 | Cost-stress @ 2× default net mean | > 0 bp |
| 11 | Deflated Sharpe (selection-bias adj., n_trials=28) | ≥ 0.0 |
| 12 | Walk-forward halves both net mean | > 0 |

## Why this might fail (red flags)

1. **Pre-open liquidity / spread risk.** 08:30–09:30 ET is BEFORE the 09:30 cash open; the SPX500
   CFD spread is wider pre-open than intraday, so realistic cost could exceed the 1.5 bp default.
   Criterion #10 (2× cost-stress) is the binding guard; if it fails the edge is friction-bound, not
   absent (lesson #26 cost-zero diagnostic distinguishes the two).
2. **t = −1.81 at the screen** is MEDIUM, not STRONG — directional content is moderate; the bootstrap
   CI (criterion #7) is the honest small-magnitude test.
3. **Griffin-Shams effect may have decayed post-publication** (2018) and post-regulatory-scrutiny —
   criterion #2 (W3 holdout ≥ +2 bp) is the decay guard.
4. **Settlement mechanics changed** (Cboe has adjusted SOQ rules over time) — regime split (#3) flags
   any structural break across W1/W2/W3.

## Phase 1 → 2 plan

- [x] Phase 0/1 — v2 structural-flow screen cleared MEDIUM (gap −6.97 bp, t −1.81, n=88, headroom +5.5 bp)
- [ ] Phase 2 — full simulator, 12 frozen kill criteria, bootstrap CI, cost-sweep, WF halves, deflated Sharpe, direction null, placebo, recent-event trade audit
- [ ] Verdict + STATE.md / RESEARCH_NOTES update

## Files

- [vix_soq_short_demo.py](vix_soq_short_demo.py) — Phase 2 simulator (reuses `structural_flow_audit` helpers)
