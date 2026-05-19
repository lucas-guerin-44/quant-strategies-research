# quant-strategies-research

**A pipeline for killing bad trading-strategy ideas fast (and running the few that survive)**

Most retail trading research is self-deception: elegant backtests that work beautifully on the sample they were built on, then lose money live when the costs, the regime shift, or the data-snooping you didn't know you were doing all show up at once. This repo is a system for not being that person.

Every idea runs the same 8-phase pipeline with **pre-committed kill criteria** at each stage. Flawed theses die in hours, not weeks. Surviving strategies are paper-traded live with an honest research-vs-live calibration loop. The record of what died and why (see [`docs/RESEARCH_NOTES.md`](docs/RESEARCH_NOTES.md)) is as load-bearing as the few that lived.

Built on top of [`backtesting-engine-2.0`](https://github.com/lucas-guerin-44/backtesting-engine). The engine repo stays clean; this one is allowed to be messy — thesis docs, demo scripts, failed validations, and tombstoned strategies sit alongside the live-deployable ones.

---

## Table of contents

- [The pipeline](#the-pipeline)
- [Current status](#current-status)
- [Deployment targets](#deployment-targets)
- [Repo layout](#repo-layout)
- [Setup](#setup)
- [Running an experiment](#running-an-experiment)
- [Data fetching](#data-fetching)
- [Key lessons from the graveyard](#key-lessons-from-the-graveyard)

---

## The pipeline

Every strategy — surviving or tombstoned — runs these 8 phases in order. A failure at any phase triggers a tombstone doc and the strategy is abandoned. This is intentional: the cost of one bad live trade vastly exceeds the cost of one premature rejection.

Full definition with exact thresholds in [`docs/WORKFLOW.md`](docs/WORKFLOW.md).

| Phase | What | Kill if... |
|---|---|---|
| **1. Thesis** | One-page doc: mechanism, retail-accessibility argument, universe, signal math, expected Sharpe range, pre-committed fail conditions. Before any code. | No credible mechanism, no retail-accessibility story, or literature Sharpe < 0.3 at institutional scale (retail drag removes 0.2-0.4 Sharpe → you'd live-trade at zero). |
| **2. MVI** | Single-file backtest, full sample, realistic costs in bps, fixed params. Produces Sharpe, MDD, trade count, regime slice. | Sharpe < 0 full-sample, trades < 50, MDD > 50%, or total return < buy-and-hold. |
| **3. Stat battery** | Bootstrap CI on Sharpe, permutation test on positioning (not just returns), Deflated Sharpe adjusted for N variants tried. | Bootstrap 95% CI includes 0, deflated SR p > 0.05. |
| **4. Regime stability** | Split sample into 4 non-overlapping windows. Strategy should not depend on any one era. | < 3 of 4 windows Sharpe-positive, or > 80% of lifetime return concentrated in one window. |
| **5. Parameter sensitivity** | Sweep each parameter ±20%. Honest result is a plateau; a peak is overfit. | Sharpe drops > 50% on any ±20% perturbation, or any config goes negative. |
| **6. True holdout** | Pick a cutoff after development and re-run on untouched post-cutoff data. | OOS Sharpe degrades by > 0.5 vs IS, or OOS Sharpe < 0. |
| **7. Cross-strategy correlation** | Correlation vs existing live/validated strategies. | Monthly correlation > 0.3 — unless it wins standalone enough to justify adding as a 2nd bet on the same theme. |
| **8. Live** | Port to broker platform (QC for daily, MT5 for intraday). Paper-trade 3-6 months. | Live Sharpe trails research by > 70% haircut (empirical retail drag is 0.3-0.6 absolute Sharpe, worse at higher frequency). |

The numbers are intentionally conservative. Over-strict criteria kill some real-edge strategies; over-lenient criteria let fake-edge strategies through to live trading where the lesson costs money. The project explicitly biases toward the former.

---

## Current status

### Live (MT5 VPS, paper)

| Strategy | Instrument | Research Sh | Live Sh | Notes |
|---|---|---|---|---|
| **ORB DAX M5 (T+180 LONG-only)** | GER40 CFD | 0.76 | TBD | First live deploy (2026-04-22). LONG-only is the strong leg (shorts shadow-logged). Fade-gap +1.04 under symmetric R:R. 2023-2026 holdout Sh +0.93. Cadence ~3.8/week. |
| **NDX100 lunch-hour fade (LONG-only)** | NDX100 CFD | 1.02 (LONG-only, holdout +1.51) | TBD | Second live deploy (2026-05-13). Selective outlier-day strategy — ~16 LONG trades/year. Dir-gap +1.87, exceptionally cost-insensitive (Sh +0.72 even at 5pt RT). |

### Retired from live

| Strategy | Was on | Retired | Notes |
|---|---|---|---|
| **XS-momentum long-only** | QC/IB paper (research Sh 0.92 → live 0.35) | 2026-05 | Retired alongside the QC-as-live-platform decision. Canonical research-to-live-haircut reference (-0.57 Sh absolute drag). |

### Validated phases 2-7, deploy blocked by broker access

Both strategies were researched on Yahoo/Tiingo D1 data and targeted at QC. With QC retired, deploy on MT5 requires the broker to carry the underlying. Status as of 2026-05-13:

| Strategy | Instruments | Research Sh | Broker (Eightcap) status |
|---|---|---|---|
| **Treasury trend (IEF-MH)** | IEF / TLT / BIL / SHY (US Treasury ETFs) | 0.67 (full) / 0.42 (holdout) | **BLOCKED** — no US Treasury CFDs on Eightcap. Research preserved; shelved unless alternative broker or duration-proxy reframe found. |
| **Softs TSMOM ensemble** | COCOA + COFFEE + COTTON + CORN (broker subset of original 6-leg; SOYBEAN+LIVE_CATTLE absent on broker, LDSUGAR+WHEAT available as bonus) | 0.85 (full) / 1.44 (holdout) | 4/6 confirmed tradeable on Eightcap 2026-05-13. Next: pull broker D1 via `scripts/mt5_fetch.py`, re-run `softs_ensemble_demo.py` on broker data, write MT5 EA. Ensemble survives a 3-leg subset per orig thesis. |

### Rejected (tombstoned with documented reasons)

Full details in each strategy's `experiments/<name>/<name>.md`.

| Strategy | Phase killed | Root cause |
|---|---|---|
| BTC trend | Phase 8 blend | Research Sh 0.93 standalone, QC blend Sh 0.43 vs 0.90 threshold. Correlation inflated under real execution. |
| Gold trend (XAUUSD) | Phase 2 | α ≤ buy-and-hold on every metric 2015-2026. |
| ORB SPX500 / UK100 / EUSTX50 | Phase 2 | All 3 REJECT. SPX no directional content; UK100 no opening-impulse mechanism; EUSTX50 fragmented across 4 venues. |
| ORB NDX100 | Phase 4 | Baseline Sh +0.03, only +0.19 in holdout. Real but too weak. |
| NDX100 mean-reversion (z-score / BB / pre-close drift) | Phase 2 | 4 independent generic-pattern triggers all REJECT despite real fade-gaps. CFD friction is binding; only structural-microstructure (lunch fade) extracts edge. |
| DAX z-score momentum / EOD-unwind / overnight / pre-auction / US-lead / gap-fade | Phases 2-4 | Six DAX intraday/overnight theses tested 2026-04, all REJECT. ORB is the only DAX edge that survived. DAX overnight specifically: CFD-data artifact, FDAX futures Sh -0.34. |
| Pre-close MOC drift (SPX500/NDX100/GER40) | Phase 2 | All 3 venues REJECT. Mechanism real on NDX (dir-gap +0.74) but ~5 bps gross effect eaten by ~2.5 bps CFD spread. Not retail-extractable at M5+CFD on any major index. |
| Lumber+Oats TSMOM | Phase 2 | Sign error: 12-1 mom long-only Sh +0.18, fade Sh +0.52 (gap +0.35 wrong way). Physical-supply commodities mean-revert, not trend. |
| VIX term-structure (VRP) | Phase 4 | Sh 1.14 in 2015-2017, collapsed to -0.19 in 2024-2026 post-vol-compression regime. |
| Equity pairs (mega-cap US) | Phase 2 | Sh -0.99 across 10 pairs, all 5 regime windows negative. Academic half-life of pairs ran out post-2002. |
| FX carry / FX carry+trend / FX MR | Phase 2-4 | Post-2015 FX crosses are a graveyard for non-momentum factors. |
| Dual momentum | Phase 2 | IS return negative even with realistic costs. |

The rejection pile is *product*, not waste. It tells you which market-mechanism narratives are still alive in retail reality vs. which are cargo-culted from papers that worked in a different era.

---

## Deployment platform

**MetaTrader 5 on a rented VPS** — the only live platform. Strategy code is MQL5 Expert Advisors. Runs MT5 terminal under Wine on a Hetzner VPS (~€8/mo), accessed via SSH + VNC for debugging, sends a daily Telegram summary via cron. Autonomous 24/7 once attached. Live EA source and operational runbooks are kept private.

**QuantConnect / Interactive Brokers** is **NOT a live platform anymore** (as of 2026-05). The previous QC paper deploy of `xs_momentum` has been retired. New strategies need an MT5 EA to count as deployed.

**Asset access** is wide on a typical retail MT5 broker — FX, index CFDs, single-stock CFDs, commodity CFDs (incl. softs), bond CFDs, BTC. Anything we have OHLC data for in `ohlc_data/` is in principle tradeable on the broker, including data fetched via Yahoo/Tiingo for backtest convenience. The constraint is **data-source revalidation**: research run on Yahoo/Tiingo continuous-futures or cash-ETF data must be re-run on the broker's actual MT5 feed before deploy, because CFD construction, point-value, and spread differ from the cash-equivalent / continuous-front construct. This is the same Phase-2-revalidation pattern that the `dax_overnight` CFD-vs-futures gate enforces (lesson #22 in `docs/RESEARCH_NOTES.md`).

Total monthly infra cost for the current deployed book: ~€8 (Hetzner CX33).

---

## Repo layout

```
quant-strategies-research/
├── experiments/             # One subdir per strategy: thesis .md + demo/validation .py + (optional) engine Strategy class
│   ├── xs_momentum/              # LIVE (QC)
│   ├── orb/                      # LIVE (MT5 VPS) — GER40 variant; covers SPX500/NDX100/GER40/UK100/FRA40 research
│   ├── treasury_trend/           # Validated Phases 2-7, no deploy yet
│   ├── softs_ensemble/           # Validated Phases 2-6, QC port blocked on ICE data
│   ├── btc_trend/                # Rejected at Phase 8 blend
│   ├── gold_trend/               # Rejected; single_instrument_scan.py survived as a screener
│   ├── tsmom/                    # TSMOM LO + variants + validations (+ tsmom_strategy.py, tsmom_filtered_strategy.py)
│   ├── imbalance/                # FVG / imbalance — inherited, not re-validated (+ imbalance_strategy.py)
│   ├── vix_term_structure/       # Tombstoned
│   ├── equity_pairs/             # Tombstoned
│   ├── fx_carry/                 # Tombstoned
│   ├── fx_carry_trend/           # Tombstoned
│   ├── fx_mean_reversion/        # Tombstoned
│   ├── blended_portfolio/        # Superseded
│   └── _archived/                # Older rejections (e.g. dual momentum)
├── scripts/                 # Data fetchers + shared helpers
│   ├── mt5_fetch.py              # MT5 broker (FX, CFDs, indices, intraday)
│   ├── yahoo_fetch.py            # Yahoo Finance (futures, ETFs, daily)
│   ├── tiingo_fetch.py            # Tiingo (US equities, Yahoo rate-limit fallback)
│   ├── fred_fetch.py              # FRED (interest rates for carry)
│   └── _datalake.py               # Shared CSV + datalake-ingest helpers
├── ohlc_data/                # Local CSV cache (gitignored; reproducible via fetchers)
└── docs/
    ├── WORKFLOW.md                # THE Phase 1-8 pipeline definition
    ├── STATE.md                   # SINGLE SOURCE OF TRUTH for experiment verdicts + headline numbers (read this first)
    └── RESEARCH_NOTES.md          # Cross-experiment methodological LESSONS (read before designing a new thesis)
```

Live MT5 Expert Advisors and VPS operational runbooks live outside this public tree.

**File convention per strategy:**

| Stage | File |
|---|---|
| Thesis | `experiments/<name>/<name>.md` |
| Phase 2 demo | `experiments/<name>/<name>_demo.py` |
| Phase 3-6 validation | `experiments/<name>/<name>_validation.py` (or per-phase split) |
| Engine `Strategy` subclass (optional) | `experiments/<name>/<name>_strategy.py` — for strategies that plug into the engine's event loop |
| Phase 8 deploy | private (MT5 EA on VPS) |

Every strategy's code lives in its own `experiments/<name>/` subdir — thesis doc, demo, validations, and (if the strategy plugs into the engine's event loop) a `<name>_strategy.py` class. Most strategies are standalone pandas/numpy sims in `<name>_demo.py`; engine-integration is an optional path used by TSMOM and imbalance.

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

Each strategy dir is self-contained. Demos report Phase 2 stats; validations handle Phases 3-6. Example session:

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

The intraday ORB work lives in `experiments/orb/` (instrument-agnostic — swap via env vars):

```bash
# Phase 2 baseline on any instrument
ORB_SYMBOL=GER40  ORB_SESSION=EU python experiments/orb/orb_demo.py
ORB_SYMBOL=NDX100 ORB_SESSION=US python experiments/orb/orb_demo.py
ORB_SYMBOL=UK100  ORB_SESSION=UK python experiments/orb/orb_demo.py

# Refinement diagnostic: symmetric R:R + TOD-exit sweep + OR-width filter
ORB_SYMBOL=GER40  ORB_SESSION=EU python experiments/orb/orb_refine.py

# Regime breakdown + fade-test on leading candidates (run after orb_refine.py picks a winner)
ORB_SYMBOL=GER40  ORB_SESSION=EU python experiments/orb/orb_holdout.py
```

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

Distilled from the strategies that died. Full rolling log in [`docs/RESEARCH_NOTES.md`](docs/RESEARCH_NOTES.md).

1. **Low correlation ≠ useful diversifier.** A strategy with correlation 0.1 and negative Sharpe subtracts from your book. Correlation alone doesn't justify inclusion; positive standalone Sharpe does.

2. **Negative IS-OOS degradation is not automatic good news.** If every strategy you've tested has OOS > IS, a common regime is juicing the OOS — the honest long-run estimate is the IS number, not the OOS or full-sample.

3. **"Different mechanic, same universe" = same bet.** TSMOM and XS-mom on the same instruments correlated +0.69 despite opposite-looking math. For real diversification you need a different factor OR a different market.

4. **Research backtests overestimate live Sharpe by 0.3-0.6 absolute.** Observed gap from this project: XS-mom 0.92 → 0.35 live (QC). Not a 50% ratio — a roughly fixed absolute drag from costs + execution + regime narrowness.

5. **Regime decay ≠ bad strategy, but still a REJECT.** VIX VRP had Sharpe 1.14 in 2015-2017 and -0.19 in 2024-2026. Forward-looking window is all that matters for deployment; "worked in the right era" doesn't get a pass.

6. **Weight literature decay warnings heavily.** Equity pairs cited Gatev/Goetzmann/Rouwenhorst's 1962-2002 result AND Do & Faff's post-2002 decay work. Estimated Sharpe 0.4-0.7; actual -0.99. The decay warning deserved more weight than the canonical number.

7. **Diversifiers shouldn't be judged on standalone CAGR.** Treasury-trend active return over cash is +0.25%/yr — underwhelming alone. But Sharpe 0.54, MDD -9%, caught 2022 cleanly, ~0 correlation with XS-mom. Judge diversifiers on whether they help the existing book in the regimes where the existing book hurts.

8. **Match filter speed to asset duration.** Same 252-day TSMOM on TLT (~18y dur, ~15% vol) gave Sharpe 0.14; on IEF (~8y dur, ~7% vol) gave 0.54. TLT's vol creates 10-15% drawdowns in the 6-month filter-lag window that IEF's lower vol absorbs.

9. **The permutation test has to test the right null.** Shuffling a return series preserves its mean and std exactly — meaningless for continuous-weight strategies. For TSMOM-style work, use a **position-shuffle** test: shuffle the daily weights, preserve returns, recompute P&L — tests "does the timing of the position choices add value?"

10. **Extend the sample before accepting a marginal bootstrap result.** IEF Phase 3 on 11 years: bootstrap 95% CI was [-0.028, +1.138] — a near-miss. Extended to 24 years (IEF inception 2002), CI became [+0.26, +1.08], Sharpe 0.55 → 0.67. An overfit strategy loses Sharpe on extension; a real edge gains.

11. **Intraday CFD costs ≠ cash-equity costs.** ORB on SPX500 M5 failed at Sharpe -0.92 against Zarattini/Aziz (2023) reporting +1.65-2.81 on QQQ. CFD spread ≈ 2× their commission assumption; no real share volume for filters; different instrument. Published intraday results on cash equities don't port 1-1 to retail CFDs even when the mechanism nominally translates.

12. **Don't tombstone based on fade-test alone — retest under symmetric R:R first.** GER40 ORB initially looked artifact-structured (baseline Sh +0.38, fade +0.34). Under fixed 1:1 R:R exits: baseline -0.24, fade -1.21, gap +0.97 — real directional signal. EOD-exit with fixed stop is itself a confound. This one saved the only real intraday edge in the project.

13. **Cross-instrument fade test separates signal from exit-structure artifact.** Running the same mechanism on SPX500 / NDX100 / GER40 revealed GER40 had the highest absolute Sharpe but near-zero fade-gap under EOD exit (artifact); NDX100 had low absolute Sharpe but fade-gap +0.49 (real signal). Fade-gap is a better edge-quality indicator than absolute Sharpe.

14. **Time-of-day exit as an alpha discovery tool.** GER40 EOD-exit Sharpe was +0.38; T+180min exit jumped to +0.58. Opening-impulse edge has a half-life of ~3 hours on DAX M5 — holding longer accumulates noise. For any intraday strategy that exits "at EOD because literature does", test a T+60/120/180/240min sweep; often the edge is diluted by over-holding.

---

## Further reading

- [`docs/STATE.md`](docs/STATE.md) — **single source of truth for every experiment's verdict + headline numbers**. AI-readable structured per-experiment blocks. Updated after each experiment closes. Start here.
- [`docs/RESEARCH_NOTES.md`](docs/RESEARCH_NOTES.md) — cross-experiment methodological lessons. Read this before designing a new thesis to avoid known traps.
- [`docs/WORKFLOW.md`](docs/WORKFLOW.md) — full Phase 1-8 pipeline with exact kill thresholds.
- Each `experiments/<name>/<name>.md` — strategy-specific thesis, validation trail, and tombstone record. STATE.md indexes these; the deep-dives live here.
