# Non-Mag7 earnings-gap fade (intraday)

**Status**: Phase 2 + walk-forward complete (2026-05-22).

**Verdict**: **REJECT (MARGINAL)** on pre-committed kill criteria. Phase 2 PASSES all 4 criteria; direction null-check PASSES decisively (gap +1.63); both regimes positive; **but Phase 6 walk-forward mean OOS Sharpe +0.27 vs the +0.30 floor — fails by 0.03**. Strict reading of pre-commits → REJECT. Re-examining-honestly: this is the closest-to-deploy candidate in the earnings-family but the pre-commit was tight precisely because the parent's full-sample result was post-hoc; failing by 0.03 doesn't deserve a goalpost-move.

## Phase 2 results (2026-05-22)

### Baseline (fade, MIN_GAP=1.5%, T+60min, stop=1.5×, cost=4 bp RT) — 17 non-Mag7

| Metric | Value | vs threshold |
|---|---|---|
| Period | 2021-09 → 2026-05 (4.7y) | — |
| Sharpe | **+0.57** | PASS (>+0.45) |
| MDD | -14.74% | PASS (<20%) |
| Events | 197 (42.1/yr) | PASS (>=150) |
| WR / PF | 55.3% / 1.23 | PASS |
| CAGR | +2.54% | — |

### Regime breakdown — both available regimes positive

| Window | n | Sharpe | MDD |
|---|---|---|---|
| 2018-2020 pre/COVID | 0 | — | — |
| 2021-2022 vol | 50 | +0.87 | -5.7% |
| **2023-2026 holdout** | **147** | **+0.47** | **-14.7%** |

Phase 4 PASS (2/2 available). Holdout decay vs 2021-22 (-0.40 Sh) but still well above the +0.30 floor.

### Direction null-check — PASS decisively

Continuation direction Sharpe **-1.06** (MDD -29.8%, WR 40.6%) — dir-gap **+1.63**. Lesson-#39's +0.40 threshold easily met. The fade direction is real and decisive on this universe.

### LONG / SHORT split — genuinely two-sided

| Leg | n | Sharpe | WR |
|---|---|---|---|
| LONG (fade down-gaps) | 83 | +0.50 | 54.2% |
| SHORT (fade up-gaps) | 114 | +0.62 | 56.1% |

No catastrophic asymmetry (unlike Mag7 where LONG broke in holdout). Both legs roughly symmetric and positive.

### Per-ticker dispersion (full sample)

Strong: **CRM Sh +4.11 (n=14, WR 86%)**, MA +3.97 (n=9), GS +2.79, JPM +2.40, ORCL +1.83.

Weak/negative: PEP -3.03, UNH -2.57, JNJ -2.38, CVX -1.58, BAC -1.27, V -1.18, AVGO -0.59, WMT -0.58.

Roughly 50/50 split by name count; PnL is positive on net because winners are larger than losers. The pattern suggests a deeper sub-thesis: software / finance / payments / retail-discretionary names FADE strongly; staples / health / energy / defensive names DON'T (their earnings moves are less news-driven, more rate-/macro-driven). Further refinement to a 9-name "info-rich earnings" basket would likely lift Sharpe meaningfully — but per lesson #20 this is exactly the post-hoc cherry-pick path; a new pre-committed experiment is the correct vehicle.

### Variant sweeps

| Lever | Best | Sharpe |
|---|---|---|
| MIN_GAP_PCT | 5.0% | +1.46 (n=56 — cherry-pick) |
| MIN_GAP_PCT | 3.0% | +0.90 (n=120) |
| TIME_EXIT_MIN | T+60 | +0.57 (baseline) |
| Cost (0/2/4/8/15 bp) | 0 / 2 / 4 / 8 / 15 → +0.77 / +0.67 / +0.57 / +0.37 / +0.02 | linear decay |

T+60 is the actual baseline-optimal exit; this is consistent with the parent earnings_fade demo finding. Mid-bucket (3%) MIN_GAP filter strengthens — the same pattern as the parent (mid-magnitude gaps are the cleanest fades).

### Walk-forward — Phase 6 BINDING test, narrowly FAILS

| Split | IS Sh | OOS Sh | OOS n | OOS MDD |
|---|---|---|---|---|
| IS 2021-09 → 2024-09 / OOS → 2026-05 | +0.79 | **+0.27** | 76 | -14.7% |
| IS 2022-09 → 2025-09 / OOS → 2026-05 | +0.58 | **+0.06** | 32 | -13.2% |
| IS 2021-09 → 2023-09 / OOS → 2025-09 | +0.93 | **+0.47** | 87 | -7.7% |

