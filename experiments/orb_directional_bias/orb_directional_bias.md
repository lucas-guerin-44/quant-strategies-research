# ORB Directional-Bias Predictor — GER40 (filter / revive companion to `orb_dax`)

**Status**: REJECTED at Phase 2 — 2026-05-21.

**Verdict**: REJECT. **No prior-day signal predicts GER40 first-break direction**, and the variants with full-sample Sharpe lift over the parent are 2019-2022 in-sample artifacts that **DEGRADE on the 2023-2026 holdout**. Lesson #16 ("holdout is the honest deployment signal") is decisive — full-sample numbers misleading.

Headline:

| Variant | Full Sh | 2019-20 | 2021-22 | **Holdout 23-26** | vs parent holdout +0.93 | MDD | Trades |
|---|---|---|---|---|---|---|---|
| **Parent LONG-only (reference)** | **+0.76** | +0.94 | +0.44 | **+0.93** | — | -7.8% | 1,440 |
| filter_long::pcir_60/40 (best full-Sh) | +1.07 | +1.64 | +0.81 | **+0.78** | **-0.15 (WORSE)** | -6.06% | 920 |
| filter_long::spx_0.0000 | +1.04 | +1.76 | +0.15 | +0.97 | +0.04 (noise) | -5.74% | 815 |
| filter_long::spx_0.0010 | +0.88 | +1.62 | -0.05 | +0.82 | -0.11 | -6.27% | 975 |
| combined::spx_0.0000 (revival path) | +0.90 | +1.58 | +0.16 | +0.80 | -0.13 | -6.60% | 1,413 |
| filter_short::spx_0.0000 (best revival) | +0.11 | +0.11 | +0.06 | +0.16 | (vs short +0.01) | -9.18% | 649 |

**No variant produces meaningful holdout lift.** The best holdout improvement (spx_0.0000 filter_long, +0.04) cuts trade count from 1,440 → 815 — half the cadence for noise-level Sharpe gain. The full-sample lift came from filtering 2019-2020 noise, not from any forward-looking edge.

---

## Run log — 2026-05-21

GER40 M5, 188,895 RTH bars + SPX500 M5, 515,873 bars (24h CFD). 2019-01-02 → 2026-04-17, 1,853 trading days.

### Hit-rate diagnostic — the core direction-prediction test

Does predictor sign match first-break direction better than chance? Unconditional first-break-up rate is 52.0% (secular DAX drift). Each predictor active only on bias != 0 days:

| Predictor | n signalled | hit-rate | vs 50% | vs 52% baseline |
|---|---|---|---|---|
| gap_0.0000 (sign only) | 1,852 | 49.8% | -0.2 | -2.2 |
| gap_0.0010 | 1,592 | 50.4% | +0.4 | -1.6 |
| **gap_0.0025 (best)** | **1,222** | **51.1%** | **+1.1** | **-0.9** |
| pcir_75/25 | 969 | 48.4% | -1.6 | -3.6 |
| pcir_60/40 | 1,513 | 49.4% | -0.6 | -2.6 |
| spx_0.0000 | 1,821 | 49.0% | -1.0 | -3.0 |
| spx_0.0010 | 1,464 | 48.9% | -1.1 | -3.1 |
| spx_0.0025 | 1,024 | 50.1% | +0.1 | -1.9 |
| mom5_0 | 1,847 | 49.2% | -0.8 | -2.8 |

**The 53% pre-committed bar fails on every predictor.** The best is gap_0.0025 at 51.1% — within the standard error of the 52.0% unconditional drift-up rate. **No predictor adds direction-prediction information.** Among the literature-classical candidates (gap continuation, prior close-in-range, SPX overnight lead), all fail the basic direction test.

This is the load-bearing diagnostic of the experiment. The premise — that one or more prior-day signals would lift hit-rate to 54-58% — is empirically refuted.

### Filter-mode results (LONG-only with bias filter)

