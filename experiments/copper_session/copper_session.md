# XCUUSD (copper) intraday session structure — Phase 0/2 — **REJECT** (cost-bound)

**Status (2026-05-24 EOD):** Phase 0 + Phase 2 complete. **REJECT** at realistic
5bp RT copper-CFD cost. Mechanism direction CONFIRMED (Driver A — LONG was
correct, fade-gap vs SHORT is **+1.46 Sharpe**) and Phase 0 shows the 23 UTC
Asian-handoff bullseye exists (t=+2.14, mean +0.021%/H1 bar). But the per-trade
gross is too thin to survive copper-CFD spread: gross Sharpe +0.73 at 0bp,
+0.26 at 3bp, **-0.06 at 5bp (deploy)**, -0.53 at 8bp (stress).

| phase | test | result |
|---|---|---|
| Phase 0 | hour-of-day t-stats | t=+2.14 @ 23 UTC, t=+2.13 @ 14 UTC (NY-open) |
| Phase 2 | W4 Sharpe > +0.50 @ 5bp | **FAIL** (-0.06) |
| Phase 2 | MDD < 15% | **FAIL** (-16.09%) |
| Phase 2 | Trades ≥ 200 | PASS (450) |
| Phase 2 | Fade-gap (LONG-SHORT) > +0.60 | **PASS (+1.46)** |
| Phase 2 | Control-gap (Asia - NY) > +0.40 | **FAIL (+0.06)** |
| Phase 2 | WF deg < +0.70 | PASS (-0.52, OOS > IS) |
| Phase 2 | DOW max share < 50% | PASS (26.0%) |
| Phase 2 | Cost-stress @ 8bp > 0 | **FAIL (-0.53)** |

**Verdict reasoning:** the directional signal is real but **shallow**.
Gross Sharpe +0.73 / mean per-trade +0.022% (= +2.2bp gross over 9 hours)
cannot absorb 5bp RT realistic copper-CFD spread + commission. xau_session
worked partly because XAU spread is ~1.9bp all-in; copper is ~5bp all-in,
2.5× the friction, on a similar per-trade gross. **Same mechanism, different
microstructure, REJECT.**

**Critical secondary finding:** the **control-hold gap is essentially zero**
(Variant C -0.06 vs Control NY -0.11). Unlike XAU where Variant C's Sharpe
gap vs NY-hours was +0.96 (session-specific), copper's Variant C is no
better than running the same 9-hour hold during NY hours. This **refutes
the Asian-session-specificity premise** of Driver A — copper drifts upward
broadly during 2024-2026 (it IS the bullrun) and the Asian window has no
structural premium over other windows. Per the pre-committed driver framework,
this is a **driver-mismatch failure**: copper looks more like a continuous
bull-market drift than like a session-handoff microstructure.

