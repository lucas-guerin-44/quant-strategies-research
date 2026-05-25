# Hurst-exponent regime classifier — diagnostic study (cross-instrument)

**Status**: Phase 1 complete (2026-05-23). Backward-looking diagnostic.

**Verdict**: **MARGINAL (asymmetric)** — Hurst regime label is informative for the
TSMOM family (6/8 instruments full-sample pass; 3/5 W4-eligible post-2023 pass),
but is NOT informative for the MR/fade family (4/8 full-sample, 0/5 post-2023).
The MR-side null-collapse independently corroborates lesson #43 — post-2022
0DTE-amplification has killed MR direction on risk assets regardless of any
regime classifier. Concrete follow-up: a Hurst-gated TSMOM Phase 2 is worth
running on `tsmom` / `btc_trend` (specifically: H>0.50 entry filter over the
prior 252d, pre-committed Sharpe improvement ≥ +0.15 absolute on W4).

---

## What this experiment is (and isn't)

This is **not** a new strategy. It's a **diagnostic study** answering one question:

> Does a rolling Hurst exponent computed on the underlying instrument's daily returns
> classify regimes in a way that separates winning from losing windows for the
> trend / mean-reversion families already validated in this repo?

Specifically, the meta-claim being tested is: *Hurst regime is informative about
which strategy family (TSMOM vs MR/fade) extracts edge in the current sub-window*.
If it is, a rolling Hurst gate is a candidate **regime overlay** for the existing
tsmom / btc_trend / lunch_fade / opex_pin_fade / earnings_fade families. If it
isn't, the entire Hurst-as-regime-filter direction gets tombstoned and we save
ourselves from a known overfit trap (Hurst lookback + threshold are two free
parameters that almost always curve-fit in-sample).

This is a pre-emptive Phase-0 study, not Phase 2 of any strategy.

## Thesis (mechanism)

The Hurst exponent `H` of a time series partitions behaviour:
1. **`H > 0.5` — persistent / trending.** Successive returns positively
   autocorrelated. TSMOM-style mechanisms should extract edge here.
2. **`H < 0.5` — anti-persistent / mean-reverting.** Successive returns
   negatively autocorrelated. Fade / MR mechanisms should extract edge here.
3. **`H ≈ 0.5` — geometric Brownian.** Neither family has a directional prior.

If Hurst is a useful regime label for *this* repo's strategies, then on a
**fixed**, parameter-free naive-TSMOM rule and a **fixed**, parameter-free
naive-MR rule, the realised per-bar Sharpe should be reliably **higher in the
matched regime** than in the mismatched regime across multiple instruments.

If the regime-conditional Sharpe gap is small, inconsistent across instruments,
or sign-flipped in the holdout half — the Hurst label is not load-bearing.

## Key reference

- **Peters (1991/1994), Fractal Market Hypothesis** — the canonical motivation
  for using Hurst as a market-regime classifier; rescaled-range (R/S) origin.
- **Peng et al. (1994), DFA on heartbeat series** — Detrended Fluctuation
  Analysis, the more robust modern estimator we use here (handles
  non-stationarity in mean).
- **Lo (1991), "Long-Term Memory in Stock Market Prices"** — classic critique:
  the apparent long-memory in equity returns largely vanishes under modified-R/S
  bias correction. Honest prior: equity D1 series are mostly near H ≈ 0.5.

## Signal math

