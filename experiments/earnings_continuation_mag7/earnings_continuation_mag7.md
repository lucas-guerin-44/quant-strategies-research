# Mag7 earnings-gap continuation (intraday)

**Status**: Phase 2 + walk-forward complete (2026-05-22).

**Verdict**: **REJECT** on pre-committed kill criteria, but with deep mechanistic finding: **the direction signal IS regime-flipped post-2022 on Mag7** (holdout cont Sh +0.78 vs holdout fade Sh -1.67; Δ +2.45). Full-sample washes out (+0.18 each direction, dir-gap -0.02) because 2021-2022 is the anti-regime where fade worked. Walk-forward mean OOS +0.94 PASSES the +0.30 floor but min OOS -0.09 FAILS the no-negative-window pre-commit. Baseline FAILS the +0.40 Sharpe floor at -0.18.

## Phase 2 results (2026-05-22)

### Baseline (cont, MIN_GAP=1.5%, T+60min, stop=1.5×, cost=4 bp RT) — Mag7 only

| Metric | Value | vs threshold |
|---|---|---|
| Period | 2018-02 → 2026-05 (8.2y) | — |
| Sharpe | **-0.18** | **FAIL** (< +0.40) |
| MDD | -18.56% | PASS |
| Events | 123 (14.9/yr) | PASS (>=80) |
| WR / PF | 48.0% / 0.94 | PASS |
| CAGR | -0.55% | — |

### Regime breakdown — **the mechanism flips sign at 2022/2023 boundary**

| Window | n | Sharpe | MDD |
|---|---|---|---|
| 2018-2020 pre/COVID | 7 | -6.00 | -5.7% |
| 2021-2022 vol | 32 | -1.51 | -13.6% |
| **2023-2026 holdout** | **84** | **+0.78** | **-6.1%** |

Compared to earnings_fade Mag7 holdout (Sh **-1.67**): **same universe, same trigger, opposite direction wins** in the holdout regime. Δ = +2.45. The mechanism sign-flip predicted by lesson #43 / #44 is empirically confirmed on Mag7 specifically.

### Direction null-check — `cont` and `fade` BOTH lose at full sample

| Direction | Full Sh | Holdout Sh |
|---|---|---|
| Continuation (this thesis) | -0.18 | +0.78 |
| Fade (null) | -0.15 | -1.67 (per earnings_fade dissection) |

**Direction-gap = -0.02 at full sample** — no decisive direction. But by regime:
- 2021-2022: fade wins (continuation -1.51 vs fade ~+0.95 by symmetry math)
- 2023-2026: continuation wins (+0.78 vs fade -1.67)

Either direction picked at full-sample averages to neutral. The signal is real but regime-dependent in opposite directions.

### Walk-forward — Phase 6 binding test

| Split | IS Sh | OOS Sh | OOS n | OOS MDD |
|---|---|---|---|---|
| IS 2021-09 → 2024-09 / OOS → 2026-05 | -0.19 | **+0.63** | 42 | -6.1% |
| IS 2022-09 → 2025-09 / OOS → 2026-05 | -0.26 | **+2.27** | 17 | -1.9% |
| IS 2021-09 → 2023-09 / OOS → 2025-09 | -0.38 | **-0.09** | 48 | -5.7% |

Mean OOS Sh **+0.94** PASSES (+0.30 floor). Min OOS -0.09 FAILS (<0). The first two splits put the IS-train inside the 2021-22 anti-regime AND test on the post-flip period — those OOS values are very strong. The third split's OOS straddles the regime boundary (2023-09 → 2025-09 includes both anti-regime tail and on-regime body) and is marginally negative.

### Per-ticker (full sample)

Best: **TSLA Sh +2.31 (+10.79% total)**, NVDA +0.40, MSFT +0.17. These are the names with the largest single-stock 0DTE OI (per published Goldman/JPM strategist notes 2024-25).

