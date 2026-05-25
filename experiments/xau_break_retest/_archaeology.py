#!/usr/bin/env python3
"""Discretionary trade-history archaeology for xau_break_retest.

Reads Trades Report_export_*.xlsx at repo root, dedups, filters to XAUUSD,
emits hour-of-day / direction / hold / volume / cadence / DOW distributions.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
XLSX = os.path.join(_ROOT, "Trades Report_export_1779728880181.xlsx")


def main() -> int:
    df = pd.read_excel(XLSX, header=1)
    print(f"raw rows: {len(df)}")
    df = df.drop_duplicates()
    print(f"after dedup: {len(df)}")
    df = df[df["Symbol"] == "XAUUSD"].copy()
    print(f"after XAUUSD filter: {len(df)}")

    df["Open Time"] = pd.to_datetime(df["Open Time"])
    df["Close Time"] = pd.to_datetime(df["Close Time"])
    for col in ("Volume", "Profit", "Open Price", "Close Price"):
        df[col] = pd.to_numeric(df[col], errors="coerce")

    print()
    print(f"date range: {df['Open Time'].min()} -> {df['Open Time'].max()}")
    print()
    print("Type counts:")
    print(df["Type"].value_counts().to_string())
    print()

    df["open_hour"] = df["Open Time"].dt.hour
    print("Hour-of-day (broker time, entries):")
    print(df["open_hour"].value_counts().sort_index().to_string())
    print()

    df["hold_min"] = (df["Close Time"] - df["Open Time"]).dt.total_seconds() / 60.0
    print("Hold duration (minutes):")
    print(df["hold_min"].describe(percentiles=[0.1, 0.25, 0.5, 0.75, 0.9, 0.95]).to_string())
    print()

    print("Volume (lots):")
    print(df["Volume"].describe(percentiles=[0.1, 0.25, 0.5, 0.75, 0.9, 0.95]).to_string())
    print()

    print("Profit (EUR):")
    print(df["Profit"].describe(percentiles=[0.1, 0.25, 0.5, 0.75, 0.9, 0.95]).to_string())
    print()

    df["gross_points"] = np.where(
        df["Type"] == "buy",
        df["Close Price"] - df["Open Price"],
        df["Open Price"] - df["Close Price"],
    )
    print("Gross XAU points per trade (signed by side):")
    print(df["gross_points"].describe(percentiles=[0.1, 0.25, 0.5, 0.75, 0.9, 0.95]).to_string())

    wins = (df["Profit"] > 0).sum()
    losses = (df["Profit"] <= 0).sum()
    print()
    print(f"WR = {wins}/{wins + losses} = {wins / (wins + losses) * 100:.1f}%")

    df["date"] = df["Open Time"].dt.date
    per_day = df.groupby("date").size()
    print()
    print(f"Trading days: {len(per_day)}, avg trades/day: {per_day.mean():.2f}, max/day: {per_day.max()}")
    print(f"Median trades/day: {per_day.median():.0f}")
    days = sorted(per_day.index)
    gaps = [(days[i] - days[i - 1]).days for i in range(1, len(days))]
    print("Days-between-trades distribution:")
    print(pd.Series(gaps).describe(percentiles=[0.1, 0.25, 0.5, 0.75, 0.9, 0.95]).to_string())

    print()
    print("Day-of-week distribution:")
    print(df["Open Time"].dt.day_name().value_counts().to_string())
    print()
    print("Hour bucket (broker time):")
    bins = [(0, 8, "Asia/early"), (8, 12, "London-AM"), (12, 14, "Pre-NY"),
            (14, 16, "NY-open"), (16, 18, "NY-mid"), (18, 24, "NY-late")]
    for lo, hi, name in bins:
        m = (df["open_hour"] >= lo) & (df["open_hour"] < hi)
        print(f"  {name:<14s} ({lo:02d}-{hi:02d}h): {m.sum():>4d} trades ({m.sum() / len(df) * 100:.1f}%)")

    # Long-vs-short concentration in the user's stated US-session window (14-15 broker)
    us_mask = (df["open_hour"] >= 14) & (df["open_hour"] < 16)
    us = df[us_mask]
    if len(us):
        print()
        print(f"In 14-16h broker window: n={len(us)} ({len(us)/len(df)*100:.1f}%)")
        print(us["Type"].value_counts().to_string())

    return 0


if __name__ == "__main__":
    sys.exit(main())
