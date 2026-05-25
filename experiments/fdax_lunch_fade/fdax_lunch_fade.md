# FDAX lunch fade (GER40 Berlin-lunch basis-arb)

**Status**: Phase 2 complete (2026-05-22).

**Verdict**: **REJECT (decisive)**. Lesson #48 generalization is REFUTED on FDAX/cash-DAX. Baseline Sh -0.10, dir-gap -0.08 (no directional content), cost-zero Sh -0.04 (signal-absent, not friction-eaten). Combined with `single_stock_lunch_fade` REJECT, lunch-fade mechanism narrows further to NDX/NQ-specific.

## Phase 2 results (2026-05-22)

### Baseline (fade, morning=180min/12:00 CET, afternoon=270min/13:30 CET, thr=0.25, cost=1pt)

| Metric | Value | vs threshold |
|---|---|---|
| Sharpe | **-0.10** | FAIL |
| MDD | -14.40% | PASS |
| Trades | 281 (0.74/wk) | PASS |
| WR / PF | 47.3% / 0.94 | PASS WR / FAIL PF |
| CAGR | -0.47% | — |

### Regime breakdown

| Window | n | Sharpe | CAGR | MDD |
|---|---|---|---|---|
| 2019-2020 pre/COVID | 78 | **+0.58** | +3.1% | -5.6% |
| 2021-2022 vol | 81 | -1.16 | -4.1% | -8.6% |
| 2023-2026 holdout | 122 | -0.14 | -0.4% | -5.4% |

Only 1/3 regimes positive (2019-2020), and that early regime is the smallest sample. Modern regime (holdout) is decisively flat-to-negative.

### Direction null-check — INVERTED-ish, no decisive signal either way

| Direction | Sharpe | MDD |
|---|---|---|
| Fade (baseline) | -0.10 | -14.4% |
| Continuation (null) | -0.03 | -12.9% |

Dir-gap **-0.08** (kill if < +0.30). Neither direction has signal; both are mild losers. This is the canonical "no mechanism" pattern.

### Threshold sweep — only outlier-magnitude bins show edge

| thr | Sharpe | MDD | trades |
|---|---|---|---|
| 0.10 | -0.16 | -22.3% | 933 |
| 0.20 | -0.29 | -18.4% | 413 |
| **0.25** (NDX-deployed) | **-0.10** | -14.4% | 281 |
| 0.30 | -0.04 | -10.6% | 188 |
| 0.40 | +0.33 | -7.5% | 95 |
| 0.50 | +0.39 | -3.3% | 50 |

High-threshold cells show positive Sharpe but trade counts collapse (n=50 at thr=0.50 = ~7/yr, well below the 200 floor). These are cherry-picks, not the mechanism.

### Afternoon-exit sweep — reveals a DIFFERENT mechanism

| afternoon exit | CET time | Sharpe | trades |
|---|---|---|---|
| 210 | 12:30 | -0.17 | 281 |
| 240 | 13:00 | -0.02 | 281 |
| **270** (lunch_fade-equivalent) | 13:30 | -0.10 | 281 |
| 300 | 14:00 | -0.11 | 281 |
| **360** | **15:00** | **+0.38** | 281 |
| **420** | **16:00** | **+0.32** | 281 |

Holding past Berlin lunch into the post-US-open window (15:00-16:00 CET) produces positive Sharpe — but this is a **different mechanism** (full-day morning-fade with US-open hand-off), not the lunch-vacuum thesis being tested. Logged as a side observation, not promoted (post-hoc cell selection + different mechanism family).

### Cost sensitivity — signal-absent, not friction-eaten

| Cost (pt RT) | Sharpe |
|---|---|
| 0.0 | **-0.04** |
| 1.0 | -0.10 |
| 2.0 | -0.17 |
| 3.0 | -0.23 |

Cost-zero Sharpe is essentially zero. The mechanism doesn't extract directional content even with zero friction. Per lesson #26 diagnostic, this is a no-signal REJECT, not an edge-eaten-by-cost REJECT.

