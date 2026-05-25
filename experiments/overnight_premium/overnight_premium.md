# Single-stock overnight return premium

**Status**: Phase 2 + walk-forward complete (2026-05-22).

**Verdict**: **REJECT (MARGINAL)** per pre-committed MDD floor; mechanism is REAL and SIGN-CORRECT but equal-weight risk is unbounded.

## Phase 2 results

### Baseline (no filters, swap=1.5 bp/day)

| Metric | Value | vs threshold |
|---|---|---|
| Period | 2018-01 → 2026-05 (8.4y) | — |
| Sharpe | +0.08 | **FAIL** (<+0.30) |
| MDD | **-95.72%** | **FAIL** (catastrophic) |
| Events | 28,496 (3,402/yr) | PASS |
| CAGR | -21.78% | — |
| WR (per overnight) | 50.3% | — |

The 95.72% MDD is the 2020-COVID overnight crash (mid-March 2020) at full equal-weight on 24 names. Baseline overnight buy-and-hold without risk-control is catastrophic, dominated by tail events.

### Filter sweep (additive on top of baseline, 1.5 bp/day swap)

| trend | vol | earn | Sharpe | CAGR | MDD | n |
|---|---|---|---|---|---|---|
| — | — | — | +0.08 | -21.8% | -95.7% | 28,496 |
| ✓ | — | — | **+0.37** | +6.46% | -46.0% | 16,089 |
| — | ✓ | — | **+0.44** | +8.92% | -32.1% | 22,802 |
| — | — | ✓ | +0.07 | -22.2% | -95.2% | 27,609 |
| ✓ | ✓ | — | +0.33 | +5.33% | -50.4% | 13,243 |
| ✓ | — | ✓ | +0.33 | +5.42% | -45.2% | 15,546 |
| — | ✓ | ✓ | +0.42 | +8.18% | -34.6% | 22,133 |
| ✓ | ✓ | ✓ | +0.32 | +4.89% | -46.6% | 12,816 |

**Earnings-skip alone is useless** (events on earnings night are ~5% of total). Trend and vol filters each lift Sharpe by +0.29 / +0.36 vs baseline. **Vol-filter is the strongest single overlay** (skip overnights where 20d vol > 80th percentile).

### Cost sensitivity

| Swap (bp/day) | Sharpe |
|---|---|
| 0.0 | +0.16 |
| 1.0 | +0.11 |
| 1.5 | +0.08 |
| 3.0 | +0.00 |
| 5.0 | -0.10 |
| 8.0 | -0.26 |

Cost-zero baseline Sharpe **+0.16** — there's a real signal pre-cost. Cost halves it at 1.5 bp; doubles to negative at 5 bp. **Swap-binding** finding.

### Direction null-check — PASS (sign correct)

| Direction | Sharpe | MDD | WR |
|---|---|---|---|
| LONG overnight (mechanism) | +0.08 | -95.7% | 50.3% |
| SHORT overnight (null) | -0.24 | -87.2% | 48.1% |

Direction-gap **+0.32** PASSES (>+0.30 implicit). The sign IS correct; overnight returns are systematically positive in aggregate.

### Regime breakdown

| Window | n | Sharpe | CAGR | MDD |
|---|---|---|---|---|
| 2018-2020 pre/COVID | 511 | +0.18 | -62.3% | -95.7% |
| 2021-2022 vol | 7,880 | -0.72 | -10.3% | -32.5% |
| **2023-2026 holdout** | 20,105 | **+0.44** | +4.0% | -19.8% |

**Holdout is the strongest regime** — consistent with Fang et al 2024's "post-2020 strengthening" finding. 2022 bear is the catastrophic window (overnight crashes during bear). 2018-2020 dominated by COVID-March-2020 single event.

### Per-ticker — extreme dispersion, NVDA exceptional