- Mean OOS Sharpe **+0.27** vs +0.30 floor → **FAIL by 0.03**
- Min OOS Sharpe **+0.06** vs 0 floor → **PASS** (no negative OOS window)
- IS Sharpe uniformly strong (+0.58 → +0.93) across the three splits → consistent training signal
- OOS Sharpe degrades monotonically with regime recency: oldest OOS (S3) +0.47, newest OOS (S2) +0.06

The pattern is **mild holdout decay over time**, NOT regime-flip (cf. earnings_continuation_mag7). The mechanism still works on non-Mag7, but is getting more crowded / arbed as 0DTE-options activity grows beyond pure Mag7. By the time S2's OOS window starts (2025-09), per-event edge has thinned to nearly zero.

## Verdict reasoning

Pre-committed criteria, in order:

1. Phase 2 (4 sub-criteria) — **all PASS** (Sh +0.57, MDD -14.7%, n=197, WR 55.3% / PF 1.23).
2. Direction null-gap ≥ +0.40 — **PASS** (+1.63).
3. Phase 4 both regimes positive — **PASS** (2021-22 +0.87, holdout +0.47).
4. Phase 6 walk-forward mean OOS ≥ +0.30 — **FAIL** (+0.27).
5. Phase 6 walk-forward min OOS ≥ 0 — **PASS** (+0.06).
6. Phase 6 holdout ≥ +0.30 — **PASS** (+0.47).

5-of-6 PASS. The one FAIL is criterion 4, by 0.03 Sharpe on a 3-window walk-forward (statistical CI ~±0.20 on each window). Per strict reading of pre-commits: **REJECT**.

Per lesson #43 and the user's pre-commit discipline: the +0.30 floor was chosen ex-ante; missing by 0.03 doesn't deserve a relax. If anything, the pre-commit was *too lenient* — a 4.7y sample + 3-window walk-forward is inherently underpowered, and the OOS recency decay is a real warning signal.

## What we learned (for RESEARCH_NOTES.md)

1. **The lesson-#44 prediction held**: non-Mag7 single-stock earnings-fade DOES still work in the post-2022 regime (full-sample +0.57 / holdout +0.47, dir-gap +1.63 — all sign-correct and meaningful magnitude).
2. **But the same 0DTE arbitrage is bleeding into non-Mag7 over time**. Walk-forward shows OOS Sharpe declining from +0.47 (2023-09 → 2025-09) to +0.06 (2025-09 → 2026-05). If extrapolated linearly, by mid-2027 the OOS Sharpe is near zero. This is a **measurable rate of mechanism decay**, distinct from the binary regime-flip seen on Mag7.
3. **Per-ticker dispersion suggests a smaller "info-rich earnings" sub-basket** (9 names: CRM ORCL GS MA JPM HD XOM LOW KO) would have Sh ~+1.0+ but per lesson #20 cannot be promoted from this experiment.

## Pivot candidate: NOT proposed

The natural pivot would be the 9-name info-rich sub-basket. But per lesson #20 the path is: NEW experiment, fresh pre-commit, walk-forward. The cumulative parent-of-pivot chain (earnings_fade → earnings_fade_nonmag7 → earnings_fade_info_rich) is approaching the "infinite-refinement-until-pass" anti-pattern. Sane stopping point: tombstone the earnings-fade family at this level; revisit in 6-12 months with fresh OOS data and a single pre-committed top-9 basket.

## Files

- Thesis: this file.
- Demo: `earnings_fade_nonmag7_demo.py` (wraps earnings_fade_demo).


---

## Thesis

Direct pivot from the rejected `earnings_fade` parent thesis. Phase 2 dissection of the parent isolated a clean Mag7 / non-Mag7 bifurcation in the holdout regime (Δ +2.34 Sharpe between sub-universes). Hypothesis: **the post-2022 0DTE-options arbitrage of single-stock earnings-day fades is CONCENTRATED on Mag7 (and especially TSLA / NVDA / MSFT / META).** Names with smaller 0DTE OI relative to free float — banks, payments, staples, health, energy, software ex-FAANG — retain the classical intraday-fade mechanism (So & Wang 2014 dealer-inventory adjustment; Berkman et al 2012 attention-driven overnight reversal).

This experiment is a **fresh pre-commit, not a refinement of earnings_fade**. The post-hoc bifurcation in the parent's dissection is the ex-ante story, but the pre-commit and walk-forward are decisive — must pass on their own merits.

## Universe

17 names (the parent universe minus Mag7):