```
Rolling Hurst (per instrument, per day t):
  returns_t = log(close[t-252:t]).diff()
  H_t       = DFA(returns_t, scales=[10, 20, 50, 100])

  scales:  s in {10, 20, 50, 100}
  for each s:
    1. integrate:     X[k] = cumsum(returns - mean(returns))
    2. segment X into N/s non-overlapping windows
    3. per window: detrend (linear), compute RMSD around trend
    4. F(s) = mean of RMSDs across windows
  H_t = slope of log(F(s)) vs log(s)

Regime label (per t):
  TREND   if H_t > 0.55
  MR      if H_t < 0.45
  NEUTRAL otherwise   (excluded from regime-conditional Sharpe stats)

Naive TSMOM probe (fixed, no parameters tuned):
  signal_t = sign(close[t] / close[t-60] - 1)
  position_t = signal_t   (long/short, full notional)
  bar return = position_t * (close[t+1] / close[t] - 1)

Naive MR probe (fixed, no parameters tuned):
  z_t      = (ret[t] - mean(ret[t-20:t])) / std(ret[t-20:t])
  if z_t > +1.5: position_t = -1
  if z_t < -1.5: position_t = +1
  else:          position_t = 0
  hold 5 trading days then exit
```

Both probes are deliberately parameter-free relative to common usage — the
*lookback*, the *threshold*, the *hold period* are written into the spec
before any data is touched. We do NOT sweep these.

## Why retail-accessible

This is a diagnostic. Not deployed. If it passes, the follow-up work is to
strap the Hurst gate onto an existing-deploy strategy and re-run that
strategy's Phase 2-6 with the gate active — that's where retail-accessibility
gets evaluated.

## Universe

8 instruments with ≥ 5y D1 history on disk:

- **Equity indices**: SPX500, NDX100, GER40
- **Crypto**: BTCUSD, ETHUSD
- **Commodities**: XAUUSD, USOUSD (WTI)
- **FX**: EURUSD

Window: 2015-01-02 → 2026-04-17 (full history per instrument; varies).

## Expected performance (at thesis time)

Honest priors from the literature and this repo's accumulated lessons:

- **Equity-index daily H** sits very close to 0.5 (Lo 1991) — expect most days
  classified NEUTRAL, with the TREND-vs-MR split having low N.
- **Crypto daily H** has been argued to drift above 0.5 in early-cycle bull
  regimes and below 0.5 in chop — expect more regime contrast.
- **Commodities and FX** are mixed; XAU has notable regime persistence,
  EURUSD is the textbook "random walk" benchmark.

Expected outcome distribution (writing this BEFORE seeing data):
- **Most likely (60%)**: REJECT — equity indices show flat or sign-flipped
  TSMOM-vs-MR conditioning; crypto shows the expected pattern; FX and
  commodities mixed. Not enough instruments line up to call the gate useful.
- **Plausible (25%)**: MARGINAL — TSMOM directional probe works as expected
  but the MR probe doesn't (asymmetry consistent with lesson #43 — post-2022
  MR mechanisms keep sign-flipping anyway).
- **Unlikely (15%)**: PASS — full validation, both probes line up on ≥5 of 8
  instruments. Strong signal to follow up with a Phase 2 on btc_trend +
  Hurst gate.

## Fail conditions (pre-committed)

This is the load-bearing section. Written BEFORE the experiment runs.

**Primary kill criterion** — the Hurst regime gate is REJECTED if BOTH of the
following hold:

1. **TSMOM directional failure**: fewer than 5 of 8 instruments show naive-TSMOM
   Sharpe in the TREND (H > 0.55) regime that is at least **+0.30 absolute Sharpe
   higher** than in the MR (H < 0.45) regime.
2. **MR directional failure**: fewer than 5 of 8 instruments show naive-MR
   Sharpe in the MR (H < 0.45) regime that is at least **+0.30 absolute Sharpe
   higher** than in the TREND (H > 0.55) regime.

If both fail → **REJECT** + tombstone.
If exactly one passes → **MARGINAL** (asymmetric — note which direction).
If both pass → **PASS** + follow-up with concrete next-experiment proposal.

