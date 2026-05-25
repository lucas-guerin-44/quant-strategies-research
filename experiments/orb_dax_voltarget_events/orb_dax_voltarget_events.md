# ORB_DAX × Vol-Target Sizing + Macro-Event Blackout — pre-committed Phase 2

**Status**: Phase 2 complete (2026-05-22). REJECTED on the combined pre-committed candidate. The VT lever passes its directional null but fails as a deployable Sharpe-lift mechanism for reasons that are mechanistically interesting (see verdict).

**Verdict**: **REJECT — combined VT+EB fails 3 of 7 pre-committed checks.** Sharpe lift only +0.094 (< +0.15), holdout lift only +0.049 (< +0.10), cost-robustness fails (combo@2pt < baseline@1pt). EB does nothing standalone (-0.006 Sh) despite event-only-null clearly underperforming (gap +0.370) — the right days are flagged, but skipping them doesn't move annualized Sharpe because event days are only ~14% of trade-days with proportional variance. VT alone (+0.121 Sh) was the only lever with meaningful lift, but year-by-year diagnostic shows it amplifies edge in low-vol years rather than reducing variance on bad days — it lost worse than baseline in 4 of 8 years (2019: −0.448, 2022: −0.180, 2024: −0.213). The vol-targeting mechanism is **regime-dependent reshuffling, not robust Sharpe lift**.

Headline numbers (re-impl baseline, 1pt RT cost, 2019-01 → 2026-04):

| Variant | Sharpe | Δ vs base | MDD | Trades | Note |
|---|---|---|---|---|---|
| Baseline | +0.460 | — | -11.29% | 1457 | re-impl matches `orb_dax_sentiment` re-impl |
| **VT alone** | **+0.581** | **+0.121** | -7.76% | 1457 | only lever with meaningful lift; year-by-year unstable |
| EB alone | +0.454 | -0.006 | -9.81% | 1307 | essentially no effect |
| **VT+EB combined** | **+0.554** | **+0.094** | -7.28% | 1307 | **FAIL** pre-committed +0.15 lift |
| Inv-VT (null) | +0.381 | -0.079 | -17.00% | 1457 | gap +0.201 — PASS null (just barely) |
| Event-only (null) | +0.090 | -0.370 | -3.40% | 150 | gap +0.370 — PASS null clearly |

**Pre-committed kill-criteria check** (VT+EB combined):

| Check | Threshold | Actual | Result |
|---|---|---|---|
| Full-period Sharpe lift | ≥ +0.15 | +0.094 | **FAIL** |
| Holdout 2023-26 lift | ≥ +0.10 | +0.049 | **FAIL** |
| MDD not worse by >1pp | ≥ -1pp | +4.01pp **better** | PASS |
| Trade count | ≥ 1000 | 1307 | PASS |
| Null VT (VT − Inv-VT) | ≥ +0.20 | +0.201 | PASS |
| Null Events (base − only) | ≥ +0.20 | +0.370 | PASS |
| Regime consistency | ≥ 2/3 windows | 2/3 (2019-20 fails -0.331) | PASS |
| Cost robustness (combo@2pt > base@1pt) | yes | +0.285 vs +0.460 | **FAIL** |

Three FAILs, one borderline regime split. The pre-commit verdict is REJECT.

## Why VT alone is NOT a deploy candidate either (and not just goalpost-moving)

The natural next move is "OK, drop EB, deploy VT alone — it lifted Sharpe by +0.121 with better MDD." Refused, for three reasons that are not just process pedantry:

1. **Year-by-year is not stable.** Years where VT helped: 2020 (+0.237), 2021 (+0.475), 2025 (+0.171). Years where VT HURT: 2019 (−0.448), 2022 (−0.180), 2024 (−0.213). Roughly 4 vs 4. The full-sample +0.121 is a tail-of-the-distribution average. A live deploy could easily land in a "VT hurts" year and underperform the baseline by half a Sharpe.

2. **The mechanism is not what we pre-committed.** The thesis claimed VT works by "down-weighting high-vol whipsaw days." Diagnostic shows: VT helps in years where low-vol days *happen to be profitable*, and hurts in years where they happen to be losing. In 2019 (low realized vol throughout, baseline negative Sh), VT up-sized trades on most days and amplified the loss. This is variance reshape, not edge-extraction.