### LONG/SHORT split (fade)

| Leg | n | Sharpe | MDD |
|---|---|---|---|
| LONG-only (fade down-mornings) | 127 | -0.23 | -7.6% |
| SHORT-only (fade up-mornings) | 154 | +0.09 | -9.1% |

Asymmetric: fading UP-mornings has slight positive Sh +0.09 (consistent with DAX structural up-drift — selling rallies is a mild loss compounding with up-drift, but fading the up-extremes catches over-extension). Fading DOWN-mornings is negative because DAX has structural up-drift (per orb_dax LONG-only deploy) — buying dips into lunch fights against opening-impulse momentum. **Same DAX directional asymmetry as orb_dax**: the structural edge on DAX is LONG opening-impulse momentum, not afternoon mean reversion.

## Verdict reasoning

Pre-committed kill criteria:

| Criterion | Floor | Observed | Verdict |
|---|---|---|---|
| Phase 2 Sharpe | > +0.30 | -0.10 | **FAIL** |
| Direction null-gap | ≥ +0.30 | -0.08 | **FAIL** (no directional content) |
| Phase 4 ≥ 2/3 regimes positive | 2 | 1 | **FAIL** |
| Phase 6 holdout > 0 | yes | -0.14 | **FAIL** |
| Cost-zero positive | yes | -0.04 | **FAIL** (signal-absent) |

5-of-5 fail. **REJECT.**

## Mechanistic interpretation — three reasons lesson #48 doesn't generalize

1. **No simultaneous flow-removal during Berlin lunch.** The NDX lunch_fade works because 11:30-13:30 ET is the *simultaneous* NY lunch + EU close — two distinct sources of institutional flow removal. Berlin lunch is ONE flow source removal (European desks at lunch); US hasn't opened yet (15:30 CET); Asia closed. Single flow removal isn't enough to create the vacuum-MR pressure.

2. **FDAX/cash-DAX basis-arb may be shallower than NDX/NQ basis-arb.** NQ is the world's #2 index future by daily volume; FDAX is Eurex's flagship but smaller. The HFT density during the lunch hour may not reach the threshold where basis-arb flow dominates the residual tape.

3. **DAX morning impulse is structurally persistent.** orb_dax's deploy demonstrates that DAX morning moves continue, not revert. Fading the morning move during lunch is fighting the same structural up-drift that orb_dax extracts as alpha. This is mechanism collision — the two strategies would be on opposite sides of the same trade.

## What we learned (for RESEARCH_NOTES.md)

This is the **second independent negative result** narrowing lunch_fade's mechanism scope:
1. `single_stock_lunch_fade` REJECT (2026-05-22): doesn't extend to NDX constituents → mechanism is index-level, not name-level
2. `fdax_lunch_fade` REJECT (2026-05-22): doesn't extend to FDAX/cash-DAX during Berlin lunch → mechanism is NDX/NQ-specific, not generic index-basis-arb

Sharpens lesson #48 from:
- **Old (after single_stock REJECT)**: "lunch fade is an INDEX-CASH-vs-FUTURES-BASIS-ARB exception"
- **New (after fdax REJECT)**: "lunch fade is specifically the **NDX/NQ midday-vacuum** mechanism. Even other deep index-futures pairs with comparable HFT participation don't replicate it. The simultaneous NY-lunch + EU-close confluence appears to be load-bearing — not the basis-arb mechanism alone."

**Implication for the live book**: lunch_fade is more fragile than the prior "structural exception" framing suggested. It has zero validated sibling mechanism in the repo. If NDX/NQ market structure shifts (further 0DTE saturation, MM behavior change, NY-EU session-overlap dynamics), there's no fallback. **Cannot diversify within the lunch-fade family**. The kill criteria + shadow-log on lunch_fade (steps #2 and #5 of this session's tightening) are now more important, not less.

## Files

