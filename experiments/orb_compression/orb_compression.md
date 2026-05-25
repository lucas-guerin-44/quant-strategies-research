# ORB Compression / Inside-Day Fade — GER40 (companion to `orb_dax`)

**Status**: REJECTED at Phase 2 — 2026-05-21. Thesis premise empirically refuted in one diagnostic.

**Verdict**:

| Metric | Value | Phase 2 floor | Pass? |
|---|---|---|---|
| Inside-days @ snap=180 | **3** in 7.3y | premise was ~360 | **FAIL (premise off by 100×)** |
| Sharpe (baseline-fade) | +0.07 | > +0.30 | FAIL |
| Trades | 3 | ≥ 100 | FAIL |
| MDD | -0.26% | < 25% | PASS (trivially — barely traded) |
| WR / PF | 66.7% / 1.25 | WR≥38 or PF≥1.1 | PASS (n=3, meaningless) |
| Fade-gap vs continuation null | +0.62 | ≥ +0.30 | PASS (n=3, meaningless) |

**Verdict line**: REJECT at Phase 2 due to **cadence floor failure traceable to a flawed premise**, not weak signal. The mechanism was never tested because the population it was designed for is essentially empty on GER40 M5.

**Headline finding**: The thesis assumed ~20% of GER40 days would be "inside-days" (no M5 close outside the 09:00-09:30 OR through the 12:00 entry cutoff). Empirically that fraction is **0.16% (3 days in 7.3 years)**. Xetra's morning auction is so reliably directional that — in the symmetric "no break either side" sense — compression days through lunch effectively do not exist.

This is itself a strong-form confirmation of the parent `orb_dax` thesis: the breakout-impulse mechanism doesn't just produce a positive expected payoff — it produces a directional break **on virtually every trading day**.

---

## Run log — 2026-05-21

GER40 M5, 188,895 bars, 2019-01-02 → 2026-04-17 (1,853 trading days, 7.3y).

### Inside-day population by snapshot timing

The load-bearing diagnostic. Inside-day count as a function of when we sample for "no break yet":

| Snapshot mod | Window scanned | Inside-days | Per year |
|---|---|---|---|
| 120 min (10:30) | 09:30-10:30 | 39 | 5.4 |
| 150 min (11:00) | 09:30-11:00 | 6 | 0.8 |
| **180 min (12:00, parent cutoff)** | **09:30-12:00** | **3** | **0.4** |
| 210 min (12:30) | 09:30-12:30 | 1 | 0.1 |
| 240 min (13:00) | 09:30-13:00 | 1 | 0.1 |
| 300 min (14:00) | 09:30-14:00 | 0 | 0 |

By the parent's 12:00 entry cutoff, only 3 days in 7 years had price still bracketed by the 09:00-09:30 OR in both directions. **Cadence ceiling at the parent's entry-cutoff anchor is ~0.4 trades/year** — three orders of magnitude below the 50/year design target.

### Why the premise was wrong

I anchored on the parent's LONG-only trade count (1,440 / 1,813 days ≈ 80% breakout days) and assumed the ~20% complement was inside-days. That was a conflation error: the parent strategy fires LONG when price closes above OR_high — but it's silent on days where price *broke down* (closed below OR_low) without an up-break. Those days are not inside-days; they have a clean down-break that the LONG-only EA simply doesn't trade.

The true inside-day set (no close outside the OR in *either* direction across a 2.5-hour window of M5 bars on a volatile German index CFD) is empirically near-empty. With 30 M5 bars in [09:30, 12:00), the probability of all 30 closing inside a 30-min range is structurally tiny on any half-volatile day.

### Baseline-fade result (n=3 trades)

```
Sharpe        : +0.07
trades        : 3 over 7.3y
WR / PF       : 66.7% / 1.25
fade-gap vs continuation null: +0.62
```

Numbers exist but mean nothing at n=3. The fade-gap is in the right direction but the standard error overwhelms it.

### Earlier-snapshot variants (snap=120, more data)

