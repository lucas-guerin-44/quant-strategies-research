"""Quick data-coverage check for XAUUSD_M5."""
import os, sys
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
df = pd.read_csv(os.path.join(_ROOT, "ohlc_data", "XAUUSD_M5.csv"), parse_dates=["timestamp"])
df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
print("rows:", len(df))
print("range:", df["timestamp"].min(), "->", df["timestamp"].max())
df["hour"] = df["timestamp"].dt.hour
ny = df[(df["hour"] >= 13) & (df["hour"] < 16)]
print(f"NY 13-16 UTC bars: {len(ny):,}")
ndays = ny["timestamp"].dt.date.nunique()
print(f"unique NY days: {ndays}, bars/NY-day: {len(ny)/ndays:.2f}")
yr = df["timestamp"].dt.year.value_counts().sort_index()
print("bars per year:")
print(yr.to_string())