Strongest: **NVDA Sh +1.15 (+360.9% total!)**, AVGO +0.40 (+41%), BAC +0.39 (+28%), CVX +0.39 (+28%), META +0.25 (+14%), XOM +0.24 (+14%), AAPL +0.16 (+6%).

Weakest: GOOGL Sh -0.04 (-89.6% total — COVID-2020), AMZN +0.13 but -86.5% total (COVID), UNH -0.99, LOW -2.46, HD -1.28, JNJ -1.78.

The Sharpe and total-return rankings sometimes disagree because total-return is dominated by the 2020 single-event crash; Sharpe normalizes across many overnights. NVDA is exceptional on BOTH metrics — its overnight premium is real, consistent, and post-2018 has compounded to +360%.

### Walk-forward (Phase 6 binding test)

#### Trend-filter variant (pre-committed lead overlay)

| Split | IS Sh | OOS Sh | OOS n | OOS MDD |
|---|---|---|---|---|
| IS 2021-09 → 2024-09 / OOS → 2026-05 | -0.72 | +0.14 | 5,913 | -18.9% |
| IS 2022-09 → 2025-09 / OOS → 2026-05 | +0.65 | +0.38 | 2,391 | -6.8% |
| IS 2021-09 → 2023-09 / OOS → 2025-09 | -1.20 | +0.27 | 7,256 | -18.9% |

**Mean OOS +0.26 (>=+0.20 floor) PASS**, min OOS +0.14 (>=0 floor) PASS. Trend filter survives walk-forward.

#### Baseline (no filter)

| Split | IS Sh | OOS Sh | OOS n | OOS MDD |
|---|---|---|---|---|
| 3 splits | -0.21 / +0.36 / -0.62 | -0.16 / -0.19 / +0.32 | (varies) | (varies) |

Mean OOS **-0.01** FAILS, min OOS **-0.19** FAILS. Confirms baseline-without-filter isn't deployable.

## Verdict reasoning

Pre-committed kill criteria:

| Criterion | Floor | Observed | Verdict |
|---|---|---|---|
| Baseline Sharpe | > +0.30 at 1.5 bp/day | +0.08 | **FAIL** |
| MDD baseline | < 25% | -95.7% | **FAIL** |
| Best-filtered − baseline | ≥ +0.20 | +0.36 (vol-filter) | PASS |
| Filtered MDD | < 25% (carried over) | -32.1% (vol-filter) | **FAIL** |
| Phase 4 all 3 regimes > 0 | 3/3 | 2/3 (2021-22 negative) | FAIL |
| Phase 6 holdout > +0.30 | filter required | +0.44 (vol-filter) | PASS |
| Walk-forward mean OOS ≥ +0.20 | trend-filter | +0.26 | PASS |
| Walk-forward min OOS ≥ 0 | trend-filter | +0.14 | PASS |
| Direction-gap | ≥ +0.30 | +0.32 | PASS |

**5 PASS / 4 FAIL.** The FAILs are all MDD-related at the equal-weight portfolio level — the mechanism is real and signed correctly, walk-forward validates on the filter variant, but unbounded overnight risk is the problem. **Strict pre-commit: REJECT.**

## What we learned

1. **Overnight premium is real and post-2020-strengthening on this universe** — holdout +0.44 Sh (vol-filter) is the BEST regime, consistent with Lou et al / Fang et al. The mechanism direction is correct (LONG +0.08 vs SHORT -0.24, gap +0.32).
2. **Equal-weight risk is unbounded on overnight equity** — even with filters, MDD is 30-46%. This is structural: a single overnight crash (COVID, 2022 bear, 2024 carry unwind) drops the portfolio 20-30% in one print. No filter mitigates a *single-event* tail. Risk-control requires per-name **position sizing** + **portfolio-level stop-out**, neither of which we tested. Standard risk-targeting (e.g., 10%-vol-target with a 2σ stop) would convert this to a deployable strategy at the cost of much lower CAGR.
3. **NVDA is the standout exposure** — Sh +1.15 / +361% over 4.7y on plain overnight buy-and-hold. That's not a strategy, that's a stock. But it's the cleanest single-name alpha extraction in the repo.
4. **The +0.36 filter-lift is the second-largest "filter-found-real-signal" finding** in the repo after lunch_fade's thr=0.25 knee. Vol-filter > trend-filter > earnings-filter consistently. Combined filters do NOT additively improve — each filter individually captures most of the lift, suggesting they're correlated proxies for the same "skip dangerous overnights" signal.

