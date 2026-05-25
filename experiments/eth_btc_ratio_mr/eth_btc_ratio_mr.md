# ETH/BTC Ratio Mean-Reversion — post-Merge two-sided crypto spread

**Status**: Phase 2 complete (2026-05-22). REJECT — decisive failure on 6 of 7 pre-committed checks plus sub-window stability plus cost robustness. The pre-committed MR direction was wrong-signed on post-Merge ETH/BTC; the momentum-null variant beats the baseline by +0.42 Sharpe.

**Verdict**: **REJECT — pre-committed mean-reversion direction inverted; mechanism is post-instit MOMENTUM, not MR.**

Headline numbers (post-Merge 2022-09-15 → 2026-03-31, 10bp RT cost, all pre-committed parameters unchanged):

| Variant | Sharpe | MDD | Trades | Hold med |
|---|---|---|---|---|
| **Baseline (MR both)** | **−0.235** | **−59.85%** | 21 (L18/S3) | 30d |
| Cheap-only (LONG ETH) | +0.078 | −46.42% | 18 | 28d |
| Rich-only (SHORT ETH) | −0.464 | −36.76% | 4 | 22d |
| **Momentum-null (both)** | **+0.190** | −48.71% | 21 (L3/S18) | 30d |
| No-time-stop | −0.137 | −59.57% | 15 | 23d (p90 92d) |
| z≥1.5 entry (cadence ↑) | +0.002 | −53.97% | 32 | 22d |
| z≥2.5 entry (cadence ↓) | −0.104 | −33.20% | 13 | 30d |

**Sub-window split — the load-bearing finding:**

| Window | Baseline Sh | MDD | n_days |
|---|---|---|---|
| H1 2022-09 → 2024-06 | **+1.099** | −15.26% | 654 |
| H2 2024-07 → 2026-03 | **−0.976** | −59.85% | 635 |

H1 looked clean (Sh +1.10, MDD -15%). H2 catastrophic. This is the classic one-window-wonder shape that the sub-window check is specifically designed to catch (lesson `btc_volbreak` REJECT).

**Pre-committed kill-criteria check:**

| Check | Threshold | Actual | Result |
|---|---|---|---|
| Full-window Sharpe | ≥ +0.50 | −0.235 | **FAIL** |
| Trade count | ≥ 30 | 21 | **FAIL** |
| MDD | ≤ 20% | −59.85% | **FAIL** |
| Momentum-null gap | ≥ +0.30 | **−0.424 (inverted)** | **FAIL DECISIVELY** |
| Cheap-leg Sh ≥ 0 | yes | +0.078 | PASS |
| Rich-leg Sh ≥ 0 | yes | −0.464 | **FAIL** |
| Half-life sane (5 ≤ med hold ≤ 20) | yes | 30d | **FAIL** |
| Sub-window stability (both ≥ +0.20) | yes | H1 +1.10 / H2 −0.98 | **FAIL** |
| Cost robustness (20bp ≥ +0.20) | yes | −0.257 | **FAIL** |

6 of 7 in-experiment checks plus sub-window plus cost robustness — comprehensive REJECT.

## Mechanistic interpretation — what we actually learned

**The H1 "MR working" was a one-time directional ratio re-rating, not mean-reversion.**

Post-Merge ETH (Sep 2022) was historically cheap vs BTC at ~0.066. Over H1 (through mid-2024), capital rotated *into* ETH on the Merge / Shapella / pre-Spot-ETF narrative, mean-reverting (in z-score terms) the ratio back toward its 90d-rolling mean again and again. The signal looked like clean MR because every cheap-side entry got faded — but it wasn't faded by mean-reversion mechanics. It was a slow directional re-rating that the rolling-90d mean tracked behind. **Each "MR trade" was really riding a multi-month directional flow.** This is the same shape as the `dual_momentum` reject ("positive full-sample only from 2023+ bull; cash filter actively hurts") and the canonical "look like MR, actually trend" failure mode.

**H2 was the regime flip — BTC won institutionalization.**

Jan 2024 BTC spot-ETF launch and 2025 "treasury asset" narrative concentrated post-institutionalization capital in BTC, not ETH. ETH ETFs lagged. The ratio kept making new lows (from 0.058 in mid-2024 to 0.018 in early 2026). The "cheap-side" z-score signals fired again and again, and every entry got SMACKED because the ratio's "mean" was still trending down. The 90d-rolling mean lag meant z-scores stayed negative for entire quarters — the strategy was buying a falling knife mistaking trend for over-extension.

**Three independent observations of "MR/sentiment pre-commits invert on post-2022 risk assets"** — pattern emerging:

