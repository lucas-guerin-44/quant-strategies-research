"""``fetch_ohlc`` -- the canonical OHLC loader for the research repo.

Drop-in replacement for the engine's old ``utils.fetch_ohlc`` (same signature,
same returned columns), with the cache-precedence bug fixed:

The old loader returned the local CSV **unconditionally** whenever it was
non-empty in range. A stale 333-row ``COFFEE_D1.csv`` (a short broker feed) thus
silently shadowed years of upstream history, and the backtest ran on the stub
without warning.

Here the CSV is still a cache, but before trusting it we run a **date-span
coverage guard** against the lake catalog: if the local slice is missing history
the lake has at the head or tail of the requested window, we warn loudly and fall
through to the lake instead of silently returning a short series.

Design choices that matter:

* The guard keys on **date-span gaps, not row counts.** Some instruments are
  *doubled* in the lake (source-mixed double-writes -- e.g. COCOA), so a clean
  local CSV legitimately has ~half the lake's row count. A count-based trigger
  would wrongly pull the corrupted doubled series; a date-span gap will not fire
  on a contiguous local series.
* **Source-aware:** on fall-through we return the lake series outright rather than
  concatenating a short local CSV of a possibly different ``source`` (different
  price scale / tz-misaligned bars) into it.
* **Best-effort / numbers-preserving:** if the catalog is unreachable, we fall
  back to the old cache-first behavior (with a warning). So for instruments whose
  cache is already complete the code path and returned frame are unchanged --
  existing backtest numbers do not move.
"""

from __future__ import annotations

import warnings

import pandas as pd

from .client import get_client
from .config import LOCAL_DATA_DIR

_OHLC_COLUMNS = ["instrument", "timeframe", "timestamp", "open", "high", "low", "close"]

# Per-timeframe calendar tolerance for the coverage guard. Generous on purpose:
# we only want to fall through when the cache is *materially* short of the lake,
# not when it trails by a bar or two. (days)
_HEAD_TOL_DAYS = {"D1": 15, "W1": 60, "MN1": 90, "H4": 5, "H1": 5}
_TAIL_TOL_DAYS = {"D1": 30, "W1": 90, "MN1": 120, "H4": 10, "H1": 10}
_INTRADAY_HEAD_TOL_DAYS = 3
_INTRADAY_TAIL_TOL_DAYS = 5


def _tol_days(timeframe: str, table: dict, intraday_default: int) -> int:
    return table.get(timeframe, intraday_default)


def _cache_is_sufficient(
    df_local: pd.DataFrame,
    instrument: str,
    timeframe: str,
    start_ts: pd.Timestamp,
    end_ts: pd.Timestamp,
) -> bool:
    """Return True if the local slice can be trusted, False -> fall through to lake.

    Best-effort: any catalog problem (unreachable, uncatalogued instrument) returns
    True so we preserve the old cache-first behavior offline.
    """
    try:
        cov = get_client().coverage(instrument, timeframe)
    except Exception as exc:  # noqa: BLE001 -- best-effort guard, trust cache on any failure
        warnings.warn(
            f"datalake catalog unreachable for coverage check ({exc}); "
            f"using local cache for {instrument} {timeframe} as-is",
            stacklevel=2,
        )
        return True

    if not cov or not cov.get("min_date") or not cov.get("max_date"):
        return True  # not catalogued / no bounds -> nothing to compare against

    lake_min = pd.to_datetime(cov["min_date"], utc=True)
    lake_max = pd.to_datetime(cov["max_date"], utc=True)

    # Effective window = requested window intersected with what the lake actually has.
    eff_start = max(start_ts, lake_min)
    eff_end = min(end_ts, lake_max)
    if eff_start >= eff_end:
        return True  # lake has nothing extra in this window

    local_min = df_local["timestamp"].min()
    local_max = df_local["timestamp"].max()

    head_tol = pd.Timedelta(days=_tol_days(timeframe, _HEAD_TOL_DAYS, _INTRADAY_HEAD_TOL_DAYS))
    tail_tol = pd.Timedelta(days=_tol_days(timeframe, _TAIL_TOL_DAYS, _INTRADAY_TAIL_TOL_DAYS))

    head_gap = local_min > eff_start + head_tol
    tail_gap = local_max < eff_end - tail_tol

    if head_gap or tail_gap:
        which = []
        if head_gap:
            which.append(f"head (local starts {local_min.date()}, lake has from {eff_start.date()})")
        if tail_gap:
            which.append(f"tail (local ends {local_max.date()}, lake has to {eff_end.date()})")
        warnings.warn(
            f"local cache for {instrument} {timeframe} is materially short of the lake: "
            f"{'; '.join(which)}. Falling through to the datalake.",
            stacklevel=2,
        )
        return False
    return True


def fetch_ohlc(
    instrument: str, timeframe: str, start_date: str, end_date: str, limit: int = 0
) -> pd.DataFrame:
    """Fetch OHLC bars, using the local CSV cache with a datalake fallback.

    Parameters mirror the engine's historical signature. Returns a DataFrame with
    at least ``instrument, timeframe, timestamp, open, high, low, close`` columns
    (the local cache may carry extra ``source``/``fetched_at`` columns).
    """
    LOCAL_DATA_DIR.mkdir(parents=True, exist_ok=True)
    filepath = LOCAL_DATA_DIR / f"{instrument}_{timeframe}.csv"

    start_ts = pd.to_datetime(start_date).tz_localize("UTC")
    end_ts = pd.to_datetime(end_date).tz_localize("UTC")

    if filepath.exists():
        df = pd.read_csv(filepath, parse_dates=["timestamp"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        df = df[(df["timestamp"] >= start_ts) & (df["timestamp"] <= end_ts)]
        if not df.empty and _cache_is_sufficient(df, instrument, timeframe, start_ts, end_ts):
            return df

    # Cache miss, empty slice, or insufficient coverage -> go to the lake.
    rows = get_client().query(
        instrument, timeframe, start_date, end_date, limit=limit
    )
    if not rows:
        return pd.DataFrame(columns=_OHLC_COLUMNS)

    df_new = pd.DataFrame(rows)
    df_new["timestamp"] = pd.to_datetime(df_new["timestamp"], utc=True)
    df_new = df_new.drop_duplicates(subset="timestamp").sort_values("timestamp").reset_index(drop=True)

    # Source-aware: do NOT blend a short/stale local CSV (possibly a different
    # source / price scale) into the authoritative lake series. Overwrite the
    # cache with the lake result so the stale stub stops shadowing real history.
    # Only when this was a full (unlimited) pull -- never persist a truncated set.
    if not limit:
        from .csv_cache import write_csv

        write_csv(df_new, filepath)
    return df_new