- Thesis: this file
- Demo: `fdax_lunch_fade_demo.py`


---

## Thesis (mechanism)

Direct sibling of the deployed `lunch_fade` (NDX100) strategy, motivated by **lesson #48** (which this experiment validates or refutes):

> "lunch fade is an INDEX-CASH-vs-FUTURES-BASIS-ARB exception that does NOT generalize to constituents. Future thesis path: lunch fade on FUTURES BASKETS (FDAX, FESX during EU lunch) where basis-arb mechanism exists."

Berlin lunch hour creates an institutional flow vacuum on Xetra-listed DAX names:
- **12:00-13:30 CET**: European institutional desks take lunch; LSE morning auction is over (well past 09:30 BST open); **US has not yet opened** (NY open is 15:30 CET); Asian sessions closed
- This is **EU's equivalent of the NDX 11:30-13:30 ET vacuum** that powers `lunch_fade` — but anchored on a different timezone with different cross-asset flow dynamics
- Cash-DAX (GER40 CFD) trades on Xetra; **FDAX futures** trade on Eurex with deep liquidity through the lunch hour
- During the vacuum, HFT basis-arb between cash-DAX and FDAX dominates the residual flow → mean-reverting bias on whichever side overshot in the morning (09:00-12:00 CET) leg

If lesson #48 is correct, the morning-move → afternoon-fade pattern should replicate on GER40 M5 with parameters analogous to lunch_fade NDX.

If lesson #48 is wrong (or the EU basis-arb mechanism is too weak / too efficient), this fails decisively — and that's a strong negative-result corroboration of lunch_fade's specificity to the NDX/NQ pair.

## Mechanism vs lunch_fade NDX

| Property | NDX lunch_fade | FDAX lunch_fade (this) |
|---|---|---|
| Institutional vacuum hours | 11:30-13:30 ET | 12:00-13:30 CET (3.5h earlier UTC-wise) |
| Concurrent flow | Asia closed, EU closing | Asia closed, US not yet open |
| Cash venue | NYSE/Nasdaq diffuse | Xetra single-venue |
| Futures venue | NQ (CME) | FDAX (Eurex) |
| Basis-arb depth | Very deep (NQ is the world's #2 index future) | Deep (FDAX is Eurex's flagship) |
| Currency | USD | EUR (no FX leg for euro accounts) |
| Holdout regime (2023-26) | Best regime — mechanism INTENSIFIED post-2022 | unknown — Phase 2 will tell |

## Universe

GER40 CFD (Eightcap, M5 data already on disk from `orb_dax`). Backtest range 2019-01 → 2026-05.

## Signal math (baseline — direct port of lunch_fade NDX with CET timing)

```
Session: 09:00-17:30 CET (Xetra cash session)
  -> minute-of-session = 0 at first M5 bar of day
  -> 180 min = 12:00 CET (morning measurement end)
  -> 270 min = 13:30 CET (afternoon exit)

MORNING_END_MIN       = 180   (= 12:00 CET; morning move = open -> 12:00 close)
AFTERNOON_END_MIN     = 270   (= 13:30 CET; exit at 13:30 close)
MIN_MOVE_ATR          = 0.25  (start with NDX-deployed thr; sweep 0.10-0.50)
COST_POINTS_ROUND_TRIP = 1.0  (GER40 CFD typical retail spread; matches orb_dax)
direction             = "fade"
ATR_LOOKBACK_DAYS     = 20

Per day:
  open_px           = first M5 OPEN of session (~09:00 CET)
  morning_end_px    = M5 close at minute-of-session = 180
  r_morning         = morning_end_px / open_px - 1.0
  daily_vol         = mean(abs(bar_returns)) for the day
  atr_proxy         = rolling 20d mean of daily_vol
  threshold         = MIN_MOVE_ATR * atr_proxy * morning_bars
  if abs(r_morning) < threshold: skip
  position          = -sign(r_morning)   # FADE
  entry             = open of next M5 bar after morning_end
  exit              = M5 close at minute-of-session = 270
```