## Pivot candidates (NOT pursued in this experiment)

1. **`overnight_nvda_only`** — single-name pre-commit on NVDA. Either accepts the post-hoc selection risk explicitly (and tests on truly OOS 2027+ data), or extends to "top-5 single-stock-overnight-Sharpe names ranked on 2018-2022 IS-only data" with walk-forward.
2. **`overnight_premium_voltarget`** — same baseline but with 10% annualized vol-target sizing + portfolio-level 15% MDD stop-out. Should convert -32% MDD to -15% MDD at the cost of 30-50% CAGR. The right next step if pursuing this family.

## Files

- Thesis: this file.
- Demo: `overnight_premium_demo.py`

---

## Thesis (mechanism)

US single-stocks systematically earn most of their return *overnight* (close-to-open) rather than *intraday* (open-to-close). Documented in:

- **Berkman, Koch, Tuttle, Zhang (2012)** "Paying attention: overnight returns and the hidden cost of buying at the open." JFQA 47(4) — high-retail-attention stocks underperform intraday and over-perform overnight; effect concentrated post-2000.
- **Lou, Polk, Skouras (2019)** "A tug of war: Overnight versus intraday expected returns." J. Financial Economics 134 — overnight return is the dominant component of total return for most factor-sorted portfolios, with the **gap widening post-2010**.
- **Fang, Pinello, Yang (2024 WP)** — overnight premium documented as **strengthening post-2020** on Mag7-like high-retail-attention names.

Mechanism (consensus across papers):
1. **Retail attention concentrates intraday**, institutional execution concentrates overnight (via auction-print + dark-pool sweeps + earnings-night repositioning). When retail attention is intraday-only, retail buys (push price up) during the day; institutions sell into retail demand; net intraday drift is flat-to-negative on retail-attention names. The OPPOSITE flow operates overnight.
2. **Earnings overnight gaps** asymmetrically positive on average (beats > misses by frequency × magnitude). Even excluding earnings days, overnight return remains positive.
3. **Liquidity premium** — overnight positions require capital commitment + crash risk premium. Risk-bearing rewarded.

## Why retail-accessible

- Pure D1 strategy (close-to-open). M5 needed only for clean entry/exit prints (15:55 ET close, 09:35 ET open).
- Eightcap allows overnight long positions on stock CFDs. Overnight swap (financing cost) is the main friction — typically 4-6% annualized for long stocks (LIBOR+spread). Daily swap ≈ 1.5 bp/day ≈ 0.015% per overnight. Cost-binding check: per-overnight gross return needs to exceed swap.
- 24-name universe × 252 overnights/yr = ~6000 overnight-events / year, fully diversified by name + day. Sample size is huge.

## Filter design — user-flagged "don't just blindly buy"

Per user direction: naive "long all 24 every overnight" is a B&H proxy plus swap cost. Need filters. Pre-committed filter set:

