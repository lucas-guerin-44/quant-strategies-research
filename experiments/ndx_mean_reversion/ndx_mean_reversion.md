# NDX100 intraday mean-reversion — M5 z-score fade

**Status**: Phase 2 complete, 2026-04-19. **REJECT — tombstoned.**
**Verdict summary**: Baseline Sharpe −0.68 (need > +0.30), MDD −40%, even costless Sharpe is −0.21. Momentum (null-check) Sharpe −0.40 vs fade −0.68 → **fade-gap is −0.28**, i.e., the signal has directional content **in the momentum direction**, not the mean-reversion direction. The parent ORB-fade hint does NOT generalize to a z-score mean-reversion trigger. Tombstoning with a clear null result.
**Parent insight (origin)**: orb_spx.md cross-instrument refinement (2026-04-19) found that under tight R:R exits, the fade-of-ORB-breakout direction beats the baseline on NDX100 — the opposite of GER40. This experiment tested whether that hint generalizes to a proper mean-reversion trigger. It does not.

## Thesis (mechanism)

NASDAQ-100 index price action is dominated by a small number of high-weight mega-cap tech names (AAPL, MSFT, NVDA, GOOGL, AMZN, META). Short-term intraday dynamics in these names are driven by:

1. **Gap-and-fade behavior.** Overnight catalysts and pre-market sentiment push the open up/down, but liquidity providers systematically lean against the open, producing a 30-90 minute fade back toward a session anchor (prior close, VWAP, or short-term mean).
2. **Market-maker inventory mean-reversion.** Concentrated tech names have heavy options and ETF-arb flow; market makers absorb directional imbalance at the open and unwind it through the session, producing short-horizon reversion.
3. **No concentrated opening impulse** (unlike DAX, which has a sharp Xetra-morning auction resolution). NDX100 price discovery is distributed across the session, with intraday extremes not particularly predictive of continuation.
4. **Literature support**: intraday mean-reversion in NDX components is one of the oldest documented patterns (Avellaneda & Lee 2008, Stübinger & Endres 2018 on statistical-arb at 5-15 min horizons for S&P components). Index-level reversion is a weaker version of the same phenomenon.

## Key reference

- **Avellaneda, M., & Lee, J.-H. (2010).** "Statistical arbitrage in the U.S. equities market." *Quantitative Finance* 10(7). Residual-reversion on stock pairs, 5-60 min horizons. Cited as evidence that intraday mean-reversion is pervasive in US equities at short horizons.
- **Connors, L., & Alvarez, C. (2008).** *Short Term Trading Strategies That Work.* RSI-2 and similar oversold/overbought fades on ETFs and indices. Daily-bar oriented but the z-score family of triggers is adjacent.
- **Stübinger & Endres (2018).** "Pairs trading with a mean-reverting jump-diffusion model on high-frequency data." *Applied Economics.* 5-min frequency on S&P 500 names.

## Signal math

```
Parameters:
  WINDOW_BARS        = 20      (rolling z-score window: 20 M5 bars = 100 min)
  Z_ENTRY            = 2.0     (enter when |z| >= 2.0)
  Z_EXIT             = 0.5     (take profit when |z| <= 0.5 — price back near mean)
  Z_STOP             = 3.0     (stop when |z| >= 3.0 — stretch continues)
  T_EXIT_MIN         = 60      (time stop after 60 min if neither TP nor stop hit)
  ENTRY_CUTOFF_MIN   = 300     (no new entries in last 60 min of session)
  EXIT_MIN_BEFORE_CLOSE = 5    (flat by 15:55 ET)
  COST_POINTS_RT     = 1.0     (pessimistic retail CFD)

Per M5 RTH bar b (09:30-16:00 ET):

  Compute within-day rolling stats over last WINDOW_BARS *completed* bars:
    mean_b = rolling_mean(close, WINDOW_BARS)
    std_b  = rolling_std(close, WINDOW_BARS, ddof=1)
    z_b    = (close_b - mean_b) / std_b

  Entry (flat only, within ENTRY_CUTOFF_MIN of open):
    z_b >=  Z_ENTRY  -> SHORT at next bar open (fade up-stretch)
    z_b <= -Z_ENTRY  -> LONG  at next bar open (fade down-stretch)
    Record entry_mean = mean_b (snapshot of target at entry).
    Record entry_z    = z_b (for stop calc).

  Exit (any of, first fired):
    |z_current|         <= Z_EXIT          -> TP   (mean-reversion success)
    |z_current| * sign  >= Z_STOP          -> STOP (stretch continues against us)
    bars_since_entry    >= T_EXIT_MIN / 5  -> TIME (drift without resolution)
    minute_of_day       >= 385             -> EOD  (15:55 ET forced close)

  Max 1 concurrent position. Flat overnight.
```