## Why retail-accessible

- Data on disk (GER40 M5 from existing orb_dax pipeline)
- Eightcap GER40 CFD spread typical 0.5-1pt (~2-4 bp on ~24000 level) — comfortably below the cost-zero threshold
- EUR-denominated → no FX leg for the user's EUR account
- Same VPS / EA infrastructure as the existing trio

## Expected performance

If lesson #48 generalization holds:
- Sharpe in the range of lunch_fade NDX (+0.89 symmetric / +1.02 LONG-only / +1.51 holdout LONG)
- Trade cadence comparable (~28 symmetric / 16 LONG-only per year on NDX → expect similar on FDAX/GER40 given comparable index vol)
- Cost-insensitive (per-trade gross 70-80 bp ≫ retail spread)

If lesson #48 doesn't generalize:
- Sharpe < +0.20 or sign-inverted (continuation wins)
- Would refute the basis-arb mechanism interpretation, suggesting the NDX-specific outcome is microstructure rather than EU-Eurex-analog

## Fail conditions (pre-committed)

### Phase 2

- Full-sample Sharpe < +0.30 after 1pt RT cost
- Max DD > 25%
- Trade count < 200 over the data window
- WR < 45% AND PF < 1.1
- Direction null-check fade-gap < +0.30 (kill if mirror beats baseline by >0.30 → INVERTED scenario, lesson #43)

### Phase 4 regime

- ≤ 1 of 3 regimes (2019-2020 / 2021-2022 / 2023-2026) positive

### Phase 6 holdout binding

- 2023-2026 holdout Sharpe ≤ 0 (per lesson #25 — modern regime is the deploy-relevant window for any post-2022 microstructure mechanism)

## Why this might fail

1. **EU basis-arb HFT depth is shallower than US**. NDX/NQ basis-arb has the deepest HFT participation of any global index pair. FDAX/cash-DAX may not have the same density of HFT flow during the lunch vacuum → mechanism too weak to extract edge after cost.

2. **Berlin lunch ≠ NY lunch by venue dynamics**. NY 11:30-13:30 ET is the simultaneous lunch + EU close, two distinct flow-removals. Berlin 12:00-13:30 CET is one flow-removal (EU lunch only) — the US-pre-open silence is a *separate* dynamic that may not produce the same MR pressure.

3. **Xetra's single-venue concentrated open is the dominant flow event of the day on DAX**. The lunch window is small noise relative to the 09:00 auction (per orb_dax mechanism). Whatever signal exists at 12:00-13:30 may be dominated by morning-trend persistence rather than reversal.

4. **DAX direction has STRUCTURAL UP-drift post-2019** (lesson from orb_dax LONG-only deploy). Fading DAX morning moves means systematic up-gap-shorts in a drifting-up market — adverse selection risk.

5. **0DTE-options arb on DAX is weaker** than on US indices. The lunch_fade NDX mechanism may benefit from 0DTE gamma flow dynamics that don't exist for FDAX (DAX options OI is concentrated in monthly/quarterly expiries, not zero-day).

## Phase 1 → 2 plan

- [x] Data on disk (GER40 M5 from orb_dax pipeline)
- [ ] **Phase 2a — direct adaptation** of `lunch_fade_demo.py` with GER40 + CET session + 180/270 morning/afternoon windows
- [ ] **Phase 2b — kill-criteria check + regime breakdown + null-check (continuation direction)**
- [ ] **Phase 2c — variant sweeps** on MIN_MOVE_ATR (0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50) and morning-end / afternoon-end shifts (±30min)
- [ ] **Phase 2d — LONG/SHORT split** (lunch_fade NDX deployed LONG-only because shorts were drag; may be the same on GER40)
- [ ] **Phase 6 — walk-forward** (3 rolling splits, 3y-IS / 1.5y-OOS)

## Files

- Thesis: this file
- Demo: `fdax_lunch_fade_demo.py` (next)
