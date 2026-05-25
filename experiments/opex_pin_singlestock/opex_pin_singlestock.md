# Single-Stock OPEX Pin — M5 (round-strike proxy)

**Status**: Phase 2 complete 2026-05-24. Pre-commit at end of file.

**Verdict**: **REJECT**. Six independent kill criteria failed:

| Test | Result | Threshold | Verdict |
|---|---|---|---|
| Full-sample basket Sharpe | **-1.24** | > +0.30 | FAIL |
| WR / PF | 42.3% / 0.69 | WR≥50 or PF≥1.1 | FAIL |
| Holdout 2023-2026 Sharpe | **-1.27** | ≥ 0 | FAIL |
| Direction-gap (fade − cont) | **-0.66** | ≥ +0.30 | INVERTED |
| OPEX vs all-Friday delta | **-0.06** | ≥ +0.20 | NOT-LOAD-BEARING |
| Cost-sensitivity (0bp Sh) | **-0.33** | > 0 expected | SIGNAL-DRIVEN LOSS |

The result mirrors the `opex_pin_fade` index REJECT exactly. The single-stock thesis — that mid-cap names with concentrated monthly OPEX OI would preserve the pin mechanism even after 0DTE killed the index version — is refuted on the highest-conviction venue. The basket of 15 mid/large-cap retail-IV-heavy names (LULU, COIN, MSTR, NFLX, SHOP, CRWD, NET, AVGO, ASML, MU, ROKU, DOCU, PLTR, SNOW, NOW) shows NO pinning at the cash close on monthly OPEX Fridays. The 0DTE structural-short-gamma flow has leaked from Mag7 to the broader high-IV single-stock universe.

---

## Phase 2 results — detail

Basket coverage: 15 tickers, 4.7y range (2021-09-17 → 2026-05-15), 442 events post-filter. Universe data depth varies (MSTR 2024-10-only, COIN 2024-03-only; others 5y+).

### Baseline — fade, OPEX-only, AM=120min, PM=385min, MIN_DIST=0.50%, cost=15bp

| Metric | Value |
|---|---|
| Sharpe | **-1.24** (FAIL) |
| Basket entry-day MDD | -13.0% (PASS) |
| Events | 442 (94.9/yr) (PASS ≥ 300) |
| WR / PF | 42.3% / 0.69 (FAIL) |
| Avg win / loss | +1.07% / -1.14% (symmetric; no skew) |
| Total return | -13.0% over 4.7y, CAGR -2.95% |

### Regime breakdown

| Window | n | Sharpe | MDD |
|---|---|---|---|
| 2021-2022 vol | 82 | -1.12 | -4.5% |
| **2023-2026 holdout** | **360** | **-1.27** | -8.8% |

Holdout has the largest sample AND the worst Sharpe — exactly the 0DTE-decay signature pre-committed in the index `opex_pin_fade` thesis, now confirmed at the single-stock level.

### Per-ticker breakdown

| Ticker | n | Sharpe | Mean PnL | WR |
|---|---|---|---|---|
| NET | 24 | +1.36 | +0.28% | 45.8% |
| ROKU | 39 | +1.21 | +0.23% | 53.8% |
| NOW | 18 | +0.67 | +0.06% | 44.4% |
| MSTR | 13 | +0.12 | +0.02% | 53.8% |
| NFLX | 41 | -0.66 | -0.08% | 39.0% |
| ASML | 35 | -1.21 | -0.10% | 40.0% |
| SNOW | 21 | -1.21 | -0.16% | 38.1% |
| PLTR | 35 | -1.46 | -0.24% | 42.9% |
| LULU | 33 | -1.98 | -0.18% | 39.4% |
| DOCU | 29 | -2.02 | -0.50% | 48.3% |
| COIN | 18 | -2.19 | -0.59% | 33.3% |
| MU | 40 | -2.29 | -0.29% | 47.5% |
| SHOP | 33 | -2.41 | -0.44% | 39.4% |
| CRWD | 34 | -2.56 | -0.53% | 38.2% |
| AVGO | 29 | -3.63 | -0.48% | 31.0% |

