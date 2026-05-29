"""One-off backfill: push every local OHLC CSV into the deployed datalake.

Walks ``ohlc_data/*.csv``, queries ``/catalog`` for what's already in the lake,
and POSTs only the gap (rows newer than ``coverage.max_date`` for each
``(instrument, timeframe)`` pair). Pairs with no coverage are sent in full.

Defaults to dry-run; pass ``--apply`` to actually upload.

Usage::

    python scripts/datalake_backfill.py
    python scripts/datalake_backfill.py --apply
    python scripts/datalake_backfill.py --apply --only SPX500_M5,GER40_D1

Auth note: this deployment authenticates the API key via the ``X-API-Key``
header (Bearer returns 401). ``scripts/_datalake.py`` now matches.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from data import get_client  # noqa: E402

DATA_DIR = PROJECT_ROOT / "ohlc_data"
REQUIRED_COLS = {"instrument", "timeframe", "timestamp", "open", "high", "low", "close"}

# Lower index == finer granularity. The lake auto-derives higher TFs on /ingest,
# so when an instrument has both M5 and D1 locally we only upload the M5 — but
# only if the M5 history extends as far back as the D1 (otherwise the D1 carries
# extra pre-history we'd lose by skipping it).
TF_RANK = {"M1": 0, "M5": 1, "M15": 2, "M30": 3, "H1": 4, "H4": 5, "D1": 6, "W1": 7, "MN1": 8}


def fetch_coverage() -> dict[tuple[str, str], pd.Timestamp]:
    """Return ``{(instrument, timeframe): max_date_utc}`` for everything in the lake."""
    payload = get_client().catalog()
    out: dict[tuple[str, str], pd.Timestamp] = {}
    coverage = payload.get("database", {}).get("coverage") or payload.get("coverage", [])
    for row in coverage:
        out[(row["instrument"], row["timeframe"])] = pd.to_datetime(row["max_date"], utc=True)
    return out


def read_ohlc(path: Path) -> pd.DataFrame | None:
    df = pd.read_csv(path)
    if not REQUIRED_COLS.issubset(df.columns):
        return None
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    return df.sort_values("timestamp").reset_index(drop=True)


def scan_min_timestamps(paths: list[Path]) -> dict[Path, pd.Timestamp]:
    """Cheap scan: read just the first data row of each CSV for its min timestamp."""
    out: dict[Path, pd.Timestamp] = {}
    for p in paths:
        try:
            head = pd.read_csv(p, nrows=1)
        except Exception:
            continue
        if "timestamp" not in head.columns or head.empty:
            continue
        out[p] = pd.to_datetime(head["timestamp"].iat[0], utc=True)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Backfill local OHLC CSVs into the deployed datalake."
    )
    ap.add_argument(
        "--apply", action="store_true", help="Actually POST to the lake (default is dry-run)"
    )
    ap.add_argument(
        "--only",
        help="Comma-separated CSV stems to limit upload (e.g. 'SPX500_M5,GER40_D1')",
    )
    args = ap.parse_args()

    load_dotenv(PROJECT_ROOT / ".env")
    base_url = os.getenv("DATALAKE_URL", "").strip()
    api_key = os.getenv("DATALAKE_API_KEY", "").strip()
    if not base_url or not api_key:
        sys.exit("DATALAKE_URL and DATALAKE_API_KEY must be set in .env")

    coverage = fetch_coverage()
    print(f"Catalog: {len(coverage)} (instrument, timeframe) pairs already in lake")

    only = {s.strip() for s in args.only.split(",")} if args.only else None
    paths = sorted(p for p in DATA_DIR.glob("*.csv") if p.is_file())
    if only:
        paths = [p for p in paths if p.stem in only]
    print(f"Local candidates: {len(paths)} CSV files under {DATA_DIR}")

    # Pre-scan: per instrument, find the finest local TF and the earliest bar
    # in its file. A coarser TF is shadowed by the finer one only when the
    # finer file starts at-or-before the coarser file's first bar (else the
    # coarser file holds pre-history we'd otherwise drop).
    min_ts = scan_min_timestamps(paths)
    finest_per_instr: dict[str, tuple[str, Path]] = {}
    for p in paths:
        stem = p.stem
        if "_" not in stem:
            continue
        instr, tf = stem.rsplit("_", 1)
        if tf not in TF_RANK:
            continue
        cur = finest_per_instr.get(instr)
        if cur is None or TF_RANK[tf] < TF_RANK[cur[0]]:
            finest_per_instr[instr] = (tf, p)

    sent_pairs = 0
    sent_rows = 0
    skipped_caught_up = 0
    skipped_bad = 0
    failures: list[tuple[str, str]] = []

    for path in paths:
        df = read_ohlc(path)
        if df is None or df.empty:
            print(f"  skip {path.name}: not an OHLC CSV or empty")
            skipped_bad += 1
            continue
        if df["instrument"].nunique() != 1 or df["timeframe"].nunique() != 1:
            print(f"  skip {path.name}: mixed instrument/timeframe in file")
            skipped_bad += 1
            continue

        instr = str(df["instrument"].iat[0])
        tf = str(df["timeframe"].iat[0])

        finest = finest_per_instr.get(instr)
        if finest and finest[0] != tf:
            finer_min = min_ts.get(finest[1])
            this_min = df["timestamp"].iloc[0]
            if finer_min is not None and finer_min <= this_min:
                print(
                    f"  skip {instr} {tf}: finer local TF {finest[0]} covers same range "
                    f"({finer_min} <= {this_min}); lake derives the rest"
                )
                skipped_caught_up += 1
                continue
            print(
                f"  keep {instr} {tf}: finer TF {finest[0]} only goes back to {finer_min}, "
                f"this file starts {this_min} -- uploading pre-history"
            )

        max_local = df["timestamp"].iloc[-1]
        max_lake = coverage.get((instr, tf))

        if max_lake is not None and max_lake >= max_local:
            print(f"  skip {instr} {tf}: lake max {max_lake} >= local max {max_local}")
            skipped_caught_up += 1
            continue

        gap = df[df["timestamp"] > max_lake] if max_lake is not None else df
        verb = "POST" if args.apply else "would POST"
        tag = f"[lake max {max_lake}]" if max_lake is not None else "[new pair]"
        print(
            f"  {verb} {instr} {tf}: {len(gap)} rows "
            f"({gap['timestamp'].iloc[0]} -> {gap['timestamp'].iloc[-1]}) {tag}"
        )

        if args.apply:
            try:
                get_client().ingest(gap, instr, tf)
                sent_pairs += 1
                sent_rows += len(gap)
            except Exception as e:
                print(f"    FAILED {instr} {tf}: {e}")
                failures.append((instr, tf))

    print()
    mode = "apply" if args.apply else "dry-run"
    print(
        f"Summary [{mode}]: pairs sent={sent_pairs} rows={sent_rows} "
        f"caught-up={skipped_caught_up} skipped-bad={skipped_bad} failed={len(failures)}"
    )
    if failures:
        print("Failed pairs:", ", ".join(f"{i}/{t}" for i, t in failures))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
