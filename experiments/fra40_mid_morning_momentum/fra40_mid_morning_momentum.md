# FRA40 mid-morning momentum — CFD-session first-hour drift

**Status**: Phase 2 complete (2026-05-27); look-ahead bug discovered and fixed same day — rerun and re-verdicted.
**Verdict**: **REJECT (decisive)** — fails Phase 2 kill criteria after fixing a same-bar look-ahead in entry timing. Corrected baseline: Sh **−0.17** after 1.5pt cost, MDD **−29.3%**, WR 49.9% / PF 0.97, holdout (2023-2026) Sh +0.33. Some weak directional content survives (dir-gap **+0.79**, cost-zero gross +0.40), but absolute Sharpe is negative and the 2019-2020 regime (Sh −0.94) sinks the full sample.

**Look-ahead bug (2026-05-27 post-mortem)**: the original code set `morning_end_px = close[first_bar_i + measure_bars]` (close of bar N) but `entry_px = open[first_bar_i + measure_bars]` (open of the SAME bar N). `open[N]` precedes `close[N]` by ~5 minutes, so entry was being placed 5 min before the signal forms — a classic same-bar leak. Fix: `entry_i = first_bar_i + measure_bars + 1` (enter at OPEN of the bar AFTER the signal-close, matching the orb_demo convention at [experiments/_live/orb/orb_demo.py:326](../../experiments/_live/orb/orb_demo.py#L326)). With the fix the strategy is REJECT. None of the existing safeguards caught the bug: the fade null-check produced an even larger negative Sharpe (so dir-gap stayed huge), cost-zero stayed positive, and walk-forward looked clean (the leak was uniform across time). The only soft signal that something was wrong was the prior-violation — the thesis itself predicted Sh 0.30-0.50 (smaller than orb_dax's +0.76 due to the 1-2h CFD-data lag); reporting Sh +2.05 (4-7× the prior, 2.7× orb_dax) should have been read as "your math is wrong" rather than rationalized in the verdict.

---

## Thesis (mechanism)

1. The FRA40 (CAC 40) CFD session first bar arrives at ~09:00 UTC (10:00-11:00 Paris local depending on DST) — this is the point where the broker's derivative-pricing desk begins streaming CFD quotes referenced to the underlying Euronext Paris cash market, which has been trading for 1-2 hours by then. The first hour of CFD activity captures the residual institutional flow from the post-auction cash session that hasn't been fully absorbed by the futures market.

2. If European index CFD pricing inherits the same opening-impulse momentum documented on GER40/Xetra (orb_dax, LONG-only Sh +0.76), the direction of the first ~60 min of the FRA40 CFD session should persist over the next ~2-3 hours. The mechanism is the same structural class: late-morning institutional flow drives directional persistence before the NY open at 15:30 CET introduces competing US-flow cross-currents.

3. Unlike the GER40 Xetra ORB (which exploits a formal single-price call auction at 09:00 CET), this FRA40 variant targets the **CFD-session open** — the moment the broker's price feed becomes active after the overnight desk-to-desk transfer. The edge, if it exists, comes from the same source as orb_dax (institutional morning flow persistence) but is measured through the CFD lens rather than the cash auction lens.

4. **Key difference from orb_dax**: the measurement window (first ~60 min of CFD data at 09:00 UTC) starts 1-2h after the cash open. By this time, the Xetra opening auction impulse (which orb_dax captures at 09:00 CET) has already been partially absorbed. Expected effect size: **smaller** than orb_dax's +0.76, possibly 0.30-0.50 if the mechanism survives at all across the time-lag.

## Key reference

- `experiments/orb/orb.md` (GER40 ORB) — the canonical opening-impulse thesis, deployed as orb_dax at Sh +0.76. This experiment is the FRA40 horizontal transplant (same mechanism family, different venue and timeframe).
- `experiments/fdax_lunch_fade/fdax_lunch_fade.md` (DAX REJECT) — establishes that intraday EU-index mechanisms don't auto-transfer even within the same timezone. This experiment explicitly tests whether the same caution applies to opening-impulse.
- Lesson #-14 (session portability not free) and lesson #71 (ORB is venue-specific) — both bound the transplant risk.

## Signal math

```
SESSION_START_UTC = 09:00        # first FRA40 CFD bar of the day at or after this
MEASURE_BARS      = 12           # 60 min first measurement window
HOLD_BARS         = 36           # 180 min hold after measurement
ATR_THRESHOLD     = 0.20         # skip days where |return| / atr < threshold
MODE              = "momentum"   # follow the direction of the morning move
COST_PT           = 1.5          # FRA40 CFD typical spread (pt RT). Sweep 0/1/2/3.

Per day:
  first_bar_idx     = argmin(abs(minute_of_day >= SESSION_START_UTC))
  morning_start_px  = close[first_bar_idx]
  morning_end_px    = close[first_bar_idx + MEASURE_BARS]
  r_morning         = morning_end_px / morning_start_px - 1.0
  atr_proxy         = rolling 20d mean of |daily_mid_return|

  if abs(r_morning) < ATR_THRESHOLD * atr_proxy: skip

  position          = sign(r_morning)  # LONG if morning up, SHORT if down (momentum)
  entry_px          = open[first_bar_idx + MEASURE_BARS + 1]
  exit_px           = close[first_bar_idx + MEASURE_BARS + HOLD_BARS]
  net_ret           = position * (exit_px - entry_px) / entry_px - COST_PT / entry_px
```

## Why retail-accessible

- FRA40 M5 data already on disk (`ohlc_data/FRA40_M5.csv`).
- Eightcap FRA40 CFD trades with similar spread profile to GER40 (~1-2pt RT = ~1.2-2.4bp on ~8400 level).
- Same MT5 VPS / EA infrastructure as the existing book.
- EUR-denominated → no FX leg for a EUR-account.

## Universe

- **Research**: FRA40 M5, 2019-02-13 → 2026-04-17 (~7.1 years, ~1830 trading days). Early 2019 excluded (24h data regime with different first-bar timing).
- **Live**: Eightcap MT5 FRA40 CFD. Margin/spread profile similar to GER40.

## Phase 2 results

### Headline

| Metric | Value | Threshold | Verdict |
|---|---|---|---|
| Sharpe (1.5pt RT) | **+2.05** | > +0.30 | PASS |
| Max DD | -15.73% | < 25% | PASS |
| Trades | 1595 (219/yr) | ≥ 200 | PASS |
| Win rate / Profit factor | 57.4% / 1.51 | WR ≥ 40% AND PF ≥ 1.1 | PASS |
| Direction null-gap | **+5.20** | ≥ +0.30 | PASS (decisive) |
| Cost-zero Sharpe | +2.60 | > 0 | PASS (signal-present) |

### Regime breakdown

| Window | CAGR | Sharpe | MDD | Trades |
|---|---|---|---|---|
| 2019-2020 pre/COVID | +5.43% | **+0.54** | -15.73% | 424 |
| 2021-2022 vol | +29.13% | **+2.65** | -7.10% | 438 |
| 2023-2026 holdout | **+24.75%** | **+2.92** | -5.18% | 733 |

**3/3 regimes positive** — and the holdout is the STRONGEST, not the weakest. Same signature as lunch_fade (lesson #25: mechanism INTENSIFIED post-2022).

### Walk-forward (3 rolling splits)

| Split | IS period | IS Sharpe | OOS Sharpe | IS trades | OOS trades |
|---|---|---|---|---|---|
| S1 | 2019-01 → 2023-06 | +1.78 | **+2.67** | 972 | 623 |
| S2 | 2019-07 → 2024-01 | +1.68 | **+2.97** | 1017 | 490 |
| S3 | 2020-01 → 2024-07 | +1.88 | **+3.05** | 1008 | 384 |

WF OOS mean **+2.90** (floor +0.30) — PASS.
WF OOS min **+2.67** (floor > 0) — PASS.
Every OOS split outperforms IS. The mechanism has strengthened over time.

### Variant sweeps

**Measurement window**: 60min is the only positive window. 30min Sh -0.16, 45min Sh -0.24, 90min Sh +0.33 (degraded). The 60min specificity is the M-shape pattern from lesson #-15.

**Hold window**: All positive, peaks at 60min hold (Sh +2.68) and decays monotonically with longer holds. Shorter holds capture the concentration of edge.

**ATR threshold**: All thresholds positive. Higher thresholds (0.50) improve Sharpe slightly but reduce trade count (1255 vs 1836 at 0.0). The signal doesn't depend on outlier-magnitude mornings.

**Cost sensitivity**: Linear decay from +2.60 (cost=0) to +1.50 (cost=3pt). Slope ~-0.37 Sh/pt. Cost-resilient — even at 3pt RT (2× the realistic cost), the signal survives.

**LONG/SHORT split**:
- LONG-only: Sh +1.62, 820 trades, WR 60.4%
- SHORT-only: Sh +1.28, 775 trades, WR 54.3%
Both legs win. LONG leg benefits from FRA40's structural up-drift (+0.34 Sh premium over SHORT). The directional signal is independent of drift direction — momentum works in both up- and down-mornings.

### Expected performance (retrospective)

The pre-commit expectations underestimated the effect size by 4-10×:
- **Predicted most likely**: Sh +0.20 to +0.45
- **Observed**: Sh **+2.05**
- Gap explanation: the 1-2h CFD time-lag (viewed as a weakness pre-experiment) turned out to be a STRENGTH — the early cash-session noise decays over the first 1-2h, leaving only persistent institutional flow in the CFD window. The "residual" is cleaner than the primary impulse.

## Fail conditions (pre-committed) — verdicts

### Phase 2 (baseline momentum, COST=1.5pt, MEASURE=60min, HOLD=180min, ATR=0.20)

| Criterion | Floor | Observed | Verdict |
|---|---|---|---|
| Full-sample Sharpe | < +0.30 | **+2.05** | PASS |
| Max DD | > 25% | **-15.73%** | PASS |
| Trade count | < 200 | **1595** | PASS |
| WR ≥ 40% AND PF ≥ 1.1 | both | **57.4%, 1.51** | PASS |
| Direction null-gap | < +0.30 | **+5.20** | PASS |
| Cost-zero Sharpe | ≤ 0 | **+2.60** | PASS |

### Phase 4 (regime)

- ≤ 1 of 3 regimes positive → **PASS (3/3 positive)**

### Phase 6 (holdout binding)

- 2023-2026 holdout Sharpe ≤ 0 → **PASS (+2.92)**

### Phase 7 (walk-forward)

- OOS mean < +0.30 → **PASS (+2.90)**
- OOS min ≤ 0 → **PASS (+2.67)**

## Mechanistic interpretation — why FRA40 mid-morning momentum works better than expected

The pre-experiment priors assumed the 1-2h time-lag vs cash open would WEAKEN the signal. The observed result (Sh +2.05 vs orb_dax's +0.76) shows the opposite. Three structural reasons:

1. **The first 1-2h of Euronext cash trading acts as a noise filter for the CFD window.** By the time the FRA40 CFD session starts at 09:00 UTC (10:00-11:00 local), the opening auction's micro-noise (random order imbalance, latency arbitrage, stale-quote crossovers) has been absorbed by the cash market. What remains in the CFD window is the persistent institutional directional flow — block orders being filled over 2-4 hours, ETF rebalancing, and portfolio-level drift. The CFD session's first bar starts at EXACTLY the right time to capture the "clean" part of the institutional momentum, avoiding the noisy opening period.

2. **FRA40's sector composition is BETTER suited to mid-morning momentum than GER40's.** LVMH, Hermes, L'Oreal, and other luxury/consumer names have longer order-execution tails than GER40's auto/industrial names — institutional block trades in these high-price, low-float names take 2-4 hours to fill without moving the market. This means directional persistence extends further into the session on FRA40 than on GER40, where orb_dax's opening-impulse edge is largely captured in the first 3h (T+180min exit). The 60min measurement window + 60-180min hold hits this persistence sweet spot.

3. **The CFD venue adds a pricing-reversion delay to the underlying cash move.** When the Euronext cash index moves, the CFD broker's pricing desk requires time to re-quote (especially during high-volatility periods). This creates a mechanical lag between cash index moves and CFD pricing that the strategy exploits: the CFD "catches up" to the cash move over 1-3 hours, generating a directional persistence in the CFD itself that isn't present in the underlying cash index. This is a venue-specific microstructure edge, not a generic index momentum signal.

## Why this might fail (red flags, post-hoc assessment)

1. ~~1-2h time-lag vs cash open~~ → **TURNED OUT TO BE A STRENGTH**, not a weakness (see mechanistic interpretation above).

2. ~~Euronext continuous auction ≠ Xetra single-price call auction~~ → **TURNED OUT IRRELEVANT** — the edge comes from the CFD microstructure, not the cash auction.

3. **CFD venue dependence is untested live.** The entire edge relies on Eightcap's FRA40 CFD pricing desk having the right re-quote latency. If the broker changes pricing algorithms, tightens spreads, or switches to a different liquidity provider, the mechanism could degrade or disappear. Unlike orb_dax (which exploits Xetra cash auction — a structural market feature), this FRA40 strategy exploits the BROKER's CFD pricing behavior, which is a contractual relationship, not a market invariant.

4. **FRA40 sector composition** could change with index rebalancing (MSCI/FTSE semi-annual reviews). If luxury/consumer weights decrease and tech/industrial weights increase, the longer execution-tail mechanism weakens.

5. **CFD data coverage** — first-bar timing may shift with broker configuration changes. Currently stable at 09:00 UTC since Feb 2019.

6. **Sharpe magnitude is unusually high** (+2.05) for a simple single-instrument intraday momentum strategy. Bar-level Sharpe convention (including flat-period zeros in std) inflates absolute numbers relative to daily Sharpe convention. For comparison: orb_dax at Sh +0.76 uses the same convention. The relative outperformance (FRA40 ~2.7× orb_dax) is the relevant metric, not the absolute number. Deploy should expect 10-25% relative haircut per lesson #5 (research-to-live confound-specific framing).

7. **LONG and SHORT both win** — this IS the expected pattern for a momentum strategy (different trigger conditions for each side), not a confound. LONG +1.62 vs SHORT +1.28 reflects FRA40's structural up-drift (~+0.34 Sh premium).

## Phase 1 → 2 plan (completed)

- [x] Data confirmed on disk (313K bars, 2019-01 to 2026-04).
- [x] Thesis doc with pre-committed fail conditions (this file).
- [x] **Phase 1 demo** — `fra40_mid_morning_momentum_demo.py`:
  - [x] load_m5 with session-start filter (09:00 UTC first bar)
  - [x] Baseline simulator (momentum, MEASURE=60min, HOLD=180min, ATR threshold=0.20, cost=1.5pt)
  - [x] Direction null-check (fade variant) — dir-gap +5.20
  - [x] LONG-only / SHORT-only split — both win (+1.62 / +1.28)
  - [x] MEASURE_BARS sweep — 60min is the sweet spot, 30/45/90min degrade
  - [x] HOLD_BARS sweep — 60min best (+2.68), decays monotonically
  - [x] ATR threshold sweep — all positive, threshold not load-bearing
  - [x] Cost sensitivity — linear decay, survives to 3pt RT
  - [x] Walk-forward (3 rolling splits) — OOS mean +2.90, min +2.67
  - [x] Summary + verdict — **PASS (11/11 pre-commits)**

### Phase 2 → Phase 3+ deferred

The strategy is Phase 2 PASS on all 11 pre-committed criteria. The following are NOT done and should be addressed before deploy:

- [ ] **Phase 3 (mechanism classification)**: C1 (modal regime partition), C2 (bootstrap CI on Sharpe), C3 (deflated Sharpe), C4 (cross-asset shadow — SPX/correlation confound check)
- [ ] **Phase 5 (broker spread audit)**: Measure Eightcap FRA40 CFD actual spread via MT5 M1 `copy_rates_range` — per lesson #32
- [ ] **Phase 7 (walk-forward — confirmatory)**: Extend to 5 rolling splits per lesson #29
- [ ] **Phase 5b (venue dependence test)**: Cross-validate on a different FRA40 data source (e.g., Yahoo D1 or Tiingo) to confirm the edge isn't a CFD-pricing artifact (see red flag #3)

## Phase 2 results (corrected, post-fix, 2026-05-27)

### Kill criteria

| Criterion | Floor | Observed | Verdict |
|---|---|---|---|
| Full-sample Sharpe | ≥ +0.30 | **−0.17** | FAIL |
| Max DD | ≤ 25% | **−29.3%** | FAIL |
| Trade count | ≥ 200 | 1595 | PASS |
| WR ≥ 40% AND PF ≥ 1.1 | both | WR 49.9% / **PF 0.97** | FAIL |
| Direction null-gap (mom − fade) | ≥ +0.30 | +0.79 | PASS |
| Cost-zero gross Sharpe | > 0 | +0.40 | PASS |

3 binding kill criteria fail → REJECT.

### Regime breakdown (baseline)

| Window | CAGR | Sharpe | MDD | Trades |
|---|---|---|---|---|
| 2019-2020 pre/COVID | −9.83% | −0.94 | −25.6% | 424 |
| 2021-2022 vol | −0.36% | +0.01 | −11.7% | 438 |
| 2023-2026 holdout | +2.24% | +0.33 | −12.6% | 733 |

Only 1 of 3 regimes positive — fails the Phase 4 floor (≤ 1 positive = KILL). Holdout is marginal-positive in isolation, but cannot rescue the full sample.

### Sensitivity sweeps

| Sweep | Best cell | Best Sh | Notes |
|---|---|---|---|
| MEASURE | 60 min (baseline) | −0.17 | All ≤ baseline; longer dilutes faster |
| HOLD | 180 min (baseline) | −0.17 | Surrounding cells worse |
| ATR threshold | 0.50 | −0.08 | Filters trades but never crosses zero |
| Cost (RT pt) | 0.0 | +0.40 | Crosses zero at ~1.1pt (research cost is 1.5pt) |

No variant clears Sh +0.30 at the research cost; cost-breakeven sits at ~1pt RT (tighter than Eightcap's typical FRA40 spread). Long/short split is symmetric and equally bad (long −0.12 / short −0.13).

### Walk-forward (3 rolling splits)

| Split | IS Sh | OOS Sh | OOS trades |
|---|---|---|---|
| S1 (IS 2019-01 / OOS 2023-07) | −0.38 | +0.24 | 623 |
| S2 (IS 2019-07 / OOS 2024-01) | −0.61 | +0.71 | 490 |
| S3 (IS 2020-01 / OOS 2024-07) | −0.35 | +0.77 | 384 |

Interesting wrinkle: all three OOS Sharpes are positive (mean +0.57), all three IS Sharpes are negative. This reflects the regime structure (2019-2022 negative, 2023+ positive) more than any persistent edge. The 2026-Q1 hard-stop on each OOS window means OOS lengths are shrinking; with another year of data the OOS-only Sharpe is likely to compress back toward the holdout's +0.33.

## Mechanistic interpretation

The corrected result is consistent with the thesis's own red flags rather than its hopeful prior:

1. **1-2h post-cash-open data-lag eats the impulse.** Predicted in red flag #1. The Euronext continuous-auction open has already resolved most of the morning's directional information by the time the CFD feed comes online at 09:00 UTC — what we measure is residual, not impulse, and residual at this magnitude is below cost in most regimes.
2. **2019-2020 regime sinks the strategy.** Sh −0.94 on n=424. The pre-COVID FRA40 morning structure has near-zero directional persistence at this horizon; only post-2022 (Sh +0.33 holdout) shows weak continuation. A single positive regime cannot carry the strategy through the 1.5pt RT cost.
3. **dir-gap +0.79 ≠ deployable edge.** Some directional signal exists (fade is far worse than momentum), but the absolute magnitude doesn't clear cost. This is the canonical lesson #6 / lesson #26 shape: "signal present, friction-eaten." With a tighter broker (≤ 0.5pt RT) the strategy would cross zero — but Eightcap's typical FRA40 spread is 1-2pt, so this is not deployable on the realistic cost model.
4. **No structural reason to expect Euronext to behave like Xetra.** orb_dax works on the Xetra single-price call auction (concentrated information-resolution event at 09:00 CET). Euronext uses a continuous opening auction and is already 1-2h stale by 09:00 UTC. The mechanistic prior (red flag #2) was correct.

## Files

- `fra40_mid_morning_momentum.md` — this thesis doc
- `fra40_mid_morning_momentum_demo.py` — Phase 1-2 simulator (look-ahead bug fixed 2026-05-27)
