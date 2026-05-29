# EU Close-Auction Overshoot Fade — FRA40 (Euronext) + GER40 (Xetra) paired test

**Status**: Phase 2 complete (2026-05-27).
**Verdict**: **REJECT decisive (both venues fail)** — cross-venue paired gate REJECT-or-VENUE-SPECIFIC fires; both FRA40 and GER40 fail Sh > +0.30 on the FADE direction. FRA40 FADE Sh **−1.47** (dir-gap **−0.55**, MOMENTUM Sh −0.93 is less bad — sign-INVERTED, weak continuation consistent with Bogousslavsky-Muravyev "auction is informational"). GER40 FADE Sh **−0.23** (dir-gap +0.09 below floor, MOMENTUM −0.32, both directions near-zero — no auction-print directional content at retail M5). Cost-zero FADE: FRA40 −0.27 / GER40 +0.05 — both far below the +0.30 deploy bar even at zero friction. The fade-overshoot thesis is refuted: on FRA40 the print continues (small magnitude, cost-eaten); on GER40 the print has no consistent direction. Adds to the family of close-window REJECTs (preclose_drift, dax/pre_auction, eod_unwind) — four independent close-mechanism attempts now tombstoned on European indices at retail M5 CFD friction.

**Bug-audit (lesson #77)**: FRA40 |Sh|=1.47 trips the >0.80 tripwire, but the rule is for unrealistically POSITIVE results (look-ahead inflates fitted Sharpe). A strongly NEGATIVE Sharpe with sign-inverted dir-gap is the opposite shape — "fade is the wrong direction, by a lot." Code-audited: `entry_i = entry_bar (17:35)` is strictly > `print_bar (17:30)`, signal uses `close[print_bar]`, ATR proxy is past-only. No look-ahead bug. The magnitude of the negative is genuine: the auction print continues, and FADE is exactly the wrong side at this venue.

---

## Thesis (mechanism)

Both Euronext Paris (FRA40) and Xetra (GER40) end the cash session with a single-price call auction at **17:30 CET**. The 5-min call phase concentrates the daily MOC imbalance (index-fund rebalancing, ETF cash creation/redemption, end-of-day discretionary unwinds) into a single clearing price. When the auction print materially differs from the immediately-preceding continuous-session CFD price, the gap reflects a one-sided liquidity-demand shock at the auction itself, **partially independent of information arriving in the same window**. The hypothesis is that the first 15-30 min of post-close CFD trading partially reverts this overshoot:

1. **Liquidity providers who absorbed the auction imbalance unwind in the post-auction CFD.** Dealers and prop desks that took the other side of the imbalance at the print have inventory pressure; they trade out in the lower-liquidity post-close window, pushing price back toward the pre-print level.
2. **Cross-venue arbitrage absorbs the temporary dislocation.** FRA40/GER40 are CFD instruments; their underlying components also trade as ADRs on NYSE/Nasdaq (LVMH ADR, SAP ADR, Siemens ADR, etc.), and the cash-vs-futures basis-arb (FESX/FDAX) operates continuously through the European close. Either path can fade the auction overshoot.
3. **Key distinction from existing tombstones**: this thesis is **not pre-close drift** (already tested and rejected — dax/pre_auction REJECT, preclose_drift REJECT on SPX/NDX) and **not last-hour fade-the-day's-drift** (eod_unwind REJECT on SPX/NDX/GER/UK). It's specifically about the **auction-print discontinuity itself** as the signal — measured at the bar containing 17:30 CET, traded in the bars after.
4. **Pair-test rationale**: running FRA40 + GER40 simultaneously gives a cross-venue null bake-in. If the mechanism is real (auction-microstructure-overshoot), both venues should show the effect with same sign and similar magnitude. If only one works, the result is venue-specific and likely a confound rather than the hypothesized mechanism. Mirrors the orb_dax / orb_uk100 / orb_eustx50 cross-venue pattern (lesson #71 — ORB is venue-specific) but applied as a paired-experiment design at thesis time rather than post-hoc.

## Key references

- **Bogousslavsky & Muravyev (2023)**, "Who Trades at the Close? Implications for Price Discovery, Liquidity, and Costs." JF — documents NYSE MOC informational content; we test the European-auction counterpart's reversion shape.
- **Hu, Pan, Wang (2024)** — passive index flows concentrate at the close and produce mechanical price impact; impact decays over 30-60 min.
- `experiments/dax/pre_auction.md` (REJECT, sign-inverted) — establishes that the **pre-close** continuation thesis fails on Xetra; the **post-close** reversion thesis tested here is mechanistically distinct (auction-print discontinuity vs continuous pre-close drift).
- `experiments/preclose_drift/preclose_drift.md` (REJECT) — establishes NYSE-MOC pre-close drift is too thin for retail M5 CFD; the European post-auction reversion may have larger magnitude because the European cash close concentrates 100% of MOC flow into a single print (vs NYSE's gradual 15:50-16:00 flow).
- `experiments/eod_unwind/eod_unwind.md` (REJECT all 4 venues) — fade the day's drift in the last hour. Different mechanism (retail leverage unwind, T-60 to T-5), tombstoned at retail cost. This thesis is the auction-print snap, not the pre-close drift.
- Lesson #77 (same-bar look-ahead) — binding bug-audit checklist for this experiment.
- Lesson #54 (pre-commit BOTH directions) — fade + momentum null built into Phase 2 from the start.

## Signal math

```
session_close_local = 17:30 in Europe/Paris (FRA40) / Europe/Berlin (GER40)
# Both convert to 16:30 UTC in winter, 15:30 UTC in summer — use local-time
# alignment, not UTC, to handle DST cleanly.

For each session-day:
  pre_bars  = M5 bars in [17:00, 17:30) local time         # last 30 min of cash session
  print_bar = M5 bar timestamped 17:25 (closes at 17:29:59, contains last pre-auction trades)
  # Auction transition: the bar timestamped 17:30 will contain the auction print
  # plus the first 5 min of post-close CFD. We use bar[17:35] open as entry to
  # avoid same-bar look-ahead on the print (lesson #77).
  pre_avg   = mean(close) over pre_bars                     # pre-auction reference price
  print_px  = close of bar timestamped 17:30                # captures auction print
  gap       = (print_px - pre_avg) / pre_avg                # signed auction overshoot
  atr_proxy = rolling 20-day mean of |gap|                  # daily-volatility scaling

  if |gap| < ATR_THRESHOLD * atr_proxy: skip                # filter small overshoots

  position  = -sign(gap)        # FADE (primary direction; momentum is null check)
  entry_px  = open of bar timestamped 17:35 local           # first POST-print bar
  exit_px   = close of bar timestamped (17:35 + HOLD_BARS * 5) local
  net_ret   = position * (exit_px - entry_px) / entry_px - COST_PT / entry_px

Defaults:
  ATR_THRESHOLD = 0.20
  HOLD_BARS     = 4   (20 min)
  COST_PT_FRA40 = 1.5
  COST_PT_GER40 = 1.0
```

**Bug-audit checklist (lesson #77)**:
- ✓ `entry_bar = print_bar + 1` (entry strictly after signal bar)
- ✓ Signal uses `close[print_bar]`; entry uses `open[print_bar + 1]`. No same-bar overlap.
- ✓ ATR proxy uses ONLY past values (excludes current day).
- Tripwire: if observed Sh > 2 × prior-midpoint (i.e., > +0.80 in either direction), mandatory code audit before writing verdict.

## Why retail-accessible

- FRA40 M5 data on disk (`ohlc_data/FRA40_M5.csv`); GER40 M5 data on disk (`ohlc_data/GER40_M5.csv`).
- Eightcap CFD spreads: FRA40 ~1-2pt RT, GER40 ~0.8-1.5pt RT. Both within research-cost assumptions.
- Trades at 17:35 CET local on weekdays — no overnight risk, deterministic entry/exit windows, fits standard MT5 EA structure.
- EUR-denominated venues → no FX leg for a EUR account.

## Universe

- **Research**: FRA40 M5 + GER40 M5, 2019-01-02 → 2026-04-17 (~7.3 years, ~1830 trading days × 2 instruments ≈ 3600 instrument-days).
- **Live**: Eightcap MT5 FRA40 + GER40 CFD. Standard spreads.

## Expected performance

Direction is uncertain — pre-commit BOTH FADE and MOMENTUM directions per lesson #54. Honest priors:

- **Most likely (45%)**: REJECT. Auction overshoot exists but is < 1 cost-unit per trade on a 5-bar hold. Both instruments show real-but-too-small Sharpe (analogous to eod_unwind GER40 +0.14). Mechanism present, cost-eaten.
- **Plausible (25%)**: MARGINAL on one venue, REJECT on the other. Cross-venue asymmetry would indicate venue-specific microstructure (Xetra vs Euronext call-auction mechanics differ slightly), and the surviving venue would be Phase 3 candidate.
- **Plausible (20%)**: REJECT — no directional content. Auction print is fully informational (Bogousslavsky-Muravyev), continues rather than reverts. Fade-gap < +0.30. This would be the "auction is information, not liquidity shock" finding.
- **Plausible (10%)**: PASS on both venues. Sh +0.30-0.60 each. Would be the strongest paired-mechanism result in the repo to date.

Effect-size midpoint prior: |Sh| 0.20-0.40. **Tripwire**: observed |Sh| > 0.80 ⇒ code audit (lesson #77).

## Fail conditions (pre-committed)

### Phase 2 per-instrument (baseline FADE, COST = 1.5pt FRA40 / 1.0pt GER40, HOLD=20min, ATR=0.20)

KILL the instrument if ANY of:

| Criterion | Floor | Rationale |
|---|---|---|
| Full-sample Sharpe | < +0.30 | Deploy bar |
| Max DD | > 25% | Risk ceiling |
| Trade count | < 200 | Statistical power (target: ~1 trade/day × 7y ≈ 1800; filter brings to ~300-800) |
| WR < 40% AND PF < 1.1 | both | Profitability floor |
| Direction null-gap (fade − momentum) | < +0.30 | Directional content (lesson #54) |
| Cost-zero gross Sharpe | ≤ 0 | Signal-present diagnostic (lesson #26) |

### Phase 4 (regime, per instrument)

- ≤ 1 of 3 regimes (2019-2020 pre/COVID, 2021-2022 vol, 2023-2026 holdout) positive

### Phase 6 (holdout binding, per instrument)

- 2023-2026 holdout Sharpe ≤ 0 (lesson #25 — modern regime is deploy-relevant)

### Cross-venue gate (paired-experiment-specific)

- **If both venues fail individually**: REJECT decisive — no auction-overshoot mechanism.
- **If only one venue passes**: MARGINAL — venue-specific, candidate for Phase 3 isolated thesis on that venue. Likely indicates a confound (e.g., FRA40 has dividend-flow seasonality, GER40 has Bundesbank-day flow) rather than the hypothesized mechanism.
- **If both venues pass with same sign**: Phase 3 candidate as paired strategy with built-in cross-venue robustness.
- **If the venues pass with OPPOSITE signs**: REJECT — incompatible with any clean mechanistic story; one (or both) is a curve-fit.

## Why this might fail (red flags)

1. **Auction is information, not liquidity shock** — Bogousslavsky-Muravyev document that institutional MOC flow is INFORMATIVE on NYSE (auction print continues, not reverts). If the European close auction has the same property, fade is sign-inverted and signal direction is momentum. The null-check catches this — but the absolute magnitudes may be cost-bound in both directions.
2. **5-min M5 granularity is too coarse for auction microstructure**. The actual auction price formation is sub-second. By the time the M5 print-bar closes (17:34:59), the most informative reversion may already have happened. Higher-frequency data (M1) might show the effect but is outside the repo's standard frequency.
3. **US-flow contamination** — 17:30 CET = 11:30 ET (winter) or 12:30 ET (summer). US equity markets have been trading for 2-3 hours. The post-close European CFD is increasingly driven by US flow as the post-close window extends. The hypothesized mechanism is European-microstructure-specific; US flow is noise. Shorter hold windows (10-20 min) should be cleaner than longer ones (60+ min); test as a sweep.
4. **Tombstone family pressure** — pre-close drift (dax/pre_auction, preclose_drift) and EOD unwind (eod_unwind) both REJECT, including on GER40 specifically. Three independent close-window mechanisms have already failed at retail M5 CFD friction; the post-auction-overshoot variant tested here is the fourth attempt to find an extractable EOD edge on this venue. Prior on success is correspondingly low.
5. **Cross-venue confound risk** — FRA40 includes luxury/consumer/energy names with very different close-flow shapes (LVMH ADR-arb-driven, TotalEnergies oil-correlated, Sanofi pharma-defensive); GER40 is auto/industrial/financial. If the mechanism is partly index-sector-specific, the cross-venue test could give noisy/contradictory results that look like venue-specific edge rather than pattern absence.

## Phase 1 → 2 plan

- [x] Data confirmed on disk (FRA40 313K bars, GER40 ~similar).
- [x] Thesis doc with pre-committed fail conditions (this file).
- [x] **Data-audit step (Phase 0)**: verify M5 bar containing the 17:30 local-time auction print captures the print, and that the 17:35 bar is post-auction CFD only. Cross-check with one historical day per venue.
- [ ] **Phase 1 demo** — `eu_close_auction_fade_demo.py`:
  - [ ] `load_m5(symbol)` with local-time alignment (Europe/Paris for FRA40, Europe/Berlin for GER40) to handle DST
  - [ ] Baseline FADE simulator (HOLD=20min, ATR=0.20, cost=1.5pt FRA40 / 1.0pt GER40)
  - [ ] Direction null-check (MOMENTUM variant)
  - [ ] LONG-only / SHORT-only split per instrument
  - [ ] ATR threshold sweep (0.0 / 0.10 / 0.20 / 0.50)
  - [ ] HOLD window sweep (10 / 20 / 40 / 60 min)
  - [ ] Cost sensitivity (0.5 / 1.0 / 1.5 / 2.0 / 3.0 pt RT)
  - [ ] Walk-forward (3 rolling splits, baseline only)
  - [ ] Regime breakdown per instrument
  - [ ] Cross-venue agreement check (sign-match across all variants)
  - [ ] Bug-audit checklist verification before writing summary
- [ ] Run A-to-Z per CLAUDE.md §7 autonomy convention.
- [ ] Update verdict + mechanistic interpretation in this doc.
- [ ] Update STATE.md and STATE_GRAVEYARD.md per UPDATE PROTOCOL.

## Phase 2 results (2026-05-27)

### Per-instrument kill criteria

| Criterion | Floor | FRA40 (1.5pt) | GER40 (1.0pt) |
|---|---|---|---|
| Full-sample Sharpe | ≥ +0.30 | **−1.47** FAIL | **−0.23** FAIL |
| Max DD | ≤ 25% | −36.4% FAIL | −16.1% PASS |
| Trade count | ≥ 200 | 1551 PASS | 1588 PASS |
| WR ≥ 40% AND PF ≥ 1.1 | both | WR 41.2% / PF 0.68 FAIL | WR 47.8% / PF 0.93 FAIL |
| Direction null-gap (fade − momentum) | ≥ +0.30 | **−0.55** FAIL (inverted) | +0.09 FAIL |
| Cost-zero gross Sharpe | > 0 | −0.27 FAIL | +0.05 marginal |

FRA40: 5/6 kill criteria fail. GER40: 4/6 kill criteria fail. **Both venues REJECT.**

### Regime breakdown (FADE, baseline)

| Window | FRA40 Sh | FRA40 trades | GER40 Sh | GER40 trades |
|---|---|---|---|---|
| 2019-2020 pre/COVID | −0.77 | 431 | **+0.20** | 443 |
| 2021-2022 vol | −1.76 | 438 | −0.59 | 434 |
| 2023-2026 holdout | **−2.09** | 682 | −0.43 | 711 |

FRA40: 3/3 regimes negative, holdout worst (monotonic decay). GER40: 1/3 positive, holdout negative — Phase 4 KILL.

### Sensitivity sweeps (both venues)

| Sweep | FRA40 best cell / Sh | GER40 best cell / Sh |
|---|---|---|
| ATR threshold | 1.00 / −0.73 | 1.00 / −0.09 |
| HOLD | 60 min / −1.24 | 10 min / −0.12 |
| Cost (RT pt) | 0.0 / −0.27 | 0.0 / +0.05 |
| Long/short | long / −0.92 | long / −0.11 |

No variant crosses zero on FRA40. On GER40 only `cost=0.0` reaches +0.05 and `thr=1.00` (high-overshoot only) reaches −0.09 — both well below the +0.30 deploy bar even at zero cost.

### Walk-forward (3 rolling splits, FADE baseline)

| Split | FRA40 IS / OOS | GER40 IS / OOS |
|---|---|---|
| S1 (IS 2019-01 / OOS 2023-07) | −1.26 / −2.09 | −0.16 / −0.41 |
| S2 (IS 2019-07 / OOS 2024-01) | −1.39 / −1.89 | −0.18 / −0.29 |
| S3 (IS 2020-01 / OOS 2024-07) | −1.43 / −2.03 | −0.26 / −0.17 |
| **OOS mean / min** | −2.01 / −2.09 | −0.29 / −0.41 |

Floor: OOS mean > +0.30, min > 0. Both venues FAIL on every split.

### Cross-venue gate

- Both venues same-sign: YES (both FADE Sh negative)
- Both venues Sh > +0.30: NO
- **Verdict gate**: REJECT (decisive — not even venue-specific, both fail)

## Mechanistic interpretation

The two venues fail in *different ways*, which is itself the diagnostic finding:

1. **FRA40 fade is sign-inverted with magnitude** — dir-gap −0.55 means MOMENTUM beats FADE by 0.55 Sharpe units. Cost-zero FADE −0.27 → cost-zero MOMENTUM ≈ +0.27 (mirror trades). The auction print on Euronext Paris has weak **continuation**, not reversion — consistent with Bogousslavsky-Muravyev (2023) that institutional MOC flow is informative, not pure liquidity demand. The price moves *toward* the auction print and the post-auction CFD continues that drift. But the cost-zero magnitude (+0.27 MOMENTUM) sits below the +0.30 deploy bar, and 1.5pt RT cost drags the actual Sharpe to −0.93 even in the right direction. **Real-but-too-small continuation, same shape as preclose_drift/NDX (Sh +0.57 holdout, cost-eaten).**

2. **GER40 has no consistent directional content** — dir-gap +0.09, cost-zero FADE +0.05, both directions near-zero, 1/3 regimes positive on FADE but only 2019-2020. The Xetra close auction print at retail M5 granularity carries no extractable directional signal in either direction. This is *different* from FRA40's "real but too small" — GER40 is *signal-absent* per lesson #26's cost-zero diagnostic.

3. **Why the venue asymmetry?** Speculative, but two structural differences:
   - **Euronext continuous-auction call phase** allows order modification/cancellation throughout the 5-min call window (17:30-17:35); price formation is gradual, so the print embeds participants' final positioning decisions and is more informative.
   - **Xetra single-price call** with random end (17:30 +0-30 sec random) is harder to game; the print is more truly a clearing event and less prone to informational continuation. The post-print CFD has more noise than directional information.
   - Sector composition also differs (FRA40 luxury/energy with ADR-arb exposure; GER40 auto/industrial). FRA40 components have more US-listed ADR counterparts → cross-venue arb may bleed European auction information into the post-print CFD via the ADR channel.

4. **Closes the close-window family on European indices.** Four independent attempts on the close window now tombstoned at retail M5 CFD friction: preclose_drift (US), dax/pre_auction (GER40 continuation), eod_unwind (4 venues), and this experiment (FRA40+GER40 post-print fade). The structural-level conclusion is that **retail M5 + 1-1.5pt CFD cost is the binding constraint** — the close auction has microstructural events but their magnitude per-trade is sub-cost at this granularity. The mechanism would likely show up on M1 data with sub-second auction-print proxies — out of scope for this repo.

5. **No bug**. Tripwire fired on FRA40 |Sh|=1.47 but in the wrong direction for a look-ahead (look-ahead inflates *fitted* Sharpe, not strongly-negative ones). Code re-audited: entry strictly after print bar, signal uses past-only ATR, cost subtracted on exit only. The −1.47 is a genuine measurement of "fade is structurally wrong here, and after cost the wrong side bleeds heavily."

## Files

- `eu_close_auction_fade.md` — this thesis doc
- `eu_close_auction_fade_demo.py` — Phase 1-2 simulator