Despite no direction-prediction edge, **filter_long mode produced apparent full-sample Sharpe lifts**:

| Predictor | Full Sh | 2019-20 | 2021-22 | **23-26 HO** | HO vs parent +0.93 |
|---|---|---|---|---|---|
| pcir_60/40 | +1.07 | +1.64 | +0.81 | +0.78 | **-0.15** |
| spx_0.0000 | +1.04 | +1.76 | +0.15 | +0.97 | +0.04 |
| spx_0.0010 | +0.88 | +1.62 | -0.05 | +0.82 | -0.11 |
| pcir_75/25 | +0.86 | +1.27 | +0.44 | +0.86 | -0.07 |
| spx_0.0025 | +0.79 | +1.37 | -0.04 | +0.86 | -0.07 |

**Every filter variant degrades or noise-equals the parent's +0.93 holdout** while cutting trade count 30-43%. This is the classic Lesson #16 / #20 pattern: full-sample Sharpe improvements concentrated in 2019-2020 with weaker holdout — overfit signature.

### Combined-mode (revival path)

Take LONG on +1, SHORT on -1, skip neutral:

| Predictor | Full Sh | 2019-20 | 2021-22 | 23-26 HO |
|---|---|---|---|---|
| **spx_0.0000 (best)** | **+0.90** | +1.58 | +0.16 | +0.80 |
| gap_0.0025 | +0.68 | +1.56 | -0.17 | +0.45 |
| gap_0.0010 | +0.61 | +1.15 | +0.14 | +0.46 |

The +0.90 spx_0.0000 looks impressive but holdout +0.80 < parent LONG-only +0.93. The combined-mode also re-enables the short leg on bias=-1 days, but holdout-period shorts drag in every regime tested. The short leg cannot be resurrected by any of the tested predictors.

### Revival-mode (SHORT-only with bias filter)

| Predictor | Full Sh | 2019-20 | 2021-22 | 23-26 HO |
|---|---|---|---|---|
| spx_0.0000 | +0.11 | +0.11 | +0.06 | +0.16 |
| spx_0.0025 | +0.10 | -0.09 | -0.15 | +0.50 |

Best SHORT-leg Sharpe is +0.11 vs the +0.30 pre-committed revival bar. **No predictor resurrects the silent short side.** The dax-orb shorts are a near-zero-Sharpe drag in every regime, and no prior-day signal localizes the small subset of days where shorts have edge.

### Null check (combined mode, predictor inverted)

| Predictor | Base Sh | Invert Sh | Gap | vs +0.30 bar |
|---|---|---|---|---|
| spx_0.0000 | +0.90 | -0.23 | +1.13 | PASS |
| gap_0.0025 | +0.68 | +0.20 | +0.49 | PASS |
| gap_0.0010 | +0.61 | +0.17 | +0.44 | PASS |
| pcir_75/25 | +0.32 | -0.15 | +0.47 | PASS |
| pcir_60/40 | +0.21 | -0.08 | +0.29 | borderline (just below +0.30) |
| spx_0.0010 | +0.58 | -0.11 | +0.69 | PASS |
| spx_0.0025 | +0.36 | -0.09 | +0.45 | PASS |
| gap_0.0000 | +0.46 | +0.20 | +0.27 | FAIL |
| mom5_0 | -0.07 | +0.75 | -0.82 | FAIL (inverted!) |

The null check passes for most predictors, which is interesting: when forced to take *opposite* of the predictor's call, combined-mode loses. But this is the trade-quality signal, not direction. Reading: the predictor partially identifies days/sides where the OR break has higher per-trade EV — not days where the break direction is predictable. Subtle distinction; the experiment was designed to test the former by way of the latter.

mom5 inverts decisively (-0.82 gap) — a small but real *contrarian* signal in DAX. Not pursued further; effect lives entirely in 2019-2020 pre-COVID and dies later.

### Cost sensitivity (combined::spx_0.0000)

