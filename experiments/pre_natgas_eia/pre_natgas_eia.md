# Pre-EIA-NG drift on XNGUSD (24h pre-release, direction TBD)

**Status**: Phase 2 complete (2026-05-24). First test of the macro-event-drift
family on a *commodity-specific* event (vs NDX-on-US-macro events). Tested
24h pre-EIA-Weekly-Natural-Gas-Storage-Report drift on XNGUSD (Eightcap CFD,
broker symbol for Henry-Hub natural gas).

**Verdict**: **REJECT — tombstone**. Null-gap FAIL (+0.130 vs ≥+0.30
required), full-sample LONG mean -0.235% at 30bp RT (PF 0.83, Sh -0.53,
MDD -64.5%). W4 (2024-2026) shows tentative LONG activation (+0.179%,
Sh +0.39, walk-forward OOS mean +0.76 min +0.39) but the 2023 post-crisis
collapse drags the full-sample headline. Not deploy-grade; W4-only edge
doesn't clear the null-gap pre-commit. Family-extension lesson: index-on-
macro-event mechanism does NOT generalise to commodity-on-own-fundamental-
event in the same direction-LONG sense — different microstructure.

## What this experiment tests

The macro-event family (FOMC LONG, CPI LONG, NFP SHORT) all hit *index*
(NDX100) on *broad macro* releases. The mechanism story there is institutional
risk-premium accumulation/de-risking on equity exposure ahead of policy or
labour reads.

This thesis pivots in two ways:

1. **Asset is the *underlying* of the event**, not an index. The EIA Weekly
   Natural Gas Storage Report directly moves the Henry-Hub gas price; XNGUSD
   tracks Henry-Hub. If pre-event positioning exists, it should be visible in
   the price of the directly-exposed contract, not just a downstream equity.
2. **Event is *commodity-specific*, weekly cadence, mid-morning release.**
   EIA NG Storage Report drops Thursdays at 10:30 ET. ~52 events/yr.

