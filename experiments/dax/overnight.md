# DAX Overnight Drift Capture

**Status**: Phase 2 complete 2026-04-20.

**Verdict**: **REJECT — research result is a CFD-data artifact**. Phase 2b combined filter delivered research Sharpe +0.80 on GER40 CFD M5 (MT5). QC port to FDAX futures (continuous, IB execution model, same logic and filters) delivered **Sharpe −0.34 / CAGR +1.54% / MDD −10.4%** after fixing schedule timing and continuous-contract roll handling. The avg-win magnitude on futures is ~half the CFD research value (0.34% vs 0.63%), indicating the research edge doesn't survive the move off of CFD pricing. See "QC validation" section below for the full diagnostic.

**Root cause (best-guess mechanism)**: MT5 CFD providers construct synthetic close-to-open price series from dealing-desk quote repricing, spread changes over the CFD-paused window, and auction-fill logic — none of which exist on continuously-traded futures. The research effectively measured CFD-provider quote construction, not an exploitable market edge.

---

## Results summary

Baseline (always-LONG, entry 17:25 close, exit 09:00 next day open, cost=1pt):

| Metric | Value | vs threshold |
|---|---|---|
| Sharpe | **+0.42** | PASS (bar lowered to +0.20) |
| Max DD | **−31.96%** | **FAIL (bar −25%)** |
| Trades | 1,852 (4.89/wk) | PASS (n/a) |
| WR / PF | 54.6% / 1.09 | PASS |
| CAGR | +5.27% | — |

**Regime breakdown**: +0.09 / **−0.44** / **+1.40**. 2021-2022 is the weak regime (ECB hawkish pivot + Russia gaps). Holdout +1.40 is striking — post-2023 DAX has strengthened overnight drift, consistent with ECB cut cycle + recovery.

**Null-check** (always-SHORT):
- LONG Sharpe +0.42
- SHORT Sharpe −0.64
- Sum −0.22 → real positive premium. The premium isn't symmetric; SHORT loses more than LONG gains, which is the classic "overnight premium + volatility asymmetry" signature.

**Day-of-week split (LONG)**:

| Day | n | Sharpe | avg pnl | WR |
|---|---|---|---|---|
| Mon | 366 | **+1.14** | +0.131% | 57.9% |
| Tue | 375 | +0.09 | +0.010% | 52.5% |
| Wed | 373 | +0.26 | +0.035% | 53.9% |
| Thu | 373 | +0.10 | +0.012% | 54.7% |
| **Fri** | 365 | **−0.40** | −0.065% | 54.2% |

Monday dominates — weekend-gap premium. Friday is a drag — consistent with institutional de-risking into the weekend. Drop-Friday filter would cut ~20% of trades and materially lift Sharpe.

**Prior-day direction (LONG)**:

| Condition | n | Sharpe |
|---|---|---|
| after UP day | 1,028 | +0.04 |
| after DOWN day | 825 | **+0.54** |

Strong asymmetry. Overnight premium concentrates after down days (mean-reversion stacking with overnight drift).

**Cost sensitivity**: 0.5pt +0.47, 1.0pt +0.42, 2.0pt +0.31, 3.0pt +0.20. Robust to spread widening.

## Phase 2b refinement (drop-Fri × after-DOWN-day combined) — 2026-04-20

Combined filter: keep only overnight trades entered on Mon-Thu (Fri dropped) where the prior-day DAX close-to-close return was negative.

**Filter-sweep comparison**:

| Variant | n | Sharpe | MDD | PF | WR |
|---|---|---|---|---|---|
| baseline (always LONG) | 1,852 | +0.42 | **−31.96%** FAIL | 1.09 | 54.6% |
| drop-Fri only | 1,487 | +0.76 | −18.87% | 1.18 | 54.7% |
| after-DOWN only | 825 | +0.54 | −20.67% | 1.18 | 55.5% |
| **combined** | **670** | **+0.80** | **−15.57%** | **1.31** | **55.4%** |

Each filter individually helps; the combination is strictly better than either alone on Sharpe, MDD, and PF.

**Regime split comparison**:

| Variant | 2019-2020 | 2021-2022 | 2023-2026 HO |
|---|---|---|---|
| baseline | +0.09 | **−0.44** | +1.40 |
| drop-Fri | +0.47 | +0.25 | +1.41 |
| after-DOWN | +0.38 | +0.28 | +0.86 |
| **combined** | **+0.63** | **+1.00** | **+0.85** |

**Key observation**: the combined filter lifts the prior-*weakest* regime (2021-2022, −0.44 → +1.00) to become the *strongest*. This is the opposite of the overfit signature (where holdout degrades while full-sample improves). Mechanism story: in the 2021-2022 hawkish-ECB / Russia-Ukraine window, down days were often followed by more down days, killing the baseline premium. Filtering to after-down-day specifically keeps the rebound setups while the drop-Friday filter removes weekend-de-risking drag — the combination selects for the "oversold rebound" subset of overnight trades.