Worst: GOOGL Sh -1.21, AMZN -1.37, META -1.18, AAPL -0.55. AAPL is the surprise — has high 0DTE OI but doesn't continue cleanly.

### Variant sweeps

| Lever | Best | Sharpe |
|---|---|---|
| MIN_GAP_PCT | 2.0% | +0.03 |
| TIME_EXIT_MIN | T+240 | +0.44 (best of all variants) |
| Cost | 0 bp | -0.00 |

T+240 continuation > T+60 continuation makes mechanistic sense: a real continuation rides further. The 60-min sweet spot from earnings_fade (mean-reversion) doesn't apply to the mirror.

## Verdict reasoning

Pre-committed kill criteria, in order:

1. Phase 2 Sharpe > +0.40: **FAIL** (-0.18). The full-sample mechanism averages to neutral.
2. Direction null-gap ≥ +0.50: **FAIL** (-0.02 at full sample). Both directions individually lose.
3. Walk-forward mean OOS Sh ≥ +0.30 AND no OOS window < 0: **FAIL** (mean +0.94 passes, min -0.09 fails).
4. Phase 6 holdout Sh ≥ +0.30: **PASS** (+0.78) — but binding only if Phase 2 also passes.

3-of-4 binding criteria fail. **REJECT.**

## What we learned (for RESEARCH_NOTES.md)

This is the cleanest single-experiment confirmation of lesson #43 yet:
- Pre-committing both fade and continuation as co-equal candidates would have arrived at this verdict directly: "BOTH directions FAIL at full sample on Mag7; signal is regime-conditional and currently sits at +2.45-Sharpe holdout-by-direction split."
- The regime-flip is at 2022/2023, consistent with the timing of the single-stock 0DTE-options explosion (per public 0DTE OI data; CME 0DTE volume grew ~10× 2022-2024).
- Walk-forward exposed the failure: training in the anti-regime predicts OOS strongly, but a train-split that straddles the boundary fails.
- The deploy path here is NOT another flip-and-refit. It's accepting that the mechanism is **regime-conditional, not directional**, and Mag7 earnings-day intraday is currently not deployable in either direction without a regime-detection overlay (which itself requires pre-commit + walk-forward, and is at risk of the same overfit pattern).

## Pivot candidate: regime-detection overlay

NOT proposed here — would need fresh pre-commit. Sketch: pre-commit a binary 0DTE-OI proxy (e.g., AAPL 0DTE volume / total options volume rolling 30d, or VIX9D/VIX ratio as low-cost proxy). Trade fade when proxy is below threshold; trade continuation when above. Walk-forward + sign-stability constraints. This is a candidate for a future experiment, not a fix to this one.

## Files

- Thesis: this file.
- Demo: `earnings_continuation_mag7_demo.py`

---

## Thesis (mechanism)