The only configuration that actually accumulates trades is `snap=120` (declare a day "inside" if price hasn't broken either side by 10:30):

| snap | trades | Sharpe | MDD | WR |
|---|---|---|---|---|
| 120 | 39 | **-0.66** | -2.28% | 35.9% |
| 150 | 6 | -0.03 | -0.70% | 33.3% |
| 180 | 3 | +0.07 | -0.26% | 66.7% |

At the only timing that produces enough samples to read, **the fade decisively loses** (Sharpe -0.66, WR 36%). When the parent ORB hasn't fired by 10:30, the eventual outcome is *not* range-fade; it's just noise day with no exploitable structure.

### Cost sensitivity (snap=180, n=3)

Sharpe moves +0.09 → +0.03 across 0.0pt → 3.0pt RT — flat to cost because there are 3 trades. Cost-zero Sharpe ≈ 0 says "no edge in the snap=180 set" even before friction. At snap=120 (where we have data), the diagnostic says "negative edge."

### Regime breakdown

Mostly empty. Snap=180 baseline has 0 trades in 2019-2020, 1 in 2021-2022 (Sharpe -0.70 from one loss), 2 in 2023-2026 (Sharpe +0.78 from two wins). Statistical noise.

### Null check

Continuation variant on the same 3 trades produced Sharpe -0.55 → fade-gap +0.62. At n=3 this carries no information.

---

## Mechanistic interpretation

The finding is **not** that range-fade on inside-days is a bad strategy. The finding is that on GER40, *there is no inside-day population to fade* at the parent's natural timing anchor (12:00 Berlin). Xetra's morning auction-discovery process resolves to a directional break on roughly every trading day. By 10:30 only 5/year are still bracketed; by 12:00 only 0.4/year.

This refines the parent ORB mechanism explanation:

- The parent thesis says "Xetra's morning auction concentrates overnight info into a clean breakout impulse." Implication: most days *should* break.
- This experiment empirically measures that "most" ≈ 99.6% by 12:00 and 97% by 10:30.
- The reliability of the parent's breakout mechanism is **a structural property of Xetra**, not a probabilistic statement. The parent works precisely because the complement is empty.

### Cross-experiment implication

The complement-mechanism approach (trade what the parent is silent on) only works when the parent's silent set is large enough to constitute a trading population. For ORB on GER40 — no. For ORB on instruments where the parent FAILED with low fade-gap (i.e. ORB doesn't have directional content) — no (parent failed because there's no signal at all, not because the OR boundary is broken less). The complement-mechanism approach is structurally not viable for the ORB family on any tested instrument.

The general rule: before designing a complement strategy, *count the days it would actually trade*. A 60-second diagnostic that would have killed this thesis before any code was written.

---

## What was NOT pursued (and why)

- **Touch-fade variant (Design B in the original draft)** — entering on bar-high touch of OR boundary without close. Could increase cadence but would still be working on a near-empty inside-day population. Not worth re-running.
- **Soft inside-day definition (allow one false break)** — would change the population but also changes the mechanism (now trading "ORB false-break days" — a different thesis). Worth considering as a *separate* future experiment but does not rescue this thesis as written.
- **Lower-timeframe (M1) compression** — Xetra's auction is timeframe-invariant; M1 inside-day rate would be even lower than M5. Won't help.
- **Different instrument** — universe is constrained to GER40 (only instrument where parent works). Cannot port.

---

## Files

- Thesis: this file.
- Demo: `experiments/orb_compression/orb_compression_demo.py` (full Phase 2 sweep, ~10s on M5 GER40).
- Run output: see ad-hoc command — `venv/Scripts/python.exe experiments/orb_compression/orb_compression_demo.py`.

---

## Thesis (mechanism)

The deployed `orb_dax` strategy fires LONG on ~80% of GER40 trading days (1,440 trades over ~1,813 days, 2019-2026). The remaining ~20% are days where, by the 12:00 Berlin entry cutoff, price has stayed **entirely inside** the [09:00-09:30] opening range — no M5 close above OR_high, no M5 close below OR_low. These are the days the parent strategy is silent on.

The mechanistic story for these days:

1. **Xetra's morning concentrated auction did not resolve to direction.** The mechanism that powers the parent ORB — overnight information + pre-market positioning collapsing into a clean breakout at the cash open — *failed to fire*. The auction processed the order book and produced no net new directional signal.
2. **Information-light open ⇒ range-bound day.** Days with no decisive overnight catalyst tend to range within the auction-discovered bracket. The OR becomes a self-fulfilling support/resistance because every flow-trader is using the same reference level (Xetra publishes the auction print explicitly).
3. **Touches of OR boundaries are rejections, not breakouts.** On a compression day, late-morning/afternoon touches of OR_high or OR_low without follow-through are the inverse signal: liquidity sitting at those levels, faded by mean-revert flow.

This is **not** the inverse of ORB (fading the breakout) — that hypothesis is already settled (orb.md fade-gap +0.97 to +1.04 *against* fading). It is a **disjoint-subset strategy** on the days the parent is silent.

## Key reference

- **Crabel (1990)** notes "narrow-range / inside-day" patterns as the precursor to either a late breakout *or* persistent compression. Compression follow-through is regime-dependent.
- **Lo, Mamaysky, Wang (2000)** "Foundations of Technical Analysis" — range-trade Sharpe is structurally smaller than breakout Sharpe but has near-zero correlation; complement, not replacement.
- No direct ORB-companion paper exists; this is a structural complement to the parent thesis rather than a literature replication.

## Signal math — baseline candidate (snapshot fade at 12:00)

```
Parameters:
  OR_MINUTES                = 30     (inherited from parent)
  SNAPSHOT_MIN              = 180    (12:00 Berlin — parent's entry cutoff)
  T_EXIT_MIN                = 180    (15:00 Berlin)
  EXIT_MIN_BEFORE_CLOSE     = 5      (17:25 Berlin hard flat)
  COST_POINTS_ROUND_TRIP    = 1.0
  MODE                      = "fade" (or "continuation" for null check)

Per day (Berlin RTH 09:00-17:30):

  OR_high = max(high) over [09:00, 09:30)
  OR_low  = min(low)  over [09:00, 09:30)
  OR_mid  = (OR_high + OR_low) / 2

  inside_day = TRUE iff for all M5 bars b in [09:30, 12:00):
                 OR_low <= b.close <= OR_high
  (i.e. parent ORB did not fire on either side)

  if not inside_day:  skip day  (parent strategy owns these)

  Let b* = M5 bar with mod == SNAPSHOT_MIN.
  if MODE == "fade":
    if b*.close > OR_mid: SHORT at b*+1 open, stop = OR_high break
    if b*.close < OR_mid: LONG  at b*+1 open, stop = OR_low  break
  if MODE == "continuation":
    inverse direction (null check — same setup, opposite call)

  Exit: stop hit, OR T+180 min after entry, OR 17:25 Berlin hard flat.
  Max 1 trade per inside-day.
```

The stop is the OR boundary breakout in the same direction price was leaning — i.e. the parent ORB strategy's entry trigger doubles as our "we were wrong" signal. Symmetric and theoretically coherent with the parent.

## Why retail-accessible

Same MT5 GER40 CFD as parent. No new instrument, no new data source. Disjoint trade set means the two strategies can run on the same account with no overlap risk — only one will be in a position on any given day.

## Universe

GER40 M5 only. The parent thesis was confirmed only on GER40 (5 instruments tested, 1 PASS, 4 REJECT) so the mechanistic complement is sample-of-one by construction. If GER40 compression passes Phase 2, *that* unlocks the case for testing the same complement on a hypothetical future single-venue-auction unlock (JPN225 / SWI20 / ITA40 once data-blocked).

## Expected performance (at thesis time)

- Inside-day frequency: ~20% of GER40 trading days ⇒ ~360 days over 7y ⇒ ~50/year cadence ceiling.
- Per-trade payoff: structurally smaller than parent (range-fade is a smaller bet than breakout continuation). Expect Sharpe per-trade lower; total Sharpe pulled down by lower cadence.
- **Expected retail-net after 1pt RT cost**: Sharpe 0.20-0.40, 40-50 trades/year, WR 50-60%, PF 1.2-1.4, MDD 8-15%.
- Live target after 10-25% haircut: Sharpe 0.15-0.36 (lower bar — this is a *complement*, value comes from low correlation to parent, not standalone strength). To be validated against 6-12 months of live data.

## Fail conditions (pre-committed)

Phase 2 kills if ANY:
- Full-period Sharpe < +0.30 after 1pt RT cost (same bar as parent — no special pleading).
- Max DD > 25%.
- Trade count < 100 over 7 years. _(Lower than parent's 200 floor because the strategy is a disjoint-subset of days by construction; ~50/year × 7y ≈ 350 is the ceiling.)_
- WR < 38% AND PF < 1.1.

Phase 4 kills if Sharpe positive in ≤ 1 of 3 regime windows (2019-2020 / 2021-2022 / 2023-2026).

Phase 6 kills if 2023-2026 holdout Sharpe ≤ 0.

**Null-check fade-gap**: continuation variant (same setup, opposite direction) must have Sharpe at least **+0.30 below** the fade variant. If fade and continuation are similar, the snapshot setup has no directional content (just sampling the return distribution on inside-days).

## Why this might fail (red flags)

1. **Compression days are low-vol days.** Even if direction is right, edge per trade is small. Costs may swallow it at 1pt RT.
2. **Inside-day selection bias.** By construction these are days where the impulse mechanism *failed*. There's no reason to assume the failed-impulse day has any other tradeable structural property — it might just be "noise day."
3. **Drift confound.** DAX has secular upward drift 2019-2026 (10.6k → 22k+). Long-fades from lower OR half might just be capturing drift on quiet days; if so, expect symmetric long/short to differ as in parent.
4. **Sample-of-one mechanism.** GER40 is the only instrument where the parent works. If parent succeeded for an idiosyncratic GER40 reason (Xetra microstructure), the complement might not have any mechanism to work on the silent days.
5. **Selection-bias confound with parent.** "Inside-day" is defined via the parent's entry-cutoff logic. If we change SNAPSHOT_MIN, the inside-day set changes too. Sensitivity to that knob is the load-bearing diagnostic.

## Phase 1 → 2 plan

- [ ] Build numpy inner-loop simulator matching `orb_demo.py` style.
- [ ] Baseline run: snapshot=180, T+180 exit, both directions, fade mode.
- [ ] Null check: same parameters, continuation mode. Compute fade-gap.
- [ ] Long/short asymmetry split.
- [ ] Snapshot-timing sweep: 150 / 180 / 210 / 240 (sensitivity to the load-bearing knob).
- [ ] Time-exit sweep: 60 / 120 / 180 / 240 / EOD.
- [ ] OR-width filter sweep (compression-within-compression — narrow OR ⇒ stronger fade?).
- [ ] Regime breakdown 2019-2020 / 2021-2022 / 2023-2026.
- [ ] Cost sensitivity 0.5 / 1.0 / 1.5 / 2.0 pt.
- [ ] Correlation with parent `orb_dax` daily PnL (should be near-zero by construction — disjoint trade days — but verify).

## Files

- Thesis: this file.
- Demo: `experiments/orb_compression/orb_compression_demo.py`.
- Data: `ohlc_data/GER40_M5.csv`.
- Run: `venv/Scripts/python.exe experiments/orb_compression/orb_compression_demo.py`.

## References

- Crabel, T. (1990). *Day Trading with Short Term Price Patterns and Opening Range Breakout*. Traders Press. (Inside-day / NR4 / NR7 patterns chapter.)
- Lo, Mamaysky, Wang (2000). "Foundations of Technical Analysis." *Journal of Finance* 55(4).
- Parent thesis: `experiments/orb/orb.md`.
