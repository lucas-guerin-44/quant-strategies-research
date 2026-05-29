# Softs TSMOM ensemble — VALIDATED_NO_DEPLOY (6-name research PASS; Eightcap-tradeable subset REJECT 2026-05-29)

## Origin

From the single-instrument scan in `experiments/gold_trend/single_instrument_scan.py`,
three soft-commodity instruments passed Phase 2 kill-criteria AND showed
meaningful alpha vs their own buy-and-hold. An expansion-batch fetch of 9
additional ag/livestock futures then screened for Phase 2 gate (Sharpe ≥
0.30 AND alpha vs B&H ≥ 0.00); three more passed.

**Final ensemble (6 instruments), per-instrument MH-LO + pyramid, scan-stage stats:**

| Instr        | Strat Sharpe | B&H Sharpe | α vs B&H | Strat CAGR | MDD  |
|---|---|---|---|---|---|
| COCOA        | 0.45 | 0.21 | +0.24 | +3.1% | -29% |
| COFFEE       | 0.41 | 0.32 | +0.09 | +3.0% | -30% |
| COTTON       | 0.40 | 0.22 | +0.18 | +3.2% | -27% |
| CORN         | 0.34 | 0.17 | +0.17 | +2.5% | -24% |
| SOYBEAN      | 0.46 | 0.17 | +0.29 | +3.2% | -19% |
| LIVE_CATTLE  | 0.48 | 0.29 | +0.19 | +3.9% | -15% |

Dropped candidates (failed Sharpe ≥ 0.30 or α ≥ 0.00):
- Grains: WHEAT (Sharpe 0.09, α -0.06), KC_WHEAT (-0.04, α -0.20), OATS (0.03, α -0.18)
- Other: ORANGE_JUICE (0.24, α -0.01)
- Livestock: FEEDER_CATTLE (0.33, α -0.00), LEAN_HOGS (-0.20, α -0.44)
- From initial scan (softs): SUGAR (failed), LUMBER (failed, short history)

Standalone Sharpes are modest (0.34-0.48) but **alpha over buy-and-hold is
real on all 6** — meaning trend following adds value over passive exposure,
unlike what we saw on gold and BTC where the edge was purely drawdown
avoidance.

The bet is that an equal-weight ensemble of 6 low-correlation ag/livestock
futures materially outperforms any single instrument, matching MOP (2012)'s
cross-asset TSMOM result at a retail-tradable subset.

## Why softs / grains / livestock, why retail-accessible

**Mechanism:** these instruments trade on weather/supply shocks that play
out over months-to-years. Hurricane seasons, crop-disease cycles, El Niño
/La Niña regimes, trade-policy shifts (EUR cocoa deforestation regulation
2024, Brazil frost 2021, mad-cow / disease outbreaks on livestock). These
drive multi-month persistent trends structurally different from macro-
driven FX / equity cycles.

**Retail-accessible:**
- Futures on CME/ICE are liquid, centrally cleared, IB/IBKR-tradable at
  retail size (one contract COCOA ~$30k, SOYBEAN ~$60k, LIVE_CATTLE ~$75k).
- Alternative: ag ETFs (NIB cocoa, JO coffee, BAL cotton, CORN, WEAT, SOYB,
  COW livestock) exist but have significant contango drag (2-5% CAGR)
  — futures are the honest vehicle.
- Monthly rebalance cadence — nowhere near HFT territory.
- Combined OI across these six markets is > $20B — no capacity constraint
  at our scale.

**Critically:** these markets are uncorrelated with equities (our XS-mom
leg) and with bonds (our treasury_trend leg). If the ensemble works, it
slots into the portfolio as a true non-overlapping diversifier — unlike the
BTC-trend rejection where equity exposure through XS-mom's ETF ranking
already dominated the blend.

## Universe / Period

All 6 instruments span **2015-01-02 → 2026-04-17** (~2835-2840 bars each,
11.3 years). Data sourced via `scripts/yahoo_fetch.py` (Yahoo front-month
futures).

