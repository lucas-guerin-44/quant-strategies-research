# Project State — Graveyard

Rejected/tombstoned experiments. **One row per reject. Overview only — full write-up lives in the linked thesis doc.**

**Brevity rule for the `load-bearing failure mode` column**: one short sentence (≤ ~120 chars), no bold, no
multi-clause analysis. If you feel the urge to write a second sentence, it belongs in the thesis doc, not here.
Active state → [STATE.md](STATE.md). Lessons → [RESEARCH_NOTES.md](RESEARCH_NOTES.md).

---

## Intraday CFD (47)

| name | verdict | killed | Sh full / holdout | dir-gap | load-bearing failure mode | date |
|---|---|---|---|---|---|---|
| [jpn225_orb](../experiments/jpn225_orb/jpn225_orb.md) | REJECT | Phase 0b C1 gate | CONT +0.52 zc / W3 +0.68 | +1.04 | Real opening-momentum but C1 delta +0.28<+0.40 — all-session not TSE-open-specific; ORB 0-for-7 outside DAX. | 2026-05-28 |
| [jpn225_lunch_fade](../experiments/jpn225_lunch_fade/jpn225_lunch_fade.md) | REJECT | Phase 0/1 (C1 gate) | -0.03 / W3 +0.05 | +0.00 | C1 delta +0.27<+0.40 & dir-gap 0; formal cash halt ≠ continuous-lull, removes basis-arb leg (refines #8/#27). | 2026-05-28 |
| [orb_asx200](../experiments/orb_asx200/orb_asx200.md) | REJECT | Phase 0/1 | +0.04 / **W3 -0.62** | n/a | One-window-wonder (W1 +1.37 only); ASX commodity/financials-heavy like FTSE — ORB still DAX-only (6th non-DAX ORB reject). | 2026-05-28 |
| [letf_eod_rebalance](../experiments/letf_eod_rebalance/letf_eod_rebalance.md) | REJECT | Phase 0 screen | ~0 net / **W3 neg** | +1.0 to +1.3 (shallow) | LETF-rebalance continuation real but sub-cost; W3 holdout inverts; deep-down days fade (0DTE dip-buy). | 2026-05-28 |
| [vix_soq_short](../experiments/vix_soq_short/vix_soq_short.md) | REJECT (9/12, deploy-binding fails) | Phase 2 | +0.51 / **W3 -0.06** | +1.33 | One-window-wonder — edge entirely pre-2023 (W1 +5.2/W2 +13.6/W3 -0.4); Griffin-Shams VIX-settlement effect arbed post-publication. | 2026-05-28 |
| [nr7_breakout_ger40](../experiments/nr7_breakout_ger40/nr7_breakout_ger40.md) | REJECT | Phase 0/1 | +0.04 (pre-fix +2.69) | +0.32 | Phantom gap-through fill alpha; gap-aware fill collapses edge; cost-zero +0.16 signal-absent. Lesson #81 class, 3rd catch. | 2026-05-28 |
| [megacap_earnings_index_drift](../experiments/megacap_earnings_index_drift/megacap_earnings_index_drift.md) | REJECT | Phase 0/1 | reaction-day SHORT +0.77 | n/a | No sub-test deploy-grade; reaction-day SHORT murky mechanism + earnings-family-adjacent; post-cluster Sh 0.15-0.42. | 2026-05-28 |
| [xau_imbalance](../experiments/xau_imbalance/xau_imbalance.md) | REJECT (post-tz-fix + geometry-bug fix) | Phase 2 re-eval | +0.56 / W3 ~+1.0 | +5.30 | Most of apparent Sh was phantom "stop fill at stop_level" when retest overshoot put entry past stop; live MT5 rejects invalid stops. Lesson #81. | 2026-05-28 |
| [xau_imbalance_m15](../experiments/xau_imbalance_m15/xau_imbalance_m15.md) | REJECT (post-tz-fix + geometry-bug fix) | Phase 2 re-eval | +0.66 / W3 ~+1.0 | +3.45 | Same geometry-bug class as M5 sibling; survives bar but adds net-vol drag at portfolio level. Lesson #81. | 2026-05-28 |
| [xau_break_retest_h1](../experiments/_live/xau_break_retest_h1/xau_break_retest_h1.md) | REJECT (post-geometry-bug fix) | Phase 2 re-eval | -0.74 / W3 ~0 | n/a | 24.6% of trades violated entry-stop geometry on violent retest closes; pre-fix Sh +1.46 was 100%+ phantom alpha. Lesson #81. | 2026-05-28 |
| orb_spx500 | REJECT | Phase 2 | -0.92 | ~0 | Multi-venue diffuse open dilutes opening-impulse | 2026-04-19 |
| orb_ndx100 | REJECT | Phase 4 | 0.03 / 0.19 | small | Every refinement that helped GER40 hurt NDX | 2026-04-19 |
| orb_uk100 | REJECT | Phase 2 | -0.54 | n/a | FTSE commodities-heavy + ADR-priced overnight → no opening-impulse | 2026-04-19 |
| orb_eustx50 | REJECT | Phase 2 | -1.54 | n/a | Multi-venue basket; FESX futures lead cash open by 60min | 2026-04-19 |
| [ndx_mean_reversion](../experiments/ndx_mean_reversion/ndx_mean_reversion.md) | REJECT | Phase 2 | -0.68 | -0.28 | Fade-gap inverted; generic z-score MR fails on NDX M5 | 2026-04-19 |
| [bb_reversion](../experiments/bb_reversion/bb_reversion.md) | REJECT | Phase 2 | -0.34 / +0.50 NDX | +0.50 NDX | NDX fade-gap real but Sh negative even at zero cost | 2026-04-19 |
| [dax_zscore_momentum](../experiments/dax_zscore_momentum/dax_zscore_momentum.md) | MARGINAL | Phase 2 | -0.12 / -0.09 | +0.82 | Mechanism real but orb_dax captures it cleaner | 2026-04-19 |
| [vix_term_structure](../experiments/vix_term_structure/vix_term_structure.md) | REJECT | Phase 4 | 0.31 / -0.45 | n/a | 0DTE compression + post-2022 vol regime change | N/A |
| [eod_unwind](../experiments/eod_unwind/eod_unwind.md) | REJECT | Phase 2 | -0.85 / -1.90 | +0.46 | Real fade-gap but absolute Sh + holdout decay both fail | 2026-04-20 |
| [dax_overnight](../experiments/dax/overnight.md) | REJECT | Phase 8 | 0.85 / **live -0.34** | n/a | CFD-vs-futures artifact — dealer prints don't survive on real FDAX | 2026-04-20 |
| [dax_pre_auction](../experiments/dax/pre_auction.md) | REJECT | Phase 2 | -0.66 | -0.33 | Sign-inverted; no Xetra public imbalance feed | 2026-04-20 |
| [dax_us_lead](../experiments/dax/us_lead.md) | REJECT | Phase 2 | -0.48 | -0.42 | Sign-inverted; DAX over-extended by SPX via futures arb by 15:45 | 2026-04-20 |
| [dax_gap_fade](../experiments/dax/gap_fade.md) | REJECT | Phase 2 | -1.04 | -1.16 | Sign-inverted; DAX gaps CONTINUE (Xetra under-prices info) | 2026-04-20 |
| [preclose_drift](../experiments/preclose_drift/preclose_drift.md) | REJECT | Phase 2 | -0.41 / 0.57 NDX | +0.74 NDX | No threshold cell hits Sh>0.30 AND trades≥200 at M5 friction | 2026-05-12 |
| [vwap_fade](../experiments/vwap_fade/vwap_fade.md) | REJECT | Phase 2 | -0.77 / -1.41 | -0.15 | 0DTE trend amplification killed late-session MR | 2026-05-13 |
| [gap_continuation](../experiments/gap_continuation/gap_continuation.md) | REJECT | Phase 2 | -0.88 | -0.48 / -0.92 | Sign-inverted both — US-index gaps DON'T continue (unlike DAX) | 2026-05-13 |
| [wti_session](../experiments/wti_session/wti_session.md) | REJECT | Phase 1+6 | 0.32 / **W4 -0.58** | +1.53 | W4 decay — Asian-session mechanism reversed 2024+ | 2026-05-16 |
| [orb_compression](../experiments/orb_compression/orb_compression.md) | REJECT | Phase 2 | n=3 / +0.07 | +0.62 (noise) | Setup empirically empty (~0.16% of days); Xetra auction too reliable | 2026-05-21 |
| [orb_directional_bias](../experiments/orb_directional_bias/orb_directional_bias.md) | REJECT | Phase 2 | +1.07 / HO +0.78 vs parent +0.93 | +0.29 to +1.13 | No prior-day signal predicts GER40 first-break direction | 2026-05-21 |
| [orb_dax_sentiment](../experiments/orb_dax_sentiment/orb_dax_sentiment.md) | REJECT | Phase 2 | +0.46 / +0.46 | -0.10 inv | Composite carries signal in MIRROR direction; null-gap fails | 2026-05-21 |
| [orb_dax_voltarget_events](../experiments/orb_dax_voltarget_events/orb_dax_voltarget_events.md) | REJECT | Phase 2 | +0.46 / +0.55 (Δ +0.09) | VT +0.20 / EB +0.37 | VT is variance reshuffle, not edge extraction; 4/8 years HURT | 2026-05-22 |
| [fdax_lunch_fade](../experiments/fdax_lunch_fade/fdax_lunch_fade.md) | REJECT | Phase 2 | -0.10 / HO -0.14 | -0.08 | NDX lunch_fade is NDX/NQ basis-arb-specific; no Berlin-lunch analog | 2026-05-22 |
| [opex_pin_fade](../experiments/opex_pin_fade/opex_pin_fade.md) | REJECT | Phase 2 | NDX -0.25 / SPX -0.68 | -0.48 / -1.33 inv | Sign-inverted both — 0DTE makes dealer-gamma structurally short | 2026-05-22 |
| [cross_asset_lead_lag](../experiments/cross_asset_lead_lag/cross_asset_lead_lag.md) | REJECT | Phase 0 | n/a | n/a | No pair clears \|corr\|>0.10 over 1,400 cells — HFT closes lead-lag | 2026-05-22 |
| [pre_pce_drift](../experiments/pre_pce_drift/pre_pce_drift.md) | REJECT | Phase 2 | +0.07 / **W4 -1.23** | +0.16 | PCE = confirming-read, does NOT inherit CPI's first-read drift | 2026-05-24 |
| [copper_session](../experiments/copper_session/copper_session.md) | REJECT | Phase 2 | -0.06 @ 5bp / -0.53 @ 8bp | +1.46 | Cost-bound on Eightcap; Asia-vs-NY control gap only +0.06 (no session edge) | 2026-05-25 |
| [fx_lunch_fade](../experiments/fx_lunch_fade/fx_lunch_fade.md) | REJECT | Phase 2 | EUR -0.20 / GBP +0.04 / JPY -0.54 | EUR -0.26 / GBP +0.23 / JPY -0.99 inv | Spot-FX has no basis-arb analog; 0 validated lunch_fade siblings | 2026-05-25 |
| [xau_ldn_orb_m1](../experiments/xau_ldn_orb_m1/xau_ldn_orb_m1.md) | REJECT | Phase 2 | -0.17 / W3 -0.24 | +0.24 | Off-session control kills it (LDN delta -0.06); orb_dax needs single-venue cash auction | 2026-05-26 |
| [xau_ldn_am_fade](../experiments/xau_ldn_am_fade/xau_ldn_am_fade.md) | REJECT | Phase 2 | -0.25 / W2 -0.63 | +0.44 | LDN-AM is directional-drift window; fades get run over by LBMA flow | 2026-05-26 |
| [xau_fix_drift](../experiments/xau_fix_drift/xau_fix_drift.md) | REJECT | Phase 2 | -1.91 / W3 -1.10 | +0.08 | Post-2015 LBMA electronic-auction reform fully arbed pre-fix drift | 2026-05-26 |
| [xau_asia_range](../experiments/xau_asia_range/xau_asia_range.md) | REJECT | Phase 1 | +0.50 / **W4 +1.24** | +2.29 | Bullrun-isolation: LDN-range W4 ≈ Asia W4; generic breakout-in-trend, not microstructure | 2026-05-27 |
| [xau_dxy_stall](../experiments/xau_dxy_stall/xau_dxy_stall.md) | REJECT | Phase 0 | n/a (no Phase 1 built) | combined ≈ 0 | Real-vs-baseline delta ≈ 0; HWM/LWM both drift up = W4 bullrun rider; mechanism-strongest cells (prior DXY > ±0.10%) sign-INVERT; data 2022-11+ only | 2026-05-27 |
| pre_xau_macro_drift | REJECT (whole book) | Phase 2 | FOMC +0.31 / CPI +0.54 / RS +0.28 / NFP +0.36 | all FAIL (+0.18 to +0.26) | XAU drifts symmetrically; placebo ≥ event drift (gold bull regime confound) | 2026-05-25 |
| [usdjpy_tokyo_fix](../experiments/usdjpy_tokyo_fix/usdjpy_tokyo_fix.md) | REJECT | Phase 0b | DOW-mapped gross -1.337 bps | n/a | Pre-committed Mon/Tue SHORT direction inverted (all weekdays t=+8.03 LONG) | 2026-05-26 |
| [post_fomc_amateur_fade](../experiments/post_fomc_amateur_fade/post_fomc_amateur_fade.md) | REJECT | Phase 0 | +3.84 bps gross / W3 -0.36 | n/a | Gross < +5 bps floor; 0DTE/HFT closes the T+15-T+60 imbalance | 2026-05-26 |
| [month_end_usd_short](../experiments/month_end_usd_short/month_end_usd_short.md) | REJECT | Phase 2 (7/13) | basket +0.85 bp / W3 +0.93 bp | dir-gap +0.45 | Magnitude/cost ratio ~1.5× sub-threshold for retail FX (cost-blocked, not signal-absent); VALIDATED_BLOCKED_AT_COST. Lesson #75. | 2026-05-27 |
| [last_hour_month_end_ndx](../experiments/last_hour_month_end_ndx/last_hour_month_end_ndx.md) | REJECT | Phase 2 (7/13) | best-dir SHORT +3.57 bp / W3 +3.52 bp | dir-gap +0.18 | **W2 2021-2022 sign-flip** (SHORT −5.17 / LONG +4.67) — regime-conditional direction inversion via QE-on/off. Lesson #74. | 2026-05-27 |
| [xau_session_v2_ffr_gated](../experiments/xau_session_v2_ffr_gated/xau_session_v2_ffr_gated.md) | REJECT | Phase 2 (9-10/11) | v2a +1.11 / v2b +1.08 (parent +0.79) | n/a | Fail crit #1 (Sh ≥ +1.20) by 0.10; +1.20 bar over-calibrated to active-aware diagnostic. Lesson #76. | 2026-05-27 |
| [last_hour_month_end_ndx_v2_vix_gated](../experiments/last_hour_month_end_ndx_v2_vix_gated/last_hour_month_end_ndx_v2_vix_gated.md) | REJECT | Phase 2 (8/10) | CALM-gated SHORT +0.64 (parent +0.29) | dir-gap +0.84 | Fail crit #10 (deflated Sh +0.04 vs +0.20) at n=17. Lesson #76. | 2026-05-27 |
| [fra40_mid_morning_momentum](../experiments/fra40_mid_morning_momentum/fra40_mid_morning_momentum.md) | REJECT | Phase 2 (3 KILL) | -0.17 / HO +0.33 | +0.79 | Initial PASS Sh +2.05 was a same-bar look-ahead (entry open[N] vs signal close[N]); post-fix fails Sh/MDD/PF. Lesson #77. | 2026-05-27 |
| [eu_close_auction_fade](../experiments/eu_close_auction_fade/eu_close_auction_fade.md) | REJECT (paired) | Phase 2 (both venues) | FRA40 -1.47 / HO -2.09; GER40 -0.23 / HO -0.43 | FRA40 -0.55 inv; GER40 +0.09 | Auction print continues on FRA40 (Bogousslavsky-Muravyev), no signal on GER40; both cost-eaten at retail M5. Lesson #78. | 2026-05-27 |

## Single-stock equity (8)

| name | verdict | killed | Sh full / holdout | dir-gap | load-bearing failure mode | date |
|---|---|---|---|---|---|---|
| [opex_pin_singlestock](../experiments/opex_pin_singlestock/opex_pin_singlestock.md) | REJECT | Phase 2 | -1.24 / HO -1.27 | -0.66 inv | 0DTE short-gamma has metastasized to non-Mag7 single-stock universe | 2026-05-24 |
| [earnings_fade](../experiments/earnings_fade/earnings_fade.md) | REJECT | Phase 6 | +0.37 / **HO -0.22** | +1.35 | Mag7 HO -1.67 (0DTE gap-runs); non-Mag7 still works → pivot candidate | 2026-05-22 |
| [earnings_continuation_mag7](../experiments/earnings_continuation_mag7/earnings_continuation_mag7.md) | REJECT | Phase 2+WF | -0.18 / HO +0.78 | -0.02 / HO +2.45 | Mechanism flipped sign at 0DTE-OI ramp; min WF OOS -0.09 | 2026-05-22 |
| [earnings_fade_nonmag7](../experiments/earnings_fade_nonmag7/earnings_fade_nonmag7.md) | REJECT (MARGINAL) | Phase 6 (WF) | +0.57 / HO +0.47 | +1.63 | WF mean OOS +0.27 < +0.30 floor — 0DTE arb bleeding Mag7 → non-Mag7 | 2026-05-22 |
| [single_stock_lunch_fade](../experiments/single_stock_lunch_fade/single_stock_lunch_fade.md) | REJECT | Phase 2 | -1.06 / HO -1.26 | -0.53 inv | Lunch_fade is index-basis-arb-specific; no single-name analog | 2026-05-22 |
| [overnight_premium](../experiments/overnight_premium/overnight_premium.md) | REJECT (MARGINAL) | Phase 2 (MDD) | +0.08 / vol-filter +0.44 | +0.32 | Mechanism real and sign-correct but baseline MDD -95.7% (COVID) | 2026-05-22 |
| [retail_overshoot_fade](../experiments/retail_overshoot_fade/retail_overshoot_fade.md) | REJECT | Phase 2 | -0.26 / W2 +1.30 / **W3 -1.07** | -0.10 | Existed in meme-stock era, inverted post-2024; MDD -70.9% | 2026-05-26 |
| [sector_rel_strength](../experiments/sector_rel_strength/sector_rel_strength.md) | REJECT — both directions | Phase 2 + universe-ext | mom -0.74; mirror 24n +0.43 → 100n +0.24 | 24n +1.02 inv → 100n +0.70 | Mirror passed 24n / failed 100n — small-sample overfit | 2026-05-22 |

## Daily-frequency multi-asset / FX / equities (22)

(`pre_ecb_drift` and `pre_ecb_drift_eurusd` are intraday CFD by trade structure but classified here for thematic
grouping with macro-event family.)

| name | verdict | killed | Sh full / holdout | dir-gap | load-bearing failure mode | date |
|---|---|---|---|---|---|---|
| [fed_cycle_even_week](../experiments/fed_cycle_even_week/fed_cycle_even_week.md) | REJECT | Phase 0/1 | strat +0.21 vs B&H +0.90 | even−odd −8.0bp | Cieslak 2019 even-week anomaly INVERTED post-publication; premium now in odd weeks; fails B&H gate (#73). | 2026-05-28 |
| [fx_carry](../experiments/fx_carry/fx_carry.md) | REJECT | Phase 2 | -0.38 | n/a | 2015-2026 carry graveyard — rate convergence + Fed hikes vs EM | N/A |
| [fx_carry_trend](../experiments/fx_carry_trend/fx_carry_trend.md) | REJECT | Phase 2 | -0.38 | n/a | 3M momentum filter fired sparingly; bad-carry pairs still lost | N/A |
| [fx_mean_reversion](../experiments/fx_mean_reversion/fx_mean_reversion.md) | REJECT | Phase 2 | -0.17 | n/a | All 12 configs negative; 58.5% WR but avg-loss > avg-win | N/A |
| [tsmom_filtered](../experiments/tsmom/tsmom_filtered.md) | REJECT | Phase 2 | -0.02 | n/a | EMA(200) filter whipsaws on FX crosses; worse than baseline | N/A |
| [equity_pairs](../experiments/equity_pairs/equity_pairs.md) | REJECT | Phase 2 | -0.99 | n/a | Gatev/Goetzmann/Rouwenhorst half-life ran out post-2002 | N/A |
| [blended_portfolio](../experiments/blended_portfolio/blended_portfolio.md) | REJECT | Phase 7 | 0.64 | n/a | tsmom + xs_momentum corr +0.69 — blending interpolates same bet | N/A |
| [dual_momentum](../experiments/_archived/dual_momentum.md) | REJECT | Phase 2 | 0.39 (IS -0.13) | n/a | Positive only from 2023+ bull; cash filter actively hurts | N/A |
| lumber_oats_tsmom | REJECT | Phase 2 | 0.18 | -0.35 (fade wins) | Sign error — physical-supply commodities mean-revert, not trend | 2026-04-21 |
| [btc_volbreak](../experiments/btc_volbreak/btc_volbreak.md) | REJECT | Phase 2+4+6 | 0.40 / **W4 0.18** | +1.17 | One-window wonder — W2 2020-21 carries everything; MDD -52% | 2026-05-13 |
| [btc_weekend](../experiments/btc_weekend/btc_weekend.md) | REJECT | Phase 2+4 | 0.61 / W4 +1.81 inv | +1.86 | Activates post-2022 but MDD -40% accumulated in W1-W2 dormancy | 2026-05-13 |
| [short_tsmom](../experiments/short_tsmom/short_tsmom.md) | REJECT | Phase 2 | -0.25 | -0.89 | Null inverted — QE-era drawdowns are buy-the-dip EV, not trend | 2026-05-18 |
| [fx_safe_haven](../experiments/fx_safe_haven/fx_safe_haven.md) | REJECT | Phase 2 | -0.32 / 2020 +1.39 / 2022 -0.91 | -0.55 | JPY-haven property NOT structural; breaks on Fed-BoJ rate divergence | 2026-05-18 |
| [usd_safe_haven](../experiments/usd_safe_haven/usd_safe_haven.md) | REJECT | Phase 2+WF | -0.08 / 2022 +0.63 IS | -0.13 | Every hedge weight degrades book Calmar in 2023-2026 holdout | 2026-05-18 |
| [eth_btc_ratio_mr](../experiments/eth_btc_ratio_mr/eth_btc_ratio_mr.md) | REJECT | Phase 2 | -0.235 / H1 +1.10 / **H2 -0.98** | -0.424 inv | MR direction wrong-signed on post-Merge ratio (slow re-rating, not MR) | 2026-05-22 |
| [tsmom_hurst_gated](../experiments/tsmom_hurst_gated/tsmom_hurst_gated.md) | REJECT | Phase 2 | base W4 +1.17 / gated +1.03 | inv gate +1.11 beats proper +1.03 | Hurst-overlay redundant with 12-1 momentum (both encode persistence) | 2026-05-23 |
| [gold_trend](../experiments/gold_trend/gold_trend.md) | REJECT | Phase 2 | +0.80 / HO +1.59 | null-LO +0.54 (gap +0.21) | Loses to XAU B&H +0.85; 100% of alpha from 2023-2026 bull regime | 2026-05-27 |
| [pre_ecb_drift](../experiments/pre_ecb_drift/pre_ecb_drift.md) | REJECT | Phase 2 | -0.056% / Sh -0.11 | -0.011% | FOMC drift does NOT port to ECB; press-conference confound + banks-heavy bi-modal | 2026-05-23 |
| [pre_ppi_drift](../experiments/pre_ppi_drift/pre_ppi_drift.md) | REJECT | Phase 2 | SHORT -0.019% / Sh -0.04 | -0.061% | Second-tier release — info already priced by CPI 1 day prior | 2026-05-24 |
| [pre_natgas_eia](../experiments/pre_natgas_eia/pre_natgas_eia.md) | REJECT | Phase 2 | LONG -0.235% / W4 +0.39 | +0.130% | Equity risk-premium flow doesn't port to commodity-on-own-fundamental | 2026-05-24 |
| [pre_fomc_drift](../experiments/pre_fomc_drift/pre_fomc_drift.md) | REJECT | Phase 2 | +0.0335% / **W4 -0.07** | +0.75 Sh | FX-side DXY-mirror of NDX-LONG; magnitude-shadow, decays first | 2026-05-26 |
| [pre_ecb_drift_eurusd](../experiments/pre_ecb_drift_eurusd/pre_ecb_drift_eurusd.md) | REJECT | Phase 2 | +0.050% / **W4 -0.46** | +0.119% | DXY-mirror confirmed on FAIL-primary; pre-tombstones FX-side event extensions | 2026-05-26 |
| [cfd_wed_rollover_eurusd](../experiments/cfd_wed_rollover_eurusd/cfd_wed_rollover_eurusd.md) | REJECT | Phase 2 | SHORT -0.28 bps / **W3 -1.16** | +1.16 bps | Capacity moat ≠ edge — gross +0.58 bps vs +3-12 bps prior | 2026-05-26 |
| [crypto_funding_fade](../experiments/crypto_funding_fade/crypto_funding_fade.md) | REJECT | Phase 2 (2/8) | -0.33 / **W3 -0.79** | +1.22 | Funding-fade correctly signed but institutionalised to ~0 post-2022; cost-zero +0.35 eaten by spread. | 2026-05-28 |
| [month_end_rebal](../experiments/month_end_rebal/month_end_rebal.md) | REJECT | Phase 1 | +0.45 / W2 +0.95 / **W3 -0.01** | +1.05 | Well-known flow arbed by systematic desks; null-gap can flag real-but-arbed | 2026-05-25 |
| [treasury_auction_drift](../experiments/treasury_auction_drift/treasury_auction_drift.md) | REJECT (paired) | Phase 1 + Phase 2 | NDX +0.70 bp / HO +0.05; SPX +0.69 bp / HO -0.71 | NDX/SPX placebo > event (t -0.90 / -0.89); Phase 2 BTC z neg-Sh | Auction is supply-clearing event not information event; reaction fully arbed sub-second. Lesson #79. | 2026-05-27 |