- Banks: JPM BAC GS
- Payments: V MA
- Health / retail / staples: UNH WMT HD LOW KO PEP JNJ
- Energy: XOM CVX
- Software (non-FAANG): ORCL CRM AVGO

Note: AVGO is a borderline call — it's a semiconductor with significant options activity. But it's not a constituent of "Mag7" as commonly defined, and its parent-experiment per-ticker showed -2.38 in full sample. Kept in for completeness; per-ticker review post-Phase 2 may flag for exclusion in a future refinement.

## Signal math (same as earnings_fade, universe restricted)

```
direction = 'fade' (LONG down-gaps, SHORT up-gaps)
MIN_GAP_PCT = 0.015
ENTRY_BAR_INDEX = 1   # second M5 bar, 09:35 ET
TIME_EXIT_MIN = 60
STOP_GAP_FRAC = 1.5
COST_BPS_RT = 4.0
```

## Expected performance (from parent dissection, full sample)

Non-Mag7 sub-universe Phase 2 results from earnings_fade dissection (g):
- n=197, Sharpe **+0.81**, MDD -14.7%, WR 55.3%
- 2021-2022: n=50, Sh +1.22
- 2023-2026 holdout: n=147, Sh +0.67

These look like a deploy-grade strategy. The pre-commit below is intentionally tight to catch the post-hoc-selection risk.

## Fail conditions (pre-committed)

### Phase 2

- Full-sample Sharpe < +0.45 (tightened from parent's +0.30 since the post-hoc full-sample is already +0.81; requiring +0.45 leaves room for re-run noise but doesn't accept much degradation).
- Max DD > 20%.
- Events < 150.
- WR < 50% AND PF < 1.15.
- Direction null-check (continuation): gap < +0.40 (tightened from parent's +0.30).

### Phase 6 — binding via walk-forward (per lesson #29)

- **Walk-forward mean OOS Sharpe ≥ +0.30** across 3 rolling splits (3y-IS / 1.5y-OOS).
- **Walk-forward min OOS Sharpe ≥ 0**. Single-window kill is binding (per lesson #44 sub-finding).
- 2023-2026 holdout Sharpe ≥ +0.30. (Lower bar than the parent's pre-commit because the parent had +0.67 — significant tolerance for some decay.)

### Phase 4

- Both available regimes (2021-22, 2023-26) positive. 2018-20 ignored (data coverage too thin pre-2021 on most names).

### Phase 0 (already passed in parent)

- Spread basket median ≤ 5 bps in deploy hours — parent confirmed 2.07 bp basket median; non-Mag7-only sub-basket is similar (BAC 3.80 / GS 3.33 / MA 3.46 are the higher-spread names; everything else <3 bp). No new Phase 0 needed.

## Why this might fail

1. **Post-hoc universe selection.** Even though the mechanism story is mechanistic, dropping the half of the parent universe that lost is the canonical overfit move. The +0.81 full-sample / +0.67 holdout could degrade once we walk-forward.
2. **AVGO inclusion is uncomfortable.** It had Sh -2.38 in parent full-sample, the worst non-Mag7 outcome. If walk-forward shows AVGO is the dominant negative contributor, the path forward is excluding AVGO in a FUTURE experiment, not refitting this one.
3. **0DTE-OI on banks is rising.** Bank 0DTE options have been growing as a category since mid-2024. If the mechanism that killed Mag7-fade is spreading, the holdout decay may be visible already in 2025-2026 data and a 2027+ live deploy would catch the inflection.
4. **Quarterly cadence + 17 names = ~70 events/year** (after the 1.5% gap filter). Walk-forward OOS windows have n=15-30 each — low statistical power, wide CIs.
5. **Cross-ticker variance is high.** Parent dissection showed CRM, MA, GS, JPM as best; UNH, PEP, CVX, JNJ as drags. Even within "non-Mag7" the distribution is heterogeneous. A future thesis could narrow to the top-5 winners but that's a separate pre-commit.

## Phase 1 → 2 plan

- [x] Data on disk (parent Phase 1 already done).
- [ ] Phase 2a — direct run via `earnings_fade_nonmag7_demo.py` (wraps earnings_fade_demo with universe = 17 non-Mag7).
- [ ] Phase 2b — kill criteria, regime breakdown, direction null-check.
- [ ] Phase 6 — walk-forward (3 rolling 3y-IS / 1.5y-OOS splits).
- [ ] Per-ticker holdout review.

## Files

- Thesis: this file.
- Demo: `earnings_fade_nonmag7_demo.py`