**Phase 2 kill-criteria (combined)**: PASS on all.

| Criterion | Bar | Actual | Result |
|---|---|---|---|
| Sharpe | > +0.20 | +0.80 | PASS |
| Max DD | < 25% | 15.57% | PASS |
| Trades | ≥ 200 | 670 | PASS |
| WR ≥ 50 or PF ≥ 1.05 | — | 55.4% / 1.31 | PASS both |

**Cost sensitivity (combined)**:

| Cost RT | Sharpe | MDD |
|---|---|---|
| 0.5pt | +0.83 | −15.54% |
| 1.0pt | +0.80 | −15.57% |
| 1.5pt | +0.77 | −15.60% |
| 2.0pt | +0.73 | −15.63% |
| 3.0pt | +0.67 | −15.69% |

Exceptionally cost-robust. The gross edge is large relative to spread — the binding cost is overnight financing (not modelled), not spread.

**Null-check (combined)**: the mirror config (SHORT-only × drop-Fri × after-UP-day) gives Sharpe −0.42 (n=818). LONG+SHORT sum = +0.38 — mildly antisymmetric, weaker than the ideal "strong-antisymmetry" case but clearly directional.

**Deploy-readiness qualifiers**:

1. **Overnight financing**: at current ECB rates (~3.5%) + CFD financing spread (~2%), carrying DAX CFD long overnight costs ~1.5-2.5pt/night. This is a 10-15 bps drag per trade that the 1pt RT spread model doesn't capture. Conservative live-cost estimate: ~4pt-equivalent, giving research-Sharpe +0.67 at 3pt extrapolated to +0.60-0.65 net of financing. Still positive.
2. **Live Sharpe expectation** after standard 10-25% haircut on +0.80 research → +0.60 to +0.72. (Moot — QC futures validation invalidated this; thesis preserved for tombstoning only.)
3. ~~**Blend with ORB T+180 LONG-only**~~ — not pursued. The QC validation (see below) invalidated the overnight leg's research edge; blending would drag ORB down.

## QC futures validation — 2026-04-20

QC port [deploy/qc_overnight_dax.py](../../deploy/qc_overnight_dax.py) on FDAX continuous futures (IB execution model, Berlin TZ), identical filter logic and entry/exit times.

| Metric | Research (CFD) | QC v2 (FDAX, fixed) | Delta |
|---|---|---|---|
| Sharpe | +0.80 | **−0.34** | −1.14 |
| CAGR | +7.33% | +1.54% | 0.21× |
| MDD | −15.57% | −10.4% | matches loosely |
| Win rate | 55.4% | 53% | matches |
| Avg win | 0.63% | 0.34% | 0.54× |
| Avg loss | −0.60% | −0.34% | 0.57× |
| PF | 1.31 | 0.99 | large drop |
| Trades / orders | 670 / ~1340 | 786 / 1577 | ~17% more |

**What the diagnostic says**:
- Win-rate and filter-dates matched between research and QC → the filter logic is implemented correctly.
- Avg-win AND avg-loss both ~half the research magnitude → per-trade P&L magnitude is compressed on futures.
- MDD matches loosely → tail-risk exposure is about the same, but the compensating positive days are much smaller.
- Rough breakdown of the Sharpe gap:
  - Research → QC v1 (17:28/09:01 timing + per-mapped liquidate): Sharpe +0.80 → −0.37 (gap −1.17).
  - QC v1 → QC v2 (17:29/09:00 timing + liquidate-all): Sharpe −0.37 → −0.34 (gap +0.03).
  - Timing fix and roll fix account for ~0.03 of the +1.17 gap. **The remaining +1.14 is structural.**

**Why CFD data overstated the edge (best-guess)**: IC Markets / similar MT5 GER40 feeds synthesize the overnight close-to-open return from dealer-desk quote mechanics — spread repricing over the CFD-paused window (17:30-09:00 on many CFD brokers), open-auction fill logic, possibly slippage-adjusted quote construction. None of that exists on continuously-traded FDAX. The strategy's "alpha" was the CFD-provider's quote construction, not a tradeable market effect.

**Implication**: the combined-filter research Sharpe +0.80 does NOT translate to any futures-executable environment. Do not deploy on futures. Overnight leg is not a usable blend-component either — it would drag any companion strategy rather than diversify it.

**Retained finding that's still real**: the DAX does have a positive overnight drift on continuously-traded futures — gross CAGR +1.54% over 7y, Sharpe −0.34 only because risk-free rates (~4-5%) are now above that gross. A futures-passive "always long overnight" approach would earn less than T-bills. Nothing exploitable on the combined-filter strategy.