Only 4 of 15 tickers positive — all with small N (13–39 events) and modest Sharpe (NET +1.36 is the strongest but n=24 is borderline). The 11 negative names have larger samples and decisive negative Sharpe. No mechanism-coherent positive subset emerges; the "winning" names are sampling noise.

### Variant sweeps

**MIN_DIST_FROM_PIN sweep**: monotonically negative across 0.25–2.0% thresholds. Loosening or tightening the distance filter doesn't recover signal. No threshold makes the trade work.

**PM exit minute sweep**: Sharpe is flat around -1.20 across exit times 14:00 → 15:55 ET. The pin doesn't tighten into the close (the core gamma-hedging mechanism) — exit time has zero impact. If pinning were happening, late-PM exits should outperform.

**Cost sensitivity**: Sharpe at 0bp = **-0.33** — even with zero friction, the strategy loses. Confirms a SIGNAL-driven loss (no edge to be eaten), not a cost-driven loss (edge eaten by friction).

### Direction null check — continuation

Cont Sharpe -0.58 (vs fade -1.24). Direction-gap = -0.66 = INVERTED. Continuation is "less bad" than fade but still negative — neither direction is profitable. The morning-distance-to-strike feature carries no usable directional signal: the future-PM move is not predictably toward OR away from the round strike.

### All-Friday null check

All-Friday fade Sharpe -1.18 (n=1952, 414/yr) vs OPEX-only fade Sharpe -1.24 (n=442). Delta = -0.06. The OPEX calendar lock has NO incremental signal — running the same fade-toward-strike trade on EVERY Friday loses at almost the same rate. This is the cleanest refutation of the pin-specific mechanism: if monthly OPEX Friday were structurally different from a generic Friday, we'd see a meaningful delta. We don't.

---

## Mechanistic interpretation

Three convergent refutations from the data:

1. **The mid-cap-non-Mag7 universe is NOT a safe harbor from 0DTE structural-short-gamma.** The thesis premise was that mid-caps haven't yet had the 0DTE takeover that killed the index pin. Per the holdout result (Sh -1.27 on n=360), 0DTE has metastasized to the broader high-IV single-stock universe — COIN, MSTR, PLTR, ROKU, CRWD class are now in the same regime as TSLA / NVDA. The 2024 CBOE single-stock-options data the pre-commit cited is already stale.

2. **Round-strike proxy doesn't matter.** Even if the proxy is noisy, the ALL-Friday null result (delta -0.06) rules out the calendar-specific mechanism. It's not "we picked the wrong pin proxy" — there is no pin to find. Generic Friday afternoon fade is essentially the same trade (and equally loses).

3. **Both directions lose** — at -0.33 Sh zero-cost, fade is signal-negative. Cont at -0.58 (entry-day basket; not shown but per simulator output). The "AM distance from round strike" feature has no predictive content for the PM move on this universe. The mechanism is absent, not just sign-flipped.

The wider pattern, with this REJECT, is now: **monthly OPEX pinning on US equities is dead in 2023-2026, on both indexes AND single stocks**. The two-experiment fail (this + index `opex_pin_fade`) is more decisive than either alone — the academic NPP 2005 / Stoll-Whaley 1991 / Golez-Jackwerth 2012 mechanism family has been comprehensively arbed/0DTE-displaced. Tombstone the entire OPEX-pin family for US equities.

---

## Lessons captured (for RESEARCH_NOTES.md)

- **0DTE-driven mechanism inversion has metastasized to non-Mag7 high-IV mid-caps.** The pre-commit hypothesis that COIN/MSTR/PLTR/ROKU class would preserve the pre-0DTE pin mechanism is refuted. The structural-short-gamma narrative now applies to any single-stock name with meaningful retail options activity. Pre-commit for any future "mid-cap escape from 0DTE inversion" thesis must include an *external* 0DTE-share indicator (CBOE single-stock 0DTE OI vs total OI) as a regime filter, not just a population selection.
- **"All-X null" is the cleanest mechanism falsification when a generic baseline exists.** OPEX-only vs all-Friday delta of -0.06 settled the verdict cleaner than any kill threshold. For any future calendar-restricted intraday strategy (FOMC-only, NFP-only, earnings-only, options-expiry-only), the all-day version of the SAME signal is the strongest available null. If the calendar lock doesn't add ≥ 0.20 Sharpe over the unconstrained baseline, the calendar isn't load-bearing.
- **OPEX-pin family is tombstoned for US equities, 2023-2026.** Two independent REJECTs (`opex_pin_fade` index, `opex_pin_singlestock` mid-cap basket) close the file. Future "options-expiry hedging flow" theses for US should pivot to either (a) non-US venues (Nikkei, FTSE OPEX behavior may differ — untested in this repo), (b) different calendar events (FOMC, OPEX-week MONDAY before expiry, quarterly futures roll), or (c) single-stock low-IV names where 0DTE flow is still nascent (defensive sectors, REITs, utilities — completely different population than this basket).

