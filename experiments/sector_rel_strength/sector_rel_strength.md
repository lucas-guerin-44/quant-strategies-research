# Sector-internal relative-strength rotation (24-name universe)

**Status**: Phase 2 + mirror-validation + extended-universe validation complete (2026-05-22).

**Verdict**: **REJECT.** Pre-committed direction (momentum) fails decisively. Mirror direction (mean reversion) initially looked alive on 24-name universe (Sh +0.43, walk-forward mean OOS +1.09) but **fails decisively on 100-name extended universe** — Sh drops to +0.24, walk-forward 5/5 tested cells FAIL with mean OOS range -0.49 to +0.04. The 24-name result was a small-sample artifact. Universe extension did its job — caught the overfit before deploy.

## Phase 2 results

### Baseline (long-top short-bottom; lookback=5d, K=5, hold=5d, cost=4 bp RT)

| Metric | Value | vs threshold |
|---|---|---|
| Period | 2021-09 → 2026-05 (4.7y) | — |
| Sharpe | **-0.74** | **FAIL** |
| MDD | -74.83% | FAIL |
| CAGR | -22.91% | — |
| Trade days | 1,174 (251/yr) | PASS |

### Direction null-check — INVERTED decisively

| Direction | Sharpe | CAGR | MDD |
|---|---|---|---|
| Long-top / short-bottom (baseline) | -0.74 | -22.9% | -74.8% |
| Long-bottom / short-top (null = mean reversion) | **+0.53** | **+12.0%** | -52.4% |

**Direction-gap = -1.02.** Pre-committed kill (gap < +0.20) triggered. **The 5-day single-stock signal is mean-reverting on US large-caps 2021-2026, not momentum.** Consistent with Jegadeesh (1990) and Lehmann (1990) short-horizon-reversal literature; appears to have strengthened post-2020.

### Regime breakdown — baseline

| Window | n | Sharpe | CAGR | MDD |
|---|---|---|---|---|
| 2018-2020 pre/COVID | 511 | 0.00 | 0.0% | 0.0% (data warmup) |
| 2021-2022 vol | 481 | -1.00 | -25.8% | -56.7% |
| **2023-2026 holdout** | **847** | **-0.54** | **-17.5%** | **-64.3%** |

Holdout is worst — momentum direction has accelerated its decay post-2022. 0/2 available regimes positive.

### Lookback sweep — only 90-day classical horizon shows mild momentum

| Lookback | Sharpe | CAGR | MDD |
|---|---|---|---|
| 3 | -0.66 | -14.4% | -74.7% |
| 5 | -0.59 | -13.5% | -74.8% |
| 10 | -0.24 | -6.8% | -54.8% |
| 20 | -0.45 | -10.8% | -68.3% |
| 60 | -0.30 | -8.2% | -56.7% |
| **90** | **+0.19** | **+1.6%** | -43.3% |

Only the 90-day (classical Jegadeesh-Titman 3-month) lookback shows positive Sharpe in the momentum direction — but only +0.19, well below the +0.30 floor.

### Hold-period sweep (lookback=5d)

| Hold (days) | Sharpe |
|---|---|
| 1 | +0.14 |
| 3 | -0.34 |
| 5 | -0.59 |
| 10 | -0.46 |
| 20 | -0.07 |

Daily rebalance shows mild positive Sharpe (+0.14) — short-horizon momentum has a tiny 1-day flicker, swamped by friction. Above 1-day hold, momentum reverses.

### 2D heatmap — lookback × hold (baseline direction, Sharpe)

```
                    h=1       h=3       h=5      h=10      h=20
        lb=3     -0.05     +0.28     -0.66     -0.55     +0.27 
        lb=5     +0.14     -0.34     -0.59     -0.46     -0.07 
       lb=10     -0.24     -0.21     -0.24     +0.03     +0.35 
       lb=20     -0.30     -0.30     -0.45     -0.25     -0.03 
       lb=60     -0.08     -0.05     -0.30     -0.20     -0.22 
```

