"""Local CSV cache helpers for the OHLC cache layer.

These were previously in ``scripts/_datalake.py``; they live here now so the data
layer is self-contained. ``scripts/_datalake.py`` re-exports them for backward
compatibility with the fetchers.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .config import LOCAL_DATA_DIR

# Repo-root ``ohlc_data`` cache directory.
DATA_DIR = LOCAL_DATA_DIR

CSV_COLUMNS = ["instrument", "timeframe", "timestamp", "open", "high", "low", "close"]


def merge_with_existing(df_new: pd.DataFrame, path: Path) -> pd.DataFrame:
    """Merge new bars into an existing CSV, deduping on timestamp (keep newest)."""
    path = Path(path)
    if not path.exists() or df_new.empty:
        return df_new

    df_old = pd.read_csv(path, parse_dates=["timestamp"])
    df_old["timestamp"] = pd.to_datetime(df_old["timestamp"], utc=True)

    combined = pd.concat([df_old, df_new], ignore_index=True)
    combined = combined.drop_duplicates(subset="timestamp", keep="last")
    combined = combined.sort_values("timestamp").reset_index(drop=True)
    return combined


def write_csv(df: pd.DataFrame, path: Path) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