3. **Cost robustness fails** even on VT alone: VT@2pt = +0.285, baseline@1pt = +0.460. The lift evaporates under realistic broker spreads.

Re-deploying VT post-hoc — having seen these regime numbers — is exactly the failure pattern `orb.md` warns about ("optimized variant wins in-sample that fail OOS").

## Diagnostic — VT year-by-year and 2020 month-by-month

Per `_explore_vt_2020_breakdown.py`:

| Year | Baseline Sh | VT Sh | Δ |
|---|---|---|---|
| 2019 | -0.405 | -0.852 | **-0.448** |
| 2020 | +0.824 | +1.061 | +0.237 |
| 2021 | +0.985 | +1.459 | +0.475 |
| 2022 | -0.391 | -0.572 | -0.180 |
| 2023 | +0.779 | +0.784 | +0.005 |
| 2024 | +1.437 | +1.224 | -0.213 |
| 2025 | +0.465 | +0.636 | +0.171 |
| 2026 (YTD) | +0.468 | +0.468 | +0.000 |

The 2019-2020 regime failure is **all 2019** — Mar/Apr 2020 COVID was actually well-handled by VT (it down-weighted the most volatile bars and PnL stayed positive at smaller scale). The mechanism failure is in *low-vol bear years* (2019), not *high-vol shock years* (Mar 2020). Excluding the 2-month COVID shock, the full-period VT lift jumps to +0.213 — but that's pure regime-cherry-picking, not a real result.

## Mechanistic interpretation — why VT is reshuffle not lift, and why EB is gating the right days but extracting no edge

**VT — mathematical clarity post-hoc**:
The deployed baseline already uses percentage returns, so each trade is already vol-normalized in *cross-trade* terms. The remaining variance heterogeneity is across *days* — Mar 2020 has 10× the bar-level vol of Aug 2019. Vol-target sizing reduces the bar-level variance from those high-vol days but does NOT change the *direction* of trade outcomes. If the underlying trade-day Sharpe distribution is roughly uniform across vol regimes, VT mechanically lifts annualized Sharpe by compressing the variance denominator. If trade-day Sharpe is *higher* in high-vol regimes (which would be the case if breakouts work especially well in volatile years like 2020 and 2022-vol), VT would *hurt* by underweighting the most-edge bars. The DAX result is in between — 4/8 years up, 4/8 down — suggesting the trade-day-Sharpe-vs-vol covariance is roughly zero. Without that covariance, vol-targeting is just risk shuffling, not Sharpe extraction.

**EB — calendar identifies the bad days but skip doesn't help**:
The Event-only null was Sh +0.090 vs baseline +0.460 — event days are unambiguously worse per-bar (gap +0.370). But EB alone moved annualized Sharpe by −0.006. Reason: event days are ~14% of trading days (28/250). When the variance contribution of those days is also ~14% of total (which it is in a Sharpe denominator), removing them doesn't improve the mean/std ratio. The 13% of days you remove had ~13% of the variance and ~7% of the cumulative PnL — net effect on annualized Sharpe is negligible. **The calendar is informationally correct but the gate-then-trade-the-rest math doesn't move annualized Sharpe.** A version that *sized* event days down (e.g., 0.5×) instead of skipping might extract more — but adding that as a follow-up sweep would be the fitted overlay this experiment was explicitly built to avoid.

## What this means for the user-facing question ("Sharpe > 1 realistic?")

The previous answer suggested stacking VT + EB + better cost realization could lift the deployed +0.76 research Sharpe toward +1.0-1.1. The data now says:

- **VT** is at best +0.12 absolute, regime-unstable, and fails cost-robustness. Sharpe contribution: probably **+0.05 expected** in a haircut-honest forward.
- **EB** is zero on annualized Sharpe even though the calendar is informationally correct.
- **Cost realization** (1pt → 0.5pt) is still the cleanest +0.13. That part of the prior answer stands.