Direct mirror-direction pivot from the rejected `earnings_fade` thesis (lesson #44). Phase 2 dissection of `earnings_fade` produced:

- Full-sample dir-gap = **+1.35** (fade wins overall) BUT
- **Mag7-only holdout dir-gap = approximately −2.34** (continuation wins in the post-2022 regime on 0DTE-options-concentrated names — see earnings_fade.md dissection section (b))
- Mag7-only holdout fade Sharpe **−1.67** (n=84, WR 46.4%, MDD -20.7%); the symmetric continuation should sit near **+1.0 to +1.5** Sharpe before friction (pure dir-gap algebra; will be re-measured precisely in Phase 2)

The mechanism is the canonical lesson #43 pattern: **post-2022 0DTE-options gamma flow makes dealers aggregate-short gamma on single-stock earnings days at the high-OI names**. MMs delta-hedging into the gap move amplifies — does not fade — the opening drive. The continuation direction is the post-2022 active one on Mag7.

**Mechanistic prediction**: the holdout regime IS the load-bearing window per lesson #25 — the mechanism intensifies with 0DTE OI growth (2024+ post-spot-ETF retail options proliferation). If the thesis is real and modern, holdout should be the BEST regime, not the worst (unlike earnings_fade which had inverse). Pre-2022 sample is expected to be neutral-to-negative (continuation worked weakly when fade was the dominant institutional flow); 2022 vol regime is the inflection point; 2023+ is where the mechanism activates.

## Key reference

- This thesis is the **lesson #43 / #44 pivot path**, not a literature replication. The continuation direction does not appear in the academic intraday-MR literature (So & Wang 2014; Berkman et al 2012) because those papers were written before 2020 — the mechanism direction has flipped post-0DTE.
- Brogaard et al (2024 working papers) on 0DTE single-stock options and intraday return predictability is the modern anchor — predicting positive serial correlation in the first 30-90 min on names with high 0DTE OI.
- Mechanism family corroboration: `opex_pin_fade` REJECT (lesson #42) — same dealer-short-gamma flow at the index Friday-PM level.

## Signal math (baseline — same simulator as earnings_fade, direction=cont, universe restricted to Mag7)

```
Universe: 7 Mag7 names (AAPL MSFT GOOGL AMZN META NVDA TSLA).

Per earnings event:
  prior_close       = last RTH M5 close on day D-1
  today_open        = first RTH M5 OPEN on trade_date (~09:30-09:35 ET)
  gap_pct           = today_open / prior_close - 1.0

  if abs(gap_pct) < MIN_GAP_PCT (1.5%): skip

  entry_bar         = SECOND M5 bar of RTH (09:35 ET, conservative slippage)
  position          = +sign(gap_pct)   # CONTINUATION: long the up-gap, short the down-gap
  stop              = entry_price ∓ STOP_GAP_FRAC × abs(gap_pct in $)
  exit              = T+TIME_EXIT_MIN minutes (default 60) or stop or last RTH bar

  cost              = 4 bps RT (Phase 0 confirmed 2 bps basket median for Mag7 names specifically)

  Max 1 trade per (ticker, event).
```

## Why retail-accessible

- Intraday-only, event-driven (already verified by earnings_fade Phase 0): 7 names × 4 events/yr × 5 backtest years × ~70% setup rate = ~98 trades. Above 200 only when extended across more years of data; with Mag7-only universe + restricted history, expect 80-130 events. Borderline for the 200-floor pre-commit (see Fail conditions).
- Eightcap broker spread on Mag7 specifically: AAPL 1.08 / MSFT 1.42 / NVDA 1.46 / TSLA 1.37 / GOOGL 1.23 / AMZN 1.45 / META 1.78 bp — all sub-2 bp deploy-window medians. 4 bp RT cost assumption has 2× headroom.
- M5 data already on disk + datalake. Earnings calendar already on disk. **Zero new data infrastructure required.**

## Universe

7 Mag7 names: AAPL MSFT GOOGL AMZN META NVDA TSLA.

## Expected performance

Per-event gross: 60-150 bps (continuation moves typically 0.5-1.5% in the first hour on a 2-5% gap).

Trade cadence: 80-130 events / 5 years (Mag7 only on M5-history-restricted window).

**Expected research Sharpe**: based on earnings_fade Mag7-holdout fade Sh −1.67, continuation should be approximately +1.0 to +1.5 at zero cost. After 4 bp friction: **+0.6 to +1.0**. After 10-25% relative haircut (per rewritten lesson #5): live target **+0.45 to +0.90**. Event-driven strategies may haircut wider — to be validated against 6-12 months of live data.

WR: target 50-60% (continuation isn't winner-take-all; persistent drift gives moderate WR with positive PF).

## Fail conditions (pre-committed)

Per lesson #43 rule 1: **both directions are co-equal candidates**. This thesis's pre-commit covers the CONTINUATION direction specifically; the FADE direction has already been rejected on Mag7 (see earnings_fade.md). The honest verdict states for this experiment are:

- PASS: continuation passes all kill criteria
- REJECT: continuation fails any kill criterion (regardless of fade-direction status)
- INVERTED: implausible — would mean both directions fail, in which case the universe has no exploitable directional content (Mag7 noise; tombstone permanently)

### Phase 2 kill criteria

- Full-sample Sharpe < +0.40 after 4 bp RT cost. (Higher bar than +0.30 because the expected gross is meaningfully larger than typical opening-impulse strategies; +0.40 corresponds to ~+0.7 at zero cost which is the lower edge of the mirror-image expectation.)
- Max DD > 25%.
- Events count < 80 (Mag7-only universe; standard 200-floor relaxed but lower bound enforced).
- WR < 45% AND PF < 1.15.
- Direction null-check: continuation Sharpe − fade Sharpe < +0.50. (Higher gap requirement than lesson-#39's +0.30 because the prior-experiment dissection already implies +2.34 in the holdout sub-sample.)

### Phase 6 kill criteria (binding, per lesson #25/#31)

- 2023-2026 holdout Sharpe ≤ +0.30. (Tight floor — the deploy case rests on the holdout being the strongest regime; this is the mirror of `earnings_fade`'s mechanism, so holdout-best is mechanistically required.)
- Walk-forward (3y-IS / 1.5y-OOS rolling splits): mean OOS Sharpe ≥ +0.30 AND no single OOS window < 0. Required because the M5 data window is short (4.7y median), so a single train/test split is fragile; walk-forward (per lesson #29) is mandatory.

### Phase 4 regime kill

- ≤ 1 of 2 available regimes (2021-2022 vol, 2023-2026 holdout) positive. 2018-2020 window is mostly empty on Mag7 (only AMZN has pre-2021 data); not load-bearing.

## Why this might fail (red flags)

1. **The earnings_fade dissection was post-hoc.** The +2.34 dir-gap on Mag7 holdout is a sub-population selection — taking the mirror direction of a rejected universe sub-slice is exactly the "promote the winning sub-variant" overfit pattern per lesson #20. The fresh pre-commit + walk-forward is the mitigation but doesn't fully eliminate the risk.
2. **N=84 holdout events on Mag7 is statistically borderline.** Even +2.34 dir-gap has wide CI at this sample size.
3. **Asymmetric LONG/SHORT in holdout (earnings_fade dissection (e))**: fade-down-gaps was broken (Sh -0.58), fade-up-gaps was neutral (Sh +0.12). Mirror form: continuation-down-gaps should be the strong leg; continuation-up-gaps mildly negative. Pre-commit a LONG/SHORT split check.
4. **The mechanism is fragile to dealer positioning changes.** If 0DTE-OI shrinks (e.g., regulatory restriction, broker leverage rules), the gamma flow that drives the continuation evaporates.
5. **Per-event variance on continuation is HIGHER than on fade** — winners are clipped at time-exit; losers can be the full opposite-direction gap (multi-percent moves). Expect lower Sharpe-per-trade than research literature on lower-variance strategies.

## Phase 1 → 2 plan

- [x] **Data already on disk**: 7 Mag7 names M5 + earnings calendar.
- [ ] **Phase 2a — direct run**: re-use `earnings_fade_demo.run_backtest()` with `direction='cont'` and universe filtered to Mag7. Single script: `earnings_continuation_mag7_demo.py`.
- [ ] **Phase 2b — kill criteria check + regime breakdown + null-check (fade direction)**.
- [ ] **Phase 6 — walk-forward (3y-IS / 1.5y-OOS rolling splits)**. ~3 splits achievable on the 4.7y window.
- [ ] **Phase 4 — LONG/SHORT split**. Should be asymmetric per dissection (e).

## Files

- Thesis: this file.
- Demo: `earnings_continuation_mag7_demo.py` (wraps earnings_fade_demo's run_backtest).
- Walk-forward: `_walk_forward.py`.

## References

See `earnings_fade.md` references + lesson #42 (opex_pin_fade) for mechanism-family corroboration + lesson #43 (mirror-pattern named) for methodology rule.