Best cells in momentum direction: lb=10 h=20 (+0.35), lb=3 h=3 (+0.28). Both isolated; not a smooth knee. Not a robust signal.

**In the mirror (mean-reversion) direction**, the same heatmap inverted has multiple cells at +0.4 to +0.6 — a structural pattern, not a cherry-pick.

### Cost sensitivity (baseline direction)

| Cost (bp RT) | Sharpe |
|---|---|
| 0 | -0.51 |
| 4 | -0.59 |
| 15 | -0.82 |

Cost-zero **still -0.51** — signal-not-friction failure on the momentum direction (lesson #26 diagnostic).

## Verdict reasoning

- Phase 2 Sharpe > +0.30: **FAIL** (-0.74)
- MDD < 25%: **FAIL** (-75%)
- Direction null-gap ≥ +0.20: **FAIL, INVERTED -1.02**
- Phase 6 holdout > 0: **FAIL** (-0.54)
- Phase 4 regimes positive: **FAIL** (0/2 available)

5-of-5 fail. **REJECT.** No deploy candidate from the pre-committed direction.

## What we learned

1. **Short-term single-stock momentum is dead on US large-caps post-2021.** Consistent with the academic decay literature (Jegadeesh-Titman half-life). Holds across lookback × hold parameter space; only 90d / classical-J-T window shows even +0.19.
2. **The mirror — short-horizon mean reversion — is alive at the same parameters** (Sh +0.53 at lb=5/K=5/h=5). This is a different mechanism family entirely: liquidity-provision premium / overreaction reversal at single-stock level. Same direction as `lunch_fade` and `bb_reversion` — but those are intraday and on indices; this is D1 cross-sectional and on single-stocks.
3. **The 24-name universe is small but sufficient to falsify the momentum direction decisively** (-1.02 gap). For a deployable mean-reversion sub-thesis, extension to 100-200 names would be necessary to get statistical power on top/bottom-K baskets.

## Mirror-direction validation (`_mirror_validation.py`, 2026-05-22)

The mirror direction (long-bottom / short-top, i.e. 5-day mean reversion) was the natural follow-up. Lesson #43 says we measured both directions co-equally already; lesson #20 says don't promote winning sub-variants without fresh validation. Running the binding tests the momentum direction failed.

### Parameter robustness (mirror direction, cost=4 bp RT)

| Lookback | Hold | K | Sharpe | CAGR | MDD |
|---|---|---|---|---|---|
| 3 | 5 | 5 | +0.49 | +7.8% | -45.9% |
| **5** | **5** | **5** | **+0.43** | **+6.5%** | **-52.4%** |
| 10 | 5 | 5 | +0.11 | +0.0% | -51.8% |
| 3 | 3 | 5 | -0.56 | -12.7% | -72.5% |
| 5 | 1 | 5 | -0.53 | -12.2% | -76.5% |
| 5 | 5 | 3 | +0.35 | +5.4% | -71.3% |
| 5 | 5 | 8 | +0.38 | +4.5% | -44.2% |

**Hold-period is structurally required**: h=1 and h=3 fail, h=5 is the sweet spot. The mean-reversion mechanism needs ~5 days to play out — daily rebalance destroys it via cost.

### Walk-forward at 3 cells (Phase 6 binding test)

| Cell (lb/h/K) | IS-1 / OOS-1 | IS-2 / OOS-2 | IS-3 / OOS-3 | Mean OOS | Min OOS | Verdict |
|---|---|---|---|---|---|---|
| **5/5/5 (lead)** | +0.17 / **+1.16** | -0.11 / **+1.77** | +0.32 / +0.34 | **+1.09** | **+0.34** | **PASS** |
| 3/5/5 | +0.60 / +0.64 | -0.08 / +0.91 | +0.95 / +0.13 | +0.56 | +0.13 | PASS |
| 10/5/5 | +0.08 / +0.25 | -0.51 / +1.32 | -0.19 / +0.13 | +0.57 | +0.13 | PASS |

All three cells pass mean-OOS ≥ +0.20 AND min-OOS ≥ 0. Lead cell mean OOS **+1.09** is 5× the floor. The OOS lift over IS is consistent across cells (IS is often negative; OOS is strongly positive) — this is the *holdout-best* signature from lesson #25, the strongest deploy-direction signal in the framework.

### Regime breakdown — lead cell (lb=5, h=5, K=5)

| Window | n | Sharpe | CAGR | MDD |
|---|---|---|---|---|
| 2018-2020 pre/COVID | 511 | 0.00 | 0.0% | 0.0% (warmup) |
| 2021-2022 vol | 481 | **+0.84** | +20.7% | -19.4% |
| **2023-2026 holdout** | 847 | **+0.32** | +5.2% | -44.1% |

2/2 available regimes positive. Holdout decays from 2021-22 peak (consistent with mechanism crowding) but stays well above 0.

### Sector neutrality — NOT a covert "long banks 2022" trade

Total days on each sector per side:

| Sector | LONG | SHORT | Net | % skew |
|---|---|---|---|---|
| tech | 2813 | 2946 | -133 | -2.3% |
| fin | 887 | 931 | -44 | -2.4% |
| health | 575 | 552 | +23 | +2.0% |
| staples | 503 | 390 | +113 | +12.7% (mild long-bias) |
| discret | 560 | 508 | +52 | +4.9% |
| energy | 519 | 529 | -10 | -1.0% |

**No sector has >12% net skew** across 4.7y. Staples slightly long-tilt (KO/PEP weakness 2024-2025 → fade pattern), but this is mechanically reasonable and not load-bearing. The strategy IS cross-sectional MR, not a sector-beta trade.

### Per-ticker top contributors (lb=5, h=5, K=5)

Largest positive contributions to total PnL:
- GOOGL-SHORT +106.6% (GOOGL is over-bought frequently → faded)
- NVDA-LONG +105.1% (NVDA over-sold occasionally → bought)
- XOM-LONG +96.0%
- TSLA-LONG +89.0%
- AVGO-LONG +69.8%
- ORCL-LONG +67.2%
- CRM-SHORT +51.5%
- META-LONG +51.3%

**Diversified**: top single-name contribution (GOOGL-SHORT) is ~12% of total +874% gross — no single name carries the result. 26 of 30 top-30 contributions are positive.

### Cost sensitivity (mirror)

| Cost (bp RT) | Sharpe | CAGR |
|---|---|---|
| 0 | +0.51 | +8.4% |
| 2 | +0.47 | +7.4% |
| 4 | +0.43 | +6.5% |
| 8 | +0.34 | +4.7% |
| 15 | +0.19 | +1.6% |

Linear decay ~0.02 Sharpe per bp. Robust to retail-CFD friction.

## Updated verdict

- **Pre-committed direction (momentum)**: REJECT decisively (Sh -0.74, dir-gap -1.02 INVERTED).
- **Mirror direction (mean-reversion)**: passes ALL the binding tests the pre-commit would have required:
  - Phase 2 Sharpe +0.43 at 4 bp (above +0.30 floor)
  - Direction null-gap +1.02 (above +0.20 floor) — measured co-equally per lesson #43
  - Phase 4 2/2 available regimes positive
  - Phase 6 holdout +0.32 (above 0)
  - Walk-forward: 3/3 tested cells PASS mean OOS ≥ +0.20 AND min OOS ≥ 0; lead cell mean OOS +1.09
  - Sector-neutrality + per-ticker diversification confirmed
  - Cost-insensitive
- **MDD -52%** remains the only soft fail vs the +25% pre-commit. Position-sizing layer (vol-target + portfolio stop-out) would mitigate at the cost of ~30-40% of CAGR — standard risk-control problem.

## Extended-universe validation (`_extended_validation.py`, 2026-05-22)

To test whether the 24-name mirror finding was real signal or small-sample overfit, the universe was extended via `_universe_extension.py` (77 additional S&P 100-style large-caps backfilled from MT5 to the datalake; 100 total names after dropping BRK.A which the datalake rejects due to dot-in-name validation).

### Baseline mirror (lb=5, h=5, K=20 — same 20% top/bottom concentration as 24-name K=5)

| Metric | 24 names | 100 names | Delta |
|---|---|---|---|
| Sharpe | +0.43 | **+0.24** | -0.19 |
| MDD | -52.4% | -24.6% | +27.8 (better) |
| CAGR | +6.5% | +2.4% | -4.1% |
| Holdout (2023-26) Sh | +0.32 | **-0.01** | -0.33 |

Lead-cell Sharpe degraded 44%. **Holdout is no longer positive** — the regime that was the deploy-binding test is now zero.

### K sweep (lb=5, h=5, 100 names)

| K | Sharpe | CAGR | MDD |
|---|---|---|---|
| 5 | +0.15 | +0.1% | -54.9% |
| 10 | +0.24 | +2.5% | -30.4% |
| **15** | **+0.30** | +3.5% | -24.2% |
| 20 | +0.24 | +2.4% | -24.6% |
| 25 | +0.08 | +0.1% | -28.3% |
| 30 | +0.16 | +1.1% | -25.7% |
| 40 | +0.22 | +1.7% | -17.4% |

K=15 is the best cell (Sh +0.30) — barely meets the +0.30 Phase 2 floor and degrades immediately on either side.

### Lookback sweep (100 names, h=5, K=20)

| Lookback | Sharpe | CAGR | MDD |
|---|---|---|---|
| 3 | **+0.60** | +7.9% | -31.0% |
| 5 | +0.24 | +2.4% | -24.6% |
| 10 | -0.07 | -2.3% | -35.1% |
| 20 | +0.10 | +0.2% | -33.2% |
| 60 | +0.09 | +0.0% | -27.8% |
| 90 | -0.19 | -4.6% | -43.5% |

lb=3 cell shows Sh +0.60 — but walk-forward at this cell fails (see below).

### Walk-forward — ALL 5 tested cells FAIL on 100-name extension

| Cell (lb/h/K) | IS-1 / OOS-1 | IS-2 / OOS-2 | IS-3 / OOS-3 | Mean OOS | Min OOS | Verdict |
|---|---|---|---|---|---|---|
| 5/5/20 (lead) | +0.60 / **-0.24** | +0.28 / **-0.80** | +0.55 / +0.42 | **-0.21** | -0.80 | **FAIL** |
| 3/5/20 | +1.31 / -0.33 | +0.77 / -0.34 | +1.08 / +0.80 | +0.04 | -0.34 | FAIL |
| 10/5/20 | +0.08 / -0.38 | +0.33 / -1.43 | -0.56 / +1.02 | -0.26 | -1.43 | FAIL |
| 5/5/15 | +0.74 / -0.28 | +0.24 / -0.79 | +0.73 / +0.40 | -0.22 | -0.79 | FAIL |
| 5/5/25 | +0.47 / -0.53 | +0.06 / -1.04 | +0.48 / +0.11 | -0.49 | -1.04 | FAIL |

**Every cell**: strong IS Sharpe (+0.06 to +1.31), negative OOS Sharpe (-0.24 to -1.43). The 24-name walk-forward mean OOS +1.09 has **collapsed to -0.21 on the lead cell** when the universe expands 4x. Classic small-sample-overfit signature: signal exists in IS, disappears in OOS, magnitude inversely correlated with universe size.

### Direction null still positive but weakened

| Direction (100 names) | Sharpe | MDD |
|---|---|---|
| Mirror (mean reversion) | +0.24 | -24.6% |
| Momentum (null) | -0.46 | -61.7% |

Direction-gap +0.70 (was +1.02 on 24 names). Some real signal exists, but it's been diluted to barely tradeable.

### Cost sensitivity (100 names, lead cell)

| Cost | Sharpe |
|---|---|
| 0 bp | +0.35 |
| 4 bp | +0.24 |
| 15 bp | -0.06 |

Cost-zero +0.35 — modest gross signal; friction-binding at 8-15 bp.

## Final verdict reasoning

Pre-committed kill criteria, against the 100-name extended universe:

| Criterion | Floor | Observed | Verdict |
|---|---|---|---|
| Phase 2 Sharpe | +0.30 | +0.24 (lead) / +0.30 (K=15 best) | MARGINAL |
| MDD | < 25% | -24.6% (lead) | PASS (barely) |
| Direction-gap | +0.30 | +0.70 | PASS |
| Phase 4 regimes | both available positive | 2021-22 +0.79 / **2023-26 -0.01** | **FAIL** |
| Walk-forward mean OOS | +0.20 | **-0.21** (lead), all cells fail | **FAIL** |

3-of-5 PASS, 2 binding-FAIL. The walk-forward failure is decisive — on the extended universe, IS-trained models lose money OOS.

**Honest conclusion**: the 24-name mirror finding (walk-forward mean OOS +1.09) was a **small-sample artifact**. Extending to 100 names refutes it. The mechanism direction is real (dir-gap +0.70) but the EDGE has been mostly arbed away on the broader large-cap universe. The 24-name version got an inflated walk-forward result because the small basket happened to contain a few names with strong post-2022 reversion (NVDA, GOOGL, TSLA, CRM) that don't generalize to the broader universe.

This is an excellent example of why **universe extension is a binding robustness check** on any cross-sectional D1 strategy. Per lesson #20 corollary — a winning sub-variant on a small universe is exactly the canonical overfit pattern.

## Pivot candidates: NOT pursued

Three theoretical paths remain, none recommended:
1. **Top-9 info-rich sub-basket** (CRM/MA/GS/JPM/HD/XOM/LOW/KO/AAPL) — promotes the winners post-hoc; would not survive the same universe-extension robustness test.
2. **K=15 (cell that barely meets +0.30)** — single-cell pass with no headroom; the 100-name validation shows the K-sweep peak isn't structural.
3. **Add 100 more names** — diminishing returns; if 100 doesn't work, 200 won't suddenly resurrect the signal.

## Files

- Thesis: this file.
- Demo: `sector_rel_strength_demo.py`
- 24-name mirror validation: `_mirror_validation.py`
- Universe extension (77 stocks backfilled to datalake): `_universe_extension.py` + `_repush_to_datalake.py`
- Extended-universe validation: `_extended_validation.py`
- Universe file: `extended_universe.txt` (100 names; BRK.A dropped due to datalake name-validation)

## Files

- Thesis: this file.
- Demo: `sector_rel_strength_demo.py`

---

## Thesis

Sector-internal momentum on US large-caps: daily rank the 24-name universe by trailing N-day return, long the top-K, short the bottom-K, periodic rebalance. Different from `xs_momentum` (24-instrument multi-asset, monthly rebalance, top-5 long-only equity-CFDs+commodities+FX) in three load-bearing ways:

1. **Sector-internal** (all US large-cap equity), not multi-asset → tests pure within-sector dispersion alpha, not asset-class momentum
2. **Higher frequency** (daily/weekly rebalance vs xs_momentum's quarterly) → captures shorter-horizon flow rotation, not slow fundamental drift
3. **Long-short** (not long-only) → designed to be market-neutral via beta-1 dollar offset

Mechanism (consensus across momentum literature):
- **Jegadeesh & Titman (1993)** — single-stock momentum over 3-12 month horizons, monthly rebalance: Sh ~0.5-0.7 pre-1990s, much-decayed post-2000.
- **Daniel & Moskowitz (2016)** — momentum crashes during bear-market V-recoveries.
- **Asness et al (2013, 2019)** — momentum still works but signal-to-noise is poor at horizons < 1 month for equities specifically.
- **Recent (2020+)** — single-stock momentum has weakened further on US large-caps but shows signs of life on shorter horizons (1-5 day) in specific sectors. Open question whether this is real or 0DTE-microstructure noise.

The 24-name universe is small (statistical power borderline), so this is a **framework-validation experiment** — if the signal exists at all, we'd extend to 100-200 names via additional MT5 backfills.

## Universe

24 names already on disk: AAPL MSFT GOOGL AMZN META NVDA TSLA JPM BAC GS V MA UNH WMT HD LOW KO PEP JNJ XOM CVX ORCL CRM AVGO.

## Signal math (baseline)

```
On each rebalance day:
  For each ticker, compute trailing N-day return (default 5d).
  Rank tickers descending.
  long_basket  = top K (default 5)    equal-weight, each 1/K of long sleeve
  short_basket = bottom K              equal-weight short
  Dollar-balance long sleeve = short sleeve (market-neutral by gross dollar)
  Hold for HOLD_DAYS days (default 5, weekly rebalance).
  Daily PnL = mean(long_basket daily returns) - mean(short_basket daily returns)
  Cost: 4 bps RT × (turnover / horizon) ≈ ~1 bp/day at K=5 + weekly rebal

Parameters to sweep:
  N = 3, 5, 10, 20 (lookback)
  K = 3, 5, 8 (basket size)
  HOLD_DAYS = 1, 5, 10 (rebalance frequency)
```

## Why retail-accessible

- D1 data on disk (computed from M5 close last bar per day).
- Long/short on stock CFDs available at Eightcap. Short borrow cost ~2-4 bp/day; long swap ~1.5 bp/day; net carry per overnight ~3-5 bp combined (modeled in cost-sensitivity).
- 5-day-rebalance with K=5 implies ~5 names rotated per week × 2 sides = 10 round-trip trades/week.

## Expected performance

This is genuinely uncertain. Literature is split:
- If signal exists on US large-caps at 1-2 week horizon: Sh +0.3 to +0.7 net of costs.
- If signal is gone (most likely): Sh -0.2 to +0.2.

**Pre-Phase-2 expected**: research Sharpe +0.2 to +0.5 if mechanism is alive; tighter pre-commits than usual because this is a low-conviction probe.

## Fail conditions (pre-committed)

### Phase 2

- Best variant Sharpe < +0.30 after cost.
- MDD > 25%.
- Trade-day count < 250.
- Direction null-gap (long-top - short-top variant) < +0.20.

### Phase 4 regime

- ≤ 1/3 regimes positive (2019-2020 / 2021-2022 / 2023-2026).

### Phase 6 holdout binding

- 2023-2026 holdout Sharpe ≤ 0.

## Why this might fail

1. **Equity momentum has been arbed away post-2000** — Jegadeesh-Titman half-life. Most rigorous studies on US single-stock momentum 2010+ show flat-to-negative net Sharpe.
2. **24-name universe is too small** for meaningful dispersion — top-3 / bottom-3 = 25% of basket, way more concentrated than a 100-name SP500 ranking.
3. **Sector concentration in universe** — 7 Mag7 (tech), 3 banks, 2 staples, 2 energy, etc. Cross-sector momentum dominates within-sector ranking; banks during 2022 bear all rank low together → short basket overweight banks → losing momentum is sector-beta exposure, not idiosyncratic.
4. **Daniel-Moskowitz momentum crashes** at V-recovery points: COVID-2020 March-April, 2022-Q4 bottom. Single-stock momentum crashed -50% in 2009 and similar magnitudes in 2020.
5. **Daily/weekly rebalance + 4 bp RT cost** is friction-heavy. Even if gross signal exists, cost may eat it.

## Files

- Thesis: this file.
- Demo: `sector_rel_strength_demo.py`