Realistic stacked Sharpe for orb_dax research-side: **+0.76 → ~+0.85** (cost) **→ ~+0.90 marginal** (VT, if you accept the regime risk). Not the +1.0+ originally suggested. Apologies for the optimism in the prior message.

Sharpe > 1 *live* on this single retail strategy is now confirmed not realistic. Sharpe > 1 research on this strategy is also looking unrealistic without finding a real signal-conditional refinement (which `orb_dax_sentiment` ruled out for the Layer 1 quantified composite). Layer 2 (LLM news) is the only remaining single-strategy path; portfolio blending across uncorrelated mechanisms is the only path to portfolio Sharpe > 1.

## Pre-commitment principle

This experiment is the natural follow-up to `orb_dax_sentiment` (REJECTED) and is the second of two improvement levers the user-facing analysis identified as "realistic" for the deployed ORB_DAX baseline:

- **Lever 1**: Vol-target position sizing — scale lot inversely to trailing realized vol so that high-vol whipsaw days carry less notional and low-vol clean-trend days carry more.
- **Lever 2**: Macro-event blackout — skip Xetra-open entries on scheduled FOMC / ECB / NFP days, where the opening-impulse mechanism is plausibly degraded by pre-event positioning.

Both levers are **structural** (calendar-driven and vol-driven), not signal-conditional. Neither searches over a tunable parameter against the in-sample Sharpe; each has parameters fixed up-front from public/expanding-window references. This is the entire point — the prior experiment (`orb_dax_sentiment`) tried to add a fitted overlay (quintile breaks, composite of 7 features). It REJECTED. This experiment trades signal-conditional fitting for structural prior knowledge.

## Thesis (mechanism)

1. **Vol-target sizing — low-vol days are higher Sharpe per unit notional.** Intraday opening-impulse strategies (orb.md) work because the Xetra auction concentrates overnight information into a clean 09:00 cut. On high-vol days the opening range is wide, breakouts are noise-driven, stops are far, and the impulse decays into mid-session whipsaw. Sizing inversely to GER40's trailing realized vol equalizes the *risk contribution* of each trade — calm tape contributes the same DV01 as hectic tape, instead of being underweighted by being a small move. **The Sharpe lift is mechanical** (heterogeneous-variance correction) and well-documented in equity index intraday literature (Moskowitz–Ooi–Pedersen 2012 for trend; same logic for opening-impulse).

2. **Event blackout — opening impulse is contaminated on pre-event days.** Three macro event types overlap with or precede the T+180 trade window:
   - **FOMC** (8/yr) — decision at 14:00 ET = 19:00-20:00 Berlin, AFTER Xetra close. But pre-decision positioning suppresses directional follow-through in the AM Xetra session — DAX banks/exporters hedge dollar exposure into the close.
   - **ECB** (8/yr) — decision at 13:45 Berlin, statement + press conf 14:30. Xetra trades through the announcement. T+180 exit lands at ~12:30, *just before* ECB. Pre-ECB drift in DAX banks/insurers is small, mean-reverting, and uncorrelated with the OR breakout direction.
   - **NFP** (1st Friday/month) — release at 14:30 Berlin. T+180 from 09:30 entry exits at ~12:30, well before NFP. But pre-NFP overnight session is typically low-volume "parked" markets; the overnight US tape that drives the Xetra open carries less of the usual continuation signal.

   These are not "extreme" days the strategy should fear because of drawdown risk; they are days where the **information-resolution mechanism** the strategy relies on is structurally disrupted.

3. **Both levers are structural, not fitted.** Vol-target uses an *expanding-window median* as the target (no in-sample target tuning); the lookback window (20d) and clip ([0.5, 2.0]) are pre-committed from convention, NOT swept. Event blackout is a hardcoded public calendar; not a single parameter is tuned against the historical Sharpe. This is the explicit overfit-defense — we cannot improve the Phase 2 result by adjusting a knob, because there are no knobs.

## Key references

- Moskowitz, Ooi, Pedersen (2012). "Time series momentum." *JFE* 104(2). Vol-target inverse-realized-vol scaling formalized for trend strategies; same mechanical Sharpe lift transfers to opening-impulse breakouts.
- Lucca & Moench (2015). "The Pre-FOMC Announcement Drift." *JF* 70(1). Equity-index returns are systematically distorted in the 24h before FOMC — direct precedent for FOMC-day-blackout as a structural overlay.
- Savor & Wilson (2013). "How much do investors care about macroeconomic risk?" *JFQA* 48(2). Macro-news days carry premium-loaded returns that are mechanistically different from non-news days.