| Cost RT | Sh |
|---|---|
| 0.0 pt | +1.14 |
| 0.5 pt | +1.02 |
| 1.0 pt | +0.90 |
| 1.5 pt | +0.78 |
| 2.0 pt | +0.66 |
| 3.0 pt | +0.41 |

~0.24 Sh/pt linear decay. Edge survives realistic retail spread.

---

## Mechanistic interpretation

Three findings, in order of importance:

**1. DAX first-break direction is genuinely unpredictable from prior-day-available info.** Gap direction, prior-close-in-range, SPX overnight lead, 5-day momentum — none of them lift hit-rate above the 52% unconditional drift baseline by more than 1 percentage point. The Xetra morning auction's price-discovery process appears to fully absorb whatever overnight information would be reflected in these signals, by the time the OR window completes. The 09:00-09:30 OR is *itself* the directional resolution; the predictors are stale by the time the break fires.

This is the same mechanistic conclusion the `dax_overnight` REJECT reached on a different timeframe (CFD overnight Sharpe +0.80 was a vendor-pricing artifact; on real FDAX it was -0.34). Whatever directional information overnight gives away on DAX gets correctly priced into the cash open before the OR-break trigger.

**2. The apparent full-sample Sharpe lifts are 2019-2022 in-sample fitting.** Every filter variant shows the same regime profile: 2019-2020 Sharpe much higher than parent (+1.27 to +1.76 vs parent +0.94), 2021-2022 mixed, **2023-2026 holdout flat-to-worse than parent**. The 2019-2020 lift is real *in-sample* but the predictor isn't capturing forward-looking information — it's capturing realized COVID-era regime structure that doesn't generalize.

Lesson #20 ("'Marginal' strategies don't become non-marginal through refinement") and Lesson #16 ("holdout is the honest deployment signal") together: a filter that raises full-sample by +0.31 but lowers holdout by -0.15 is overfit to the early regime. The parent's unfiltered LONG-only is correctly identified as the deployment ceiling, not a floor that this experiment was supposed to lift off of.

**3. The short leg of ORB-DAX cannot be resurrected by tested predictors.** SHORT-only Sharpe across all predictors and regimes maxes at +0.50 in one cell (filter_short::spx_0.0025 holdout 23-26) and is otherwise stuck at ~0. The parent's choice to run LONG-only and shadow-log shorts is correct; shadow-PnL analysis on real live data is the right path to detect a future regime where shorts re-earn their seat, not a prior-day filter.

### Cross-experiment lesson

When a filter variant shows full-sample Sharpe lift but null hit-rate improvement, the lift is mechanically suspect. The two ways a directional filter can lift Sharpe are: (a) it predicts direction correctly more often → lift via win-rate. (b) it predicts which days have higher per-trade EV even at constant win-rate → lift via per-trade payoff distribution. (b) is real but fragile — it requires a stable correlation between the predictor and the post-break trade outcome that doesn't reduce to direction prediction. In 2019-2022 GER40 ORB, (b)-style structure existed (prior-close-in-range correlated with trade quality). In 2023-2026 holdout, it disappeared. This pattern — (b)-style structure that disappears post-2022 — is a mild form of the same regime decay that killed VWAP fade, gap continuation, and other intraday MR strategies (lesson #28).

---

## What was NOT pursued (and why)

- **Multi-predictor stack** (ensemble of gap + pcir + spx). Each individual predictor already failed the hit-rate test, and the filter-mode lifts are holdout-degrading. Stacking won't fix overfit; it'll deepen it.
- **Tighter pcir quantiles** (e.g. 0.85/0.15). Trade count would collapse below the 200 floor.
- **Time-of-day-conditioned predictors** (e.g. gap only valid for first 60-min entry, not full 180-min window). Possible follow-up if a future thesis revisits, but unjustified now given the load-bearing hit-rate finding.
- **VIX-regime overlay**. Cross-experiment lesson #28 says regime-decay shape (intraday MR strength) flips post-2022 via 0DTE flow. Possible mechanistic explanation but doesn't rescue the predictor.
- **Walk-forward parameter selection.** Same overfit risk as single-split; not appropriate for a signal that fails the core hit-rate test.

