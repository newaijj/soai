"""
Generate a deterministic SOXL minute series for the local smoke test.

This exists so ``python backtest.py`` runs end-to-end on a clean clone with no
API keys and no downloads. It is an *interface* test - it proves the entry
slicing, the volume caps and the cutoff liquidation all fire and that the book
ends flat. It is not performance evidence and must not be read as any kind of
forecast. The real evidence for the strategy is the field study in
``research/field_study.py``, which uses actual market history.

The series is calibrated to SOXL as measured on 7 August 2026:

    last price               $140.25
    20-day realised vol      179% annualised
    average minute volume    190,482 shares
    average dollar volume    ~$10.9bn / day

Set ``--drift`` to shape the scenario (default 0, i.e. a driftless random
walk). ``--drift 0.5`` produces roughly a +50% window so you can watch the
winning branch execute.
"""

from __future__ import annotations

import argparse
import math
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"

# Measured on the real instrument, 7 Aug 2026.
START_PRICE = 140.25
ANNUAL_VOL = 1.79
AVG_MINUTE_VOLUME = 190_482

# US regular session in UTC during EDT: 13:30 -> 20:00.
SESSION_OPEN_UTC = (13, 30)
SESSION_MINUTES = 390
TRADING_DAYS_PER_YEAR = 252


def _sessions(start: datetime, end: datetime) -> list[datetime]:
    days, cursor = [], start
    while cursor <= end:
        if cursor.weekday() < 5:
            days.append(cursor)
        cursor += timedelta(days=1)
    return days


def _minute_volume(minute_of_session: int, rng: random.Random) -> int:
    """Crude U-shape: heavy at the open and into the close, thin midday."""
    x = minute_of_session / max(SESSION_MINUTES - 1, 1)
    shape = 0.55 + 2.6 * math.exp(-12.0 * x) + 1.5 * math.exp(-9.0 * (1.0 - x))
    if minute_of_session == 0:
        shape *= 30.0  # opening auction print
    return max(1, int(AVG_MINUTE_VOLUME * shape * rng.uniform(0.7, 1.3)))


def generate(start: datetime, end: datetime, drift: float, seed: int) -> Path:
    rng = random.Random(seed)
    sessions = _sessions(start, end)
    n_minutes = len(sessions) * SESSION_MINUTES
    if n_minutes == 0:
        raise SystemExit("empty date range")

    per_minute_vol = ANNUAL_VOL / math.sqrt(TRADING_DAYS_PER_YEAR * SESSION_MINUTES)
    # Total log drift spread evenly across every minute of the window.
    per_minute_drift = math.log1p(drift) / n_minutes

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = DATA_DIR / "SOXL_1m_spot.csv"

    price = START_PRICE
    rows = ["open,high,low,close,volume,timestamp"]
    for day in sessions:
        opened = day.replace(
            hour=SESSION_OPEN_UTC[0], minute=SESSION_OPEN_UTC[1],
            second=0, microsecond=0, tzinfo=timezone.utc,
        )
        for m in range(SESSION_MINUTES):
            o = price
            step = per_minute_drift + rng.gauss(0.0, per_minute_vol)
            price = max(0.01, o * math.exp(step))
            c = price
            wick = abs(rng.gauss(0.0, per_minute_vol)) * o
            h = max(o, c) + wick
            l = max(0.01, min(o, c) - wick)
            ts = (opened + timedelta(minutes=m)).isoformat().replace("+00:00", "+00:00")
            rows.append(
                f"{o:.4f},{h:.4f},{l:.4f},{c:.4f},{_minute_volume(m, rng)},{ts}"
            )

    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    print(
        f"[smoke-data] {path.relative_to(ROOT)}: {len(rows) - 1:,} bars, "
        f"{sessions[0].date()} -> {sessions[-1].date()}, "
        f"${START_PRICE:,.2f} -> ${price:,.2f} ({price / START_PRICE - 1:+.1%})"
    )
    return path


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--start", default="2026-08-17")
    ap.add_argument("--end", default="2026-09-15")
    ap.add_argument("--drift", type=float, default=0.0,
                    help="total simple return across the window (0 = driftless)")
    ap.add_argument("--seed", type=int, default=290)
    a = ap.parse_args()
    generate(
        datetime.fromisoformat(a.start),
        datetime.fromisoformat(a.end),
        a.drift,
        a.seed,
    )


if __name__ == "__main__":
    main()
