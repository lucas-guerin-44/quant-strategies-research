# Single-stock lunch fade (US RTH)

**Status**: Phase 2 + walk-forward complete (2026-05-22).

**Verdict**: **REJECT (decisive)**. Generalization hypothesis cleanly falsified: zero of 24 names has positive Sharpe; basket Sh **-1.06** (cost=4bp), **-0.26** at cost=0bp; direction null-gap **-0.53** (continuation loses LESS than fade — mechanism is sign-NEUTRAL/weakly-continuing on single stocks, not mean-reverting); holdout is the WORST regime (-1.26 vs NDX +1.51); all three walk-forward OOS windows negative (-0.95 / -1.19 / -1.44). Three independent kill-criteria fail; mechanism categorically does not generalize.

## Phase 2 results (2026-05-22)

### Baseline (fade, morning=24bar, afternoon=48bar, thr=0.25, cost=4 bp RT)

| Metric | Value | vs threshold |
|---|---|---|
| Period | 2018-01 → 2026-05 (8.4y) | — |
| Sharpe | **-1.06** | **FAIL** |
| MDD | -65.79% | **FAIL** |
| Events | 12,913 (1542/yr) | PASS |
| WR / PF | 45.6% / 0.80 | PASS WR / FAIL PF |
| CAGR | -12.02% | — |

Trade cadence is **53× higher than expected**: ~1542 events/yr vs the ~30/yr projection from NDX cadence × 24 / correlation-deflation. The thr=0.25 threshold calibrated on NDX is mechanically wrong for single stocks because single-stock M5-mean-abs-return is higher than NDX's, but the threshold formula multiplies daily-vol-proxy × `morning_end_bar` directly. Single-stock firing rate ~46% of stock-days vs NDX ~12% of days.

### Regime breakdown — holdout is WORST (opposite of NDX lunch_fade)

| Window | n | Sharpe | MDD |
|---|---|---|---|
| 2019-2020 pre/COVID | 122 | -0.66 | -4.8% |
| 2021-2022 vol | 3568 | -0.58 | -19.4% |
| **2023-2026 holdout** | **9107** | **-1.26** | **-41.1%** |

**Per lesson #25/#28**: the parent NDX lunch_fade had 2023-2026 as its BEST regime (+1.06). Single-stock has 2023-2026 as the WORST regime. **Same time window, same date filter, opposite direction of post-2022 evolution.**

### Direction null-check — SIGN-FLIPPED

| Direction | Sharpe |
|---|---|
| Fade (baseline) | -1.06 |
| Continuation (null) | -0.53 |

**Direction-gap = -0.53.** Both directions lose, but fade loses MORE. Continuation is the less-bad direction at single-stock level — meaning if anything, single-stock morning moves continue (weakly) rather than fade. This is the **opposite** of the index-level mechanism direction.

### LONG / SHORT split

| Leg | n | Sharpe | WR |
|---|---|---|---|
| LONG (fade down-moves) | 6070 | -1.15 | 46.6% |
| SHORT (fade up-moves) | 6843 | -0.98 | 44.6% |

Both legs negative, no asymmetry rescue.

### Mag7 vs non-Mag7 (per lesson #44 reflex check)

| Sub-universe | n | Sharpe | MDD |
|---|---|---|---|
| Mag7 | 4096 | -0.82 | -63.4% |
| non-Mag7 | 8817 | -1.24 | -49.6% |

Both lose — lesson-#44 bifurcation doesn't save this thesis. (Mag7 marginally less bad because Mag7 includes AAPL/MSFT which are S&P-300-correlated and inherit *some* of the basket-arb pressure, but still negative.)

### Per-ticker — zero winners

Best: GOOGL Sh **-0.07** (close to neutral, but not positive). META -0.13. V -0.66. MA -0.85.

Worst: AMZN -1.40 (-64.4% total), AVGO -1.67 (-56.0%), XOM -1.73, AAPL -1.66, WMT -1.84.

**Not a single name across 24 produces a positive Sharpe**, and the spread between best (GOOGL -0.07) and worst (AMZN -1.40) is well within per-name noise — there's no "this set of names works" sub-thesis hiding here.

### Variant sweeps — no cell rescues