1. `short_tsmom` (REJECT, 2026-05-18): equity-bear-trigger SHORTS were inverted — long-side did +0.64 at the same conditions where shorts did −0.25 (QE-era buy-the-dip EV).
2. `orb_dax_sentiment` (REJECT, 2026-05-21): "risk-on tape = better breakouts" was inverted — risk-OFF days were the alpha-bearing ones.
3. `eth_btc_ratio_mr` (REJECT, 2026-05-22, THIS): "MR at z-extremes" was inverted — momentum direction was the right side at the same z-thresholds.

The unifying pattern: assets/markets undergoing structural regime change (post-2008 QE for equity dips, post-0DTE for index opening-impulse, post-Merge + post-spot-ETF for crypto) develop **persistent flow imbalances that look like extremes but are actually unfinished re-pricing**. Pre-committing the fade direction on these is repeatedly wrong-signed.

## What the experiment ALSO confirms

- **Two-sided in name only — direction-asymmetry was extreme.** 21 baseline trades = 18 LONG-ETH (the cheap-side) and only 3 SHORT-ETH. The ratio was in the LOW-z regime for most of the window, so the "fade rich" leg essentially never fired. A "two-sided" mechanism that ends up being 86% one-sided is not actually solving the user's "not long-only" requirement on its own — even ignoring the REJECT verdict.
- **Time-stop is binding** (median hold = 30d = the time-stop value; 11 of 21 exits were `time_stop`). The "MR" wasn't reverting; positions were getting closed by the calendar, not by signal mean-reversion.
- **Cost was NOT the binding constraint** — Sharpe at 5bp RT is −0.22, basically unchanged from 10bp (−0.235). This isn't a cost-eaten-edge story; it's a no-edge story. The full lesson #26 diagnostic confirms: cost-zero Sharpe ≈ cost-realistic Sharpe → no signal in the direction we pre-committed.

## Implications for the user-facing question ("4th strategy, not long-only")

- ETH/BTC ratio MR is **out**. The post-instit regime supports MOMENTUM not MR on this spread (the null-check direction). However, adopting that mirror direction post-hoc would be exactly the goalpost-moving pattern the orb.md lessons warn against — if a future pre-commit wants to re-test, it must be **explicitly pre-committed as a momentum thesis on this ratio, on truly OOS data (post-2026-04)**, with the symmetric null being the MR direction. The current data is now contaminated; do not re-fit.
- The structural break (Merge anchoring post-2022 ETH-supply regime) was real but not exploitable as MR. Will revisit IF: (a) ETH ETF flows reverse the 2024-2026 trend; (b) BTC dominance retraces; (c) a new structural-break candidate (e.g., Pectra, ETH-restaking) creates a future pre-commit-able regime.
- The four candidate strategies on the table for "not long-only" go down to three: single-stock earnings-gap fade (Option A from prior turn) or NDX expiry-Friday pinning fade (Option C), or a fresh idea. Crypto two-sided ratio MR is now blocked; would have to be a different crypto mechanism family.

## What I would change about the pre-commit if re-running with hindsight (for methodology, not for re-fitting)

1. **Population count at z=2.0 was 38 fresh crossings in 3.5y** — comfortably above the 15-floor I had hand-waved, but the actual *trade* count came in at 21 because many crossings happened while a position was already open. Future pre-commits on signal-crossing strategies should distinguish "fresh signal events" from "fresh tradeable entries" (event minus "while flat") and use the latter for the population-count floor.
2. **Sub-window stability check is the most informative check by a wide margin.** A naive single-Sharpe summary masked the +1.10 / −0.98 split entirely. Make sub-window stability a Phase 0 diagnostic, not a Phase 2 final check.
3. **30d time-stop was the binding-by-default exit.** A future pre-commit on a MR-on-spread strategy should make the time-stop a *function of the spread's empirical half-life* (Ornstein-Uhlenbeck half-life estimate from the rolling-window residuals), not a fixed 30d. But again — adding that now would be goalpost-moving.

## Files (post-run)

- Thesis (this file).
- Demo: `experiments/eth_btc_ratio_mr/eth_btc_ratio_mr_demo.py`.
- Data: `ohlc_data/ETHUSD_D1.csv`, `ohlc_data/BTCUSD_D1.csv`.

---

(Original Phase 1 pre-commit notes preserved below for verification of pre-vs-post hypothesis fidelity.)

## Why this experiment, why now