---

## Files

- Thesis: this file.
- Simulator: `experiments/opex_pin_singlestock/opex_pin_singlestock_demo.py`.
- Data:
  - M5 OHLC: `ohlc_data/<TICKER>_M5.csv` for 15 names (MT5-fetched 2026-05-24).
  - Run log: `experiments/opex_pin_singlestock/data/run_log.txt`.
- Run command: `venv/Scripts/python.exe experiments/opex_pin_singlestock/opex_pin_singlestock_demo.py`

---

## Pre-commit (original — preserved for audit)


## Thesis (mechanism)

The `opex_pin_fade` REJECT on SPX500/NDX100 (index level) showed that monthly OPEX pinning on US indices is dead post-0DTE — dealer gamma is diffuse across hundreds of strikes and 0DTE absorbs aggregate flow. Single-stock options have a **different gamma structure**:

1. **Concentrated dealer book per name.** A single mid/large-cap stock (LULU, COIN, MSTR, NFLX class) has a handful of strikes with meaningful open interest. Dealer gamma exposure clusters tightly, unlike the index where 5000+ strikes diffuse the book.
2. **0DTE single-stock options are nascent.** Per CBOE 2024 data, 0DTE volume on single-stock options remains < 15% of total volume on most names (excluding TSLA/NVDA where retail 0DTE has exploded). Monthly OPEX still dominates the gamma profile for non-meme single-stocks.
3. **Round-strike clustering (Ni-Pearson-Poteshman 2005).** Without OI data, NPP's robust empirical finding is that stock prices on monthly OPEX Fridays cluster to round-number strikes (multiples of $5 / $10 / $25 / $50 depending on price level) at the cash close — far more than on non-OPEX Fridays. This effect is direct evidence of dealer pin pressure and is the cleanest proxy when OI is unavailable.
4. **The strongest pin effect is in the 11:30 ET → 16:00 ET window** as time-to-expiry shrinks and dealer hedge flow accelerates.

The trade: on monthly OPEX Friday, for each candidate stock, identify the nearest round-number strike to the 11:30 ET price; if the spot has drifted ≥ X% AWAY from that nearest strike, fade back toward it (long if below, short if above), exit at 15:55 ET.

This is the **single-stock variant** of opex_pin_fade. The index-level REJECT does NOT refute the single-stock thesis — the mechanism (per NPP 2005) was originally demonstrated on **single stocks**, not indexes. The index test was a downstream generalization that has been arbed away post-0DTE. The single-stock effect on mid-OI, mid-cap names is the closer-to-source phenomenon.

## Why small-AUM matters here

- **Single-stock options market depth is shallow.** A $100M book hedging into LULU at OPEX afternoon would push the stock through the pin. At $500k–$1M, the trade is invisible.
- **No professional desk runs this on the long tail of mid-caps** — the per-name notional is too small ($500k–$2M per trade across 5–10 names) and execution complexity (synchronized OPEX-day fades on a basket) is high vs the per-trade dollar gross.
- **The trade is calendar-rare** — 12 OPEX Fridays/yr × ~10 candidate stocks = ~120 trade opportunities/yr. At $100M AUM and 1% per name sizing, that's $1M × 120 = $120M of throughput on a strategy that won't move the institutional needle. At $500k, it's the core book.

## Key references

