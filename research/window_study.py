"""
How an all-in SOXL position behaves over a competition-length window.

The competition scores one number: terminal return over a single ~30-day
window. So the useful thing to know about the strategy is not its annualised
performance but the *distribution* of what a single 30-day window pays.

This runs the strategy over every overlapping 21-trading-day window of the last
five years and scores each one exactly the way the organisers will: buy at the
window open, hold, liquidate at the window close, 2 bps each way, nothing else.

    pip install yfinance
    python research/window_study.py
"""

from __future__ import annotations

import sys

SYMBOL = "SOXL"
WINDOW = 21      # trading days ~ the 30 calendar days the competition runs
FEE = 0.0004     # 2 bps in, 2 bps out


def load(period: str = "5y") -> tuple[list[str], list[float]]:
    try:
        import yfinance as yf
    except ImportError:
        sys.exit("pip install yfinance")

    df = yf.download(SYMBOL, period=period, interval="1d",
                     auto_adjust=True, progress=False)["Close"].dropna()
    close = df[SYMBOL] if hasattr(df, "columns") else df
    return [d.strftime("%Y-%m-%d") for d in close.index], close.tolist()


def run() -> None:
    dates, px = load()

    rows = []
    for i in range(len(px) - WINDOW):
        gross = px[i + WINDOW] / px[i]
        rows.append((dates[i], gross * (1.0 - FEE) - 1.0))

    returns = sorted(r for _, r in rows)
    n = len(returns)
    q = lambda p: returns[int(p * (n - 1))]  # noqa: E731

    print(f"\n{SYMBOL}, all-in, {WINDOW}-trading-day windows, {FEE * 1e4:.0f} bps round trip")
    print(f"{n:,} overlapping windows  ({rows[0][0]} -> {rows[-1][0]})\n")

    print("Terminal-return distribution")
    print(f"{'p5':>8} {'p25':>8} {'median':>8} {'p75':>8} {'p95':>8} {'max':>8}")
    print(f"{q(.05):+8.1%} {q(.25):+8.1%} {q(.50):+8.1%} "
          f"{q(.75):+8.1%} {q(.95):+8.1%} {max(returns):+8.1%}")
    print(f"\nworst window {min(returns):+.1%}   mean {sum(returns) / n:+.1%}")

    print("\nHow often the window clears a level")
    for thr in (0.25, 0.40, 0.50):
        hit = sum(1 for r in returns if r >= thr)
        print(f"  >= {thr:+.0%}: {hit:>5,} windows  ({100.0 * hit / n:4.1f}%)")

    print("\nBy year")
    years: dict[str, list[float]] = {}
    for d, r in rows:
        years.setdefault(d[:4], []).append(r)
    for y in sorted(years):
        a = sorted(years[y])
        hit = sum(1 for r in a if r >= 0.25)
        print(f"  {y}: {len(a):>4} windows, median {a[len(a) // 2]:+6.1%}, "
              f"{100.0 * hit / len(a):4.1f}% cleared +25%")


if __name__ == "__main__":
    run()