- **Threshold sweep**: every thr from 0.10 to 0.50 produces Sh between -0.93 and -1.06. No knee.
- **Afternoon-exit sweep**: every exit (T+180 to T+360 equivalent) negative. Best is afternoon=72bar (~16:00 ET, full day) at -0.90.
- **Cost sensitivity**: cost=0bp **-0.26**. The negative Sharpe is signal-not-friction (lesson #26 diagnostic). Even at zero cost the mechanism doesn't extract directional content.

### Walk-forward — uniformly catastrophic

| Split | IS Sh | OOS Sh | OOS n | OOS MDD |
|---|---|---|---|---|
| IS 2021-09 → 2024-09 / OOS → 2026-05 | -1.08 | -0.95 | 4745 | -22.4% |
| IS 2022-09 → 2025-09 / OOS → 2026-05 | -1.22 | -1.19 | 2064 | -10.4% |
| IS 2021-09 → 2023-09 / OOS → 2025-09 | -0.61 | -1.44 | 5355 | -32.0% |

Mean OOS -1.19, min OOS -1.44. Train and OOS uniformly negative — no regime saves it.

## Verdict reasoning

Pre-committed criteria, all binding kill-criteria fail:

- Phase 2 Sharpe > +0.30: **FAIL** (-1.06)
- Phase 2 MDD < 25%: **FAIL** (-65.8%)
- Direction null-gap ≥ +0.30: **FAIL** (-0.53)
- Phase 4 ≤ 1/3 regimes positive: **FAIL** (0/3 positive)
- Phase 6 holdout ≥ 0: **FAIL** (-1.26)
- Walk-forward mean OOS ≥ +0.20: **FAIL** (-1.19)

6-of-6 fail. **REJECT, no ambiguity.**

## Mechanistic interpretation — the generalization hypothesis is cleanly refuted

The lunch-vacuum mechanism on NDX appears to be **driven by basket-level cash-vs-futures arbitrage flow**, not by retail/institutional inventory-rebalance at the individual-stock level. The mechanism story (from lunch_fade.md):
> "the simultaneous NY/Chicago lunch + EU close = institutional flow vacuum, leaving HFT inventory rebalancing dominant (mean-reverting)"

Refined post-this-result:
- The "HFT inventory rebalancing" on NDX is concentrated on **NDX cash-vs-NQ-futures basis arb**, not single-stock inventory.
- During the 11:30-13:30 ET vacuum, the basis-arb HFTs are the dominant flow, and their behavior is mean-reverting on the basket (compressing any morning overshoot of the NDX-NQ basis).
- At single-stock level, there is **no equivalent single-name cash-vs-futures basis** with comparable liquidity. Individual-stock futures are illiquid (E-mini single-stock futures barely trade). So no basis-arb mechanism, no MR signal.
- Additionally, individual stocks during lunch are subject to **idiosyncratic news flow** (analyst upgrades, sector rotation, social-media chatter) that overwhelms any positioning-flow signal at the per-name level.

This refines **lesson #27** ("Lunch fade is a structural exception, not a generic 'fade overshoot on indices' rule") to a stronger form: **the structural exception is INDEX-ARB-SPECIFIC and does not extend to constituents**. A future thesis on "lunch fade on FUTURES BASKETS" (e.g., FDAX, FESX during EU lunch) might generalize because the same basis-arb mechanism exists; but single-stock lunch fade is mechanism-empty.

## Files

- Thesis: this file.
- Demo: `single_stock_lunch_fade_demo.py`


---

## Thesis (mechanism)

Direct generalization of the **deployed** `lunch_fade` NDX strategy (Sh +1.02 LONG-only / holdout +1.51, lesson #25-#27) from the index level to its 24 single-name constituents and adjacent S&P large-caps.

**Mechanism (from lunch_fade.md)**: during 11:30-13:30 ET, the simultaneous NY/Chicago lunch + European close creates an institutional flow vacuum. HFT inventory rebalancing dominates the tape, which has a mean-reverting bias — the morning's overreaction (09:30-11:30 ET) partially retraces. The mechanism INTENSIFIED post-2022 (holdout is the BEST regime on NDX) because 0DTE-options intraday chop amplifies the morning-overshoot signal.

**The single-stock generalization hypothesis**: the same institutional-vacuum mechanism operates on individual large-cap names. Single-stock VWAP-tracking algos AND market-maker inventory hedging both produce the same 11:30-13:30 ET reversal pressure on individual tape, not just the basket. If true, we should see:
- Sub-universes that follow the index (high-beta, high-attention) fade strongly
- Defensive names (low-beta, less options activity) fade weakly or not at all
- Overall basket: lower-Sharpe-per-name than NDX index (idiosyncratic noise), but ~5-10× the trade count → comparable total Sharpe after diversification

If false (mechanism is purely index-level, basket-arbitrage flow), single-stock results should be weak or sign-flip on the high-beta-vs-defensive bifurcation.

## Universe

Same 24 names already on disk from earnings_fade Phase 1:

AAPL MSFT GOOGL AMZN META NVDA TSLA JPM BAC GS V MA UNH WMT HD LOW KO PEP JNJ XOM CVX ORCL CRM AVGO

(MS dropped — not on Eightcap.)

## Signal math — same as deployed lunch_fade (thr=0.25)

Per RTH session (09:30-16:00 ET), per ticker:

```
morning_end_min       = 120   (= 11:30 ET, end of morning measurement window)
afternoon_end_min     = 240   (= 13:30 ET, end of afternoon hold window)
MIN_MOVE_ATR          = 0.25  (cadence-passing knee from NDX sweep)
COST_BPS_RT           = 4.0   (Phase-0-confirmed single-stock Eightcap; vs 1pt CFD on indices)
direction             = "fade"
ATR_LOOKBACK_DAYS     = 20    (per-name rolling ATR)

per ticker, per day:
  open_px           = first M5 OPEN on the day (~09:30-09:35 ET)
  morning_close_px  = M5 close at the bar that ends the 09:30-11:30 ET window
  r_morning         = morning_close_px / open_px - 1.0
  daily_vol         = mean(abs(bar_returns) for the day)
  atr_proxy         = rolling 20d mean of daily_vol
  threshold         = MIN_MOVE_ATR × atr_proxy × morning_bars
  if abs(r_morning) < threshold: skip
  position          = -sign(r_morning)    # FADE
  entry             = open of next M5 bar after morning_close
  exit              = M5 close at the bar that ends the 11:30-13:30 ET window
  cost              = COST_BPS_RT bps RT
```

## Why retail-accessible

- Data already on disk (parent earnings_fade Phase 1 backfill).
- Cost confirmed by parent Phase 0: 2 bp basket median, 4 bp RT deploy assumption with 2× headroom.
- Total trade cadence (assuming ~30 setups / name / year @ thr=0.25 — extrapolated from NDX 29/yr): ~720 trades/year basket-wide. Even after 50% correlation deflation, ~360 effective trades/yr. Well above the 200 floor.

## Expected performance

This is a generalization hypothesis test, not a literature-based estimate. The mechanism story predicts:

- **If hypothesis holds**: basket Sharpe +0.5 to +1.0 at 4 bp cost, dir-gap > +0.50, holdout positive.
- **If hypothesis is partially correct (some names work)**: basket-aggregate Sharpe +0.3 to +0.5, with per-ticker dispersion correlated to beta/options-activity.
- **If hypothesis fails (mechanism is index-only)**: basket Sharpe ≈ 0 or negative, dir-gap small.

## Fail conditions (pre-committed)

### Phase 2

- Basket Sharpe > +0.30 after 4 bp RT cost.
- MDD > 25%.
- Trades < 200.
- WR < 45% AND PF < 1.1.
- Direction null-check (continuation): gap < +0.30.

### Phase 4 regime

- ≤ 1 of 3 regimes positive (2019-2020 / 2021-2022 / 2023-2026 holdout) where regime has n ≥ 20 events.

### Phase 6 (binding per lesson #25, given parent strategy showed holdout-best)

- 2023-2026 holdout Sharpe ≤ 0. (Lower bar than the lesson-#25 ideal of holdout-best, because single-stock generalization may degrade per-name signal even when index-level remains strong.)

### Walk-forward (per lesson #29)

- 3 rolling splits: mean OOS Sharpe ≥ +0.20 AND min OOS ≥ -0.10. (More tolerant than earnings family pre-commit because single-stock variance is mechanically higher.)

## Why this might fail

1. **Idiosyncratic news flow dilutes the mechanism**: single-name morning moves are often news-driven (analyst upgrade, sector rotation, earnings carryover) rather than positioning-driven. Fading news is a known loss pattern (gap_continuation REJECT, lesson #5 venue-specific gap-direction).
2. **0DTE-options arbitrage** — same effect that killed earnings-fade on Mag7 could kill single-stock lunch-fade on the same names. Critical test: per-ticker results split on Mag7 vs non-Mag7.
3. **Index-arb is dominant at lunch hour**: the 11:30-13:30 vacuum may be specifically a basket-arbitrage phenomenon (HFT cash-vs-futures spread compression), in which case single-stock tape doesn't show the same pattern.
4. **VWAP-algo flow is institutional-only** and not strong enough on individual names to outweigh retail/news flow.
5. **Threshold calibration**: thr=0.25 was tuned on NDX's intraday ATR distribution. Single-stock ATR is mechanically different (per-name beta varies 0.3-2.0). Per-name thresholds may need to be β-adjusted; baseline uses uniform thr=0.25 and accepts the calibration mismatch.

## Phase 1 → 2 plan

- [x] Data already on disk (parent earnings_fade Phase 1).
- [ ] Phase 2a — `single_stock_lunch_fade_demo.py` loops the `simulate_lunch_fade` function from `experiments/lunch_fade/lunch_fade_demo.py` across the 24-name universe, aggregates events.
- [ ] Phase 2b — kill criteria, regime breakdown, per-ticker breakdown.
- [ ] Phase 4 — direction null-check + LONG/SHORT split.
- [ ] Phase 6 — walk-forward (3 rolling splits).

## Files

- Thesis: this file.
- Demo: `single_stock_lunch_fade_demo.py`