## Why retail-accessible

1. NDX100 CFD is spreadable on MT5 brokers at typical 1-2pt spread (slightly wider than SPX500). Cost model of 1pt RT is optimistic; 2pt is realistic.
2. Same MT5/research pipeline as orb_spx — data already on disk at `ohlc_data/NDX100_M5.csv` (520,594 bars).
3. Mechanical, slow enough (5-min decisions) for QC minute-resolution deployment with MNQ (Micro Nasdaq futures) as the cleanest exchange-traded analog.
4. No volume-filter dependence (unlike Zarattini ORB) — z-score is computed purely from closes.

## Universe

- **Primary (research)**: NDX100 M5, RTH 09:30-16:00 ET, 2019-01-01 → 2026-04-18.
- **Primary (live)**: NDX100 CFD on existing MT5 broker. QC analog: MNQ (Micro E-mini Nasdaq-100 futures, CME).

## Expected performance

Given the parent insight (fade beats ORB baseline by ~0.17 Sharpe at 1:1 R:R on NDX100), but that was the ORB-boundary trigger — a weaker signal than a true stretch trigger. A proper z-score fade should produce a cleaner edge if the mechanism is real.

**Prior expectation** (point estimates, not confidence intervals):
- Full-sample Sharpe **0.3-0.8** after 1pt RT cost.
- Trade frequency **3-10 per week** (z ≥ 2.0 trigger fires maybe 1-2 times per day on average).
- **Win rate 55-70%** (mean-reversion strategies are high-WR, small-win-small-loss).
- Profit factor **1.1-1.4**.
- Max DD **8-18%**.