## Signal math — pre-committed parameters (NOT tuned)

```
A. Vol-target sizing
  realized_vol[d] = std(GER40_D1_close_to_close_return, window=20d)  # observable at end of day d
  target_vol[d]   = expanding_median(realized_vol[: d])              # uses only history strictly < d
  scale[d]        = clip(target_vol[d-1] / realized_vol[d-1], 0.5, 2.0)
  # Applied to ALL per-bar returns within a trade entered on date d.
  # scale is computed from t-1 close; entry is t open. Zero look-ahead.

B. Event blackout (hardcoded calendars)
  FOMC_DATES = scheduled FOMC meeting dates 2019-01 → 2026-04 (Fed public schedule)
  ECB_DATES  = scheduled ECB Governing Council monetary policy meeting dates 2019-01 → 2026-04
  NFP_DATES  = 1st Friday of each month, 2019-01 → 2026-04 (algorithmic)
  BLACKOUT_DATES = FOMC_DATES ∪ ECB_DATES ∪ NFP_DATES
  # Trade entries are skipped if entry_date ∈ BLACKOUT_DATES.
  # Existing positions are NOT interrupted (trade exits per normal logic).

C. Combined: apply both A and B.
```

## Variants

| Variant | Rule | Hypothesis sign |
|---|---|---|
| **Baseline** | Deployed ORB_DAX T+180 LONG-only | reference |
| **VT** (vol-target only) | Apply A only | Sharpe up, MDD same-or-better |
| **EB** (event blackout only) | Apply B only | Sharpe up, MDD same-or-better |
| **VT+EB** (combined) | Apply A and B | Sharpe up by ~sum of individual lifts |
| **Inv-VT** (null) | Use INVERSE scale: `clip(realized/target, 0.5, 2.0)` | MUST hurt — sizes UP in high vol |
| **Event-only** (null) | Trade ONLY on event days (gate non-event days) | MUST hurt — events should be the bad days |

## Why retail-accessible

- Vol-target uses GER40 D1 already on disk; rolling-std and expanding-median in numpy.
- Event calendar is public information; no paid feeds. NFP is algorithmic.
- Zero broker-side complexity. Position-size adjustment is a single multiplier per trade.

## Universe

- Target: deployed ORB_DAX on GER40 M5, 2019-01-02 → 2026-04-17 (same window as `orb_dax_sentiment`).
- Vol input: `ohlc_data/GER40_D1.csv`.

## Expected performance (pre-committed estimates — point estimate, not optimization target)

- **VT alone**: +0.05 to +0.15 Sharpe lift. MDD 0-2pp improvement. Trade count unchanged.
- **EB alone**: +0.05 to +0.15 Sharpe lift. ~30 days/year × 7 years × 3.8 trades/wk × (~30/250 day-rate) ≈ 60-80 trades dropped of 1457 baseline. Trade count drops to ~1370-1400.
- **VT+EB combined**: +0.10 to +0.25 Sharpe lift if levers are roughly orthogonal. If combined ≥ sum of individuals, suspicious of regime-interaction; flag.

If lift on full sample is < +0.05 absolute on the combined variant, the structural-overlay thesis is wrong — the two effects are either already priced or are noise.

## Fail conditions (pre-committed)

The combined VT+EB variant PASSES if **all** hold:

