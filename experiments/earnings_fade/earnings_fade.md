# Single-stock earnings-gap fade (intraday)

**Status**: Phase 2 + holdout dissection complete (2026-05-22).

**Verdict**: **REJECT** on pre-committed universe. Mechanism real and large (dir-gap +1.35) but Phase 6 holdout fails (-0.22 Sh) per kill-criteria. Cleanly bifurcates: Mag7 holdout -1.67 (0DTE-options arbed); non-Mag7 holdout +0.67. Pivot candidate documented at end of file, but requires a fresh pre-committed thesis (new experiment dir), not a within-thesis refit.

## Phase 0 results (2026-05-22)

Eightcap MT5 broker (Eightcap Global Limited, Raw account analog).

- **Symbol coverage**: **24 / 25 PASS** (only `MS` missing on Eightcap; Morgan Stanley not stocked). Drop universe slot to 24 names.
- **Spread (M1 broker-quoted `spread` column, last 30 days, deploy window = NYSE first 90 min = server hours 16:00-17:59 EEST)**: **basket median 2.07 bps RT** / mean 2.51 bps / max 8.45 bps (LOW). Sub-3 bp on every Mag7 name (AAPL 1.08 / MSFT 1.42 / NVDA 1.46 / TSLA 1.37 / GOOGL 1.23 / AMZN 1.45 / META 1.78). Bank widest: BAC 3.80 / GS 3.33. Software/staples: most 2-3 bp.
- **M5 history depth**: median 4.71y, min 2.59y (LOW), max 8.38y (AMZN). Most names start 2021-09-03. PASS for ≥ 3y median.
- **Cost-model revision**: pre-Phase-0 placeholder was 5 bps RT. Phase-0-confirmed broker is **2 bps RT** for basket; deploy cost assumption **4 bps RT** to absorb open-auction slippage + 1-tick fill uncertainty.

All three Phase 0 gates PASS → proceed to Phase 1.

---

## Thesis (mechanism)

Mag7 / S&P large-cap names gap on earnings releases (after-close ER or pre-open ER). The first 30-60 minutes of US RTH after the gap-open commonly **over-reacts**, then partially fades back toward the prior close before settling into the trend direction. Mechanistic basis:

1. **Pre-open price discovery is thin and order-driven.** Only ~5% of daily volume executes pre-market (cite NASDAQ data); the open auction sets a clearing price reflecting urgent overnight order imbalance, not fundamental value.
2. **0DTE / weekly-options gamma amplification post-2020.** Single-stock options open interest concentrated at near-the-money strikes around earnings; market-maker delta-hedging accelerates the initial gap move and then mean-reverts as gamma decays through the morning.
3. **Late entrants chase the gap.** Retail order flow (Robinhood, IBKR retail) hits the tape post-open chasing the headline direction; institutional execution desks fade them into the chase via VWAP-tracking algos that target prior-close anchors.
4. **Post-earnings drift (PEAD) is the slow signal; intraday fade is the fast counterweight.** PEAD operates on days-to-weeks; the intraday fade is the first-30-90-min mean reversion within the larger PEAD trajectory. We're targeting the fast intraday reversion, not the slow PEAD.
5. **Two-sided by construction.** Up-gaps and down-gaps are faded symmetrically — no directional drift assumption (unlike single-instrument TSMOM theses).

Effect sizes documented in: So & Wang (2014) "News-driven return reversals" (single-stock event reversal day-of news); Aboody et al (2018) post-0DTE gamma intraday MR studies; Heston/Korajczyk (2010) intraday seasonality reversals.

## Key reference

- **So & Wang (2014), "News-driven return reversals: Liquidity provision ahead of earnings announcements"** (Journal of Financial Economics 114). Documents systematic intraday reversal in single-stock prices on earnings-announcement days, attributable to liquidity-provider inventory adjustment.
- **Berkman, Koch, Tuttle, Zhang (2012), "Paying attention: overnight returns and the hidden cost of buying at the open"** (J. of Financial and Quantitative Analysis 47). High retail-attention stocks (earnings names being a canonical example) systematically reverse intraday after over-extended opens.
- Modern anchor: post-2020 0DTE gamma flow literature documents intensification of this mechanism (Brogaard et al 2024 working papers).