- **Ni, Pearson, Poteshman (2005)**, "Stock price clustering on option expiration dates", *J. Financial Economics* 78(1) — THE canonical paper. Documents single-stock clustering at strikes on monthly OPEX. The original effect is single-stock; index-level (Stoll-Whaley / Golez-Jackwerth) is a derivative.
- **Avellaneda & Lipkin (2003)**, "A market-induced mechanism for stock pinning", *Q. Finance* — theoretical gamma-hedging model on single stocks.
- **Ni, Pearson, Poteshman, White (2021)**, follow-up — finds the pinning effect persists post-2010 on single stocks with high option open interest, though has weakened on the highest-volume names where alternative liquidity (dark pools, single-stock futures-equivalents) has dampened it.
- **opex_pin_fade REJECT (this repo, 2026-05-22)** — confirms the index-level effect has died post-0DTE; explicitly distinguishes the single-stock thesis (this experiment) as not directly refuted.

## Signal math

```
Parameters:
  MORNING_END_MIN    = 120     (11:30 ET — AM reference)
  AFTERNOON_END_MIN  = 385     (15:55 ET — 5min before cash close)
  COST_BPS_RT        = 15      (mid-cap CFD on Eightcap: 5-10bp spread × 2 + slippage)
  STRIKE_GRID = {                # nearest round-number gridlines by price-band
    px < 50:      $1
    50 <= px < 200:   $5
    200 <= px < 500:  $10
    500 <= px:    $25
  }
  MIN_DIST_FROM_PIN_PCT = 0.50  # require spot ≥ 0.5% away from nearest strike at 11:30
  MAX_DIST_FROM_PIN_PCT = 3.00  # if too far from pin, abort (no pin reachable in 4 hrs)

Per OPEX-Friday day, per ticker in UNIVERSE:
  bar_1130_close = close at 11:30 ET
  nearest_strike = round_to_grid(bar_1130_close)
  dist_pct = (bar_1130_close - nearest_strike) / nearest_strike

  if abs(dist_pct) < MIN_DIST_FROM_PIN_PCT: skip (already near pin)
  if abs(dist_pct) > MAX_DIST_FROM_PIN_PCT: skip (too far)

  direction = -sign(dist_pct)              # fade toward strike: LONG if below, SHORT if above
  entry at next M5 bar open after 11:30 ET
  exit  at first M5 bar with minute_of_day >= 385 (15:55 ET)
```

One round-trip per (ticker, OPEX-day) max. No intraday stop — pinning thesis depends on the strike being a magnet through the close.

## Why retail-accessible

- Data: M5 OHLC for the universe (MT5-fetched from Eightcap; same broker as deploy).
- No options data required (round-strike proxy substitutes).
- Trade execution: M5-bar entries; mid-cap CFD spreads on Eightcap median 5-15 bp (per cost model in `_check_stock_spreads.py`).
- Frequency: 12 OPEX Fridays/yr × ~10-15 setups/Friday = 120-180 events/yr (basket-aggregated; per-name 12/yr).

## Universe (candidate)

15 mid/large-cap names selected for: (a) liquid options chains historically, (b) NOT dominated by 0DTE (excludes TSLA, NVDA, AAPL, AMD, META — covered in mag7 / 0DTE-flow experiments), (c) tradeable on Eightcap MT5, (d) price > $30 (round-strike grid meaningful):

`LULU, COIN, MSTR, NFLX, SHOP, CRWD, NET, AVGO, ASML, MU, ROKU, DOCU, PLTR, SNOW, NOW`

Exclusions and rationale:
- TSLA, NVDA, AAPL, AMD, META: high 0DTE share — should INVERT, not pin (predicted by post-2022 inversion pattern documented in `earnings_continuation_mag7`).
- Mag7 large-caps with diffuse options (AMZN, GOOGL, MSFT): low retail-OI concentration; closer to the failed index case.
- Anything < $30: round-strike grid is per-dollar (too tight).

## Expected performance

- Per-event gross: 50–150 bp (pin pull on a 1–2% deviation at midday).
- After 15 bp RT cost: 35–135 bp net.
- Expected research Sharpe (basket): 0.4–0.9 full sample. Per-name n is too small for individual Sharpe.
- Trade cadence: ~10/yr/ticker × 15 names = ~150/yr basket events. After threshold/eligibility filter, ~100/yr.
- MDD: < 15% expected (basket diversification + per-trade exposure capped at intraday gross move).
- WR target: 55–65% (pin-magnetic days dominate).

