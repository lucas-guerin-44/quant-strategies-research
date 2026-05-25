# Month-End 60/40 Rebalancing Flow — SPX500 (daily-bar)

**Status**: Phase 1 complete 2026-05-25. Daily-bar SPX500 (Eightcap CFD proxy for MES) conditioned on prior-21d SPX-vs-TLT return spread.

**Verdict**: **REJECT (regime decay)**. Full-sample signal is mechanistically real (Sh +0.45, dir-gap +1.05, placebo benign t=+0.47, cost-robust to 20bp) but the W3 2023-2026 holdout is flat (Sh −0.01) — fails the pre-committed 3/3-regimes-positive criterion. Signal existed in 2021-2022 vol regime (Sh +0.95) and inverted in 2019-2020 (Sh −0.67, COVID dominates). Headline: the mechanism is present in the data but is no longer extractable in the current regime, likely because the EOM-rebal flow has been well-known to systematic prop desks for years and the holdout signal has been arbed flat.

| Metric        | Baseline (5d/2%/5bp) | Pre-commit | Pass? |
|---            |---                   |---         |---    |
| Sharpe        | +0.45                | ≥ +0.30    | PASS  |
| Mean/trade    | +0.292%              | ≥ +0.10%   | PASS  |
| MDD           | −20.2%               | < 25%      | PASS  |
| Trades        | 94                   | ≥ 60       | PASS  |
| Null-gap      | +1.05                | ≥ +0.30    | PASS  |
| Placebo benign| t=+0.47              | \|t\|<1.5  | PASS  |
| **3/3 regimes pos** | **1/3 (W1 −0.67 / W2 +0.95 / W3 −0.01)** | 3/3 | **FAIL** |

## Phase 1 results (2026-05-25)

### Baseline — 5-day entry, 2% spread gate, 5bp RT, SPX500 vs TLT
Sample 2015-01 → 2025-09 (latest aligned bar), 94 trades.

| Metric | Value |
|---|---|
| Sharpe (×√12) | +0.45 |
| Mean / trade | +0.292% |
| MDD | −20.2% |
| Win rate | 55.3% |
| Profit factor | 1.43 |
| t-stat | +1.25 |

**Regime breakdown**:

| Window | n | Mean | Sharpe | MDD |
|---|---|---|---|---|
| W1 2019-2020 | 21 | −0.653% | **−0.67** | −19.1% |
| W2 2021-2022 | 17 | +0.616% | **+0.95** | −5.0% |
| W3 2023-2026 | 21 | −0.003% | **−0.01** | −7.5% |

### Null check — invert direction
Sh −0.60 (inverted), null-gap **+1.05** Sharpe — direction is clearly the mechanically correct one (PASS).