## Signal math (baseline)

```
Universe: ~25 Mag7 + S&P large-cap names (final list locked after Phase 0
broker-symbol discovery; expected: AAPL MSFT GOOGL AMZN META NVDA TSLA JPM BAC
GS MS V MA UNH WMT HD LOW KO PEP JNJ CVX XOM ORCL CRM AVGO)

Earnings calendar: 4 events per name per year via yfinance ticker.earnings_dates
(or Tiingo/Polygon equivalents if Eightcap symbols don't map cleanly to yf).

Cost assumption: TBD by Phase 0; placeholder 5 bps RT for liquid single-stock
CFDs at Eightcap (Raw account). Sweep 2 / 5 / 10 / 15 bps in cost-sensitivity.

Per earnings event (whether ER was after prior close OR pre-open today):

  prior_close       = adjusted close on day D-1
  today_open        = first 09:30:00 ET print on day D
  gap_pct           = today_open / prior_close - 1.0

  if abs(gap_pct) < MIN_GAP_PCT (default 1.5%):
    skip (not a meaningful gap event)

  entry_window      = 09:30-09:35 ET (or first 5-min bar of RTH)
  entry             = SHORT if gap_pct > 0 (fade up-gap)
                      LONG  if gap_pct < 0 (fade down-gap)
  entry_price       = today_open

  stop              = entry_price ± STOP_GAP_FRAC * abs(gap_pct in $)
                      i.e. STOP at the 1.5x-gap-extension level
                      (default STOP_GAP_FRAC = 1.5)

  take              = none initially (time-based exit defines risk-symmetry)
  time_exit_min     = 60 minutes after entry (default; sweep 30/60/90/120)
  hard_exit         = 15:55 ET if still in trade (flat by 16:00 ET)

  Max 1 trade per name per event. No overlapping positions across events.
```

## Why retail-accessible

- **Intraday-only** → no overnight swap / SI charge / borrow cost.
- **Event-driven** → no continuous spread bleed (~100 setups/yr total across universe = ~2/week — well within typical daytrader cadence).
- **Single-stock CFDs on Eightcap** → confirmed broker has 613 stocks (memory: `reference_eightcap_broker_symbols.md`). Mag7 + bank names expected to be present.
- **Mechanism direction is the post-2020-active direction** → per lesson #39, pre-commit that fade is the deploy direction; mirror (continuation) is the null check.

## Universe

Phase 0 discovery target (~25 names spanning Mag7, banks, payments, retail, staples, pharma, energy, software):

- Mag7: AAPL MSFT GOOGL AMZN META NVDA TSLA
- Banks: JPM BAC GS MS
- Payments: V MA
- Health/retail/staples: UNH WMT HD LOW KO PEP JNJ
- Energy: XOM CVX
- Software: ORCL CRM AVGO

Final universe locks after Phase 0 confirms (a) symbol existence on Eightcap, (b) M5 history depth ≥ 5y, (c) median spread < 10 bps RT.

## Expected performance

Per-event gross: 50-150 bps (gap is large relative to ordinary spread; first 30-90 min retraces 30-60% of gap on average in academic samples).

Trade cadence: 4 events × ~25 names × ~5 backtest years = ~500 trades. ~100/yr ≈ 2/week. Above the 200-trade Phase 2 floor.