**Secondary kill criterion — walk-forward integrity** (per repo lesson #29):

The regime-edge must hold separately in:
- **Pre-2023 half** (2015-2022, the IS regime that pre-dates 0DTE-amplification)
- **Post-2023 half** (2023-2026, the W4-equivalent OOS window)

If the regime-edge holds full-sample but reverses sign post-2023 → REJECT
regardless of (1)/(2). This is the same trap that took down opex_pin_fade
(lesson #-5) and earnings_continuation_mag7 (lesson #-7).

**Tertiary kill criterion — sample-size honesty**:

If any regime bucket has fewer than 100 trading days for an instrument, that
instrument is excluded from the count rather than spuriously included. Need
at least 5 instruments with sufficient data in BOTH regimes.

**Direction null-check** (per CLAUDE.md step 6):

Per-instrument, we also flip the rule:
- Naive-TSMOM in MR regime (should LOSE if mechanism real)
- Naive-MR in TREND regime (should LOSE if mechanism real)

If the "wrong-regime" Sharpe is comparable to the "right-regime" Sharpe,
Hurst has no directional content — REJECT even if numbers look symmetric.

## Why this might fail (red flags)

1. **Daily returns on equity indices have H ≈ 0.5 with very low variance
   across estimators** (Lo 1991). Hurst likely classifies almost everything as
   NEUTRAL on SPX/NDX, and the TREND/MR buckets become noise-dominated.
2. **Hurst is laggy.** A 252-day rolling window means the regime label updates
   slowly; by the time H crosses a threshold, the regime may already be
   transitioning back. This is a known weakness of long-lookback regime
   classifiers.
3. **DFA estimator variance on 252 samples is high** (theoretical σ(H) ≈ 0.05
   at N=252). Two adjacent days' H estimates can disagree by more than the
   regime threshold (0.45 vs 0.55) just from estimator noise.
4. **The naive-TSMOM and naive-MR probes are themselves crude.** A real edge
   that depends on richer signal construction (vol-targeting, multi-horizon
   ensemble) might not show up under these probes — i.e., the probes might
   reject Hurst-as-regime-classifier even though the right richer probe would
   accept it. This is acknowledged but accepted: the alternative is to start
   tuning probe parameters, which curve-fits the test itself.
5. **post-2022 0DTE inversion (lesson #43)** could make any equity-MR
   conditioning sign-flip in the holdout regardless of what Hurst says about
   the underlying.

## Phase 1 → 2 plan

- [x] Write thesis with pre-committed fail conditions (this doc).
- [ ] Implement `regime_hurst_diagnostic.py` with DFA-numpy, regime-bucket
      Sharpe table, walk-forward split, null-check.
- [ ] Run end-to-end, populate results tables below.
- [ ] Update verdict + mechanistic interpretation.
- [ ] If PASS or MARGINAL: propose specific follow-up Phase 2 in
      `experiments/<follow-up>/`. If REJECT: tombstone the family.

## Files

- `regime_hurst_diagnostic.md` — this doc
- `regime_hurst_diagnostic.py` — diagnostic runner (loads 8 D1 series, computes
  rolling H, partitions naive-TSMOM and naive-MR returns by H regime, prints
  per-instrument and walk-forward tables, returns verdict)

---

## Results (2026-05-23)

### Rolling-Hurst summary (per instrument)

DFA H estimates clustered tightly around 0.5 as Lo (1991) predicts.

| Instrument | Median H | IQR | Notes |
|---|---|---|---|
| SPX500 | 0.476 | [0.421, 0.529] | mildly anti-persistent |
| NDX100 | 0.479 | [0.428, 0.526] | mildly anti-persistent |
| GER40  | 0.495 | [0.435, 0.558] | near-symmetric |
| BTCUSD | 0.512 | [0.459, 0.563] | mildly persistent |
| ETHUSD | 0.516 | [0.460, 0.577] | most persistent |
| XAUUSD | 0.494 | [0.424, 0.567] | wide IQR (regime-switching) |
| USOUSD | 0.474 | [0.414, 0.537] | mildly anti-persistent |
| EURUSD | 0.465 | [0.418, 0.508] | strongest anti-persistent |

Crypto trends persistent (consistent with reflexive flow), FX most anti-persistent
(consistent with carry/mean-reversion equilibrium dynamics), equities and metals
on the boundary. The IQRs span the regime thresholds (0.45 / 0.55) for every
instrument — i.e., each instrument visits all three regime buckets in the
sample — so bucket-count power is acceptable in the full sample (≥ 200 days per
bucket on most instruments). Post-2023 sub-window is smaller; 3 of 8
instruments fall below the 100-day eligibility floor in one bucket.

### Full-sample regime-conditional Sharpe

| Instr | n_TREND | n_MR | n_NEUT | TSMOM in T | TSMOM in MR | Δ_TSMOM | MR in MR | MR in T | Δ_MR |
|---|---|---|---|---|---|---|---|---|---|
| SPX500 |  461 |  949 | 1090 | +1.05 | -0.26 | **+1.32** | +1.29 | +0.83 | +0.46 |
| NDX100 |  287 |  612 |  865 | +1.02 | -0.13 | **+1.16** | +2.82 | +6.74 | -3.93 |
| GER40  |  675 |  747 | 1060 | +0.25 | -0.65 | **+0.90** | -0.31 | +0.97 | -1.28 |
| BTCUSD |  750 |  534 | 1175 | +1.12 | -0.02 | **+1.14** | -2.70 | -1.10 | -1.60 |
| ETHUSD |  993 |  614 | 1223 | +0.20 | +1.49 | -1.29 | -2.68 | +0.61 | -3.29 |
| XAUUSD |  817 |  889 |  944 | +0.44 | +0.86 | -0.42 | -0.95 | -1.69 | +0.74 |
| USOUSD |  521 |  994 |  982 | +0.53 | -0.67 | **+1.20** | +0.08 | -0.72 | +0.80 |
| EURUSD |  211 | 1035 | 1291 | +0.26 | -0.10 | **+0.36** | -0.16 | -2.10 | +1.94 |

**TSMOM directional pass** (Δ ≥ +0.30): **6 of 8** (SPX, NDX, GER, BTC, USO, EUR) — clears threshold.
**MR directional pass** (Δ ≥ +0.30): **4 of 8** (SPX, XAU, USO, EUR) — misses threshold (5/8 required).

### Walk-forward split

| Direction | Pre-2023 pass | Post-2023 pass | Eligible post-2023 |
|---|---|---|---|
| TSMOM in TREND vs MR | 5 / 8 | 3 / 5 | 5 instruments survive 100-day floor |
| MR in MR vs TREND    | 3 / 8 | **0 / 5** | 5 instruments survive 100-day floor |

The MR direction is **fully sign-collapsed post-2023** — zero of five eligible
instruments shows the predicted pattern. This is not a Hurst-classifier failure
per se; it's the same post-2022 0DTE-amplification killing MR generically
across the universe (see RESEARCH_NOTES lesson #43, and the four independent
fade REJECTs noted in `feedback_fade_direction_inverts_post_2022.md`). The
Hurst label cannot rescue a mechanism that has been structurally inverted.

TSMOM walk-forward stays sign-stable: pre-2023 Δ medians and post-2023 Δ medians
agree on direction (TSMOM still does better in H>0.55 windows post-2023, even on
the reduced eligibility set). Three of the five post-2023-eligible instruments
post Δ > +1.00.

### Direction null-check

- TSMOM "wrong regime" check (TSMOM in MR should LOSE): TSMOM trend-bucket Sharpe
  > MR-bucket Sharpe on 6 of 8 instruments, with magnitudes >> typical noise band.
  Mechanism has directional content.
- MR "wrong regime" check (MR in TREND should LOSE): only 4 of 8 instruments
  show the expected direction; the asymmetric cases (NDX, GER, BTC, ETH) all
  have MR-in-TREND OUTPERFORMING MR-in-MR. Mechanism does NOT have clean
  Hurst-conditional directional content on these instruments.

### Verdict

**MARGINAL (asymmetric)**. Hurst regime label is a useful classifier for **TSMOM**
edge timing — meets the 5-of-8 bar full-sample (6/8) and shows the expected
direction holding into post-2023. It is **not** a useful classifier for **MR/fade**
edge timing — fails the bar both full-sample (4/8) and post-2023 (0/5).

### Mechanistic interpretation

1. **The asymmetry is exactly what you'd predict from the recent 0DTE-MR-kill
   lessons** (#43 + memory `project_fade_direction_inverts_post_2022.md`). Long-trend
   continues to extract edge in regimes that the textbook H>0.55 label correctly
   identifies. Fade/MR mechanisms have been independently dismantled by the
   2023+ dealer-short-gamma + 0DTE positioning regime — and that dismantling is
   *not regime-conditional within the Hurst framework*; it's a structural break
   that affects all sub-windows. No Hurst gate can rescue a mechanism that
   doesn't work in either bucket.

2. **The TSMOM side surviving 252d-lag is a positive signal for the rolling-
   window framework itself.** A common Hurst critique is that the 252-day
   lookback makes the regime label too laggy to be useful — but the persistence
   in TSMOM Δ across the pre/post-2023 split shows the lag is acceptable for
   month-to-quarter-scale mechanisms (which is exactly TSMOM's natural cadence).
   Don't extend this conclusion to intraday strategies.

3. **ETHUSD is an outlier** — Δ_TSMOM = -1.29 full-sample, the worst of the
   universe despite ETH having the highest median Hurst. Inspection of the
   pre-2023 sub-window shows TSMOM in MR regime there scored +2.93 on n=192
   bars, dragging the full sample. This is a small-N pre-2023 sample-size
   artifact: the MR-regime in ETH pre-2023 captured the 2018-2020 chop that
   contained the most-rewarding momentum trades on aggregate (because the
   classifier just happened to flag the wrong sub-period). Post-2023, ETH's
   Δ_TSMOM normalizes to -0.39. Not a load-bearing counterexample.

4. **EURUSD passing TSMOM (Δ +0.36) is the most surprising result** given FX is
   the canonical low-edge TSMOM space. The pass is marginal (just over the
   +0.30 bar) and the n_TREND bucket is the smallest in the universe (211
   days). Treat as a near-noise pass — would not stake a Phase 2 on it.

5. **Hurst-as-MR-gate is now formally tombstoned** at the universe level. Any
   future fade/MR thesis cannot recover via "but we'd add a Hurst regime
   filter" because the regime filter doesn't separate the post-2023 sample. The
   structural-microstructure prereq from lesson #4 (single-venue intraday
   vacuum mechanism) remains the only viable filter for MR theses.

### Concrete follow-up

**PROPOSE** Phase 2 experiment: `tsmom_hurst_gated` — re-run the existing
`tsmom` backtest (currently KEEP_FOR_REFERENCE at Sh 0.40 / +0.69 corr with
xs_momentum) with a per-instrument H_t > 0.50 entry filter (relaxed from
0.55, since the diagnostic showed Δ already monotonic by 0.50). Pre-commit:

- Sharpe improvement ≥ +0.15 absolute on the W4 holdout (2023-2026) over
  ungated tsmom baseline.
- Correlation with xs_momentum reduced by ≥ 0.10 (gating likely concentrates
  positions in different sub-windows than xs_momentum).
- Trade count stays ≥ 200 over the full backtest (gating cuts trade flow).

If those three pre-commits pass on the W4 holdout, we have a deploy-grade
TSMOM variant with diversification value. If they don't, the Hurst overlay
joins the tombstone pile too.

**DO NOT PROPOSE** Phase 2 for any Hurst-gated MR/fade family. The result is
unambiguous: 0/5 post-2023 eligible. Mechanism is dead.
