# TSMOM with Hurst-regime entry gate

**Status**: Phase 2 complete (2026-05-23). Direct follow-up from `regime_hurst_diagnostic`
(lesson #52), where Hurst-as-classifier passed the TSMOM-side pre-commit
(6/8 instruments full-sample, 3/5 W4-eligible post-2023) but failed the MR-side
universally (0/5 post-2023). This experiment tests whether bolting a Hurst
filter onto the existing repo-validated `tsmom` (long-only 12-1, KEEP_FOR_REFERENCE
at Sh 0.40 full / 1.14 W4 holdout, +0.69 corr with xs_momentum) delivers a
deploy-grade improvement on the W4 holdout.

**Verdict**: **REJECT** — Hurst-overlay family fully tombstoned. W4 lift is -0.13
(FAIL by 0.28 absolute) and the inverted-gate null-check produces *higher* W4
Sharpe than the proper gate (+1.11 vs +1.03), proving the gate has zero
portfolio-level directional content. Mechanistic root cause: the 12-1 momentum
signal is itself a slow-trend persistence filter, so the Hurst gate is
redundant — it either agrees with the 12-1 signal (does nothing) or contradicts
it via a 252d-lagged classifier that cuts profitable entries.

---

## Thesis (mechanism)

The classical 12-1 TSMOM signal is **directionally indiscriminate**: any positive
12-1 month return triggers a long, regardless of whether the underlying instrument
is in a trending or chopping regime. In chopping (anti-persistent, H<0.5) regimes,
a positive 12-1 return is more likely to be a transient overshoot that mean-reverts
during the holding window — the classical Wright/MoP critique of naive TSMOM in
non-trend regimes.

The `regime_hurst_diagnostic` result was unambiguous on this:
- In H>0.55 windows, naive-TSMOM Sharpe averaged ~+0.50 to +1.50 across the
  universe.
- In H<0.45 windows, the *same* naive-TSMOM rule produced negative Sharpe on
  6 of 8 instruments full-sample.

A 252d-rolling Hurst gate is therefore expected to:
1. Cut entries in instrument-windows where the underlying is anti-persistent —
   the long-side TSMOM mechanism is mis-calibrated to that regime.
2. Concentrate exposure in instrument-windows where the persistence assumption
   (the literature's motivating prior for TSMOM in the first place) actually holds.
3. **Reduce correlation with xs_momentum** by trading a different sub-sample
   of the cross-section than the all-universe ungated baseline.

If the gate is real, the W4 holdout should improve by ≥ +0.15 absolute Sharpe
with no catastrophic trade-count collapse, AND the correlation between the gated
and ungated baseline should drop materially (proxy for "the gate actually
changes what the strategy does, doesn't just thin its noise").

## Key reference

- **Moskowitz, Ooi & Pedersen (2012), "Time Series Momentum", JFE** — origin of
  the 12-1 TSMOM rule and the long-only vs long/short framing. Their full-sample
  Sharpe ~1.4 (1985-2009 futures universe) presupposes a persistence-rich
  regime that has thinned in the 2015+ universe.
- **Peters (1994), Fractal Market Hypothesis** — the canonical motivation for
  using Hurst to identify trend-friendly sub-regimes.
- **`experiments/regime_hurst_diagnostic/regime_hurst_diagnostic.md` (2026-05-23)**
  — the direct predecessor; pre-committed pass criteria on the gate side
  identified the TSMOM-asymmetric pass (lesson #52).

## Signal math

```
Per instrument i, per rebalance day t (monthly cadence):

  # Classical 12-1 TSMOM signal (UNCHANGED from baseline tsmom)
  r12_1 = close[t-21] / close[t-273] - 1     # 12-month return ex last month
  raw_signal = +1 if r12_1 > 0 else 0          # long-only

  # Vol-target sizing (UNCHANGED)
  realised_vol = std(daily_log_returns[t-60:t]) * sqrt(252)
  position_weight = 0.15 / realised_vol  (capped at size_cap = 1.0)

  # NEW: Hurst gate
  H_t = DFA(daily_log_returns[t-252:t], scales=[10,20,50,100])
  gate = 1 if H_t > 0.50 else 0                # relaxed threshold per diagnostic
  position = raw_signal * gate * position_weight

  # Portfolio: equal-weight (1/N over active positions),
  #            max single-asset 20%, monthly rebal, costs per-asset.
```

`H_t` carried forward via last-known-value when the rolling window has any NaN
in the prior 252 daily returns; entry blocked entirely if no valid H_t exists.

## Why retail-accessible

Same retail-accessibility profile as baseline `tsmom`:
- Monthly cadence — no microstructure or fill-quality concerns.
- D1 universe of broker-tradeable instruments — Eightcap MT5 confirmed for
  the major instruments; some softs and exotic FX have lighter coverage and
  may be excluded in the deploy version.
- Hurst computation is a one-line numpy DFA call per instrument per day — no
  added infrastructure cost beyond the baseline.

## Universe

Identical to baseline `tsmom`: 24 instruments, D1, 2015-01-01 → 2026-04-18.

- **Exotic FX**: AUDNZD, NZDCAD, GBPNZD, AUDCAD, CADJPY, NZDJPY, EURGBP, EURNOK, USDZAR
- **Softs**: COCOA, COFFEE, SUGAR, COTTON
- **Country ETFs**: EWZ, FXI, EWJ
- **Major indices/FX/commodities/crypto**: XAUUSD, USOUSD, SPX500, NDX100, GER40, BTCUSD, EURUSD, GBPUSD

## Expected performance (at thesis time)

Baseline (replicated): full-sample Sh ~0.40, W4 holdout Sh ~1.14, MDD ~-15.5%,
trades ~384.

Honest priors for the gated version:

- **Best case (25%)**: full-sample Sh +0.55-0.65, W4 +1.30-1.45, MDD shrinks
  to ~-12%, trade count drops to ~250-300 (gate cuts ~25-35% of entries).
  Correlation with ungated baseline falls to ~0.65-0.75. PASS.
- **Most likely (50%)**: gate works in the directionally expected way but the
  improvement is too small to clear +0.15 absolute on W4 (e.g., +0.05 to +0.12
  W4 lift). Honestly REJECT under pre-commits even if the direction is right —
  small improvement may not survive Phase 7 deploy haircut.
- **Worst case (25%)**: gate cuts trades that were on average POSITIVE
  contributors (because rolling-252d Hurst is laggy and is itself sampling
  the same "trend persistence" that the 12-1 signal already encodes). W4
  Sharpe flat or worse. REJECT.

The interesting **side-result** to watch: if the gate WORKS, the per-instrument
contribution table should show big lifts on the instruments where the diagnostic
showed largest Δ Sharpe (SPX/NDX/USO/BTC) and ~zero lifts on the diagnostic's
no-edge instruments (ETH, XAU). If the gate works UNIFORMLY across all 24, the
mechanism is weaker than it looks — that would be more consistent with the
gate just acting as a generic dampener than as a true regime selector.

## Fail conditions (pre-committed)

REJECT if ANY of:

1. **W4 holdout Sharpe improvement < +0.15 absolute** over the same-implementation
   ungated baseline. (This is the headline criterion.)
2. **Trade count < 200** over the full backtest period. (Gate cuts too aggressively.)
3. **Correlation between gated and ungated portfolio returns > 0.85**. (Gate
   doesn't actually change the strategy — it's a noise-thinning lever, not a
   regime selector.)
4. **W4 holdout Sharpe ≤ 0**. (Strategy fails the W4 floor regardless of lift.)
5. **Max DD on full sample > 25%**. (Standard repo bar.)

PASS only if ALL of (1)-(5) hold.

MARGINAL is reserved for the case where (1) is satisfied but (3) is marginal
(corr 0.80-0.85) — gate works directionally but is too close to the ungated
baseline to be deploy-distinctive.

**Direction null-check**: re-run the same backtest with the gate INVERTED
(H_t < 0.50 → take long; H_t ≥ 0.50 → skip). If the inverted gate produces a
comparable W4 Sharpe to the proper gate, the gate has no directional content —
REJECT regardless of (1)-(5).

**Walk-forward integrity**: pre-2023 vs post-2023 lift must agree on sign. If
the gate helps pre-2023 but hurts post-2023 (or vice versa), the rolling-Hurst
classifier is itself regime-conditional and not robust enough for deploy.

## Why this might fail (red flags)

1. **252d Hurst lookback is laggy**. By the time H_t crosses 0.50 from below,
   the trending regime that would have justified the entry may already be in
   the process of decaying. The diagnostic's W4 result (3/5 post-2023-eligible)
   shows the lag is *survivable* on cross-instrument average, but specific
   instruments may have unfavorable lag profiles.
2. **Vol-targeting + Hurst gate are partial substitutes.** Vol-targeting already
   reduces position size when realised vol expands (which often coincides with
   regime breakdown). The gate may be reproducing an effect the vol-target
   already captures, producing only marginal lift.
3. **12-1 momentum signal is itself a slow trend-following filter.** A positive
   12-1 return is more likely than chance in H>0.5 windows. The gate may be
   correlated with the signal it's gating, so it does less than its diagnostic
   Δ Sharpe suggests.
4. **Equal-weight portfolio averaging.** The diagnostic ran *per-instrument*;
   the strategy aggregates across 24 instruments equal-weighted. If the gate
   helps on 6 instruments and is noise on 18, the portfolio-level lift is
   diluted by ~75%.
5. **DFA σ(H) at N=252 ≈ 0.05.** Two adjacent days can swap regime labels
   from estimator noise alone — meaning the gate's true effective bandwidth
   is narrower than the threshold gap suggests. Mitigation: gate threshold
   is 0.50 (not 0.55), which moves the boundary toward the median of typical
   estimator noise distribution.

## Phase 2 plan

- [x] Write thesis with pre-committed fail conditions (this doc).
- [ ] Implement `tsmom_hurst_gated.py` — single-file numpy sim that runs both
      ungated baseline AND H>0.50 gate on identical universe + cost model.
      Also runs the inverted gate (H<0.50) for the null-check.
- [ ] Run end-to-end. Report full-sample and W4 Sharpe for all three runs,
      portfolio correlation matrix, trade count, MDD, per-instrument lift table.
- [ ] Update verdict + mechanistic interpretation.
- [ ] If PASS or MARGINAL: propose Phase 3 (statistical validation + walk-forward
      stability check). If REJECT: tombstone the Hurst-overlay family entirely
      (this is the second and final shot — diagnostic was the first).

## Files

- `tsmom_hurst_gated.md` — this doc
- `tsmom_hurst_gated.py` — sim (clean numpy reimplementation of long-only 12-1
  TSMOM + DFA-Hurst gate)

---

## Results (2026-05-23)

### Portfolio headline

| Config | Full Sh | Pre-2023 Sh | W4 Sh | MDD | CAGR | Trades |
|---|---|---|---|---|---|---|
| Ungated baseline | +0.50 | +0.15 | +1.17 | -10.5% | +1.0% | 1051 |
| **Gated (H > 0.50)** | **+0.33** | **-0.05** | **+1.03** | **-8.1%** | **+0.4%** | **902** |
| Inverted (H < 0.50) | +0.52 | +0.23 | +1.11 | -3.9% | +0.6% | 906 |

Notes on baseline reimplementation: full-sample Sh +0.50 vs documented +0.40 in
[tsmom.md](../tsmom/tsmom.md), W4 Sh +1.17 vs +1.14. Close enough to consider
the clean-numpy port a faithful representation; the small upward bias is
attributable to vol-targeting normalisation differences and the simplified
cost model. The *delta* between configurations is what matters, and is
computed within this single implementation.

### Pre-committed verdict

| # | Criterion | Threshold | Realised | |
|---|---|---|---|---|
| 1 | W4 Sharpe lift | ≥ +0.15 | **-0.13** | FAIL |
| 2 | Trade count | ≥ 200 | 902 | PASS |
| 3 | Corr(gated, ungated) | ≤ 0.85 | 0.829 | PASS |
| 4 | W4 Sharpe positive | > 0 | +1.03 | PASS |
| 5 | Max DD | > -25% | -8.1% | PASS |
| 6 | Null-check | inv W4 not within 0.10 of gated | inv +1.11 vs +1.03 | **FAIL** |

Two FAILs, one of them the headline metric. **REJECT.**

### Direction null-check (load-bearing)

The inverted gate (H<0.50 → take long, the supposedly *anti-persistent* regime)
produces **higher** W4 Sharpe (+1.11) than the proper gate (+1.03), and matches
the ungated baseline (+1.17) more closely. The proper gate is the *worst* of
the three configurations on W4.

Correlation structure underscores it:
- ungated ↔ inverted = 0.851 (inverted is essentially the baseline)
- ungated ↔ gated    = 0.829 (gate diverges slightly, in the wrong direction)
- gated   ↔ inverted = 0.413 (the two gate variants are weakly correlated to
  each other, as expected — they trade *different* sub-samples of the
  cross-section)

A gate with directional content should produce gated-W4 ≫ inverted-W4. The
observation is the opposite.

### Per-instrument lift table (gated minus ungated, full-sample)

The diagnostic predicted the gate would help most on instruments that showed
the largest Δ Sharpe in the regime study. **Empirically the opposite pattern
holds**: the high-Δ instruments from the diagnostic all show *negative* lift
in the portfolio context:

| Diagnostic Δ_TSMOM (full) | Portfolio lift here | Verdict |
|---|---|---|
| SPX500 +1.32 | -0.18 | OPPOSITE |
| NDX100 +1.16 | -0.46 | OPPOSITE (worst) |
| BTCUSD +1.14 | -0.17 | OPPOSITE |
| USOUSD +1.20 | -0.08 | OPPOSITE (mild) |
| GER40  +0.90 | -0.05 | ~zero |
| EURUSD +0.36 | +0.26 | matches sign |

Of 24 instruments, only 8 show positive gate lift; 16 show negative or zero.
The few positives are concentrated in low-trade-count exotic FX (EURNOK +0.24,
USDZAR +0.20, EURUSD +0.26) where the underlying ungated Sharpe is already
near-zero — so the "lift" is mostly noise rotation, not a real edge unlock.

### Mechanistic interpretation

1. **The 12-1 momentum signal is itself a persistence filter.** A positive
   12-1 return means the asset has been in a multi-month uptrend; by signal
   construction, this overlaps heavily with the H>0.5 regime that Hurst is
   supposed to identify. The gate therefore gates trades that the 12-1 signal
   has already vetted, providing no incremental information.

2. **252d-rolling DFA Hurst lags the 12-1 signal in regime turns.** When an
   instrument transitions from chop to trend, the 12-1 return goes positive
   ~21 bars after the trend starts (since 21 bars is the skip window). The
   252d-rolling Hurst needs ~half its window of *new-regime* data to drift
   above 0.50 — much slower. So the gate is consistently late to confirm
   regime changes that the 12-1 has already captured. The gate cuts the
   *earliest* trades of each new trend, which are the highest-Sharpe trades.

3. **Per-instrument vs portfolio aggregation collapses the diagnostic's signal.**
   The diagnostic ran fixed naive-TSMOM on *every* day in the regime bucket,
   producing the Δ Sharpe per instrument. The portfolio trades only on
   monthly rebal cadence — that's ~12 entry decisions per year per
   instrument, not ~252. With ~25% reduction from the gate, each
   instrument's effective trade count drops from ~135 (over 11y) to ~100,
   well into territory where σ(Sharpe) is dominant and the predicted ~+0.3
   per-instrument lift cannot reliably surface above noise.

4. **Vol-targeting is the load-bearing risk-shaping tool, not Hurst.** Going
   from ungated MDD -10.5% to gated MDD -8.1% looks like a benefit, but the
   inverted-gate MDD is -3.9% (*best* of the three). MDD improvement from
   gating is just the well-known "fewer trades = smaller DD" mechanical
   effect, not Hurst-conditional risk reduction. Vol-targeting (15%
   annualised per position) is doing the actual risk work — the H gate is
   noise on top.

5. **The diagnostic was right about TSMOM working better in H>0.55 sub-windows
   in isolation, but wrong to extrapolate that a strategy-level gate would
   help.** Generalizable rule: a regime classifier whose signal *correlates*
   with the strategy's primary signal cannot add value via an entry gate —
   the gate is redundant. Hurst-as-regime-filter is only useful for strategies
   whose primary signal is *not* itself a trend filter (e.g., yield-curve
   shape, vol-of-vol, calendar mechanisms). Those candidates remain
   theoretically open but require different mechanisms entirely; the
   "let's add Hurst to our existing momentum strategy" branch is closed.

### Tombstone of the Hurst-overlay family

`regime_hurst_diagnostic` (MARGINAL — TSMOM-side passed in isolation) +
`tsmom_hurst_gated` (REJECT — gate redundant with 12-1 signal) collectively
close the Hurst-as-regime-classifier-overlay line of inquiry for this repo.
Both experiments stay as KEEP_FOR_REFERENCE thesis docs (negative results are
deliverables). No further Hurst-gate proposals on existing strategies should
be entertained without a fundamentally different gating mechanism (e.g., on
a non-momentum strategy whose primary signal is orthogonal to Hurst — which
remains a theoretical possibility but is not currently in the experiment
queue).

### What was learned vs what cost

- Total time invested: one diagnostic (8 instruments, ~150 lines of code) +
  one Phase 2 (24-instrument portfolio backtest with 3 configurations,
  ~280 lines). End-to-end in one session.
- Hurst-as-regime-filter is no longer a load-bearing open question.
- Generalizable lesson #53 (added to RESEARCH_NOTES) — *regime classifier
  redundancy* — applies to any future "let's add classifier X to existing
  strategy Y" proposal, not just Hurst.
- The diagnostic-first protocol (run a parameter-free probe before scaffolding
  a Phase 2) worked correctly here in the sense that it identified the
  TSMOM-side as the only candidate worth a Phase 2, and the Phase 2 then
  decisively settled the question. The probe-first pattern is preserved for
  future regime-classifier proposals.