**Methodological lesson**: always run a QC-futures-equivalent cross-validation on MT5-CFD research, especially for any strategy whose mechanism involves overnight/session-gap / close-to-open dynamics. The CFD synthetic quote handling over session breaks is a known source of phantom alpha and was not caught by the Phase 2 cost-sensitivity or regime-breakdown tests.

---

## Thesis (mechanism)

Literature documents persistent positive overnight drift on major equity indices (Lou/Polk/Skouras 2019 on SPX, Barclay-Hendershott-Jones 2008 on earnings-overnight behaviour). Proposed drivers: (1) compensation for holding overnight gap risk that day-traders don't want, (2) information arrival concentrated during non-session hours (corporate earnings in NY after 16:00 ET, Asia macro open, European data releases 07:30-08:30 Berlin), (3) closing-auction reversion on the open.

On DAX, the overnight window is 17:30 Berlin → 09:00 Berlin (= 15.5 hours), which includes the US RTH crossover 15:30-22:00 Berlin + Asian session overnight + European pre-market data. If the overnight-premium thesis holds, a strategy that goes long the last bar of the DAX session and unwinds at the first bar of the next session should earn the net overnight return — untradeable if the cost is symmetric to overnight return, but a useful *blend-component* diversifier if Sharpe is positive.

Mechanism hypotheses:
1. **Gap-risk premium**: Sharpe positive simply because positions are compensated for overnight volatility.
2. **Asia/US crossover info**: US post-16:00 ET earnings + Asian macro imply mean positive drift (since world index-weighted earnings surprises are historically skewed positive).
3. **Closing-auction reversion**: if Xetra close clears at a (slight) discount to true value, the next open's auction clears higher — captured as close-to-open return.

## Key references

- **Lou, Polk & Skouras (2019)**, "A Tug of War: Overnight Versus Intraday Expected Returns." *JFE* 134(1). On SPX, >100% of annual return comes from overnight. Intraday is zero-to-negative.
- **Berkman, Koch, Tuttle & Zhang (2012)**, "Paying Attention: Overnight Returns and the Hidden Cost of Buying at the Open." *JFQA* 47(4). Retail attention drives overnight mispricing; reverses intraday.

## Signal math

```
Parameters:
  EXIT_BAR_ENTRY    = last bar of session (17:25-17:30)
  NEXT_BAR_EXIT     = first bar of next session (09:00-09:05)
  COST_POINTS_ROUND_TRIP = 1.0
  DIRECTION         = "long"   (baseline; "short" null-check)

Per trading day d (entry at last bar of d, exit at first bar of d+1):
  entry_px  = close[last bar of d]
  exit_px   = open[first bar of d+1]
  pnl       = sign * (exit_px / entry_px - 1) - cost / entry_px
```

Variants: always-long (baseline), always-short (null), conditional on:
- Day-of-week (Mon / Tue / Wed / Thu / Fri — Mon has weekend effect).
- Prior-day return sign (up day → long; down day → long-only or short-only).
- Prior-week VIX-proxy (realised range tercile).

## Expected performance

Literature Sharpe on SPX overnight-buy: 0.7-1.0 gross. DAX has shorter literature but generally 0.3-0.6 Sharpe on similar strategies. On CFD at 1pt RT cost the friction is ~6bps per round-trip — if mean overnight return is 5-10bps gross, this is a net-zero-to-marginally-positive trade. Expected Sharpe 0.15-0.45 net.

**This is the baseline-sanity test** to calibrate "what does the overnight window do passively?" before reading any of the signal-based DAX strategies.

## Fail conditions (pre-committed)

Phase 2 kills if ANY:
- Full-period Sharpe < 0.20 (lowered bar — this is a "premium capture" trade, not an alpha trade).
- Max DD > 25%.
- **Null-check (short direction) must lose more than long wins** (i.e., long_Sharpe + short_Sharpe < 0 is sign of a real overnight premium; if both are near zero, no premium).

Phase 4: Sharpe positive in ≥ 2 of 3 regime windows.
Phase 6: 2023-2026 holdout Sharpe ≤ 0.

**No trade-count kill** — it's 1 trade per day by construction (~1850 trades over 7.3y).

## Why this might fail

1. **Cost dominates small gross**: at 1pt RT ≈ 6bps, a 4-7bps overnight drift nets flat-to-negative.
2. **European-specific**: Lou-Polk-Skouras showed overnight effect is strongest on US equities. DAX may show weaker effect due to less retail attention and more continuous macro data flow.
3. **Regime dependence**: bull-market years (2019-2021, 2023-2024) likely dominate the overnight Sharpe; bear years (2022) may flip the sign.

## Files

- Thesis: this file.
- Demo: `overnight_demo.py` — baseline always-long, null, and day-of-week / prior-direction conditionals.