**Reading against [[project_asian_session_family_divergence]] (lesson #33):**
adds copper as the 4th family-extension data point. XAU +1.23 (physical-
sovereign activation) / BTC +0.64 (24/7 crypto rotation) / WTI -0.58
(professional-electronic decay) / **COPPER ≈ 0 (continuous-drift confound)**.
Copper does not fit either side of the family — the Asian window has no
structural edge over other windows for this instrument. Industrial-flow
hypothesis is not refuted as a directional fact (LONG wins) but is refuted
as a **session-handoff microstructure** (no window-specific edge). The
"buyers exist in Asia" story is true; the "they concentrate flow into the
NY-close → London-open handoff specifically" story is not.

---

## Data caveat (load-bearing for any forward-deploy thinking)

Eightcap's server-side history for
XCUUSD starts **2024-02-06** — confirmed via `mt5.copy_rates_from()` with
deep-past anchors returning a single 2024-02-06 bar. The symbol simply did
not exist on Eightcap before then. No W1/W2/W3 regime windows are available;
all results are **W4-only (2024-02 → 2026-05)**. This is **not** a typical
4-regime stability story — verdict reads as "W4 PASS/FAIL conditional on
in-bullrun-window data only". Alternative longer-history H1+ copper feeds
were considered and rejected:

- Yahoo HG=F (COMEX copper futures) — D1 only beyond 60d; loses the
  intraday session-handoff signal entirely.
- Tiingo — IEX feed is US-equity/ETF, not futures.
- CPER / COPX — only quote during US RTH, so the 23-08 UTC Asian window
  is literally closed. Wrong venue.

XCUUSD is the only available 24/7-ish spot-copper feed with intraday
resolution. Its history cap is the binding constraint and is documented as
the experiment's primary external risk.

## Origin

Surfaced as the copper analog of the **xau_session** PASS (Variant C
23:00 → 08:00 UTC long, 9-hour hold, Sharpe +0.79 FULL / +1.23 W4). The
xau_session research established Asian-session structural drift exists in
gold via Asian OTC physical / sovereign / Indian flow, and survived a
cross-product test where EURUSD and BTCUSD also showed drift (gold-specific
amplifier on top of an FX/crypto basket-wide effect) while cash-market
equity indices (GER40 / SPX500 / JPN225) did NOT.

Copper was **not** tested in the xau_session cross-product profile.
Industrial-metals are a structurally different flow story than store-of-
value metals — driven by Chinese real-economy industrial demand, electronics
manufacturing supply chains, and physical Asia-zone metal warehousing rather
than central-bank / Indian-jewelry / Chinese-ETF rotation. The mechanism IS
plausible (LME copper warrant flows are Asian-hours-concentrated) but is a
**different driver** than the gold story.

Per [[project_asian_session_family_divergence]] (2026-05-16 memory): the
Asian-handoff family is driver-specific, not generic. XAUUSD W4 +1.23
(physical-sovereign), BTCUSD W4 +0.64 (24/7 crypto), but WTI W4 **-0.58**
(professional-electronic energy decay). Three instruments / three opposite
outcomes / same hour-of-day window. **Pre-commit the driver before reading
the result.**

## Pre-committed driver hypothesis (per lesson #33)

Per [[project_asian_session_family_divergence]] explicit rule: pre-commit
the driver type before running. Two co-equal candidates for copper:

### Driver A — "industrial-Asia-flow activation" (PASS direction)

- **Mechanism:** Chinese property/construction close + Asian electronics
  manufacturing supply-chain demand concentrates physical copper purchasing
  during Asian afternoon (06-14 UTC = Beijing 14-22). LME copper warrant
  flow from Asian zone warehouses (Shanghai, Korea) settles into LME
  morning open (08 UTC). Result: copper drifts UP from 23 UTC (NY close →
  Sydney handoff) through London open at 08 UTC as Asian physical buyers
  absorb supply.
- **Analog:** XAUUSD Variant C (gold structural drift up, +1.23 W4 Sharpe).
- **Sign:** **LONG** Variant C wins; SHORT-null loses.
- **Family:** physical-sovereign-side activation (gold-like).

### Driver B — "professional-electronic decay" (REJECT direction)

- **Mechanism:** Same as WTI — institutional electronic flow during Asian
  hours is post-NY-close mean-reversion / risk-off (algos unwinding LME
  copper positions overnight, no physical-Asia counterweight at retail-CFD
  size). Asian session = decay window for copper just like for WTI.
- **Analog:** WTI W4 -0.58 (the family REJECT case).
- **Sign:** **SHORT** Variant C wins; LONG loses.
- **Family:** professional-electronic decay (oil-like).

### Pre-commit (FINAL — written before any backtest output is read)

**Primary pre-commit: Driver A (industrial-Asia-flow → LONG).** Reason: the
physical-Asia copper flow story has more weight at retail-CFD venue than the
algo-decay story does, because XCUUSD is a smaller-notional, lower-liquidity
mirror of LME pricing and tracks the physical wholesale tape more faithfully
than a Globex-electronic instrument. WTI's decay framing is venue-specific
to a deeply algorithmic energy market with no real-economy Asian-hours
demand-side equivalent — copper has the buyers (Chinese property is the
single largest non-electronics copper demand channel).

**BUT** per [[project_fade_direction_inverts_post_2022]] (lesson #43) and
[[project_macro_event_drift_venue_specific]] (lesson #54): on any
post-2022 risk-asset MR/handoff thesis, pre-commit BOTH directions as
co-equal candidates. The null-check (SHORT direction) is run with the same
weight as the LONG direction. If SHORT wins, the verdict is REJECT-LONG /
PASS-SHORT, not "redo".

## Phase 0 — hour-of-day profile (actuals)

XCUUSD H1, 2024-02-06 → 2026-05-22 (~592 obs/hour). Only signal-bearing hours
shown; full table in demo output.

| hour UTC | n | mean% | t | annual Sh (gross) | flag |
|---|---|---|---|---|---|
| 01 | 592 | +0.0213 | +1.73 | +5.55 | sub-threshold |
| 03 | 592 | +0.0242 | +1.65 | +5.28 | sub-threshold |
| 07 | 591 | -0.0100 | -0.99 | -3.16 | mid-Asia weakness |
| **14** | **591** | **+0.0308** | **+2.13** | **+6.82** | **NY-open burst** |
| 16 | 592 | -0.0164 | -0.80 | -2.55 | NY drift down |
| 20 | 591 | -0.0105 | -0.78 | -2.48 | NY-close drift |
| **23** | **569** | **+0.0206** | **+2.14** | **+6.97** | **Asia handoff bullseye** |

Two signal-bearing hours: **23 UTC** (Asian-handoff, +0.021%) and **14 UTC**
(NY-morning burst, +0.031%). The Asian-handoff bullseye DOES exist on copper
— hour 23 UTC has t-stat almost identical to hour 14 UTC. Cluster 01-05 UTC
is positive but sub-threshold. Cluster 06-07 UTC is the expected mid-Asia
weakness window (same shape as XAU's 04-07 weakness).

So the Phase 0 microstructure looks RIGHT for the thesis — but the per-hour
gross is small (+0.021%) and amortizing across the full 23→08 window does
not produce enough per-trade margin to clear realistic cost.

## Phase 2 — Variant C kill-criteria battery (actuals)

Variant C (23:00 → 08:00 UTC, 9h hold), unconditional, n=450 trades over
2.29y (~197/yr).

**Cost sweep (LONG direction, 450 trades):**

| cost bp RT | Sharpe | CAGR | MDD | notes |
|---|---|---|---|---|
| 0.0 | +0.73 | +8.73% | -10.5% | signal-only (gross edge confirmed) |
| 3.0 | +0.26 | +2.50% | -11.6% | tight-spread brokers, marginal |
| **5.0** | **-0.06** | **-1.46%** | **-16.1%** | **deploy assumption — FAIL** |
| 8.0 | -0.53 | -7.11% | -23.1% | stress — FAIL |
| 12.0 | -1.16 | -14.2% | -31.5% | extreme |

**Direction null-check (5bp cost):**

| direction | Sharpe | CAGR | MDD | mean/trade |
|---|---|---|---|---|
| LONG (pre-commit) | -0.06 | -1.46% | -16.1% | -0.0035% |
| SHORT (null) | -1.52 | -17.95% | -39.5% | -0.0965% |
| **fade-gap** | **+1.46** | — | — | — |

Direction is unambiguously LONG (Driver A correct). SHORT is severely
negative — running the strategy upside-down loses big. **Fade-gap +1.46
clears the +0.60 bar comfortably**, the only kill criterion that strongly
passes.

**Control-hold (session-specificity check, 5bp cost, LONG direction):**

| window | Sharpe | mean% |
|---|---|---|
| Variant C (23→08 Asia handoff) | -0.06 | -0.0035 |
| Control NY (11→20) | -0.11 | -0.0084 |
| Control LDN (06→15) | -0.75 | -0.0509 |
| Control mid-Asia (02→11) | -0.50 | -0.0321 |

**Variant C - Control NY gap = +0.06 Sharpe.** This is the killer finding.
xau_session had Variant C +0.56 vs Control NY -0.40 (gap +0.96, strong
session-specific edge). Copper has effectively no gap — Variant C is no
better than NY-hours hold. The Asian window does have the LEAST-bad
performance of the 9-hour windows tested (LDN and mid-Asia are both worse),
but the magnitude differential vs NY is noise-level.

**Reading:** copper's directional edge is **continuous-drift**, not
**session-specific**. Both Asia-window and NY-window LONG holds are net-flat
at 5bp cost; the directional signal lives in the broader 2024-2026 copper
bull-trend (Codelco supply cuts, Goldman China-recovery narrative), not in
the Asian-handoff microstructure specifically.

**Walk-forward (single 1.5y IS / 0.8y OOS split, LONG, 5bp):**

| split | n | Sharpe |
|---|---|---|
| IS 2024-02 → 2025-08 | 297 | -0.28 |
| OOS 2025-08 → 2026-05 | 153 | +0.24 |
| degradation | — | **-0.52 (OOS better than IS)** |

Recent half is positive; the signal may be strengthening as the copper
bull-trend matures into 2026. But this is the **continuous-drift confound**
manifesting, not session-specificity — the same OOS lift would appear on the
NY-window control.

**DOW concentration:** Wed 26.0% / Thu 25.1% / Fri 24.7% / Tue 24.2%.
Clean — no single-day dependence. (No Sun/Mon because broker pause.)

## Mechanistic interpretation of REJECT (Phase 2 verdict)

1. **Direction was right.** Driver A (industrial-Asia LONG) is the correct
   directional pre-commit. SHORT loses by 1.46 Sharpe. The hypothesis that
   copper drifts up overnight is supported. Memory pre-commit was vindicated.

2. **Session-specificity is wrong.** The Asian-handoff microstructure
   premise — that 23-08 UTC has a structural edge over other 9-hour windows
   — is NOT supported by the data. Variant C is no better than NY-hours.
   What looked like an Asian-handoff drift in Phase 0 (hour 23 t=+2.14) is
   real at the hour level but doesn't compound into a Variant-C edge once
   amortized over the 9-hour hold and netted against cost.

3. **Per-trade gross is too thin for copper CFD spread + swap.** xau_session's
   equivalent gross was +0.036% per Variant C trade (similar magnitude),
   but XAU costs ~1.9bp all-in vs copper's ~5bp spread + ~2.3bp LONG swap
   ≈ **7-8bp all-in per trade**. Same gross, ~4× the friction. **Swap
   correction (added post-Phase-2 from Eightcap MT5 screenshot 2026-05-25):**
   XCUUSD swap_long = -14.35 pts/day, point=0.0001, spot ~6.30 → swap cost
   = 14.35 × 0.0001 / 6.30 = -2.28 bp per overnight rollover. Variant C
   23→08 UTC crosses ~1 rollover/trade (Eightcap EET server rollover
   ~22 UTC). Adds 2.3 bp on top of the 5 bp spread+commission model — the
   8 bp "cost stress" row in the demo (Sharpe **-0.53**) is therefore the
   *realistic* deploy number, not the stress. SHORT swap is +6.33 pts/day
   (+1.0 bp credit) but SHORT direction loses by -1.52 Sharpe so the
   positive carry doesn't rescue it.

4. **Continuous-drift confound dominates.** 2024-2026 was a copper bull
   trend ($3.80 → $4.80, +26%). Any LONG-bias mechanism will look good
   over this window. The control-hold check ISOLATES this confound: if
   LONG were genuinely session-specific, the Asia window would beat the
   NY window. It doesn't. The +1.46 fade-gap measures "LONG vs SHORT
   during a bull-trend", not "Asia-window edge vs NY-window".

## Family-divergence reading (updates [[project_asian_session_family_divergence]])

Asian-handoff family extension, 4th data point:

| instrument | window-Sharpe | driver | family-side |
|---|---|---|---|
| XAUUSD | +1.23 W4 | physical-sovereign | activation |
| BTCUSD | +0.64 W4 | 24/7 crypto rotation | activation |
| WTI | -0.58 W4 | professional-electronic | decay |
| **XCUUSD (copper)** | **-0.06 W4** | **continuous-drift confound** | **neither** |

Copper is a **third category** — neither activation nor decay, but a
non-microstructural directional drift. The Asian window has no premium
over NY hours. This is methodologically novel and worth a lesson update
([[research_notes]] lesson candidate): family-extension theses should
include a control-hold (parallel-window) check BEFORE adopting any
session-specific deploy framing, because some instruments show a
directional edge without any session-microstructural component.

## Why this might fail (red flags from pre-commit, post-mortem)

1. ✅ **Wrong family — Driver B wins.** Refuted. Driver A direction was correct.
   But "Driver A wins on direction" does NOT mean "Driver A wins on microstructure".
2. ✅ **W4-only confound.** Vindicated as a real risk — control-hold shows
   the entire LONG edge IS the W4 bull-trend, not an Asia-window phenomenon.
3. ✅ **Spread cost.** Vindicated — 5bp realistic cost exactly turns Sharpe
   from +0.26 (3bp) to -0.06 (5bp). The pre-commit warning called it.
4. **Sample size.** Bootstrap CI not computed but at n=450 the cost-bound
   FAIL is robust; the gross +0.73 Sharpe at 0bp has CI maybe [+0.20, +1.25]
   but that doesn't matter if cost takes it below zero.

## Forward-deploy implication

Not deployable on Eightcap copper CFD at any realistic cost assumption,
**including with longer historical data**. Two independent binding failures:

1. **Cost is broker-side, data-independent.** Longer XCUUSD history cannot
   change Eightcap's 5bp spread or -2.28bp/day LONG swap. Per-trade gross
   would need to triple (from +0.022% to ~+0.07%) for parity, which is not
   what more history gives — more years tighten the Sharpe estimate, they
   don't grow per-trade alpha.
2. **Session-specificity refuted on the data we have.** Control-hold gap
   is +0.06 Sharpe. The question "does the Asia window outperform the
   NY window on the same instrument" doesn't need more history; the
   answer is no on 2.3 years of W4 data, and longer history typically
   dilutes such a gap rather than amplifying it.

Deployable in principle on:

- **Tight-spread copper venue** (LME futures via FCM, COMEX HG via IBKR,
  prime-broker copper swap) at ≤2-3bp all-in. Pulls to Sharpe ~+0.26 to
  +0.50. Outside current retail-CFD scope.

Could be revisited in 2027 if (a) Eightcap or another retail broker
introduces tight-spread copper (unlikely — XCUUSD spread is structurally
wide because retail copper liquidity is shallow), OR (b) a magnitude /
direction filter analog to xau_session's DOWN-med filter concentrates
trades into a higher-gross subset that clears 7-8bp. NOT pursuing now —
filter discovery on 2.3y is curve-fitting, and even a 3× per-trade gross
boost only takes us to break-even after swap+spread.

## Pre-committed kill criteria (W4-only adjusted)

These bars apply to the **Phase 2 `copper_session_demo.py` simulator**.
W4-only data forces some relaxations vs xau_session's 4-regime template:

- **W4 net Sharpe > +0.50** at 5 bp RT cost (binding constraint; this is
  the only regime we have)
- **MDD < 15%**
- **Trade count ≥ 200 cumulative** (~250/yr expected from daily firing)
- **Fade-gap (LONG Sharpe − SHORT Sharpe) > +0.60** — stricter than
  xau_session's +0.40 bar because we have no pre-2024 baseline to cross-
  check direction against. If SHORT wins (gap < -0.60), the verdict pivots
  to PASS-SHORT/REJECT-LONG (Driver B was right).
- **Control-hold gap (Variant C Sharpe − NY-hours Sharpe) > +0.40** —
  session-specificity binding (per xau_session's bullrun-isolation precedent)
- **Cost stress @ 8 bp RT** (~realistic worst-case for copper CFD):
  Sharpe > 0 required
- **DOW concentration < 50%** in any single weekday
- **Walk-forward (single split, 1.5y IS / 0.8y OOS)**: degradation < 0.7
  Sharpe (looser bar than xau_session's 0.5 because the window is short
  and degradation noise is structurally larger)

**No regime-stability check** — only W4 available. This is the load-bearing
caveat for any deploy decision.

## Why this thesis might fail (red flags)

1. **Wrong family — Driver B wins.** Copper is more like WTI (algo-electronic
   decay) than like gold (physical activation). Industrial-flow story sounds
   reasonable a priori but the actual venue / participants may be the same
   short-term algos that drive WTI overnight decay. Per lesson #54 prior
   distribution: 4 of last 6 family-extension theses rejected on
   direction-flip null-check.
2. **W4-only confound.** Copper had a sharp 2024-Q2 supply-shock rally
   ($4.30 → $5.10 in 8 weeks) driven by Codelco production cuts. Any
   long-bias mechanism will look good vs the broader trend. Need the
   control-hold to disambiguate.
3. **Spread cost.** Copper CFD spread is materially wider than XAU.
   Eightcap publishes 5-pip = 0.05 cents spread on XCUUSD ≈ 0.05/6.30 ≈
   8 bps half-spread = 16 bps RT before commission. At that cost,
   per-trade gross needs to be > +0.20% just to break even, which is 2x
   the XAU per-trade gross. Likely binding.
4. **Sample size.** ~250 trades/yr × 2.3 years = ~580 trades unconditional.
   Bootstrap CIs will be wide. Sharpe SE ~1/√(n/yr) ~ 0.06 → 95% CI width
   ~ ±0.13 annualized. Manageable but not tight.

## Files

- `copper_session.md` — this doc
- `copper_session_demo.py` — Phase 2 simulator (Variant C unconditional +
  LONG/SHORT null-check + cost sweep + control-hold + DOW + walk-forward)
- Data: `ohlc_data/XCUUSD_H1.csv` (~13.5k bars 2024-02-06 → 2026-05-22),
  `ohlc_data/XCUUSD_M5.csv` (~162k bars same range, in datalake)