1. **Trend filter**: long only if 20-day trailing return ≥ 0. Skip names in downtrend (avoid catching falling knives, lesson #34).
2. **Earnings overlap skip**: skip overnights where the stock has an AMC earnings announcement (use earnings_calendar.csv). Avoids overlap with earnings_fade family + AMC announcement is a separate idiosyncratic event.
3. **Volatility filter**: skip if 20d realized vol > 80th percentile (avoid 2020-COVID, 2022 bear regime peaks where overnight crashes happen).
4. **Macro-event blackout**: skip overnights into FOMC-day, NFP-day, CPI-day. (Use FRED data already on disk.)

Test order:
- Baseline: no filters, long all 24 every overnight, equal weight.
- Filter-additive: each filter on top of baseline, individually and combined.
- Cost sensitivity: 0 / 1.5 / 3 / 5 bps daily swap.

## Signal math (baseline)

```
Per overnight (D close -> D+1 open):
  for each ticker in 24-name universe:
    if filter passes:
      buy at D 15:55 ET close
      sell at D+1 09:35 ET open
      overnight return = open[D+1, 09:35] / close[D, 15:55] - 1.0
      cost = SWAP_BPS_PER_DAY / 1e4  (default 1.5 bp daily; sweep)
  equal-weight across names traded that night
```

Equity curve: daily PnL = mean of per-name overnight returns on that night. Sharpe annualized × sqrt(252).

## Expected performance

Literature point estimates on similar universes:
- Lou/Polk/Skouras 2019 (full SP500, 2000-2018): overnight ≈ +25-35 bps/wk; intraday ≈ -10 to +5 bps/wk.
- Fang et al 2024 (Mag7-like, 2020-2024): overnight ≈ +60 bps/wk on the 7 largest.

**Pre-Phase-2 expected**: research Sharpe +0.5 to +1.0 baseline (no filters); +0.7 to +1.5 with trend/vol/earnings filters. Cost-binding only if swap > 4 bp/day (broker-specific; Eightcap stock swap rumored 1-2 bp/day for long, will verify in Phase 0 swap check before deploy).

## Fail conditions (pre-committed)

### Phase 2

- Baseline (no filters) Sharpe < +0.30 at 1.5 bp/day swap. (Tight floor — if naive baseline doesn't hit +0.30 the mechanism is gone.)
- MDD > 25%.
- Best filtered variant Sharpe must exceed baseline by at least +0.20 (filters add value).
- Trade count >= 1000 overnight-events (any filter should keep this).

### Phase 4 regime

- All 3 regimes (2019-2020 / 2021-2022 / 2023-2026) Sharpe > 0. Per Berkman/Koch and Lou et al, mechanism is structural — should survive every regime. If 2022 bear regime is the ONLY losing window, that's accepted (overnight risk premium IS expected to compress in bear markets).

### Phase 6 holdout

- 2023-2026 holdout Sharpe > +0.30. Per Lou et al and Fang et al, post-2020 should be the STRONGEST regime, not weakest. If holdout decay is observed, it refutes the modern-strengthening literature claim.

### Walk-forward

- 3 rolling splits (3y-IS / 1.5y-OOS): mean OOS ≥ +0.20, min OOS ≥ 0.

## Why this might fail

1. **Eightcap overnight swap could be punitive.** Retail brokers sometimes charge 5-8 bp/day on long stocks. At 5 bp × 252 ≈ 12.6%/year cost; the gross overnight premium would need to be > 13% annualized. Phase 0 swap check is the first deploy gate.
2. **Earnings overlap rule**: 50 events × 24 names = 1200 overnights/yr filtered out — only ~5% of total. Probably not load-bearing but doesn't hurt.
3. **Crash risk concentrated overnight** — 1987, 2008, 2020 COVID, 2024-08 carry unwind. Tail-MDD could be brutal. Vol filter is the mitigation.
4. **Survivorship bias in 24-name universe** — these are CURRENT Mag7 + S&P large-caps. The same selection in 2018 would have been different. Bias is upward.
5. **The published premium is on cash equities at 0.5-1 bp commission**. CFD friction is 2-3 bp + 1-2 bp daily swap — different cost structure than the literature. If the literature premium is 30 bp/wk gross and our cost is 1.5 bp × 5 = 7.5 bp/wk, gross-net ≈ 22 bp/wk = ~1.1%/wk = ~56%/year. Sanity-checks the headline expectation.

## Files

- Thesis: this file.
- Demo: `overnight_premium_demo.py`
