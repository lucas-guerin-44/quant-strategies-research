# US Treasury Auction → US-Index Post-Auction Drift

**Status**: Phase 1+2 complete (2026-05-27).
**Verdict**: **REJECT decisive (both instruments, Phase 1 + Phase 2 fail)** — no auction-specific drift at retail M5 on either NDX100 or SPX500 (n=775 auctions, 354 placebo Wed/Thu). Phase 1 unconditional LONG-gross mean: NDX +0.70 bp / SPX +0.69 bp; **placebo (non-auction Wed/Thu, same 13:00 ET window) is LARGER on both** (+3.40 / +2.77 bp). t-stat (event vs placebo) is **negative** on both (−0.90 / −0.89) — auction days drift LESS than non-auction days, not more. |magnitude| is identical (34.2 vs 32.7 bp NDX; 23.9 vs 23.0 bp SPX) → no vol-shock either. Phase 2 (BTC z-score outcome-conditioning) is **negative-Sh on both at all thresholds** (NDX ann_Sh −0.18 to −0.21; SPX −0.46 to −0.67) — the thesis direction (strong-BTC → LONG, weak-BTC → SHORT) is wrong-signed. Cost-zero LONG-every-auction ann_Sh +0.15 NDX / +0.20 SPX, both below the +0.30 deploy bar even at zero friction. The auction → equity-duration channel is either (a) fully arbed by 13:05 ET (HFT closes the loop in seconds), or (b) too small to register at M5 against generic mid-week mid-day flow. Adds to the macro-event-family negative-result series (lesson #-12, #-13): not every scheduled macro event inherits the FOMC/CPI/NFP-style LONG drift, and Treasury auctions specifically don't.

---

## Thesis (mechanism)

US Treasury coupon auctions (2y / 3y / 5y / 7y / 10y / 30y) settle at **13:00 ET** on scheduled days. The auction result (high-yield vs WI pre-auction yield, bid-to-cover ratio, indirect/direct/dealer allocation) is publicly released ~13:01-13:02 ET as a discrete information event. The bond market re-prices in seconds; the **equity market's rate-duration channel** transmits this signal over the following 30-90 minutes:

1. **Strong auction (stop-through, BTC > avg, high indirect bid)** → demonstrates institutional demand at lower yield → yields drop → equity-duration tailwind, especially on long-duration sectors (NDX tech-heavy basket). Predicted post-auction drift: **LONG NDX/SPX, 30-90min hold**.
2. **Weak auction (stop-tail, BTC < avg, low indirect bid)** → demonstrates weak demand → yields rise → equity-duration headwind. Predicted: **SHORT NDX/SPX, 30-90min hold**.
3. **Mechanism distinction from `event_calendar` (FOMC/CPI/NFP)**: those are macro-policy events priced via expectations channels (rate path, inflation surprise). Treasury auctions are pure **supply-demand events** — same instrument the rate-curve discounts, traded directly. The rate-channel transmission to equities is more mechanical (Lou-Yan-Zhang 2013 "Anticipated and Repeated Shocks").
4. **Mechanism distinction from deployed `event_calendar`**: that strategy covers FOMC/CPI/NFP/RetailSales — auctions are NOT in that universe. So this is a clean additive candidate if it works, not a redundancy check.

**Phase 1 (calendar-only test)**: trade unconditionally on the post-auction 60-min window for every coupon auction; placebo is the same 13:05-14:00 ET window on non-auction Wednesdays/Thursdays. If auction days show systematically larger directional drift magnitude than placebo (t > 2), mechanism exists and is worth Phase 2 outcome conditioning.

**Phase 2 (outcome-conditioned)**: if Phase 1 passes, condition entry direction on the auction outcome signed-surprise: `signed_surprise = high_yield − WI_yield` (proxy from BTC tercile if WI not available). Strong-auction → LONG; weak-auction → SHORT.

## Key references

- **Lou, Yan, Zhang (2013)**, "Anticipated and Repeated Shocks in Liquid Markets", RFS — establishes that anticipated supply shocks (Treasury auctions) produce predictable price patterns in both bonds and adjacent rate-sensitive assets.
- **Fleming, Liu, Nguyen, Sarkar (2024)** — "The Term Structure of the Treasury Auction Effect" — auction-day yield-pattern dynamics around the WI window.
- **Beetsma, Giuliodori, de Jong, Widijanto (2016)** — sovereign auction announcements have cross-asset effects through the rate channel.
- `experiments/event_calendar` (deployed) — establishes that scheduled US-macro releases produce extractable NDX drift; this experiment tests whether the auction mechanism extends that pattern.
- `experiments/treasury_trend/treasury_trend.md` (validated, no broker access) — different mechanism (TSMOM on bonds themselves); this experiment trades the EQUITY reaction to bonds, on instruments we DO have broker access for.
- Lessons #56 (macro-event drift family), #75 (3× cost-headroom rule), #77 (same-bar look-ahead audit), #78 (paired cross-venue design).

## Signal math

**Phase 1 (calendar-only, simple unconditional test)**:

```
event_dates = unique coupon-auction dates 2019-2026 from TreasuryDirect API
session_tz  = US/Eastern
auction_time_et = 13:00 ET (varies by tenor 11:30-13:00 ET historically;
                              we use bar-at-or-after-13:05 ET to be safe
                              and avoid the print-bar same-bar look-ahead)

For each event_date:
  entry_bar = first M5 bar at or after 13:05 ET (post-print)
  exit_bar  = entry_bar + HOLD_BARS  (default 12 = 60min)
  entry_px  = open of entry_bar
  exit_px   = close of exit_bar

Direction (Phase 1 calendar test): both directions tested separately,
report mean signed return + t-stat vs placebo.

Placebo: same 13:05-14:05 ET window on non-auction Wed/Thu of same year.
```

**Phase 2 (outcome-conditioned, only if Phase 1 hits)**:

```
For each event_date:
  outcome_signed_surprise = high_yield − WI_pre_auction_yield
    # OR proxy via bid_to_cover_ratio z-score vs trailing 12 auctions
    # OR proxy via tail/through indicator if WI not available

  if outcome_signed_surprise < -threshold:  # stop-through, strong
    position = +1  # LONG (yields drop, equities rally)
  elif outcome_signed_surprise > +threshold:  # stop-tail, weak
    position = -1  # SHORT
  else:
    skip

  entry_px = open[bar at 13:05 ET]
  exit_px  = close[bar at 13:05 ET + HOLD_BARS*5min]
  net_ret  = position * (exit_px - entry_px) / entry_px - COST_PT / entry_px
```

**Bug-audit checklist (lesson #77)**:
- ✓ Entry bar is at or after 13:05 ET (auction prints at 13:01-13:02 ET; the bar timestamped 13:00 ET runs 13:00-13:04:59 and contains the print). Using `bar at >= 13:05 ET` for entry uses ONLY post-print data.
- ✓ Auction outcome data (high_yield, BTC) is published at auction time; using it as Phase 2 conditioning is real-time available (no look-ahead).
- ✓ Placebo dates are non-auction Wed/Thu (NOT randomized — explicitly disjoint from event_dates).
- Tripwire: |observed Sh| > 0.80 OR per-trade gross magnitude > 30bp ⇒ code audit before verdict.

## Why retail-accessible

- NDX100 / SPX500 M5 data on disk.
- Eightcap NDX100 / SPX500 CFD; spreads ~0.5-1pt RT = ~0.2-0.4bp at current levels.
- Treasury auction calendar is public (TreasuryDirect API; cached locally to `auctions.csv`).
- Calendar-event strategy maps cleanly to existing `event_calendar` MT5 EA scaffold.

## Universe

- **Research**: NDX100 + SPX500 M5, 2019-01-02 → 2026-04-17. Auction sample: ~6-8 coupon auctions/month × ~85 months ≈ ~500-700 events per instrument.
- **Live**: Eightcap MT5 NDX100 + SPX500 CFD.

## Expected performance

Per lesson #75 cost-headroom rule, magnitude must exceed cost by 3× for STRONG-tier promotion:

- Cost: NDX 0.5pt RT @ NDX level ~22000 = ~0.23bp; SPX 0.5pt RT @ SPX level ~6000 = ~0.83bp.
- 3× cost-headroom magnitude bar: NDX ≥ 0.7bp; SPX ≥ 2.5bp gross per trade.

Honest priors:

- **Most likely (40%)**: Phase 1 weak-PASS, Phase 2 MARGINAL. Calendar-window drift exists at 2-5bp on NDX (smaller on SPX due to lower duration), conditioning on outcome lifts to 5-10bp. Sharpe 0.20-0.45 after cost. Borderline deploy candidate.
- **Plausible (30%)**: Phase 1 REJECT. No directional drift on auction days vs placebo at retail M5 — auction reaction already happens at sub-second granularity in dealer flow, fully arbed before our 13:05 entry. Magnitude < cost on both venues.
- **Plausible (20%)**: Phase 1 PASS, Phase 2 STRONG. Outcome-conditioned strategy hits Sh 0.50+ on at least one instrument. Would be among the cleanest macro-event-flow additions to the book.
- **Plausible (10%)**: Phase 1 detects drift but in the OPPOSITE direction to the thesis prior (i.e., strong auctions → equity SELLS off, possibly via dealer-positioning unwind). Mechanism would need reinterpretation; could still be a deploy candidate if sign is consistent.

**Prior-magnitude tripwire (lesson #77)**: observed gross magnitude > 30bp per trade in any window = code audit. Observed full-sample Sh > +1.0 = audit.

## Fail conditions (pre-committed)

### Phase 1 (calendar-only, before outcome conditioning)

KILL if BOTH:

| Criterion | Floor | Rationale |
|---|---|---|
| Best-direction NDX gross magnitude | < 0.7bp/trade | Lesson #75: cost-headroom requires 3× of NDX 0.5pt = ~0.23bp |
| Best-direction NDX t-stat vs placebo | < +2.0 | Statistical distinguishability from non-event same-window drift |

If only ONE of the above fails, escalate to Phase 2 outcome-conditioning with the qualifying direction as primary prior.

### Phase 2 (with outcome-conditioning, both instruments)

KILL the instrument if ANY of:

| Criterion | Floor | Rationale |
|---|---|---|
| Full-sample Sharpe (post-cost) | < +0.30 | Deploy bar |
| Max DD | > 25% | Risk ceiling |
| Trade count | < 200 | Statistical power |
| WR < 40% AND PF < 1.1 | both | Profitability floor |
| Direction null-gap | < +0.30 | Lesson #54 — directional content test |
| Cost-zero gross Sharpe | ≤ 0 | Lesson #26 |

### Phase 4 (regime, per instrument)

- ≤ 1 of 3 regimes (2019-2020 pre/COVID, 2021-2022 vol, 2023-2026 holdout) positive

### Phase 6 (holdout binding, per instrument)

- 2023-2026 holdout Sharpe ≤ 0 (lesson #25)

### Cross-instrument gate (lesson #78 paired-design)

- **Both NDX + SPX same-sign, both Sh > +0.30**: paired deploy candidate.
- **Only one passes**: MARGINAL venue-specific; likely SPX-fail because SPX has lower duration than NDX (test whether NDX-only deploy survives Phase 3).
- **Both fail**: REJECT (mechanism absent OR too small for retail M5).
- **Opposite signs**: REJECT (one is curve-fit).

## Why this might fail (red flags)

1. **Auction reaction is sub-second** — the bond market and equity-rate-channel transmission both operate at HFT timescales. By the 13:05 ET entry bar (5 min post-print), the reaction may already be priced in. NDX's rate-beta is ~10-15bp per 1bp rate move; a 1bp surprise should show as ~10-15bp NDX in the first 60 seconds, leaving minimal drift for our 13:05-14:05 window.
2. **Strong/weak auction surprises are small** — most auctions stop within 0.5bp of WI. The "anticipated" part of Lou-Yan-Zhang is large; the surprise part is small. If the auction is largely anticipated (which is the whole point of WI), there's no post-event drift to capture.
3. **Cross-event confounds** — Treasury auctions cluster around mid-month (10y/30y) and end-of-month (2y/5y/7y), overlapping with FOMC dates, CPI release weeks, month-end rebal. The event_calendar deploy already trades 14:00 ET FOMC drifts; auction overlap is small (auctions are 13:00 ET, FOMC is 14:00 ET) but the calendar-cluster effect could confound the placebo.
4. **2y / 30y vs 10y differential reaction** — duration of the auctioned bond matters. 2y auctions affect short-rate expectations; 30y auctions affect long-end duration and risk premium; 10y is the middle. A pooled test treats them all equally — Phase 2 may need per-tenor breakdown.
5. **Family-level prior**: `event_calendar` covers 4 macro events successfully on NDX; this is the 5th candidate. But pre-PCE drift failed at the calendar level (lesson #-13); some events transmit cleanly, others don't. Auction may belong in either category.

## Phase 1 → 2 plan

- [x] Data confirmed on disk (NDX100_M5, SPX500_M5).
- [x] Treasury auction calendar fetched from TreasuryDirect API to `auctions.csv`.
- [x] Thesis doc with pre-committed fail conditions (this file).
- [ ] **Phase 1 demo** — `treasury_auction_drift_demo.py`:
  - [ ] Load auctions.csv, parse dates, filter to coupon auctions (Notes + Bonds).
  - [ ] Load NDX100 + SPX500 M5 in US/Eastern timezone.
  - [ ] Phase 1: calendar-window drift per instrument (LONG / SHORT separately) + t-stat vs placebo.
  - [ ] Per-tenor breakdown (2y / 3y / 5y / 7y / 10y / 30y).
  - [ ] Per-instrument direction null check (LONG vs SHORT magnitude).
  - [ ] If Phase 1 PASS on at least one direction, proceed to Phase 2 outcome conditioning.
- [ ] **Phase 2 (if Phase 1 hits)** — outcome-conditioned simulator with BTC z-score and stop-through/tail proxy.
- [ ] Run A-to-Z per CLAUDE.md §7 autonomy convention.
- [ ] Update verdict + mechanistic interpretation in this doc.
- [ ] Update STATE.md, STATE_GRAVEYARD.md (if REJECT), RESEARCH_NOTES.md per UPDATE PROTOCOL.

## Phase 1+2 results (2026-05-27)

### Phase 1 (calendar-only, 60-min hold, LONG-every-auction)

| Instrument | Events | Placebo | LONG gross (bp) | Placebo gross (bp) | t (ev vs pl) | t (ev vs 0) | |event| mag (bp) | |placebo| mag (bp) | Cost (bp RT) |
|---|---|---|---|---|---|---|---|---|---|
| NDX100 | 775 | 354 | **+0.70** | +3.40 | **−0.90** | +0.41 | 34.21 | 32.68 | 0.33 |
| SPX500 | 775 | 354 | **+0.69** | +2.77 | **−0.89** | +0.54 | 23.92 | 22.98 | 1.12 |

**Both Phase 1 kill criteria FAIL on both instruments**: gross magnitude < 0.7 bp/trade threshold (NDX is exactly at the boundary, SPX below); t-stat (event vs placebo) is NEGATIVE — auction days drift LESS than placebo, the opposite of "auction is informative event."

### Per-tenor breakdown (NDX gross bp, t-stat)

| Tenor | n | NDX gross | NDX t | SPX gross | SPX t |
|---|---|---|---|---|---|
| 2y | 274 | +2.47 | +0.91 | +2.56 | +1.18 |
| 3y | 111 | −0.02 | 0.00 | −1.14 | −0.34 |
| 5y | 175 | +0.69 | +0.20 | +2.13 | +0.73 |
| 7y | 106 | +4.65 | +1.06 | +3.98 | +1.31 |
| 10y | 142 | −2.15 | −0.55 | −0.60 | −0.20 |
| 20y | 50 | +6.49 | +1.01 | +3.84 | +0.80 |
| 30y | 129 | +1.01 | +0.22 | −0.73 | −0.23 |

No tenor clears |t| > 1.5; 7y and 20y are the most positive but still well below significance. 10y (the most-watched auction) is slightly NEGATIVE on NDX. No clean per-tenor sub-strategy survives.

### Regime breakdown (NDX LONG bp mean per regime)

| Window | n | NDX gross | NDX t | SPX gross | SPX t |
|---|---|---|---|---|---|
| 2019-2020 pre/COVID | 203 | +0.57 | +0.17 | +1.41 | +0.48 |
| 2021-2022 vol | 218 | +1.86 | +0.47 | +2.29 | +0.86 |
| 2023-2026 holdout | 354 | +0.05 | +0.02 | −0.71 | −0.46 |

**Holdout (2023-2026) is effectively zero on both** — modern-regime deploy-relevance per lesson #25 fails.

### Hold-window sweep (NDX, LONG)

| Hold | n | Gross bp | t | net LONG bp | ann_Sh LONG |
|---|---|---|---|---|---|
| 15 min | 775 | +1.45 | +1.51 | +1.11 | +0.43 |
| 30 min | 775 | +1.77 | +1.47 | +1.43 | +0.44 |
| 60 min | 775 | +0.70 | +0.41 | +0.36 | +0.08 |
| 120 min | 775 | +1.69 | +0.76 | +1.35 | +0.23 |
| 180 min | 775 | +1.18 | +0.46 | +0.85 | +0.12 |

The 15-30 min window is the most-positive cell: ann_Sh +0.43-0.44. But t-stat +1.47-1.51 sits well below the +2.0 binding floor for distinguishability from placebo. And the placebo at 30 min (not shown, similar ~+2.7 bp) is actually LARGER than the event at 30 min — so even the "best" hold cell doesn't beat placebo.

### Phase 2 (BTC z-score outcome-conditioning)

LONG when BTC z > +z_thr (strong demand → yields drop → equity LONG), SHORT when BTC z < −z_thr:

| z_thr | NDX n | NDX ann_Sh | NDX WR / PF | SPX n | SPX ann_Sh | SPX WR / PF |
|---|---|---|---|---|---|---|
| 0.0 | 958 | **−0.18** | 47.5% / 0.95 | 958 | **−0.46** | 47.3% / 0.87 |
| 0.5 | 607 | −0.19 | 47.4% / 0.95 | 607 | −0.46 | 46.6% / 0.88 |
| 1.0 | 351 | −0.21 | 45.3% / 0.95 | 351 | **−0.67** | 46.4% / 0.83 |

Decisively negative on both instruments at every threshold. The thesis direction is wrong-signed — strong-BTC days do NOT systematically pull equities LONG; if anything, the conditioned signal is mildly anti-correlated.

### Cost sensitivity (NDX, LONG every auction, 60 min)

| Cost | net mean (bp) | ann_Sh |
|---|---|---|
| 0.00 pt | +0.70 | +0.15 |
| 0.25 pt | +0.51 | +0.11 |
| 0.50 pt | +0.32 | +0.07 |
| 1.00 pt | −0.06 | −0.01 |
| 1.50 pt | −0.44 | −0.10 |

Cost-zero ann_Sh +0.15 — below the +0.30 deploy bar even at zero friction. **Signal-absent per lesson #26's cost-zero diagnostic**, not friction-eaten.

## Mechanistic interpretation

1. **The auction reaction is fully closed by 13:05 ET.** Cash Treasury market re-prices in seconds (electronic-only since 2013, sub-second HFT in WI/on-the-run); the equity-rate-channel transmission via S&P 500 futures or NDX futures arb is similarly sub-second. By the time our 13:05 ET M5 entry bar opens, the bond-to-equity transmission has fully completed and the post-entry window is just noise. Consistent with the original mechanism (auction → equity duration response) being REAL but **operating on a timescale 100-1000× faster than M5 retail CFD**.

2. **The 7y / 20y "weak signals" are spurious.** 7y t=+1.06 NDX / +1.31 SPX and 20y t=+1.01 NDX / +0.80 SPX are the most-positive tenors, but at n=88-106 and 50 these don't survive Bonferroni adjustment for the 7-tenor sweep. They're noise.

3. **Placebo > event is the diagnostic finding.** Non-auction Wed/Thu 13:00-14:00 ET shows +3.40 bp NDX LONG drift vs +0.70 bp on auction days. This isn't a "no effect" — it's evidence that auction days actually drift LESS than typical mid-week mid-day. Most likely interpretation: auction days have slightly elevated risk-off positioning (mild rate-uncertainty haircut on equity duration premium), which exactly cancels the generic mid-week drift. Net: auction days look like flat days, not informational events.

4. **BTC z-score conditioning is wrong-signed.** Phase 2's negative Sharpe on the "strong-auction-LONG, weak-auction-SHORT" prior is the cleanest mechanistic refutation. Bid-to-cover ratio is a backward-looking demand proxy; in modern reopening-heavy auctions (large fraction of the 781 events are reopenings of existing tenors), BTC mostly reflects dealer-vs-end-user split rather than incremental yield surprise. The BTC z-score has no signed-information about post-auction equity drift.

5. **Family-level finding (extends lesson #-12, #-13)**: scheduled US-macro events that produce extractable NDX LONG drift are *information-resolution* events on the rate-path or growth-shock (FOMC, CPI, NFP, Retail Sales). Treasury auctions are **supply-clearing events**, not information events — there is no "auction surprise" of the kind FOMC has. Operational rule: events that don't carry a sharp information surprise (auction prints, OPEC scheduled meetings without policy change, scheduled-but-no-data days like 2nd-Wed-of-month-without-CPI) should be pre-tombstoned from the macro-event-drift family without Phase 2.

6. **No bug.** Tripwire (|Sh| > 0.80, magnitude > 30bp) did not fire on the trading variants. The cost-zero ann_Sh +0.15 is below trip threshold, and per-trade magnitude +0.70 bp is far below 30 bp. Code re-audited: entry strictly post-print (13:05 ET bar = first bar at or after print_minute + 5), BTC z-score uses past-only rolling window with `.shift(1)`, placebo dates explicitly disjoint from event dates. No look-ahead.

## Cross-instrument gate

- Both NDX and SPX same-sign: YES (both near-zero with placebo > event)
- Both Sh > +0.30: NO
- Same-shape failure: YES (both Phase 1 + Phase 2 fail identically)
- **Verdict gate**: REJECT decisive (same-shape failure across paired instruments — mechanism absent, not venue-specific)

## Files

- `treasury_auction_drift.md` — this thesis doc
- `treasury_auction_drift_demo.py` — Phase 1+2 simulator
- `auctions.csv` — cached TreasuryDirect calendar (fetched 2026-05-27, 781 coupon auctions 2019-01-08 → 2026-04-28)