---

## Files

- Thesis: this file.
- Demo: `experiments/orb_directional_bias/orb_directional_bias_demo.py`.
- Data: `ohlc_data/GER40_M5.csv`, `ohlc_data/SPX500_M5.csv`.

---

## Thesis (mechanism)

The companion `orb_compression` experiment refuted on a population check: GER40 morning auction is so reliably directional that the break happens (one side or the other) on essentially every trading day. **The interesting question is therefore which side breaks first.**

Parent symmetric ORB on GER40 has LONG-only Sharpe +0.76 and SHORT-only Sharpe +0.01 (a near-zero drag). The asymmetry is partly explained by secular drift (DAX 10.6k → 22k over 2019-2026) and partly by Xetra microstructure (up-breaks signal institutional buying with follow-through; down-breaks skew toward noise flush-outs). If we can predict, with prior-day-available information only, which side will break first on a given day, then either:

- **Filter path**: take only parent-ORB trades where the predictor agrees with the breakout direction. Lifts long-leg Sharpe; modestly reduces cadence.
- **Revival path**: take SHORT trades on days the predictor flags down. Resurrects the silent shadow-logged leg.
- **Combined**: predict direction, take whichever side the predictor calls (long when bias=+1, short when bias=-1, skip neutral).

## Predictors to test (pre-committed)