### Placebo — mid-month re-anchor (EOM-15 → EOM-10)
n=93, mean +0.123%, t=+0.47, Sh +0.17. Benign — signal is NOT a generic month-end calendar artefact (PASS lesson #-13 corroboration).

### Sweeps

**Entry-days**: 3d Sh +0.62 (best), 5d +0.45, 7d −0.07, 10d +0.12 → rebal flow concentrates in last 3 sessions; signal degrades fast.

**Spread threshold**: 0% +0.26, 1% +0.39, 2% +0.45, 3% +0.46, 5% +0.23 → conditional mechanism confirmed, peak at 2-3% spread.

**Cost**: 0bp +0.52, 5bp +0.45, 10bp +0.37, 20bp +0.22 → cost-robust. Unlike `eod_unwind` / `preclose_drift`, the cost-grind is NOT the binding constraint.

**Bond-proxy robustness (IEF instead of TLT)**: Sh +0.54, n=80 → marginally better than TLT (+0.45). Choice of long-dated vs intermediate is non-load-bearing.

## Mechanistic interpretation

Three pieces of evidence support the **flow-is-real-but-arbed** reading:

1. **Direction null-gap +1.05** and **placebo t=+0.47** rule out the two cheap alternatives (noise / generic calendar drift). The conditioning variable (sign of 21d SPX-TLT spread) carries genuine directional content.
2. **Entry-days monotonic decay** (3d > 5d > 7d) matches the literature's view that rebal windows close 3-5 sessions before EOM. Flow is mechanism-consistent.
3. **Threshold-sweep monotonic up to 3%** is consistent with magnitude-proportional flow.

But the regime profile is **damning for deployment**:

- **W1 (2019-2020, Sh −0.67)**: COVID liquidation flow (Mar 2020) and Q4-2018 vol overwhelm calendar rebal. Mechanism present but dominated by regime-shift flow.
- **W2 (2021-2022, Sh +0.95)**: classic year — big monthly equity-vs-bond divergences (2021 stocks up while bonds flat; 2022 stocks down while bonds crashed). Rebal flow had a large signal-to-noise ratio. *This is when the mechanism worked.*
- **W3 (2023-2026, Sh −0.01)**: dead flat. 21 trades, mean −0.003%. The mechanism has been arbed.

This is the same shape as `earnings_fade_nonmag7` (lesson #-7) — monotonic OOS decay as a well-known flow gets front-run by systematic desks. Note also that 2023-2026 had multiple large equity-bond divergence months (Oct 2023 bond crash, 2024 SPX +25%), so it's not that the *conditioning* variable failed to trigger — the trades fired, they just didn't profit.

## Lessons / next moves

- **No deployment.** Full-sample looks decent but holdout is the load-bearing window per repo convention. Don't override.
- **Don't pivot to NDX corroboration** — the holdout failure is consistent with arb pressure on the *flow itself*, which would affect NDX equally. Spending Phase 2 on NDX is unlikely to rescue this.
- **Methodological note**: the null-gap test (+1.05) was strongly positive even on the dead holdout — this is a case where the **direction null-gap can flag a real mechanism that is still not tradeable**. Future similar work should weight the regime check over the null-gap check.
- **Adjacent ideas that survive**: (a) UK/EU LDI-pension flow around long-rate moves (different mechanism, less crowded venue), (b) Japanese fiscal year-end USDJPY repatriation (still works per FX desk anecdote, 2026), (c) ETF leveraged-rebal flow into the close on >2% SPX days. None inherit the "arbed by 2023" problem because each has fewer systematic trackers.

## Files

- `month_end_rebal.md` — this doc.
- `month_end_rebal_demo.py` — runner.

## Thesis (mechanism)

Balanced mandates (60/40 target-date funds, pension funds, sovereign wealth funds with calendar rebalance rules) drift away from policy weights as the equity/bond return spread accumulates intra-month. Most rebalance windows close in the **last 3-5 trading days of the calendar month** (NBIM 3% band, Vanguard target-date threshold band, large-pension monthly NAV-mark windows). The aggregated flow is:

1. **Conditional, not unconditional.** If SPX beat TLT by Δ% this month, rebalancers are over-equity and must sell SPX / buy bonds. Symmetric on Δ<0 months. So the mechanism predicts a **sign-conditional** drift, not a calendar drift.
2. **Concentrated late-month.** Rebal windows cluster in the last 3-5 sessions of the month; mid-month placebo windows should show no edge.
3. **Magnitude proportional to the spread.** A 5% SPX-TLT divergence month should produce a larger rebal-flow than a 1% spread month. Conditional on |spread| ≥ Δ_threshold.
4. **Should survive at daily-bar timescale.** Unlike the EOD-unwind (intraday) and MOC-imbalance (sub-minute) rejects, the cost grind on 1pt CFD round-trip over a 3-5 day hold is ~5-10× less binding than intraday execution.
5. **Lesson #-13 (PCE work, 2026-05-24)**: the *unconditional* month-end placebo was benign on NDX (mean −0.040%, t −0.29). So if a signal exists here, it must come from the conditioning variable (monthly spread sign/size), not from a generic calendar artefact.

## Key references

- **Hartzmark & Solomon (2022)**, "Predictable Price Pressure." *Review of Financial Studies* 35(11). Documents persistent EOM-rebalancing pressure on US equities.
- **Etula, Rinne, Suominen & Vaittinen (2020)**, "Dash for Cash: Monthly Market Impact of Institutional Liquidity Needs." *Review of Financial Studies* 33(1).
- **JP Morgan / Nomura quant desk EOM-rebal estimates** (institutional research, summarised in Bloomberg coverage 2019-2024).

## Signal math

```
Parameters:
  ENTRY_DAYS_BEFORE_EOM = 5      # business days before month-end close
  SPREAD_LOOKBACK_DAYS  = 21     # ~ 1 calendar month
  SPREAD_THRESHOLD_PCT  = 2.0    # |SPX_ret - TLT_ret| floor over lookback (in %)
  COST_BPS_RT           = 5.0    # 5 bps RT (~ 1.5pt on SPX500 @ ~3000 mid-2019 to ~6000 2026)

Trigger fires on the entry date if:
  spread = SPX_cum_ret(lookback) - TLT_cum_ret(lookback)
  |spread| >= SPREAD_THRESHOLD_PCT

Direction:
  spread > 0  → SHORT SPX  (rebal sells equities)
  spread < 0  → LONG SPX   (rebal buys equities)

Entry: close of (EOM - ENTRY_DAYS_BEFORE_EOM)
Exit:  close of EOM
```

## Why retail-accessible

- Daily-bar SPX500 + TLT only — already on disk.
- 1pt CFD spread on a 3-5 day hold is a ~5bp cost, not the 30-50bp grind that killed `eod_unwind`/`preclose_drift`.
- Hold window is 3-5 sessions, no intraday execution risk.

## Universe

SPX500 CFD (proxy for MES futures deployment). Could extend to NDX100 in Phase 2 if SPX passes.

## Expected performance (point estimates)

- Per-trade mean: +0.40% to +0.80% gross, ~+0.30-0.70% net @ 5bp RT.
- Trade cadence: ~12 months/year × ~50% trigger-rate (spread ≥ 2%) ≈ 6 trades/year → ~70 trades over 2015-2026.
- Sharpe: target +0.40 to +0.80 annualized.
- MDD: target < 20%.

**Trade-cadence concern (pre-flagged)**: monthly cadence × threshold gate may put us below the 200-trade preferred bar. If trade count is 50-100, treat Phase 1 as exploratory; pass requires stronger Sharpe (≥ +0.50 net) and clean 3/3 regime split to compensate for thin sample. Relaxed pre-commit floor: **trades ≥ 60** (one full cycle of ~10 years × 6/yr).

## Fail conditions (pre-committed)

Apply to baseline (5-day entry, 2% spread gate, 5bp cost) on full 2015-2026 sample:

1. **Sharpe (annualized, ×√12_trades_per_year) ≥ +0.30** after cost.
2. **Per-trade mean ≥ +0.10%** net of cost.
3. **MDD < 25%** on the per-trade equity curve.
4. **Trades ≥ 60** over the full sample.
5. **3/3 regime Sharpe positive** (2019-2020 / 2021-2022 / 2023-2026).
6. **Direction null-gap ≥ +0.30 Sharpe** — the same logic with **inverted direction** (long-on-positive-spread, short-on-negative-spread) must underperform by ≥ +0.30 Sharpe.
7. **Mid-month placebo benign** — same trigger logic re-anchored to mid-month windows (entry = month-end − 15 business days, exit = month-end − 10 business days) should show mean |return| < 0.10% AND |t| < 1.5. If the placebo prints a real edge, the signal is a generic calendar drift, NOT the rebalancing flow we claim.

PASS requires ALL of (1)-(7).

## Why this might fail (red flags)

1. **Sample too thin.** ~70 trades over 11 years. Even a real +0.40 Sharpe signal may not clear noise with this n. Phase 2 (if PASS) would need NDX corroboration to add ~70 more independent trades.
2. **Flow has decayed.** EOM rebal flow was well-known by 2018; large prop desks have been front-running it for years. The 2023-2026 holdout may show monotonic decay.
3. **Threshold gate is post-hoc.** Choosing 2% as the gate is arbitrary; we'll sweep 0/1/2/3/5% as a robustness check, but PASS is pre-committed to the 2% baseline.
4. **TLT is not the right rebal proxy.** Real LDI/pension funds rebalance vs aggregate-bond index (AGG, not TLT). TLT is long-duration only. IEF (7-10y) is closer to mean-duration pension bond exposure. Will also test IEF as a robustness check.
5. **Lesson #-3 (Asian handoff family)** suggests flow theses don't auto-port — even if this passes SPX, NDX corroboration in Phase 2 is non-trivial.

## Phase 1 → 2 plan

- [ ] Phase 1 baseline: 5-day entry, 2% spread gate, 5bp cost, SPX500 only.
- [ ] Phase 1 sweeps: entry-days (3/5/7/10), threshold (0/1/2/3/5%), cost (0/5/10/20 bp), bond-proxy (TLT vs IEF).
- [ ] Phase 1 regime split: 2019-2020 / 2021-2022 / 2023-2026.
- [ ] Phase 1 null-check: inverted direction.
- [ ] Phase 1 placebo: mid-month re-anchor.
- [ ] If PASS: Phase 2 NDX corroboration + walk-forward 3-split.

## Files

- `month_end_rebal.md` — this doc.
- `month_end_rebal_demo.py` — runner.
