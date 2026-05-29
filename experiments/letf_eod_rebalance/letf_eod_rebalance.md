# Leveraged-ETF EOD rebalance SHORT — Phase 0/1 screen

**Status**: Phase 0/1 screen 2026-05-28. **REJECT at screen** (no cell clears the promote gate).
**Verdict**: **REJECT.** The LETF-rebalance continuation signal is real but sub-cost, and the W3
holdout is net-negative at every tradeable threshold — the same EOD-US-index decay that tombstoned
`eod_unwind` / `vwap_fade` / `preclose_drift` / `last_hour_month_end_ndx`. Killed in ~30 lines before
any Phase-2 build (lesson #69 cheap-falsifier discipline).

## Thesis (mechanism)

Cheng & Madhavan (2009): leveraged & inverse ETFs rebalance daily to maintain constant leverage; the
rebalance is mechanically same-direction as the day's move, executed near the close (~last 30-60 min),
and convex in the day's return. On big DOWN days the rebalance amplifies selling into the close ⇒
last-30-min **continuation** down ⇒ SHORT. Appeal for a long-heavy book: it would fire on risk-off
days specifically ⇒ hedge *convexity* rather than constant short drag.

## Screen design + pre-committed promote gate (FROZEN before run)

- Instruments: SPX500 (1.5 bp), NDX100 (0.8 bp), M5, 2019-2026.
- Per day: `early_ret` = 09:30→15:30 ET; `close_ret` = 15:30→16:00 ET (the tradeable window).
- SHORT the 15:30→16:00 window on days where `early_ret <= threshold` (continuation), sweep
  thresholds −0.30% … −1.50%. Null-check = fade (long the close). Regime split W1/W2/W3.
- **Promote to Phase 2 only if a threshold clears ALL of**: (a) SHORT close-window net mean ≥ +3 bp,
  (b) dir-gap (continuation − fade zero-cost Sh) > +0.40, (c) W3 (2023-26) holdout SHORT net mean > 0.

## Results

| Instr | thr | n | short net bp | short Sh | cont zc bp | dir-gap | W1 | W2 | W3 |
|---|---|---|---|---|---|---|---|---|---|
| SPX500 | −0.30% | 489 | −0.31 | −0.13 | +1.19 | +1.02 | +1.61 | +2.58 | **−3.35** |
| SPX500 | −0.50% | 355 | +0.11 | +0.04 | +1.61 | +1.31 | +2.55 | +1.89 | **−2.53** |
| SPX500 | −0.75% | 242 | −0.68 | −0.25 | +0.82 | +0.60 | −2.43 | +1.73 | −1.63 |
| SPX500 | −1.00% | 163 | −1.03 | −0.33 | +0.47 | +0.30 | −3.21 | −0.41 | +0.32 |
| SPX500 | −1.50% | 74 | −3.02 | −0.80 | −1.52 | **−0.80** | −8.35 | −1.82 | +1.14 |
| NDX100 | −1.50% | 144 | +0.55 | +0.17 | +1.35 | +0.83 | −0.85 | +1.41 | +0.76 |

(NDX100 shallow thresholds all W3-negative; full table in screen output.) Unconditional SHORT
close-window = −1.84 bp / Sh −1.01 (SPX) — the close window has a mild LONG drift, as expected.

## Mechanistic interpretation (why REJECT)

1. **Signal exists but is sub-cost.** Zero-cost continuation is only +1.2 to +1.6 bp at shallow
   thresholds (dir-gap +1.0 to +1.3 — real directional content per lesson #13). After 1.5 bp cost the
   net mean is ~0. Gate (a) (+3 bp) is never met — the LETF flow is too small relative to SPX/NDX
   daily $-volume to move the close more than ~1-2 bp on average.
2. **W3 holdout inverts.** At every tradeable threshold the 2023-2026 holdout SHORT net is negative
   (−2.5 to −3.4 bp on SPX). The continuation that existed in W1/W2 is gone post-2022 — same 0DTE EOD
   decay as the rest of the tombstoned EOD-US-index cluster.
3. **Deep-down days FADE, not continue.** At −1.5% the dir-gap inverts to −0.80 (W1 −8.35): on the
   biggest down days the close mean-reverts (0DTE dip-buying / dealer gamma squeeze into the bell),
   swamping the rebalance flow. This is the intraday image of lesson #34 ("QE-era drawdowns are
   buy-the-dip EV"). The convexity the thesis hoped for points the WRONG way exactly when the book
   would most want a hedge.

**Conclusion for the short-side slate**: the LETF-rebalance angle does not survive at retail CFD
friction on the index; it is sub-cost where it continues and inverts where it's largest. No Phase 2.

## Files

- [letf_eod_rebalance_screen.py](letf_eod_rebalance_screen.py) — Phase 0/1 screen (both instruments, threshold sweep, null-check, regime split)