## Fail conditions (pre-committed)

Phase 2 kills if ANY:
- Full-sample basket Sharpe < +0.30 after 15 bp RT cost.
- Max DD > 25%.
- Trade count < 300 across the basket (basket 15 names × ~10 OPEX/yr × ~5y = 750 max; expect ~300-500 post-filter).
- WR < 50% AND PF < 1.10.

Phase 4 kills if Sharpe positive in < 2 of 3 regime windows (2019-2020 / 2021-2022 / 2023-2026).

Phase 6 kills if 2023-2026 holdout Sharpe < 0. CRITICAL — the post-2022 0DTE inversion documented in `opex_pin_fade` (index) and `earnings_continuation_mag7` is the named decay mechanism. The single-stock thesis depends on these mid-cap names NOT having had the same 0DTE takeover; the holdout window is the test.

**Direction null check** (lesson #38 + lesson #43 inversion family):
- Same simulator, `direction = +sign(dist_pct)` (CONT: ride away from strike — anti-pin).
- Require **fade Sharpe − cont Sharpe ≥ +0.30** at full sample.
- If holdout sub-window flips (cont > fade post-2022 even when full-sample passes), this is the same inversion pattern in `opex_pin_fade` index. REJECT.

**All-Friday null check** (lesson #15 + index opex_pin_fade methodology):
- Same simulator with `OPEX_ONLY=False` (every Friday). Require **OPEX Sharpe − all-Friday Sharpe ≥ +0.20**.
- If matched, the OPEX calendar lock is not load-bearing and the strategy is just "fade afternoon drifts on Fridays" — not the pin mechanism.

**Per-name min-trade gate**: Drop any name from the deployable basket if it has < 10 events over the full window (insufficient per-name signal).

## Why this might fail (red flags)

1. **0DTE has leaked further than 2024 CBOE data suggests.** If COIN/MSTR/PLTR/ROKU (the high-retail-IV names in the basket) have seen 0DTE share jump > 25% in 2024-2026, the inversion that killed the index thesis will kill these too. The holdout is the kill test.
2. **Round-strike proxy is a weak substitute for OI.** NPP 2005 used actual OI data. Round-strike grid will mis-identify the pin on names where the max-OI strike isn't a round number (e.g., NFLX often has max-OI at $-something-odd that reflects historical issuance / split history). Expect 20-40% noise reduction vs OI-aware version.
3. **Pin pull is small on mid-caps.** 30-80 bp pin pull may not consistently beat 15 bp RT cost. Cost-sensitivity sweep will diagnose.
4. **Single-name event risk on OPEX afternoons.** Earnings, M&A, FDA, news catalysts on OPEX Friday afternoons can overwhelm the pin mechanism (e.g., a name reporting earnings AMC on OPEX day will move on the news, not pin). No earnings-day filter in the baseline; if results are noisy, retest with an earnings-blackout.
5. **CFD spread widening intraday.** Eightcap mid-cap spreads can widen 2-3× into the close on low-volume names. Cost may be understated for the late-PM exit.
6. **Universe selection bias.** The 15-name basket was chosen for "moderate options activity + non-Mag7" which is exactly the population most likely to have already been arbed by mid-frequency hedge funds (Renaissance / Two Sigma class scan the long-tail intraday).

## Phase 1 → 2 plan

- [ ] Fetch M5 OHLC for 15 names via MT5 (`--datalake`). Some may already exist; fetch ≤ 5y depth.
- [ ] Build round-strike pin-fade simulator (M5 bars, OPEX-Friday-only, ticker-loop).
- [ ] Phase 2: baseline + kill criteria + regime breakdown + direction null + all-Friday null.
- [ ] Per-name breakdown.
- [ ] Distance-threshold sweep (MIN_DIST: 0.25 / 0.5 / 1.0 / 2.0 %).
- [ ] Cost-sensitivity sweep (0 / 5 / 15 / 30 / 50 bp).
- [ ] Update this thesis + STATE.md.

## Files

- Thesis: this file.
- Simulator: `experiments/opex_pin_singlestock/opex_pin_singlestock_demo.py`.
- Data: `ohlc_data/<TICKER>_M5.csv` for 15 names.