Expected research Sharpe (after honest 5-10 bp RT cost): **+0.5 to +1.0**. Expected live Sharpe after 10-25% haircut (per rewritten lesson #5): **+0.38 to +0.90**. Event-driven strategies may haircut wider than the canonical 10-25% band on continuous strategies — to be validated against 6-12 months of live data.

WR: target 55-60% (mean-reversion bias on a real signal). PF: 1.3-1.7.

## Fail conditions (pre-committed)

Phase 0 (data + cost discovery) kills if ANY:
- Fewer than 15 of the 25 target names are tradeable on Eightcap.
- M5 history depth on Eightcap stock CFDs < 3 years.
- **Median RT spread > 10 bps on the candidate basket median across deploy-relevant hours (13:30-15:00 UTC = 09:30-11:00 ET)**.

Phase 2 (backtest with honest costs) kills if ANY:
- Full-sample Sharpe < +0.30 after Phase-0-confirmed cost.
- Max DD > 25%.
- Trade count < 200 across the backtest window.
- WR < 45% AND PF < 1.1.
- **Direction null-check (mirror form per lesson #39): direction-gap (fade Sharpe − continuation Sharpe) < +0.30**. If gap ≤ −0.30, thesis is INVERTED (continuation wins) — tombstone with documented inversion; do NOT pivot to deploying continuation.

Phase 4 (regime stability) kills if Sharpe positive in ≤ 1 of 3 regime windows (2019-2020 pre/COVID / 2021-2022 vol / 2023-2026 holdout).

Phase 6 (holdout binding) kills if **2023-2026 holdout Sharpe ≤ 0**. Per lesson #25 — for an event-driven post-2020 mechanism, the recent regime is the load-bearing window because 0DTE/gamma amplification is itself a post-2022 phenomenon. If the mechanism is real-and-modern, holdout should be the BEST regime.

## Why this might fail (red flags)

1. **PEAD-day drift overwhelms the intraday fade window.** On strong-beat earnings, the gap continues all day — no fade. If only 40-50% of events fade and the rest run away, the win rate is too low.
2. **Single-stock CFD spreads at Eightcap may exceed expected 5 bps RT.** Retail single-stock CFD spreads on US tech names sometimes hit 10-30 bps. Phase 0 spread check is the binding gate.
3. **Earnings-day vol means stop sizing dominates.** A 1.5×gap stop on a 5%-gap event = 7.5% adverse move — losers can be very large. Per-trade variance is high; Sharpe could be killed by a few outlier-magnitude losses.
4. **Earnings calendar data quality is non-trivial.** yfinance earnings dates are imperfect; need to cross-check ahead of Phase 1.
5. **Lesson #5 haircut on a high-variance event strategy could be larger than the canonical 10-25% relative band that applies to continuous single-strategy deploys.** Slippage on the open-auction print + the 5-min entry window could each shave 1-3 bps per side. Event-driven multi-candidate books also stack selection-bias haircut on top (per RESEARCH_NOTES lesson #5 addendum 2026-05-24).
6. **Lesson #12 corollary**: published intraday results on cash equities don't port to retail single-stock CFDs without an explicit cost-and-execution check. Need real broker-confirmed spreads (Phase 0).
7. **Symmetry of fade direction**: down-gaps fade harder than up-gaps in some literature (asymmetric short-squeeze risk on up-gaps). Long-only / short-only split mandatory in Phase 2.

## Phase 1 → 2 plan

- [ ] **Phase 0a — Symbol discovery on Eightcap**: `_discover_stock_symbols.py` enumerates broker symbols for the 25-name target list and prints exact ticker formats + tradeable flag + min volume + point size.
- [ ] **Phase 0b — Broker spread distribution**: `_check_stock_spreads.py` — M1 bars across most-recent 30 days for each confirmed name; report median / p25 / p90 spread in bps for the deploy-relevant hours (13:30-15:00 UTC). Aggregate basket median and per-name table. Kill if basket median > 10 bps.
- [ ] **Phase 0c — M5 history depth**: per name, fetch M5 from 2018-01-01 and report first-bar date + bar count. Kill if < 3y depth on the median name.
- [ ] **Phase 1a — Earnings calendar**: pull yfinance earnings_dates per name; cross-check N events / 5y ≥ 15 per name (allows for IPO timing). Save to `data/earnings_calendar.csv`.
- [ ] **Phase 1b — M5 data fetch**: backfill all confirmed names into the datalake via mt5_fetch.py.
- [ ] **Phase 2 — Backtest**: `earnings_fade_demo.py` running the baseline + variant sweeps (MIN_GAP_PCT, stop, time exit) + regime + cost-sensitivity + null-check.
- [ ] **Phase 3+ if Phase 2 passes**: standard pipeline.

## Files

- Thesis: this file.
- Phase 0a discovery: `_discover_stock_symbols.py`
- Phase 0b spread check: `_check_stock_spreads.py`
- Phase 0c history depth: integrated into Phase 0a script
- Phase 1+ demo: `earnings_fade_demo.py` (not yet written; gate-locked behind Phase 0)

---

## Phase 2 results (2026-05-22)

Run command: `venv/Scripts/python.exe experiments/earnings_fade/earnings_fade_demo.py`

### Baseline (fade, MIN_GAP=1.5%, entry=bar1=09:35 ET, T+60min, stop=1.5× gap, cost=4 bp RT)

| Metric | Value | vs threshold |
|---|---|---|
| Period | 2018-02 → 2026-05 (8.3y) | — |
| Sharpe | **+0.37** | PASS |
| Max DD | -19.85% | PASS |
| Events | 320 (38.6/yr) | PASS |
| WR / PF | 53.4% / 1.10 | PASS |
| Avg win / loss | +1.14% / -1.19% | — |
| CAGR | +0.88% | — |

All 4 Phase 2 kill-criteria PASS at baseline level.

### Regime breakdown — Phase 6 KILL

| Window | n | Sharpe | MDD | CAGR |
|---|---|---|---|---|
| 2018-2020 pre/COVID | 7 | +7.70 | -0.7% | +3.2% |
| 2021-2022 vol | 82 | +1.51 | -6.6% | +12.4% |
| **2023-2026 holdout** | **231** | **-0.22** | **-19.9%** | **-4.2%** |

Pre-2021 window is n=7 (essentially AMZN-only — most names' M5 history starts Sept 2021). Decision-relevant cut is 2021-22 vs 2023-26 holdout. **Δ = -1.73 Sh** between adjacent regimes — exactly the 0DTE-amplification signature from lesson #28.

### Direction null-check — PASS (mechanism real)

| Direction | Sharpe | MDD | WR |
|---|---|---|---|
| Fade (baseline) | +0.37 | -19.85% | 53.4% |
| Continuation (null) | -0.97 | -33.06% | 43.4% |

**Direction-gap = +1.35.** Cleanly above the pre-committed +0.30 threshold. The fade direction has real directional content (and the mirror loses decisively) — the mechanism IS sign-correct. The kill is regime decay, not noise.

### Variant sweeps

| Lever | Best variant | Sharpe | Notes |
|---|---|---|---|
| MIN_GAP_PCT | 5.0% | +0.98 | only 122 events; cherry-pick risk |
| MIN_GAP_PCT | 3.0% | +0.53 | 220 events; mild sweep — keeps directional content |
| TIME_EXIT_MIN | T+120min | +0.46 | tighter exit better; T+15 LOSES (-0.24) — fade plays out >30min |
| STOP_GAP_FRAC | 2.0× / 3.0× / 5.0× | +0.42 | stop barely binding past 1.5× |
| Cost | 0 bp / 2 bp / 4 bp / 8 bp | +0.64 / +0.51 / +0.37 / +0.11 | linear decay; Phase-0-confirmed 2 bp is real headroom |

Sweeps mostly confirm baseline; no overlay rescues the holdout.

### LONG/SHORT split (full sample)

| Leg | n | Sharpe | MDD | WR |
|---|---|---|---|---|
| LONG (fade DOWN-gaps) | 143 | +0.36 | -21.49% | 53.1% |
| SHORT (fade UP-gaps) | 177 | +0.38 | -18.93% | 53.7% |

Two-sided thesis confirmed at full-sample. Asymmetry only appears in holdout — see dissection (e) below.

## Holdout dissection (`_holdout_dissection.py`)

### (a) Per-ticker holdout — worst-to-best

Big losers: TSLA -15.26% (n=13, WR 30.8%), NVDA -6.85%, UNH -5.15%, BAC -4.63%, MSFT -3.53%, JNJ -3.36%, PEP -2.94%, META -1.96%, AVGO -1.42%, CVX -1.02%.

Big winners: CRM +7.52% (WR 90%!), MA +6.25%, AAPL +5.31%, XOM +4.79%, HD +2.93%, GS +2.91%, JPM +2.86%, LOW +2.57%.

The TSLA drag alone is -15.26% of the basket's holdout PnL. TSLA + NVDA + MSFT collectively account for -25.64% of the holdout damage on n=35 events — that's the heart of the failure.

### (b) Mag7 vs non-Mag7 split (THE diagnostic)

| Sub-universe | n | Sharpe | MDD | WR |
|---|---|---|---|---|
| **Mag7 holdout** (AAPL MSFT GOOGL AMZN META NVDA TSLA) | 84 | **-1.67** | -20.66% | 46.4% |
| **non-Mag7 holdout** (17 names) | 147 | **+0.67** | -14.74% | 53.1% |

**Δ = +2.34 Sharpe between sub-universes.** This is the canonical post-2022 0DTE-options-concentration signature.

### (c) |gap| magnitude bucket (holdout only)

| Bucket | n | Sharpe | WR |
|---|---|---|---|
| 1.5-2.5% | 53 | -0.65 | 52.8% |
| **2.5-3.5%** | **44** | **+0.58** | 52.3% |
| **3.5-5.0%** | **43** | **+0.88** | 55.8% |
| 5.0-8.0% | 41 | -0.20 | 41.5% |
| 8.0-25% | 49 | -0.84 | 51.0% |

**The signal lives in the 2.5-5% mid-gap bucket.** Small gaps (<2.5%) are inside friction; very large gaps (>5%) are real fundamental moves that continue, not noise that fades. Consistent with the underlying mechanism (overshoot of an *information-driven* move, not the move itself).

### (d) Holdout by year — non-monotonic but lower-trend

| Year | n | Sharpe |
|---|---|---|
| 2023 | 65 | -0.27 |
| 2024 | 70 | +0.34 |
| 2025 | 65 | -0.03 |
| 2026 (partial) | 31 | -1.64 |

2026-YTD (5 months partial) is catastrophic. Recency-skew. Either a true acceleration of decay or sampling noise from 31 events.

### (e) LONG vs SHORT (holdout)

| Leg | n | Sharpe | MDD | WR |
|---|---|---|---|---|
| LONG (fade DOWN-gaps) | 107 | -0.58 | -21.49% | 47.7% |
| SHORT (fade UP-gaps) | 124 | +0.12 | -14.26% | 53.2% |

Holdout asymmetry: fading UP-gaps (SHORT side) is still mildly positive in modern regime; fading DOWN-gaps (LONG side) is negative. Down-gaps on Mag7-style names now CONTINUE (retail FOMO + algo-flow on bad earnings carries the move all session) — fading them gets run over. This is mechanistically consistent: post-2022 0DTE-options gamma flow accelerates negative-surprise moves more than positive-surprise moves (puts are bid more aggressively pre-earnings → MMs short more gamma on the downside → bigger hedge-into-move on a miss).

### (f) Combined post-hoc filter (non-Mag7 + |gap|>=3.0%) — holdout only

n=88, **Sharpe +0.94**, MDD -9.54%, WR 52.3%. Strong but a 2-filter post-hoc selection on a 231-event sample → high overfit risk. Treated as a candidate for a fresh thesis, not as a within-experiment refinement.

### (g) FULL-SAMPLE non-Mag7 re-run

| Window | n | Sharpe | MDD |
|---|---|---|---|
| Full | 197 | **+0.81** | -14.74% |
| 2021-2022 | 50 | +1.22 | -5.65% |
| **2023-2026 holdout** | **147** | **+0.67** | -14.74% |
| 2018-2020 | 0 | — | (empty: data coverage) |

Non-Mag7 sub-universe would pass 2/3 available regimes and the holdout convincingly. **But this is post-hoc** — restricting universe after seeing results is the canonical fitted variant per lesson #20 ("marginal strategies don't become non-marginal through refinement").

---

## Verdict: REJECT (with documented pivot candidate)

### REJECT reasoning (pre-committed kill-criteria)

- Pre-commit (Phase 6, binding): 2023-2026 holdout Sharpe > 0. Observed: **-0.22**. **KILL.**
- Pre-commit (Phase 4, 3/3 regimes): only 2 of 3 regimes have meaningful n; 2 of 2 isn't decisive when one is the holdout. Not load-bearing on its own.
- Phase 2 kill-criteria all PASS, but Phase 6 binds.
- Direction null-check PASSES strongly (+1.35), so this is a **regime-decay REJECT** in the lesson #25 / lesson #28 family, not a no-signal REJECT.

### Pivot candidate (DO NOT spin up as a refinement)

**`earnings_fade_nonmag7`** as a NEW experiment, requiring its own pre-committed kill-criteria and walk-forward validation:

- Universe: 17 non-Mag7 names (JPM BAC GS V MA UNH WMT HD LOW KO PEP JNJ XOM CVX ORCL CRM AVGO).
- Mechanism: same fade hypothesis, but explicit ex-ante claim that the 0DTE-options arbitrage that killed Mag7 fades does NOT extend to lower-OI names yet.
- Pre-committed walk-forward (per lesson #29): rolling 3y-IS / 2y-OOS splits — must average OOS Sh >= +0.30, with no individual OOS window below 0.
- LONG/SHORT split pre-committed: deploy SHORT-only if holdout asymmetry (e) replicates on the non-Mag7 sub-universe.
- Pre-committed |gap| filter: probably 2.5-5.0% mid-bucket per (c), or 1.5%+ untouched.

**Critical**: this is a candidate scope for a future spin-up, NOT a within-experiment pivot. Do NOT promote the (g) non-Mag7 result as the deploy strategy without spinning a fresh pre-committed thesis. Per lesson #20 (NDX100 ORB refinement) and the lumber_oats rule, choosing the winning sub-variant post-hoc is the canonical overfit pattern.

### Lesson for [RESEARCH_NOTES.md](../../docs/RESEARCH_NOTES.md)

Single-stock earnings-gap fade on 0DTE-options-dominated names (Mag7) has been arbed out post-2022. The mechanism still works on lower-OI large-caps. Cross-checks: dir-gap +1.35 (signal is real, sign is right), holdout sub-universe split shows -1.67 (Mag7) / +0.67 (non-Mag7). Generalizes: any "intraday fade" thesis on Mag7 single-name 2023+ should pre-commit the non-Mag7 control as the deploy bar, not the full universe.

## Files

- Thesis: this file.
- Phase 0 spread check: `_check_stock_spreads.py`
- Phase 1 earnings calendar fetch: `_fetch_earnings_calendar.py` -> `data/earnings_calendar.csv`
- Phase 2 demo: `earnings_fade_demo.py`
- Phase 6 dissection: `_holdout_dissection.py`
- Data: `ohlc_data/<TICKER>_M5.csv` × 24 names, pushed to datalake on backfill 2026-05-22.

## References

- So, E., Wang, S. (2014). "News-driven return reversals: Liquidity provision ahead of earnings announcements." *Journal of Financial Economics* 114(1).
- Berkman, H., Koch, P. D., Tuttle, L., Zhang, Y. J. (2012). "Paying attention: overnight returns and the hidden cost of buying at the open." *Journal of Financial and Quantitative Analysis* 47(4).
- Bernard, V. L., Thomas, J. K. (1989). "Post-earnings-announcement drift: Delayed price response or risk premium?" *Journal of Accounting Research* 27.
- Brogaard, J. et al (2024, WP). "Zero-day-to-expiry options and intraday return predictability."
