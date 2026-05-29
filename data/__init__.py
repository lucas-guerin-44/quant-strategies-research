"""Research-repo data layer: OHLC loading + the datalake client.

This package owns *all* data access for the research workflow. The backtesting
engine is used only for simulation logic and contains no knowledge of the lake,
CSV caches, or HTTP.

Typical use::

    from data import fetch_ohlc
    df = fetch_ohlc("XAUUSD", "D1", "2015-01-01", "2026-04-18")

For direct lake access (catalog / query / ingest)::

    from data import get_client
    cov = get_client().coverage("COFFEE", "D1")
"""

from .client import DatalakeClient, DatalakeError, get_client
from .config import (
    DATALAKE_API_KEY,
    DATALAKE_INGEST_PATH,
    DATALAKE_URL,
    LOCAL_DATA_DIR,
    LOCAL_TICK_DIR,
)
from .csv_cache import DATA_DIR, merge_with_existing, write_csv
from .loader import fetch_ohlc

__all__ = [
    "fetch_ohlc",
    "get_client",
    "DatalakeClient",
    "DatalakeError",
    "DATALAKE_URL",
    "DATALAKE_API_KEY",
    "DATALAKE_INGEST_PATH",
    "LOCAL_DATA_DIR",
    "LOCAL_TICK_DIR",
    "DATA_DIR",
    "merge_with_existing",
    "write_csv",
]
