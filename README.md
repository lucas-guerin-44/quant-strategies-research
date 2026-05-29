# quant-strategies-research

**A pipeline for killing bad trading-strategy ideas fast (and running the few that survive)**
   
 ‎ ‎ ‎   
   
| 101 | 82 | 7+1 | 87 | 8 |
|:---:|:---:|:---:|:---:|:---:|
| **strategies tested** | **tombstoned** (81%) | **live** (7 strict + 1 watchlist) | **methodology lessons** | **-phase pipeline** |
   
 ‎ ‎ ‎  
   
> **Reject rate: 81%.** Each tombstoned strategy ships with a post-mortem naming the failure mode. The few that survived the pipeline are the ones I trust.

Every idea runs through the same 8 phases with kill criteria set *before* the backtest. Bad theses die in hours, not weeks. Survivors go to MT5 paper trading with a research-vs-live calibration loop ([`docs/STATE_GRAVEYARD.md`](docs/STATE_GRAVEYARD.md) is the public log of each death and its failure mode).

Built on [`backtesting-engine-2.0`](https://github.com/lucas-guerin-44/backtesting-engine). The engine stays clean; this repo is allowed to be messy.

---

## Table of contents

- [Navigating this repo (humans & agents)](#navigating-this-repo-humans--agents)
- [The pipeline](#the-pipeline)
- [Current status](#current-status)
- [Deployment platform](#deployment-platform)
- [Repo layout](#repo-layout)
- [Setup](#setup)
- [Running an experiment](#running-an-experiment)
- [Data fetching](#data-fetching)
- [Key lessons from the graveyard](#key-lessons-from-the-graveyard)

---

## Navigating this repo (humans & agents)

**Public vs private.** This repo is committed, but edge-bearing detail is gitignored.  
*Public* = the pipeline, the methodology lessons, the graveyard, and the book at **aggregate** level.  
*Private* (gitignored: `experiments/_live/`, `live_tracking/`, `deploy/`, `ohlc_data/`, `live_data/`) = per-strategy thesis / params / sizing / EA and live tracking.  

**The book is the public unit; the legs are private.**

**Which doc answers what** — load the cheap index, fetch detail on demand:

| Question | Where |
|---|---|
| The process & kill criteria | [`docs/WORKFLOW.md`](docs/WORKFLOW.md) |
| Where are we now — what's live / validated / rejected? | [`docs/STATE.md`](docs/STATE.md) (one-line index) |
| Why did *X* fail? | [`docs/STATE_GRAVEYARD.md`](docs/STATE_GRAVEYARD.md) → its thesis doc |
| Why did *X* fail? (public post-mortems) | [`docs/STATE_GRAVEYARD.md`](docs/STATE_GRAVEYARD.md) |
| What have we learned (cross-experiment)? | `docs/RESEARCH_NOTES.md` (numbered lessons — **private/local-only**; names live mechanisms) |
| Live-book posture (sizing tiers, gates, cadence, fears) | `docs/BOOK_PLAN.md` (**private**) |
| Deploy an EA / connect to the VPS | `docs/mq5_deploy.md`, `docs/vps_connect.md` (**private**) |
| How an agent should *work* here (conventions, don'ts) | `CLAUDE.md` (**private**, auto-loaded each session) |

**Agent query pattern:** grep the index (STATE rows, lesson titles) → open only the one thesis doc or lesson you need.  
Don't read `RESEARCH_NOTES.md` end-to-end — it's a log; grep it. `CLAUDE.md` is *how to work here*; this README is *what this is and where things live* — they don't overlap.

---

## The pipeline

8 phases, in order. Fail one, write the tombstone, move on. Full thresholds in [`docs/WORKFLOW.md`](docs/WORKFLOW.md).

| Phase | What | Kill if... |
|---|---|---|
| **1. Thesis** | One-page doc: mechanism, retail-accessibility argument, universe, signal math, expected Sharpe range, pre-committed fail conditions. Before any code. | No credible mechanism, no retail-accessibility story, or literature Sharpe < 0.3 at institutional scale (retail drag removes 0.2-0.4 Sharpe → you'd live-trade at zero). |
| **2. MVI** | Single-file backtest, full sample, realistic costs in bps, fixed params. Produces Sharpe, MDD, trade count, regime slice. | Sharpe < 0 full-sample, trades < 50, MDD > 50%, or total return < buy-and-hold. |
| **3. Stat battery** | Bootstrap CI on Sharpe, permutation test on positioning (not just returns), Deflated Sharpe adjusted for N variants tried. | Bootstrap 95% CI includes 0, deflated SR p > 0.05. |
| **4. Regime stability** | Split sample into 4 non-overlapping windows. Strategy should not depend on any one era. | < 3 of 4 windows Sharpe-positive, or > 80% of lifetime return concentrated in one window. |
| **5. Parameter sensitivity** | Sweep each parameter ±20%. Honest result is a plateau; a peak is overfit. | Sharpe drops > 50% on any ±20% perturbation, or any config goes negative. |
| **6. True holdout** | Pick a cutoff after development and re-run on untouched post-cutoff data. | OOS Sharpe degrades by > 0.5 vs IS, or OOS Sharpe < 0. |
| **7. Cross-strategy correlation** | Correlation vs existing live/validated strategies. | Monthly correlation > 0.3 — unless it wins standalone enough to justify adding as a 2nd bet on the same theme. |
| **8. Live** | Port to broker platform (MT5 for intraday is the only live path as of 2026-05). Paper-trade 3-6 months. | Live Sharpe trails research by > 25% (relative) haircut. Empirical haircut for clean same-broker single-strategy deploys is 10-25%; multi-strategy event books and CFD→futures porting can stack worse — see `docs/RESEARCH_NOTES.md` lesson #5 for the rewritten framing. To be validated against 6-12 months of live data per deploy. |

Thresholds err on the strict side. A premature reject costs a tombstone doc. A false accept costs real money to learn the same lesson.

---

## Current status

### Live (MT5 VPS)

7 strict-PASS strategies + 1 watchlist-paper-deploy (`pre_boj_drift`, half-size, C2/C5 re-clearance trigger by 2026-12-18). Mix of intraday breakout/fade, scheduled-macro-event drift, structural-flow (quarter-end rebalance), and pre-CB-event carry-maintain (USDJPY pre-BoJ) across GER40, NDX100, XAUUSD, and USDJPY. Per-strategy specifics (thesis, params, sizing, EA) are private.

Aggregate book metrics from the internal portfolio_risk_parity audit (inv-vol sizing, monthly rebal, [5%,35%] clip):

| Metric | Equal-weight | Risk-parity | Realistic live (after blended haircut) |
|---|---|---|---|
| Annualized book Sharpe | +2.19 | **+2.57** | **+1.6 to +2.0** |
| Book CAGR (at audit notional) | +2.62% | +2.26% | depends on live sizing — see below |
| Book MDD (at audit notional) | -0.99% | -0.63% | -2% to -5% (1.5-3× research, regime/small-n) |
| Time-in-DD | 83.2% | 79.8% | similar |
| Cross-strategy max pairwise corr | all in [-0.15, +0.15] | same | < 0.30 expected live |
| Regime stability (4-window Sh, RP) | 4/4 positive | W1 +2.58 / W2 +1.67 / W3 +3.85 / W4 +2.37 | holdout-positive ≠ live-positive; validate over 6-12 months |

All 7 strategies have been live less than 6 months (newest `quarter_end_xau_short` 2026-05-27; first quarterly fire 2026-06-30). Total live trades across the book are still under ~200, so σ(realized Sharpe) ≈ 0.7 — the +1.6 to +2.0 column is a modeled prior, not a measurement. Year-one realized Sharpe will plausibly land anywhere in +1.2 to +2.4 on noise alone. Real validation horizon is 6-12 months of concurrent live data.

Sizing tiers, validation gates, review cadence, and the honest fears list are in [`docs/BOOK_PLAN.md`](docs/BOOK_PLAN.md) (private).

### Validated but not deployed

Two strategies cleared Phases 2-7 but are broker-blocked: **treasury_trend** (no US Treasury CFDs on the broker) and **softs_ensemble** (D1 history depth on broker too short for the 12M lookback). Both research traces are in `experiments/<name>/`.

### Rejected

82 tombstoned strategies with documented post-mortems. Full table in [`docs/STATE_GRAVEYARD.md`](docs/STATE_GRAVEYARD.md). The patterns that recur — sign-inversion on post-2022 US-index MR, CFD-vs-cash-equity cost gaps, regime-decay on factor strategies — are written up as numbered lessons in `docs/RESEARCH_NOTES.md` (private/local-only).

---

## Deployment platform

MetaTrader 5 on a Hetzner VPS, MQL5 EAs, daily Telegram summary via cron.  
Autonomous 24/7 once attached.  
EA source and ops runbooks are private.

Broker asset access is wide: FX, index CFDs, single-stock CFDs, commodity CFDs, bond CFDs, BTC. The binding constraint is **data-source revalidation**. Research run on Yahoo/Tiingo continuous-futures or cash-ETF data has to be re-run on the broker's MT5 feed before deploy. CFD construction differs enough from cash-equivalent or continuous-front that the edge can vanish (see `dax_overnight` in lesson #22 — research Sh +0.80, FDAX futures Sh -0.34).

---

## Repo layout

```
quant-strategies-research/
├── experiments/             # One subdir per strategy (thesis .md + demo/validation .py)
│   ├── <rejected>/               # ~30 tombstoned experiments — the public examples of the pipeline
│   ├── treasury_trend/           # Validated Phases 2-7, broker-blocked
│   ├── softs_ensemble/           # Validated Phases 2-6, broker-blocked
│   └── _live/                    # Deployed strategies (private, gitignored)
├── scripts/                 # Data fetchers + shared helpers
│   ├── mt5_fetch.py              # MT5 broker (FX, CFDs, indices, intraday)
│   ├── yahoo_fetch.py            # Yahoo (futures, ETFs)
│   ├── tiingo_fetch.py           # Tiingo (US equities)
│   ├── fred_fetch.py             # FRED (interest rates)
│   └── _datalake.py              # Datalake client
├── ohlc_data/                # Local OHLC cache (gitignored)
└── docs/
    ├── WORKFLOW.md               # The 8-phase pipeline definition
    ├── STATE.md                  # Per-experiment verdicts + headline numbers
    ├── STATE_GRAVEYARD.md        # Tombstoned strategies with failure modes
    └── RESEARCH_NOTES.md         # Cross-experiment methodological lessons
```

Per-strategy file convention:

| Stage | File |
|---|---|
| Thesis | `experiments/<name>/<name>.md` |
| Phase 2 demo | `experiments/<name>/<name>_demo.py` |
| Phase 3-6 validation | `experiments/<name>/<name>_validation.py` |
| Engine `Strategy` subclass (optional) | `experiments/<name>/<name>_strategy.py` |
| Phase 8 deploy | private (MT5 EA on VPS) |

Most strategies are standalone pandas/numpy sims in `_demo.py`. The engine `Strategy` subclass is used by TSMOM and imbalance.

---

## Setup

Expects [`backtesting-engine-2.0`](../backtesting-engine-2.0/) as a sibling directory:

```
finance/
├── backtesting-engine-2.0/    ← the engine (event-driven core)
└── quant-strategies-research/ ← this repo (thesis docs, demos, deploy)
```

Python 3.11+ recommended. From this repo's root:

```bash
python -m venv venv
venv\Scripts\activate       # Windows
# source venv/bin/activate  # Linux/Mac
pip install -r requirements.txt
pip install -e ../backtesting-engine-2.0
```

Experiment scripts add the engine repo to `sys.path` via a common bootstrap so imports work regardless of install state.

---

## Running an experiment

Demos report Phase 2 stats; validations handle Phases 3-6. Example session:

```bash
# Phase 2 (MVI) — single-file backtest, realistic costs
python experiments/softs_ensemble/softs_ensemble_demo.py

# Phase 3 (stat battery) — bootstrap CI, permutation, deflated Sharpe
python experiments/softs_ensemble/softs_ensemble_validation.py

# Phases 4-5-6 combined (regime + sensitivity + holdout)
python experiments/softs_ensemble/softs_ensemble_regime_sens_oos.py

# Screener: scan 26 trend-prone instruments for best single-instrument fit
python experiments/gold_trend/single_instrument_scan.py
```

Deployed-strategy research is private (full thesis, params, demos, EAs). The rejected experiments under `experiments/<name>/` are the public examples of the pipeline applied end-to-end.

---

## Data fetching

OHLC CSVs live in `ohlc_data/` (gitignored — too large to version, reproducible from fetchers). Populate as needed:

```bash
# Daily bars via MT5 terminal (FX, CFDs, indices)
python scripts/mt5_fetch.py --symbols AUDNZD,NZDCAD,GBPNZD --timeframes D1 --from 2015-01-01

# Intraday bars for ORB / other intraday work
python scripts/mt5_fetch.py --symbols GER40,NDX100,SPX500 --timeframes M5 --from 2019-01-01

# Softs / grains / meats via Yahoo Finance (daily)
python scripts/yahoo_fetch.py --symbols COCOA,COFFEE,COTTON,CORN,SOYBEAN,LIVE_CATTLE --timeframes D1 --from 2015-01-01

# US equities via Tiingo (when Yahoo rate-limits)
python scripts/tiingo_fetch.py --symbols KO,PEP,XOM --from 2015-01-01

# Interest rates for FX carry
python scripts/fred_fetch.py
```

---

## Key lessons from the graveyard

A short public selection. The full numbered list (87 lessons) is private (`docs/RESEARCH_NOTES.md`, local-only).

1. **Low correlation ≠ useful diversifier.** A strategy with correlation 0.1 and negative Sharpe subtracts from your book. Correlation alone doesn't justify inclusion; positive standalone Sharpe does.

2. **Negative IS-OOS degradation is not automatic good news.** If every strategy you've tested has OOS > IS, a common regime is juicing the OOS — the honest long-run estimate is the IS number, not the OOS or full-sample.

3. **"Different mechanic, same universe" = same bet.** TSMOM and XS-mom on the same instruments correlated +0.69 despite opposite-looking math. For real diversification you need a different factor OR a different market.

4. **Research-to-live Sharpe haircut is typically 10-25% relative for clean single-strategy same-broker deploys** — not the 50-70% / 0.3-0.6-absolute number this lesson originally claimed. The XS-mom 0.92 → 0.35 QC observation that anchored the old wording was inflated by (a) Sharpe-formula mismatch (QC reports rf-subtracted, research reports raw — worth ~0.2-0.3 absolute alone) and (b) cross-platform porting drag (CFD research → QC futures execution model). See `docs/RESEARCH_NOTES.md` lesson #5 for the full rewrite. To be re-validated against 6-12 months of live data per deploy.

5. **Regime decay ≠ bad strategy, but still a REJECT.** VIX VRP had Sharpe 1.14 in 2015-2017 and -0.19 in 2024-2026. Forward-looking window is all that matters for deployment; "worked in the right era" doesn't get a pass.

6. **Weight literature decay warnings heavily.** Equity pairs cited Gatev/Goetzmann/Rouwenhorst's 1962-2002 result AND Do & Faff's post-2002 decay work. Estimated Sharpe 0.4-0.7; actual -0.99. The decay warning deserved more weight than the canonical number.

7. **Diversifiers shouldn't be judged on standalone CAGR.** Treasury-trend active return over cash is +0.25%/yr — underwhelming alone. But Sharpe 0.54, MDD -9%, caught 2022 cleanly, ~0 correlation with XS-mom. Judge diversifiers on whether they help the existing book in the regimes where the existing book hurts.

8. **Match filter speed to asset duration.** Same 252-day TSMOM on TLT (~18y dur, ~15% vol) gave Sharpe 0.14; on IEF (~8y dur, ~7% vol) gave 0.54. TLT's vol creates 10-15% drawdowns in the 6-month filter-lag window that IEF's lower vol absorbs.

9. **The permutation test has to test the right null.** Shuffling a return series preserves its mean and std exactly — meaningless for continuous-weight strategies. For TSMOM-style work, use a **position-shuffle** test: shuffle the daily weights, preserve returns, recompute P&L — tests "does the timing of the position choices add value?"

10. **Extend the sample before accepting a marginal bootstrap result.** IEF Phase 3 on 11 years: bootstrap 95% CI was [-0.028, +1.138] — a near-miss. Extended to 24 years (IEF inception 2002), CI became [+0.26, +1.08], Sharpe 0.55 → 0.67. An overfit strategy loses Sharpe on extension; a real edge gains.

11. **Intraday CFD costs ≠ cash-equity costs.** ORB on SPX500 M5 failed at Sharpe -0.92 against Zarattini/Aziz (2023) reporting +1.65-2.81 on QQQ. CFD spread ≈ 2× their commission assumption; no real share volume for filters; different instrument. Published intraday results on cash equities don't port 1-1 to retail CFDs even when the mechanism nominally translates.

12. **Don't tombstone based on fade-test alone — retest under symmetric R:R first.** An index opening-range strategy first looked like an exit-structure artifact (baseline and fade Sharpes nearly equal under EOD exit). Under fixed 1:1 R:R exits the directional signal separated cleanly — baseline positive, fade sharply negative. EOD-exit with a fixed stop is itself a confound; this retest saved a real intraday edge the fade-test would have killed.

13. **Cross-instrument fade test separates signal from exit-structure artifact.** Running the same mechanism across several index CFDs, the one with the highest absolute Sharpe had near-zero fade-gap under EOD exit (artifact), while one with lower absolute Sharpe showed a clearly positive fade-gap (real signal). Fade-gap is a better edge-quality indicator than absolute Sharpe.

14. **Time-of-day exit as an alpha discovery tool.** Shifting an index opening-impulse strategy from EOD exit to a few-hours-after-open exit materially raised its Sharpe — the opening-impulse edge has a ~3-hour half-life, and holding to the close just accumulates noise. For any intraday strategy that exits "at EOD because the literature does", sweep T+60/120/180/240min; the edge is often diluted by over-holding.

---

## Further reading

- [`docs/STATE.md`](docs/STATE.md) — per-experiment verdicts + headline numbers. Start here.
- `docs/RESEARCH_NOTES.md` — 87 cross-experiment lessons (**private/local-only**). Read before designing a new thesis.
- [`docs/WORKFLOW.md`](docs/WORKFLOW.md) — the 8-phase pipeline with kill thresholds.
- `experiments/<name>/<name>.md` — strategy-specific thesis, validation, and tombstone.
