"""
Local backtest entrypoint - development only.

Runs ``strategies.strategy.Strategy`` against minute-bar CSVs in ``data/``
using Lumibot's PandasDataBacktesting engine, with the competition's 2 bps
fee applied to both sides.

On a clean clone there is no CSV, so this script generates a deterministic
one first (see ``tools/make_smoke_data.py``). That run is an **interface
test**: it proves the entry slices against bar volume, that the position is
liquidated before the cutoff, and that the book ends flat. It is not evidence
about returns - the official score comes from the organisers' engine over
16 August - 15 September 2026, and the strategy's actual case is argued from
real market history in ``research/window_study.py``.

    python backtest.py                 # driftless smoke run
    python backtest.py --drift 0.5     # watch the winning branch execute
    python backtest.py --drift -0.4    # watch the losing branch execute
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from lumibot.backtesting import PandasDataBacktesting
from lumibot.entities import Asset, Data, TradingFee

from strategies import params as P
from strategies.strategy import Strategy

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"

BUDGET = 1_000_000
FEE_BPS_PER_SIDE = 0.0002  # the competition's uniform 2 bps


def _read_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(
        path, usecols=["open", "high", "low", "close", "volume", "timestamp"]
    )
    df["datetime"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    df = df.dropna(subset=["datetime"]).drop(columns=["timestamp"])
    df = df.set_index("datetime").sort_index()
    return df[["open", "high", "low", "close", "volume"]]


def _load(symbols: list[str]) -> dict[Asset, Data]:
    quote = Asset(symbol="USD", asset_type=Asset.AssetType.FOREX)
    loaded: dict[Asset, Data] = {}
    for symbol in dict.fromkeys(symbols):
        path = DATA_DIR / f"{symbol.replace('/', '_')}_1m_spot.csv"
        if not path.exists():
            print(f"[WARN] missing CSV for {symbol}: {path}")
            continue
        df = _read_csv(path)
        if df.empty:
            print(f"[WARN] empty CSV for {symbol}: {path}")
            continue
        asset = Asset(symbol=symbol, asset_type=Asset.AssetType.STOCK)
        loaded[asset] = Data(asset, df, timestep="minute", quote=quote)
        print(
            f"[INFO] {symbol}: {len(df):,} bars "
            f"{df.index.min()} -> {df.index.max()}"
        )
    return loaded


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--drift", type=float, default=0.0,
                    help="total return of the generated smoke series")
    ap.add_argument("--seed", type=int, default=290)
    ap.add_argument("--regenerate", action="store_true",
                    help="rebuild the smoke CSV even if one exists")
    args = ap.parse_args()

    # Lumibot refuses to backtest past "now", and the competition window is in
    # the future, so the smoke series is dated into the recent past instead.
    # The strategy's real cutoff (params.CUTOFF_UTC) is overridden below to the
    # end of that series so the liquidation path still gets exercised.
    smoke_start, smoke_end = datetime(2026, 7, 6), datetime(2026, 8, 7)

    csv = DATA_DIR / f"{P.PRIMARY_SYMBOL}_1m_spot.csv"
    if args.regenerate or not csv.exists():
        from tools.make_smoke_data import generate

        generate(smoke_start, smoke_end, args.drift, args.seed)

    pandas_data = _load([P.PRIMARY_SYMBOL])
    if not pandas_data:
        raise SystemExit(f"no usable CSV data in {DATA_DIR}")

    starts = [d.df.index.min() for d in pandas_data.values()]
    ends = [d.df.index.max() for d in pandas_data.values()]
    start = max(starts).to_pydatetime().astimezone(timezone.utc)
    end = min(ends).to_pydatetime().astimezone(timezone.utc)
    # Put the cutoff one minute before the data ends, so the smoke run has to
    # perform the full entry -> hold -> sliced liquidation -> flat sequence.
    cutoff = end.replace(second=0, microsecond=0)
    print(f"[INFO] backtest window: {start} -> {end}")
    print(f"[INFO] smoke cutoff (overrides params.CUTOFF_UTC): {cutoff}")

    fee = TradingFee(percent_fee=FEE_BPS_PER_SIDE, maker=True, taker=True)

    Strategy.run_backtest(
        PandasDataBacktesting,
        start,
        end,
        pandas_data=pandas_data,
        budget=BUDGET,
        benchmark_asset=P.PRIMARY_SYMBOL,
        buy_trading_fees=[fee],
        sell_trading_fees=[fee],
        parameters={"cutoff_utc": cutoff.isoformat()},
    )


if __name__ == "__main__":
    main()