Each computed at 09:00 Berlin (today's open) using only prior-day-close-and-earlier data:

1. **Gap direction (`gap`)** — `today_open / prior_close - 1`. Threshold sweep {0, 0.0010, 0.0025}. Long-bias if gap > +thresh; short-bias if < -thresh; neutral otherwise.
   - **Prior**: lesson #5 (`dax_gap_fade` REJECT, fade-gap -1.16) established DAX gaps CONTINUE — Xetra under-prices overnight info, leading to pile-on. Strongest *a priori* predictor.

2. **Prior close-in-range (`pcir`)** — `(prior_close - prior_low) / (prior_high - prior_low)`. Buckets: top quartile (>0.75 → long-bias), bottom quartile (<0.25 → short-bias), middle (neutral).
   - **Prior**: classical Crabel/Fisher intuition — strong-close days carry into next-day continuation; weak-close days reverse.

3. **SPX overnight (`spx`)** — SPX500 CFD return from prior 22:00 Berlin (16:00 ET cash close) to 09:00 Berlin today (GER40 open). Threshold sweep {0, 0.0010, 0.0025}.
   - **Prior**: DAX is correlated with US overnight via futures arb. Note `dax_us_lead` REJECT (sign-inverted) was a *late-session* catch-up trade, not a *pre-open* lead — different timing, different mechanism. Worth testing.

4. **5-day momentum (`mom5`)** — `prior_close / close_5d_ago - 1`. Threshold {0}.
   - **Prior**: slow momentum overlay. Mostly redundant with the parent's secular-long success but included as a within-experiment baseline / sanity check; if `mom5` predicts no better than 53% it confirms gap and pcir are the candidate signals.

## Signal math — combined-mode candidate

```
For each predictor P with bias series b_P(day) in {+1, 0, -1}:

  if b_P(day) == +1: take LONG ORB if it triggers; skip SHORT trigger
  if b_P(day) == -1: take SHORT ORB if it triggers; skip LONG trigger
  if b_P(day) ==  0: skip the day entirely (combined-mode) OR take both (filter-mode)

Parent ORB rules unchanged (OR=30min, T+180 exit, opposite-OR stop, 12:00 entry cutoff, 17:25 hard flat).

Cost model: 1pt RT (same as parent).
```

## Universe

GER40 M5 only. Auxiliary data: SPX500 M5 (for `spx` predictor only, already in `ohlc_data/`).

## Expected performance (at thesis time)

Best case (gap-direction works): hit-rate 55-58% on first-break, restricted-long Sharpe ~+0.9-1.1, restricted-short Sharpe ~+0.3-0.5, combined Sharpe lift to +0.95-1.10. Trade cadence drops 3.8/wk → 1.5-2.5/wk.

Realistic case (gap-direction noisy at small thresh, useful at large thresh with cadence collapse): pick gap threshold sweet spot where Sharpe lift + cadence floor both clear. Expected combined Sharpe modest lift +0.76 → +0.85-0.95.

Skeptical case (no predictor adds info above 52-53% accuracy): tombstone with the lesson that DAX's overnight info is too efficiently priced into the OR itself for prior-day signals to predict break direction.

## Fail conditions (pre-committed)

Phase 2 kills the **entire experiment** (all predictors) if:
- Best-predictor first-break hit-rate ≤ 53% (vs ~50% drift-uncorrected baseline; 3% is the noise threshold).
- Best-predictor combined Sharpe ≤ parent LONG-only +0.76 (no lift, no point).

Phase 2 kills an **individual predictor** if:
- Filter-mode long-only Sharpe < +0.76 AND revival-mode short-only Sharpe < +0.30 (no improvement on either deploy path).
- Holdout 2023-2026 Sharpe ≤ 0.
- Sharpe positive in ≤ 1 of 3 regime windows.

**Null check**: each predictor must show its inverted-bias variant degraded by ≥ +0.30 Sharpe in the combined-mode test, or the predictor has no directional content.

## Why this might fail (red flags)

1. **Gap may already be priced into the OR.** The 09:00-09:30 OR includes the first 30 minutes after the gap. By the time the breakout fires, the gap-info may be fully absorbed — predictor signal eaten by the OR itself.
2. **Predictor cadence cliff.** Large thresholds give clean signal but cut trade count below the floor. Small thresholds have fat tails of false signal that wash out edge.
3. **SPX-overnight is correlated with gap.** If both signals are essentially the same information, no diversification benefit; just pick the cleaner one.
4. **Short-leg revival may be regime-conditional.** Even if predictor works, shorts may only pay in 2021-2022-style vol regimes; 2023-2026 sustained-drift regime kills them anyway. Holdout sub-period is the binding test.
5. **Lookahead risk in the SPX predictor.** If the SPX M5 data has any post-09:00-Berlin bars feeding the "09:00 snapshot," that's contamination. Verify timestamp alignment.

## Phase 1 → 2 plan

- [ ] Build daily predictor series + first-break-direction observable.
- [ ] Hit-rate diagnostic: each predictor x each threshold, vs unconditional baseline.
- [ ] Filter-mode runs (LONG-only, skip-when-bias-is-down, skip-neutral).
- [ ] Revival-mode runs (SHORT-only, skip-when-bias-is-up, skip-neutral).
- [ ] Combined-mode runs (take whichever side bias predicts; skip neutral).
- [ ] Regime breakdown for all surviving variants.
- [ ] Cost sensitivity for top survivor(s).
- [ ] Null check: invert each predictor.
- [ ] Comparison vs parent baselines (LONG-only +0.76, symmetric +0.58, drift benchmark +0.25).

## Files

- Thesis: this file.
- Demo: `experiments/orb_directional_bias/orb_directional_bias_demo.py`.
- Data: `ohlc_data/GER40_M5.csv`, `ohlc_data/SPX500_M5.csv`.
- Run: `venv/Scripts/python.exe experiments/orb_directional_bias/orb_directional_bias_demo.py`.

## References

- Parent thesis: `experiments/orb/orb.md`.
- DAX gap continuation rejection: `experiments/dax/gap_fade.md` (lesson #5).
- Crabel, T. (1990) — close-in-range patterns.