Cash-when-flat: 0% (no cash overlay; flat = uninvested).

## Signal + sizing

Inherited from gold_trend / btc_trend — *no re-tuning on softs*:
- **Multi-horizon** signal: sign-average of 1M + 3M + 12M past returns.
- **Long-only**: flat when signal goes negative (softs have deep bear
  cycles but shorting is costlier and short squeezes on crop-shortage
  news can be brutal).
- **Vol-target** 15% annualized per instrument.
- **Pyramid**: K=3 units, ATR(14) × 1.0 favorable trigger, cap at 1.00×.
- **Rebalance**: monthly (21 bars).
- **Costs**: 5 bps per side (softs futures at IB retail are ~2-4 bps, so
  this is a conservative baseline).

Ensemble aggregation: **equal-weight daily returns across the 6
instruments**. Each runs independent, portfolio daily return =
mean(returns) across available instruments. No cross-instrument ranking
(that's XS-mom's job, which we've already seen picks equity ETFs); this is
pure TS-mom per instrument + pooled into a portfolio.

## Correlation structure (observed)

Daily strategy-return correlation matrix:

```
             COCOA COFFEE COTTON  CORN SOYBEAN LIVE_CATTLE
COCOA        1.000  0.025  0.002 0.019  -0.019       0.037
COFFEE       0.025  1.000  0.095 0.075   0.078       0.064
COTTON       0.002  0.095  1.000 0.160   0.097       0.027
CORN         0.019  0.075  0.160 1.000   0.442      -0.043
SOYBEAN     -0.019  0.078  0.097 0.442   1.000       0.010
LIVE_CATTLE  0.037  0.064  0.027 -0.043  0.010       1.000
```

Most pairs are ~0. The one meaningful correlation is **CORN-SOYBEAN at
0.44** (both US grains, same weather/supply drivers). Effective ensemble N
is therefore ~5, not 6. Livestock's near-zero correlation with grains
(-0.04 with CORN) validates its inclusion.

Average off-diagonal daily corr: **+0.071**.

## Expected outcome

Per-instrument Sharpes: 0.34-0.48 (avg 0.42).
At average pairwise corr +0.07 and N=6 (effective ~5):

  Expected blend Sharpe = avg_Sh × sqrt(N / (1 + (N-1)ρ))
                        ≈ 0.42 × sqrt(6 / (1 + 5×0.07))
                        ≈ 0.42 × 2.04 ≈ **0.86**

Observed blend Sharpe (Phase 2 demo + Phase 3 validation): **0.85-0.89**.
Matches theoretical prediction almost exactly.

Calibrated against the research-to-QC degradation note in memory: expect
**QC-realistic Sharpe 0.55-0.70** on softs futures at IB (fees are milder
than the Coinbase / IB equity retail case that dropped crypto/XS-mom by
~0.4 Sharpe). Softs futures average ~2-4 bps/side at retail contract
sizes, below our 5bps research assumption.

## Fail conditions (pre-committed)

1. **Blend Sharpe < 0.50 at 5 bps/side** → reject.
2. **Blend alpha vs equal-weight B&H basket ≤ +0.10 Sharpe** → reject.
3. **MDD > 35%** → reject.
4. **One instrument drives > 60% of blend return** → reject.
5. **Average pairwise correlation ≥ 0.5** → yellow flag on diversification.

## Validation status

- **Phase 2 (MVI)**: PASS — blend Sharpe 0.89, CAGR 3.48%, MDD -13.3%,
  alpha vs B&H basket +0.42 Sharpe. All 6 kill criteria pass.
- **Phase 3 (stat battery, n_trials=12)**: PASS — Bootstrap CI [+0.26, +1.44]
  excludes 0, position-shuffle permutation p=0.0000 (null mean -0.54),
  Deflated Sharpe 0.81 with p=0.0000.
- **Phase 4 (regime stability)**: PASS — 3/4 windows positive, max window
  share 51.5%. (W1 2015-17 is the negative window at Sharpe -0.38.)
- **Phase 5 (param sensitivity)**: PASS — 0/21 configs negative, max drop
  under ±20% perturbation is 1.4% on vol-target and 1.3% on cost. Strategy
  is on a wide plateau.
- **Phase 6 (true holdout)**: PASS — IS 2015-2022 Sharpe +0.66, OOS
  2023-2026 Sharpe +1.44. Degradation -0.77 (negative = OOS outperformed
  IS). *Per WORKFLOW.md: flag, don't celebrate — the OOS period had
  exceptional soft-commodity trends (cocoa 2023-24 parabola, coffee bull,
  etc.) that favor the strategy by design.*
- **Phase 7 (correlation vs live strategies)**: not yet run but expected to
  be strong; softs are structurally uncorrelated with equities/bonds/crypto.
- **Q1 2026 real-OOS** (Jan-Mar 2026, post-validation period): blend +1.10%
  vs B&H basket -6.57%. Strategy stayed flat through the -45.6% COCOA
  crash. Textbook trend-following outcome.

## Eightcap-deployable subset re-validation (2026-05-29) — REJECT

Triggered by the live-book "what can we still add, Eightcap-only" pass. Two-step Phase-0:

1. **Tradeability (MT5 probe — `scripts/mt5_fetch.py --list-symbols`):** Eightcap carries COCOA,
   COFFEE, COTTON, CORN, LDSUGAR, WHEAT — but **not** soybean or live-cattle (the two highest-alpha
   validated names, α +0.29 / +0.19).
2. **CFD swap ceiling (lesson #59 — `scripts/softs_swap_probe.py`):** live long-side financing splits
   the basket. COCOA ~−0.14%/yr and COFFEE ~+0.13%/yr survive; **COTTON ~−16.9%, CORN ~−17.2%,
   WHEAT ~−11.2%/yr** are PEAD-redux (swap eats the ~3% gross edge).

So the only Eightcap-tradeable **and** swap-survivable cut is a **COCOA+COFFEE 2-name blend**.
Re-validated on the long Yahoo continuous series (`COCOA_YF`/`COFFEE_YF`, 2015→2026, swap modelled) via
`softs_ensemble_eightcap.py`:

| Check | Result | |
|---|---|---|
| Blend Sharpe (post-cost, swap on) | **+0.59** | clears +0.30 nominally |
| Alpha vs B&H basket | +0.24 | PASS |
| **Regime concentration** | **81.8% in 2023-26** | **FAIL** — W Sh: −0.40 / −1.14 / +0.01 / +0.49 / **+1.67** |
| **Null-gap (normal − inverse)** | **+0.24** | **FAIL** (need > +0.30) |
| MDD | −26.9% | over the 25% convention |
| Corr vs live book (XAU/NDX/GER/JPY) | max \|0.018\| | ~zero — would diversify beautifully |
| Trades | 170 | PASS |

**Verdict: REJECT for Eightcap standalone deploy.** The full-sample +0.59 is a mirage carried entirely
by the 2023-2026 soft-commodity bull (cocoa 2024 squeeze, coffee 2024-25 rally) — the same
one-window-wonder shape as `gold_trend` (lesson #73). The 6-name basket's robustness (Phase-6 flagged,
but max window-share 51.5%) lived in the names we can't trade: cotton/corn (swap-dead) and
soybean/live-cattle (not offered). The cruel part — cocoa+coffee is genuinely ~zero-correlated to the
entire live book, so it would have been an ideal diversifier; uncorrelated noise just isn't alpha.

**softs_ensemble stays VALIDATED_NO_DEPLOY** — the 6-name research result is unchanged and real; it's
simply not reachable on Eightcap, and the reachable subset doesn't carry it. See lesson #86.

Files: `softs_ensemble_eightcap.py` (subset re-validation), `scripts/softs_swap_probe.py` (CFD
swap-ceiling probe).