The deployed book is three LONG-only intraday strategies (orb_dax / lunch_fade / xau_session). The user explicitly asked for a 4th candidate that is **NOT long-only** to diversify direction. The graveyard rules out almost every two-sided candidate the repo has tested (equity-index shorts structural per lesson #34, FX safe-haven shorts regime-broken per #35/#36, FX MR/carry post-2015 dead, single-instrument commodity sessions cost-capped at retail Eightcap). The remaining genuinely-untouched two-sided candidates are: (i) single-name equity microstructure (untested but high research-lift), (ii) ETH/BTC ratio mean-reversion, (iii) index expiry-Friday pinning (low-cadence side bet).

This experiment tests (ii). The ETH/BTC ratio is naturally two-sided (when stretched cheap, go long ETH / short BTC; when stretched rich, go short ETH / long BTC). Both legs are crypto CFDs already on Eightcap (BTCUSD, ETHUSD), already on disk, no new data layer needed. The Sep-2022 Merge event (POS transition) is a clean structural-break anchor that aligns *exactly* with the user-requested post-institutionalization window. Mean-reversion as a mechanism family has ZERO entries in the deployed book today — the closest is `lunch_fade` (intraday MR within a single instrument), not a cross-asset spread MR. Adding a spread-MR mechanism, if it survives, gives the book a genuinely orthogonal direction.

## Thesis (mechanism)

1. **Structural anchor for relative valuation.** Post-Merge (2022-09-15), ETH became deflationary (issuance fell ~88% on day-one) while BTC remained on its fixed-issuance schedule. The ETH/BTC ratio therefore has *changed structural dynamics* vs the pre-Merge regime — old academic MR work on this ratio (pre-2022) is not directly portable. But the *mechanism* of mean-reversion at extremes survives the regime change for two specific reasons:
   - **Funding-rate / carry-driven spread MR**: when ETH perp funding diverges sharply from BTC perp funding, leveraged-position imbalances unwind toward the mean (typically over 5-20 days).
   - **Capital-rotation flows**: institutional crypto allocators rotate between BTC and ETH at extremes (e.g., late-2024 ETH-ETF launch + 2025 Merge-driven "ultrasound money" narrative). These rotations show up as ratio stretch + revert.

2. **Why mean-reversion, not momentum, on this spread post-Merge.** btc_volbreak REJECT (W4 +0.18) and btc_weekend REJECT (MDD blowup) both attempted *momentum* mechanisms on BTC alone. The data after 2022 is consistent with crypto becoming *more* range-bound in spread terms even as individual assets remain trending — a typical signature of professional flow concentrating into pair trades. **Pre-committed direction is MEAN-REVERSION**. The fade-test null (momentum entry at the same |z| threshold) must clearly lose.

3. **Two-sided by construction, no drift confound.** Unlike equity-index strategies where secular drift biases the LONG leg (lessons from lunch_fade, orb_dax LONG-only verdicts), the ETH/BTC ratio has no obvious secular drift in the post-Merge window. The natural-mean is a moving target tracked by a rolling lookback. Both directions are tested with the same threshold; asymmetric outcome would itself be informative (and require a re-pre-commit before exploiting).

## Key references

- Liu, Tsyvinski, Wu (2022). "Common risk factors in cryptocurrency." *Review of Financial Studies* 35(1). Crypto factors are dominated by a market factor — pair trades isolate idiosyncratic spread.
- Makarov & Schoar (2020). "Trading and arbitrage in cryptocurrency markets." *JFE* 135(2). Cross-exchange arbitrage was the dominant force pre-2020; post-institutionalization the dominant force shifts to relative-valuation MR.
- Choi & Patel (2024) [if available]; Yermack (2015) on ETH-specific monetary policy. The Merge ushered in a structural break specifically in the ETH supply curve.

## Signal math — pre-committed parameters (NOT swept)

```
Inputs: ETHUSD_D1.close, BTCUSD_D1.close (both on disk, MT5-fetched, Eightcap-tradeable).
Window: 2022-09-15 (Merge) → 2026-03-31 (joint coverage end).

  ratio[t]      = ETH_close[t] / BTC_close[t]
  log_ratio[t]  = ln(ratio[t])
  mu_t          = mean(log_ratio[t-LOOKBACK..t-1])      # rolling, strictly history
  sigma_t       = std (log_ratio[t-LOOKBACK..t-1], ddof=1)
  z[t]          = (log_ratio[t] - mu_t) / sigma_t

LOOKBACK     = 90 days       # 3-month rolling window (pre-committed)
ENTRY_Z      = 2.0           # enter when |z| ≥ 2.0
EXIT_Z       = 0.5           # exit when |z| ≤ 0.5 (revert to half-vol band)
MAX_HOLD     = 30 days       # time-stop pre-commit, NOT swept
COST_BPS_RT  = 10 bps        # 5bp/leg × 2 legs = 10bp total round-trip (honest)
```

**Entry rule:**
- If `z[t] ≤ -ENTRY_Z` → LONG ETH, SHORT BTC (ratio is cheap, expect mean-reversion up)
- If `z[t] ≥ +ENTRY_Z` → SHORT ETH, LONG BTC (ratio is rich, expect mean-reversion down)

**Exit rule:**
- Close the pair when `|z|` crosses below `EXIT_Z`, OR
- Time-stop at `MAX_HOLD` days regardless of z (avoids regime-break holding).

**Position sizing:** equal-dollar both legs at entry (1 unit notional each side), no rebalancing during the trade. PnL = leg1_return − leg2_return − cost.

## Variants

| Variant | Rule | Pre-commit role |
|---|---|---|
| **Baseline** | Above signal exactly | The candidate |
| **Long-only (cheap-side)** | Only LONG-ETH/SHORT-BTC entries | Direction-asymmetry diagnostic |
| **Short-only (rich-side)** | Only SHORT-ETH/LONG-BTC entries | Direction-asymmetry diagnostic |
| **Inverted (momentum null)** | Entry: trade WITH the deviation. Exit: |z|≥3.0 or 30d time-stop | MUST clearly lose if MR is real |
| **No-time-stop** | Same as baseline but `MAX_HOLD=None` | Sanity — should be similar if time-stop isn't load-bearing |
| **Z=1.5 entry** | `ENTRY_Z=1.5` (higher cadence) | Cadence sensitivity |
| **Z=2.5 entry** | `ENTRY_Z=2.5` (lower cadence) | Cadence sensitivity |

## Why retail-accessible

- BTCUSD and ETHUSD are both on Eightcap MT5 (memory-confirmed broker universe). Spreads ~3-5bp/leg → 6-10bp RT is realistic.
- D1 cadence — no swap concern over multi-day holds *for crypto CFDs* (Eightcap charges crypto swap but at much smaller %/day than FX or equity CFDs; assume 5bp/day total carrying cost as a conservative additional charge — pre-committed below).
- Two crypto CFDs sit in the same broker, same execution venue, same regulatory environment. Mechanically clean.

## Universe

- **Target**: BTCUSD + ETHUSD daily close-to-close pair.
- **Window**: 2022-09-15 → 2026-03-31. 3.55 years post-Merge, ~1290 joint trading days (crypto is 24/7, so ~1290 days = ~1290 D1 bars, modulo broker maintenance windows).
- **Why this window only**: per user-feedback memory + lesson #2 (BTC W4-floor binding), pre-2022 BTC is a different asset and pre-Merge ETH is a different asset. The post-instit + post-Merge intersection is the only deployment-relevant window. No backtest is run on earlier data; this is explicitly NOT a "split full sample 70/30" experiment.

## Expected performance (pre-committed point estimate)

If the mechanism works:
- Baseline Sharpe **+0.60 to +1.20** net of 10bp RT cost.
- Trade count **30-80** total over 3.55y (10-22 setups/year).
- Average holding period **10-15 days** (between entry at |z|=2 and exit at |z|=0.5).
- MDD **5-15%**.
- Direction-asymmetry diagnostic: expect cheap-side (LONG-ETH) to be the stronger leg (Merge ETH-supply story), but BOTH directions should be non-negative. If one direction is strongly negative, MR isn't symmetric and the verdict is degraded.

If no signal: Sharpe between −0.20 and +0.30, fade-momentum null is similar or wins. That is a clean REJECT.

## Fail conditions (pre-committed)

The strategy PASSES (deploy candidate) if **all** hold:

- **Full-window Sharpe ≥ +0.50** net of 10bp RT cost.
- **Trade count ≥ 30** (need minimum sample for any statistical claim, lesson #37 territory if trade-count is the binding empty result).
- **MDD ≤ 20%**. Crypto-generous bound but still binding — anything beyond 20% on a 2-leg spread means risk management failed.
- **Cost robustness**: Sharpe at **20bp RT** must still be **≥ +0.20**. If a 2× cost stress kills the edge, retail spread variation will too.
- **Momentum-null check**: Inverted (momentum-direction) variant Sharpe must be **at least +0.30 BELOW** baseline Sharpe. If trading WITH the stretch does as well as fading it, there's no MR — just noise reshape.
- **Direction-asymmetry**: BOTH legs (cheap-side LONG ETH and rich-side SHORT ETH) must have **non-negative Sharpe individually**. Strongly negative on one side = asymmetric mechanism, downgrade to MARGINAL.
- **Sub-window stability**: split the post-Merge window in half (2022-09 → 2024-06 vs 2024-07 → 2026-03), require **both sub-windows Sharpe ≥ +0.20**. If one sub-window carries the whole result, it's a one-window-wonder per lesson `btc_volbreak`.
- **Half-life sanity**: mean holding period from entry to exit should be **5-20 days**. <5 days = noise round-trip; >20 days = time-stop is binding which means the "MR" isn't reverting.

MARGINAL: 4-6 of the 7 checks pass and Sharpe ∈ [+0.30, +0.50]. Keep-for-reference; do not deploy.

REJECTED: any of (Sharpe < +0.30, trade count < 30, momentum null wins, both sub-windows < +0.20). All other partial pass-states are MARGINAL.

## Why this might fail (red flags)

1. **Post-Merge regime is too short** (3.55y, ~50-80 trades expected). Lesson #37 (count the population first) suggests if trade-count drops below ~30 at the pre-committed `ENTRY_Z=2.0` threshold, the experiment is mechanically empty. Sanity-check the population count in the first 60 seconds of the demo before running variants.

2. **Crypto swap charges might be punitive** for multi-day holds even on Eightcap. The 10bp RT cost model captures spread but not swap. If realized swap on crypto-CFD pairs is 5-15bp/day per leg, then a 10-day hold adds 100-300bp to round-trip cost — completely flipping the verdict. **Mitigation: a Phase 0 swap-cost note based on Eightcap published rates is required before deploy, but for the Phase 2 research demo the 10bp RT is honest research-cost.** Will flag explicitly in the post-run verdict.

3. **One-window-wonder risk** is high — btc_volbreak rejected exactly because W2 2020-21 carried everything. Sub-window check is explicitly the guard.

4. **ETH-specific narrative shocks** (Merge, Shapella, Pectra, future spot-ETF events) introduce idiosyncratic ratio moves that aren't MR but trend. The 90d rolling-mean lookback amortizes these *if* they're <90d in duration, but a 180d sustained ratio re-pricing (like Sep-2022 to mid-2023 ETH outperformance) will look like one big losing trade for the rich-side leg and a sequence of winning trades for the cheap-side. The direction-asymmetry diagnostic catches this.

5. **Crypto 24/7 vs broker-quote conventions**: Eightcap CFD D1 closes are at broker-server midnight (EET, GMT+2/+3) not UTC 00:00. The MT5-fetched CSV uses broker-server timestamps — a 1-hour offset vs spot exchanges. For a daily-close-to-close strategy this is immaterial (we're not aligning to any external benchmark), but flag for live deploy.

6. **Lookback parameter** of 90d is pre-committed from convention. A 60d lookback would catch faster regime shifts; a 180d would be more stable. We do NOT sweep this; the pre-commit value is binding. If results are borderline, lookback is the first thing the user might want to revisit in a follow-up pre-commit (but not in this run).

## Phase 1 → 2 plan

- [x] Read STATE.md / RESEARCH_NOTES.md for related crypto rejects (btc_volbreak, btc_weekend, btc_intraday).
- [x] Verify ETHUSD + BTCUSD D1 on disk (fetched ETHUSD via mt5_fetch, refreshed BTCUSD).
- [x] Pre-commit all parameters + 7 kill criteria (above).
- [ ] Implement `eth_btc_ratio_mr_demo.py` with numpy inner loop.
- [ ] Run population-count sanity-check FIRST (lesson #37) — if < 30 setups at z=2.0, log and continue to lower-threshold cadence sweep for diagnostic.
- [ ] Run baseline + long-only + short-only + momentum-null + no-time-stop + z=1.5 + z=2.5 variants.
- [ ] Sub-window split (2022-09→2024-06 / 2024-07→2026-03).
- [ ] Cost sensitivity (5 / 10 / 20 / 40 bp RT).
- [ ] Half-life statistic (mean / median / p10 / p90 of holding period).
- [ ] Apply pre-committed kill criteria — update verdict at top of doc.
- [ ] Update `docs/STATE.md` (or `STATE_GRAVEYARD.md` on REJECT) with the post-run YAML/row.
- [ ] If PASS or interesting MARGINAL → add lesson to `RESEARCH_NOTES.md` on spread-MR-as-orthogonal-direction or post-Merge-regime-properties.

## Files

- Thesis: this file.
- Demo: `experiments/eth_btc_ratio_mr/eth_btc_ratio_mr_demo.py`.
- Data dependencies (all on disk):
  - `ohlc_data/ETHUSD_D1.csv` (3061 bars, fetched 2026-05-22)
  - `ohlc_data/BTCUSD_D1.csv` (2711 bars after refresh 2026-05-22)