- Full-period Sharpe improves by **≥ +0.15 absolute** over the same-engine baseline (re-impl baseline +0.46 from sentiment demo → ≥ +0.61).
- Holdout 2023-2026 Sharpe improves by **≥ +0.10 absolute** over baseline holdout.
- Max DD does not worsen by more than **1 percentage point**.
- Trade count remains ≥ **1000** over the 7-year window.
- **Null check 1 (event direction)**: `Event-only` Sharpe must be **at least +0.20 BELOW** baseline. If event days are not visibly worse than non-event days, EB is gating noise.
- **Null check 2 (vol-target direction)**: `Inv-VT` Sharpe must be **at least +0.20 BELOW** the VT-alone Sharpe. If sizing-up-in-high-vol does about as well as sizing-down-in-high-vol, VT has no directional content.
- **Regime consistency**: at least **2 of 3 regime windows** (2019-2020 / 2021-2022 / 2023-2026) show non-negative lift on VT+EB vs baseline. A single-window blowup means the result is regime-specific.
- **Cost robustness**: VT+EB Sharpe at **2.0pt RT cost** must still exceed baseline at 1.0pt RT cost. (If the lift only exists in a thin-spread world it's not deployable on a retail broker that widens during events.)

MARGINAL: combined Sharpe lift in [+0.05, +0.15) AND all null checks pass. Do not redeploy; keep simple baseline.

REJECTED: any fail-condition triggers. The verdict line at the top of this doc is set to REJECT.

## Why this might fail (red flags)

1. **Baseline ORB_DAX may already be approximately vol-targeted** by virtue of using percentage returns (each trade's PnL is in % of entry price), which is itself a first-order vol normalization. The additional lift from full inverse-vol scaling could be near-zero.
2. **Event days may not be uniformly bad** — Lucca-Moench documented FOMC drift is mainly in US large-caps and timed to the 24h pre-announcement; DAX exposure may be ~zero given Xetra closes 5+ hours before FOMC. EB could end up gating ~10% of trade days for no benefit.
3. **NFP day suppression** — 1st Friday days might actually be ABOVE average for opening impulse on DAX if the prior overnight US session "parked" markets means the Xetra open carries pent-up information that resolves AT the open (mirror of the original ORB mechanism). If so, EB harms.
4. **Vol-target clip at [0.5, 2.0]** is binding in tail regimes — Mar 2020 realized vol was 5-10× normal, so the clipped scaling of 0.5 still left huge nominal losses. The lever does NOT protect against tail events; it only stabilizes mid-vol-regime.
5. **Combined variant could double-dip** — if event days *also* happen to be high-vol days, VT already partially down-weights them, so EB adds less marginal information than its standalone test suggests.
6. **Baseline Sharpe discrepancy** — same caveat as `orb_dax_sentiment.md`: re-impl baseline is +0.46, deployed `orb.md` reports +0.76. We compare against the **re-impl baseline +0.46** throughout, so internal lifts are valid even if absolute level diverges.

## Phase 1 → 2 plan

- [x] Read `orb_dax_sentiment/sentiment_demo.py` to confirm baseline simulator and re-use it as-is.
- [x] Verify GER40 M5 + D1 on disk.
- [x] Pre-commit fail conditions, null-check thresholds, and parameter values (see "Signal math" above).
- [ ] Implement `voltarget_events_demo.py` reusing the simulator from `sentiment_demo.py`.
- [ ] Build vol-scale series (expanding-median target) and hardcoded event calendar.
- [ ] Run baseline + VT + EB + VT+EB + Inv-VT + Event-only.
- [ ] Regime breakdown (2019-2020 / 2021-2022 / 2023-2026) on VT+EB.
- [ ] Cost sensitivity (0.5 / 1.0 / 1.5 / 2.0 pt RT) on VT+EB.
- [ ] Per-lever attribution: does combined ≈ VT + EB, or are they interacting?
- [ ] Sanity-print blackout-day counts/year to confirm calendar is plausible (~28-32/yr).
- [ ] Apply pre-committed kill criteria — update verdict line at top of this doc.
- [ ] Update `docs/STATE.md` with the post-run YAML block.
- [ ] If PASS, add a lesson to `docs/RESEARCH_NOTES.md` about structural-vs-fitted overlay outcomes.

## Files

- Thesis: this file (`experiments/orb_dax_voltarget_events/orb_dax_voltarget_events.md`).
- Demo: `experiments/orb_dax_voltarget_events/voltarget_events_demo.py`.
- Data dependencies (all on disk):
  - `ohlc_data/GER40_M5.csv` (base strategy)
  - `ohlc_data/GER40_D1.csv` (vol-target input)
  - Event calendars hardcoded in the demo (no external data files).