After 10-25% Sharpe haircut for live conditions (per the rewritten lesson #5), target live Sharpe **0.25-0.55**. To be validated against 6-12 months of live data.

## Fail conditions (pre-committed)

Phase 2 kills if:
- Full-period Sharpe < 0.30 after 1pt RT cost.
- Max DD > 25%.
- Trade count < 200 over 7.3 years.
- Win rate < 50% AND profit factor < 1.1 (a mean-reversion strategy with sub-50% WR is broken by definition).
- **Fade-gap test**: the momentum variant (enter WITH the stretch) should LOSE by ≥ 0.3 Sharpe. If momentum and fade are equally profitable/unprofitable, the signal has no directional content and we're just random-sampling the return distribution.

Phase 4 kills if Sharpe positive in ≤ 1 of 3 regime windows (2019-2020, 2021-2022, 2023-2026 holdout). The 2023-2026 holdout is especially important — the parent ORB-fade finding showed NDX100 baseline's *best* sub-period was 2023-2026, so the MR version must preserve or strengthen that.

## Why this might fail (red flags)

1. **Intraday MR on index futures is well-published.** Not a novel edge; may be arbed down. The NDX100 CFD retail cost assumption must not be optimistic — at 2pt RT the strategy may die.
2. **Stop at z=3.0 is far.** If the strategy catches a momentum blowout (e.g., 2020-03 COVID crash, 2022 FOMC day moves), a single trade can take a 1.5-2% adverse move. Risk per trade is not small.
3. **Confounded with TREND-DAY regime.** On strong trend days, z-score fades get crushed. Need to verify MDD is not concentrated in 5-10 catastrophic days. A daily-level trend filter (SPY 20d slope) may be needed.
4. **Window choice (20 bars) is arbitrary.** Short (10) may be noisy; long (60) may miss regime shifts. Variant sweep will tell.
5. **Phantom fills on breakout bars.** Z-score crosses 2.0 on a bar close; next-bar-open fill assumes we can enter AT the open, but on momentum days the open can gap multiple points. Slippage assumption of 1pt RT includes this, but a stress test with 2-3pt cost is prudent.

## Phase 1 → 2 plan

- [x] **Phase 1a — data.** `NDX100_M5.csv` already on disk from orb_spx work.
- [x] **Phase 1b — thesis (this doc).**
- [x] **Phase 2 — baseline demo.** Run `ndx_mean_reversion_demo.py` with default params; report Sharpe/WR/PF/MDD/trade-count/regime-breakdown.
- [x] **Phase 2b — variant sweep.** z_entry ∈ {1.5, 2.0, 2.5, 3.0}; window ∈ {10, 20, 40, 60}; T_exit ∈ {15, 30, 60, 120, EOD}; z_stop ∈ {2.5, 3.0, 3.5, 4.0, None}.
- [x] **Phase 2c — momentum null check.** Run same setup with direction flipped (enter WITH stretch). Expected to lose by ≥0.3 Sharpe; **actually was the OTHER way** (see results).
- [x] **Phase 2d — regime breakdown.** Split by 2019-2020, 2021-2022, 2023-2026.
- [x] **Phase 2e — cost sensitivity.** 0.5pt, 1pt, 2pt, 3pt RT.

## Phase 2 result — REJECT (all variants negative Sharpe)

Ran on NDX100 M5, 2019-01-02 to 2026-04-17 (7.3y, 146,245 RTH bars, 1,885 trading days).

### Baseline (window=20, z_entry=2.0, z_exit=0.5, z_stop=3.0, T=60min, cost=1pt)

| Metric | Value | vs threshold |
|---|---|---|
| Sharpe | **−0.68** | FAIL (need > +0.30) |
| CAGR | −6.75% | FAIL |
| Max DD | **−40.24%** | FAIL (need < 25%) |
| Trades | 4,250 (11.2/week) | PASS volume |
| Win rate | **59.0%** | PASS on WR threshold |
| Profit factor | 0.92 | FAIL (need ≥ 1.1) |
| Avg win | +0.213% | — |
| Avg loss | **−0.332%** | — |
| Exit mix | TP 2,688 / TOD 1,003 / STOP 554 | TP dominates → not a stop problem |

**Classic mean-reversion failure mode**: high WR, avg-win < avg-loss. 59% × 0.213 − 41% × 0.332 = **−0.010% per trade before costs**. The signal *books* wins at 59% rate but the 41% of losses are 1.5× larger than wins, producing a negative gross expectancy.

### Null check (momentum variant — enter WITH the stretch)

| Variant | Sharpe | WR | PF | Avg win | Avg loss |
|---|---|---|---|---|---|
| **Fade** (thesis) | **−0.68** | 59.0% | 0.92 | +0.213% | −0.332% |
| **Momentum** (null) | **−0.40** | 34.3% | 0.94 | +0.397% | −0.220% |
| **Fade-gap** | **−0.28** | — | — | — | — |

**The signal goes the WRONG way.** The thesis predicted fade-gap ≥ +0.30 (fade beats momentum). Instead, the momentum variant is 0.28 Sharpe *less negative* than the fade variant. At z ≥ 2.0 stretches on NDX100 M5, the short-term drift is **weakly in the stretch direction**, not against it.

This is the exact opposite of what the parent ORB-fade hint implied, and it's the decisive kill signal — no amount of parameter tuning fixes a signal whose directional content points the wrong way.

### Regime breakdown (baseline)

| Window | Sharpe | MDD | Trades | WR |
|---|---|---|---|---|
| 2019-2020 pre/COVID | −0.93 | −23% | 1,194 | 59.3% |
| 2021-2022 vol | −0.58 | −19% | 1,151 | 58.6% |
| 2023-2026 holdout | −0.59 | −20% | 1,905 | 59.0% |

**3/3 regimes negative.** No sub-period rescues it. The holdout is not the worst — consistency of failure, not regime decay.

### Variant sweep — z_entry (only interesting one)

| z_entry | Sharpe | MDD | Trades | WR | PF |
|---|---|---|---|---|---|
| 1.5 | −0.50 | −40% | 6,181 | 61.4% | 0.95 |
| 2.0 | −0.68 | −40% | 4,250 | 59.0% | 0.92 |
| 2.5 | −0.57 | −28% | 2,335 | 54.9% | 0.91 |
| **3.0** | **−0.02** | **−13%** | **950** | **51.4%** | **1.00** |

Extreme stretches (z ≥ 3.0) produce a ~breakeven strategy (Sharpe −0.02, PF 1.00). Still negative, and the trade cadence (~2.5/week) defeats the "showcase" rationale. Not a rescue.

### Variant sweep — window_bars

| Window | Sharpe | MDD | Trades | WR |
|---|---|---|---|---|
| 10 | −0.67 | −38% | 4,686 | 60.3% |
| 20 | −0.68 | −40% | 4,250 | 59.0% |
| 40 | −1.32 | −50% | 2,487 | 43.9% |
| 60 | −0.15 | −8% | 286 | 46.2% |

Window=60 reduces trades 15× and gets close to flat Sharpe, but that's because most z ≥ 2.0 triggers at that window are rare outliers with stretched return distributions. Not a robust pattern.

### Variant sweep — T_exit

| T | Sharpe | MDD | Trades | WR |
|---|---|---|---|---|
| 15min | −1.00 | −44% | 5,101 | 48.0% |
| 30min | −0.87 | −45% | 4,568 | 51.1% |
| 60min | −0.68 | −40% | 4,250 | 59.0% |
| 120min | −0.71 | −43% | 4,107 | 59.7% |
| EOD-only | −0.65 | −41% | 4,096 | 59.7% |

Shorter time stops are WORSE, not better. The "tight R:R favors fade" hint from ORB cross-instrument work is falsified here — at tighter exits (shorter time-stop = tighter R:R in time terms), the strategy performs worse. Conclusion: the ORB hint was an artifact of the ORB-boundary trigger specifically, not a general NDX100 mean-reversion property.

### Variant sweep — z_stop

| z_stop | Sharpe | MDD | Trades | WR |
|---|---|---|---|---|
| 2.5 | −1.18 | −56% | 5,135 | 49.0% |
| 3.0 | −0.68 | −40% | 4,250 | 59.0% |
| 3.5 | −0.61 | −38% | 3,869 | 63.2% |
| 4.0 | −0.62 | −38% | 3,783 | 63.8% |
| none | −0.64 | −39% | 3,778 | 63.7% |

Removing the stop entirely doesn't fix it — WR rises to 64% but the long tail of losing trades without a stop produces the same Sharpe. Losses are tail-heavy, not stop-heavy.

### Cost sensitivity

| Cost | Sharpe |
|---|---|
| 0.0pt | −0.21 |
| 0.5pt | −0.44 |
| 1.0pt | −0.68 |
| 2.0pt | −1.15 |
| 3.0pt | −1.62 |

**Even at zero cost the strategy loses** (−0.21). This is a signal problem, not a cost problem.

### Kill decision

Per the thesis's pre-committed Phase 2 criteria:
- Sharpe > 0.30 → **FAIL** (−0.68)
- Max DD < 25% → **FAIL** (−40%)
- Trades ≥ 200 → PASS (4,250)
- WR ≥ 50% or PF ≥ 1.1 → PASS on WR (59%), FAIL on PF (0.92)
- **Fade-gap ≥ +0.30 vs momentum null → FAIL CRITICALLY** (−0.28, opposite direction)

**4 of 5 fails, including the decisive signal-content null check.** REJECT and tombstone.

### Why the parent ORB-fade hint did NOT generalize

The orb_spx.md cross-instrument finding was: on NDX100, under tight R:R exits, fading the ORB-breakout direction is better than following it. That finding stands for that specific setup. What we learn from this MR test:

1. The "fade beats baseline" result was **ORB-boundary-specific**, not a general NDX100 mean-reversion property. OR boundaries are not particularly informative stretch levels on NDX100 — fading them is not the same signal as fading a z-score extreme.
2. **At z ≥ 2.0 rolling-window stretches, NDX100 drifts weakly WITH the stretch over the following 60 minutes**, not against it. This is consistent with short-term momentum (not strong enough for a profitable momentum strategy either — both variants are negative on a net basis), and it's the inverse of what a pure mean-reversion thesis would predict.
3. The ORB fade-gap finding (+0.49 Sharpe fade-over-baseline at R:R=1:1) was plausibly driven by the ORB-baseline being *worse* than fade, not fade being *good* in absolute terms. Relative comparison can be misleading about the underlying mechanism.

### Mechanistic correction

The original thesis section "why this might fail" red flag #3 (trend-day regime) turned out to be the dominant factor, but in an unexpected way: rather than occasional trend days wiping out a mostly-profitable MR strategy, the baseline is *chronically negative* because z-stretches on NDX100 are weakly momentum-continuation signals, not reversion signals. The 59% WR is real but compressed by an asymmetric loss distribution that wipes out 2+ wins per adverse trade.

Intraday mean-reversion edges on individual NDX100 components (Avellaneda & Lee 2010) do not translate to index-level M5 z-score fades, possibly because:
- Index level aggregates out most of the component-specific residual noise that MR strategies exploit.
- Mega-cap tech concentration in NDX100 means the index is dominated by a few correlated names' trend days, not by the diversified-noise dynamics that component-level stat-arb exploits.

### What would be worth trying separately (logged, not executed here)

1. **Opening-gap fade** (daily-level, not rolling-window): on days where NDX100 gaps up/down by ≥ X% at 09:30 ET, fade the gap with a fixed TP at prior-day close. Distinct mechanism (daily-event trigger, not continuous z-score), different from what we tested.
2. **Component-level pairs/basket stat-arb** (the Avellaneda domain): would require NDX100 component intraday data, a lot more infrastructure. Not in scope.
3. **Sector rotation intraday on NDX ETFs** (XLK vs QQQ spread): cross-sectional MR, different asset class.

These are separate theses and each deserves its own Phase 1 if pursued. This experiment specifically closes the "rolling z-score fade on NDX100 index M5" door.

## Files

- Thesis: `experiments/ndx_mean_reversion/ndx_mean_reversion.md` (this file).
- Demo: `experiments/ndx_mean_reversion/ndx_mean_reversion_demo.py`.
- Data: `ohlc_data/NDX100_M5.csv` (520,594 bars, 2019-01-02 → 2026-04-17; 146,245 RTH-only).
- Run: `venv/Scripts/python.exe experiments/ndx_mean_reversion/ndx_mean_reversion_demo.py`

## Scope discipline

Compressed showcase pipeline, same shape as orb_spx:
1. Phase 1 thesis (this doc).
2. Phase 2 backtest with explicit fail-conditions.
3. Phase 3 skipped (statistical battery optional).
4. Phase 4 regime split in Phase 2d.
5. Phase 5 sweep in Phase 2b.
6. Phase 6 holdout 2023-2026 is already the third regime window.
7. Phase 7 correlation vs GER40 ORB T+180min (if both survive) — expected ≈ 0 since different mechanisms, different sessions.
8. Phase 8 QC/MT5 deployment if Phase 2 criteria pass.

## Files

- Thesis: `experiments/ndx_mean_reversion/ndx_mean_reversion.md` (this file).
- Demo: `experiments/ndx_mean_reversion/ndx_mean_reversion_demo.py`.
- Data: `ohlc_data/NDX100_M5.csv` (520,594 bars, 2019-01-02 → 2026-04-17).
- Run: `python experiments/ndx_mean_reversion/ndx_mean_reversion_demo.py`

## References

- Avellaneda, M., & Lee, J.-H. (2010). "Statistical arbitrage in the U.S. equities market." *Quantitative Finance* 10(7).
- Connors, L., & Alvarez, C. (2008). *Short Term Trading Strategies That Work.* TradingMarkets.
- Stübinger, J., & Endres, S. (2018). "Pairs trading with a mean-reverting jump-diffusion model on high-frequency data." *Applied Economics.*
- Lo, Mamaysky, Wang (2000). "Foundations of Technical Analysis." *Journal of Finance* 55(4).