**Mechanism hypotheses (both directions co-equal per lesson #54)**:

*LONG-bias hypothesis (institutional accumulation)*:
- Commercial hedgers (utilities, producers) accumulate exposure into the
  release rather than scrambling at announcement.
- The 24h pre-release window sees gradual long-building as speculators
  pre-position for a bullish-leaning consensus draw / smaller-than-expected
  injection.

*SHORT-bias hypothesis (institutional de-risking / supply-fear premium)*:
- Pre-release uncertainty causes longs to lighten ahead of a potentially
  bearish surprise (larger-than-expected injection / smaller draw).
- Asymmetric tail risk: a bearish-surprise injection can drive a sharp
  -3-5% intraday move; a bullish-surprise draw is more measured.
- Lesson #43 (post-2022 risk-asset MR/fade direction inverts) is a
  structural warning — data is entirely post-2022, so the SHORT hypothesis
  is *not* prior-disfavoured.

**Direction-TBD discipline binds**: pre_nfp_drift inverted from prior-LONG
to SHORT, pre_cpi_drift confirmed prior-LONG, four post-2022 MR experiments
(short_tsmom / orb_dax_sentiment / opex_pin_fade / eth_btc_ratio_mr) all
inverted from pre-commit. *Whichever side wins, pre-commit both, judge by
null-gap*.

## Pre-commits (applied to BEST of LONG/SHORT per lesson #54)

Per lesson #55 (kill-criteria templates must be mechanism-aware), uses the
asymmetric-payoff kill set, not the LONG-bias WR > 55% template:

1. **Best-direction per-trade mean > +0.15%** at 30bp RT cost (default).
   (Higher than the +0.10% NDX threshold to account for NG vol ~3-4× NDX.)
2. **Best-direction W4 (2024-2026) per-trade mean > +0.10%**.
3. **Best-direction PF > 1.3** (replaces WR > 55% per lesson #55).
4. **Best-direction Sharpe (×√52) > +0.30** (annualised, ~52 events/yr).
5. **Max DD < 25%**.
6. **Events ≥ 50** (have 177 historical → not binding).
7. **Direction null-gap |LONG − SHORT| ≥ +0.30%**.
8. **Walk-forward OOS mean Sh ≥ +0.30, min OOS Sh ≥ 0** (rolling splits).
9. **Placebo non-EIA Thursdays at 10:30 ET benign** (|mean| < 0.05% or |t| < 1.5).

PASS only if ALL of (1)-(9) hold for the same direction.

**Cost-model note (NG CFD-specific)**: Eightcap typical spread on XNGUSD is
3-5 pips on a ~3.00 contract = 100-170 bp round-trip — *much* wider than
the 1-2bp index CFDs. Default sweep is 10/30/50/100 bp RT. Pass threshold
is set at 30bp RT (realistic for typical Eightcap mid-day spread); 100bp
is the pessimistic-stress case.

## Why this might fail (red flags)

1. **NG-specific spread**: XNGUSD spreads are an order of magnitude wider
   than index CFDs. Even a +0.30% per-trade mean gross would be eaten by
   30-50bp RT cost. The mechanism must clear ~0.50%+ gross to survive on
   the broker.
2. **NG is microstructure-driven, not narrative-driven**: NG price is
   dominated by *physical* fundamentals (weather forecasts, storage levels,
   pipeline outages) plus *futures-curve* mechanics (contango/backwardation
   roll). Speculator pre-positioning is a smaller share of flow than in
   index futures. Pre-event drift mechanism may be weak/absent.
3. **Data starts 2023**: XNGUSD M5 only goes back to 2023-01-03 on the
   broker. Lose W1/W2 regimes entirely. No way to verify whether the
   mechanism was different pre-COVID. Walk-forward splits will be narrow
   (1.5yr IS / 1.5yr OOS at best).
4. **Weather is endogenous to the calendar**: EIA release dates are fixed
   Thursday, but the "weekly storage move" they report covers the prior
   Mon-Fri. Speculators may already have priced the print from weather and
   pipeline data published earlier in the week, leaving no edge in the
   24h window specifically.
5. **CFD ≠ futures = roll-noise risk**: XNGUSD is a continuously-priced
   CFD; the broker rolls the underlying contract internally. The CFD
   price may diverge from front-month NG futures by several percent during
   roll periods — could noise the signal.

## Files

- `pre_natgas_eia.md` — this doc
- `eia_ng_calendar.csv` — 209 EIA NG release dates 2023-01-05 → 2026-12-31
  (177 historical, 32 forward; holiday-shift rules applied)
- `pre_natgas_eia_demo.py` — Phase 2 simulator (clone of pre_cpi_drift_demo
  with NG-CFD cost sweep, sqrt(52) annualisation, regime split for
  data-limited W3/W4 window)

---

## Results (2026-05-24)

### Headline (both directions, 30bp RT, 24h window)

| Direction | n | mean | std | t | Sh (×√52) | MDD | WR | PF |
|---|---|---|---|---|---|---|---|---|
| LONG (winner) | 173 | -0.235% | 3.217% | -0.96 | -0.53 | -64.48% | 46.8% | 0.83 |
| SHORT (loser) | 173 | -0.365% | 3.217% | -1.49 | -0.82 | -67.81% | 46.8% | 0.75 |
| **Null-gap (LONG − SHORT)** | | **+0.130%** | | | | | | |

Both directions lose at the realistic 30bp NG-CFD cost. LONG is "less bad",
not actually profitable. The null-gap (+0.130%) sits below the pre-committed
+0.30 threshold — mechanism *lacks directional content* full-sample.

### Regime breakdown (LONG)

| Window | n | mean | std | t | WR | Sh |
|---|---|---|---|---|---|---|
| W3 (2023) | 52 | **-1.199%** | 2.825% | -3.06 | 30.8% | -3.06 |
| W4 (2024-2026) | 121 | +0.179% | 3.297% | +0.60 | 53.7% | +0.39 |

Two-regime story: **2023 post-Ukraine-war NG collapse swamps the full-sample
result**. NG spot crashed from $5+ to $2 across 2023 in a near-monotonic
unwind of European supply-fear premium; 24h pre-EIA LONG positions caught
the structural bearish momentum on the long side. W4 (2024-2026) shows
*tentative* LONG bias (+0.179%, Sh +0.39 — clears the W4_mean > +0.10%
pre-commit). But on the full sample, W3 dominates.

### Walk-forward — the only positive datapoint

| Split | IS n | IS Sh | IS mean | OOS n | OOS Sh | OOS mean |
|---|---|---|---|---|---|---|
| IS 2023 / OOS 2024-2026 | 52 | -3.06 | -1.199% | 121 | +0.39 | +0.179% |
| IS 2023-H1+2024-H1 / OOS 2024-H2-2026 | 78 | -2.19 | -0.958% | 95 | +0.82 | +0.359% |
| IS 2023-2024 / OOS 2025-2026 | 103 | -1.50 | -0.690% | 70 | +1.06 | +0.435% |

Mean OOS Sh **+0.76**, min OOS **+0.39**. Three-for-three positive OOS,
monotonically increasing with later cutoffs. Suggests the LONG mechanism
*activated* post-2023-crisis (similar shape to BTC institutionalisation
profile per memory `btc_institutionalization_mirror`). But this is *only*
visible after partitioning out the W3 crisis — the full-sample baseline
is the binding deploy decision, and it fails.

### Placebo

| Population | n | mean | t | Sh | WR |
|---|---|---|---|---|---|
| Placebo non-EIA Thu 10:30 ET LONG | 12 | -0.499% | -0.57 | -1.18 | 33.3% |
| Placebo non-EIA Thu 10:30 ET SHORT | 12 | -0.101% | -0.11 | -0.24 | 58.3% |

Sample-size limited (only ~12 non-EIA Thursdays in window — most Thursdays
ARE EIA dates). Placebo passes the |t| < 1.5 criterion vacuously. Not
informative either way; not load-bearing for the REJECT.

### Cost sensitivity (LONG)

| Cost (bp RT) | mean | Sh |
|---|---|---|
| 10 | -0.035% | -0.08 |
| **30** (default) | **-0.235%** | **-0.53** |
| 50 | -0.435% | -0.97 |
| 100 | -0.935% | -2.10 |

Cost-breakeven at ~7bp full sample — impossible on Eightcap NG CFD where
typical spread is 30-50bp RT. Even at zero cost (+0.065% mean) doesn't
clear the +0.15% pre-commit threshold.

### Window sweep (LONG, 30bp)

| Window | Best EB | Best mean | Best Sh |
|---|---|---|---|
| 6h | 30min | -0.284% | -1.66 |
| 12h | 30min | -0.180% | -0.85 |
| 18h | 30min | +0.054% | +0.21 |
| **24h** (pre-commit) | 30min | -0.235% | -0.53 |
| 48h | 30min | -0.250% | -0.36 |

Best window is 18h (+0.054%, Sh +0.21) but still fails the +0.15% pre-commit.
24h is the pre-commit; not changing per lesson #16 (no post-hoc window
hunting).

### Kill-criteria summary

| # | Criterion | Threshold | Realised | Verdict |
|---|---|---|---|---|
| 1 | Per-trade mean | > +0.15% | -0.235% | **FAIL** |
| 2 | W4 per-trade mean | > +0.10% | +0.179% | PASS |
| 3 | PF | > 1.3 | 0.83 | **FAIL** |
| 4 | Sharpe (×√52) | > +0.30 | -0.53 | **FAIL** |
| 5 | Max DD | < 25% | -64.48% | **FAIL** |
| 6 | Events | ≥ 50 | 173 | PASS |
| 7 | Direction null-gap | ≥ +0.30 | +0.130 | **FAIL** |
| 8a | Walk-forward OOS mean Sh | ≥ +0.30 | +0.76 | PASS |
| 8b | Walk-forward OOS min Sh | ≥ 0 | +0.39 | PASS |
| 9 | Placebo benign | |t| < 1.5 | -0.57 | PASS |

5 of 10 binding pre-commits FAIL. REJECT.

### Mechanistic interpretation

**The macro-event-drift family does NOT auto-generalise from index-on-US-macro
to commodity-on-own-fundamental.** The mechanism story behind FOMC/CPI LONG
on NDX is *institutional equity risk-premium accumulation* — a flow story
specific to broad equity index exposure under macro uncertainty. EIA NG
Storage Reports are a *direct fundamentals print* on the commodity itself:
- The print is information about the supply-demand balance of the underlying.
- Commercial hedger flow ≠ speculator pre-positioning flow; commercials are
  not "risk-premium accumulators" the way equity-fund flow is.
- Weather and pipeline data leak the print magnitude in the days prior, so
  the 24h pre-event window doesn't capture an information-asymmetry edge —
  the print is partially priced in already.
- Asymmetric tail risk (a bearish injection surprise can move price -5% in
  an hour; a bullish draw is milder) actively *discourages* pre-event
  long-positioning by speculators.

**The 2024-2026 activation is real but not deploy-grade**. W4 LONG (+0.179%,
OOS Sh +0.39-1.06) suggests the mechanism shifted modestly LONG after the
2023 crisis-unwind ended. But:
1. Null-gap is +0.13% even within W4-like subsamples (full-sample stat) —
   the activation is too weak to clear the pre-commit;
2. Full-sample baseline is the binding deploy threshold per repo discipline;
3. NG CFD cost on Eightcap (30-50bp RT) eats anything under ~+0.30% mean
   gross. Need *gross* mean > +0.50% to deploy comfortably.

**Lesson (cross-experiment)**: when extending an event-drift family to a new
asset class, the *flow mechanism* must port, not just the *event-shaped
calendar*. If the event is fundamentals-direct on the asset (NG storage
on gas), the equity-style risk-premium-accumulation story does not apply,
and the prior should be neutral or slightly SHORT (hedger-pre-positioning,
asymmetric-tail-hedging), not LONG.

### What this rules out

- Pre-EIA-NG on XNGUSD LONG: REJECT.
- Pre-EIA-NG on XNGUSD SHORT: REJECT (loses more than LONG).
- The macro-event-family extension to *commodity-on-own-event*: rejected
  as a generic mechanism; would need an asset-class-specific flow story
  (e.g. CME COT positioning data, weather-forecast-error gating) to
  re-attempt.

### What this leaves open

- Pre-EIA-Crude (Wednesday 10:30 ET DOE) on WTI (USOUSD) — same family
  but different commodity (oil, broader speculator base, deeper liquidity
  vs NG). Could test next as a sanity check on the "commodity-on-own-
  event" rejection — if WTI also REJECTs, the family-extension is dead.
  If WTI PASSes, NG-specific microstructure (illiquidity, weather-dominated
  flow) is the local explanation.
- Pre-EIA-NG with a *narrative gate* (cold-snap-forecast filter, season-
  ality bucket): potential Phase 3 work but only worth pursuing if a
  baseline edge existed, which it doesn't.

### Mechanism-aware kill-template note

The mechanism-aware kill set (PF>1.3 + Sh>+0.30 + MDD<25%) per lesson #55
correctly REJECTed this strategy without depending on the WR > 55% template
that wouldn't have applied (WR was 46.8% — well below LONG-bias threshold
but the asymmetric-payoff trio was equally binding via Sh and PF). Either
template would have killed this; no template-bias issue.
