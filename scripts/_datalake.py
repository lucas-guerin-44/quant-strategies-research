"""Backward-compatibility shim for the data layer.

The real implementations moved into the top-level ``data`` package (the research
repo now owns all data access; see
``docs/handoffs/HANDOFF_data_layer_and_client.md``). This module re-exports the
same names so the existing fetchers (``mt5_fetch.py``, ``yahoo_fetch.py``,
``tiingo_fetch.py``, ``fred_fetch.py``) keep importing from here unchanged.

* CSV helpers (``merge_with_existing``, ``write_csv``, ``DATA_DIR``) come from
  ``data.csv_cache``.
* ``inject_to_datalake`` now goes through the robust :class:`data.DatalakeClient`
  (authed, serialized, retried) instead of a bare ``requests.post``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

# Ensure the repo root (parent of scripts/) is importable as ``data``.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from data.csv_cache import CSV_COLUMNS, DATA_DIR, merge_with_existing, write_csv  # noqa: E402,F401
from data.client import get_client  # noqa: E402


def inject_to_datalake(df: pd.DataFrame, instrument: str, timeframe: str) -> int:
    """POST bars to the datalake. Returns rows sent.

    Thin wrapper over :meth:`data.DatalakeClient.ingest` (kept for the fetchers'
    existing import site).
    """
    return get_client().ingest(df, instrument, timeframe)


__all__ = [
    "CSV_COLUMNS",
    "DATA_DIR",
    "PROJECT_ROOT",
    "merge_with_existing",
    "write_csv",
    "inject_to_datalake",
]
