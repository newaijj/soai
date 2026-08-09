"""
The evidence for the submission: does an all-in SOXL position actually win,
and how often does it win *given that it works*?

This reproduces the numbers quoted in the README. It rebuilds a replica of
every other public submission to this competition (all of them are forks of
the official template, so their strategies are readable), runs all six
entries over every overlapping 21-trading-day window of the last five years,
and scores them the way the organisers will: terminal return, nothing else.

    pip install yfinance
    python research/field_study.py

Replicas (see README for the source of each):

  me    all-in SOXL, buy and hold                       [this submission]
  own   0.95 x TQQQ, buy and hold                       [owennpine]
  sam   top-1 vol-adjusted momentum over 3x ETFs and
        crypto majors, liquidates at +25%               [samuelcheongws]
  ms    0.85 x AMAT long/flat, -12% circuit breaker     [msamhz]
  wz    S&P long-only top-5, modelled as full SPY       [weizhouzshiba]
  jk    0.9 x equal-weight top-5 of its 12-name book    [joshuakimkwan]

Every replica is drawn *generously* - where a competitor has an exposure gate,
a cash reserve or a stop that would cut its return, the replica mostly ignores
it. The conclusion survives that handicap by a wide margin.
"""

from __future__ import annotations

import math
import sys

WINDOW = 21          # trading days ~ the 30-calendar-day competition window
FEE = 0.0004         # 2 bps in, 2 bps out
SAM_LOCK = 0.25      # samuelcheongws' Browne target-lock, from their params.py

GEARED = ["TQQQ", "UPRO", "SPXL", "SOXL", "TNA", "QLD", "SSO", "USD", "FAS", "LABU"]
SAM_UNIVERSE = GEARED + ["BTC-USD", "ETH-USD", "SOL-USD"]
JK_UNIVERSE = ["AAPL", "ABBV", "AMD", "COST", "GOOGL", "LLY",
               "MOD", "NVDA", "VRTX", "BTC-USD", "ETH-USD", "SOL-USD"]
ALL = sorted(set(GEARED + SAM_UNIVERSE + JK_UNIVERSE + ["SPY", "AMAT", "SOXX", "QQQ"]))


def load(period: str = "5y") -> tuple[list[str], dict[str, list[float]]]:
    try:
        import yfinance as yf
    except ImportError:
        sys.exit("pip install yfinance")

    raw = yf.download(ALL, period=period, interval="1d",
                      auto_adjust=True, progress=False)["Close"]
    # Crypto trades seven days a week. Left as-is, its weekend rows would pad
    # the index and a "21-row" window would only span 15 trading days. Anchor
    # everything to the US equity calendar so a window really is 21 sessions,
    # i.e. the ~30 calendar days the competition actually runs for.
    calendar = raw["SPY"].dropna().index
    raw = raw.ffill().reindex(calendar).dropna(how="any")
    dates = [d.strftime("%Y-%m-%d") for d in raw.index]
    return dates, {s: raw[s].tolist() for s in ALL}


def momentum(px: dict, s: str, i: int) -> float | None:
    """Vol-adjusted 20/60-day momentum with a 100-day absolute trend filter."""
    if i < 101:
        return None
    p = px[s]
    sma100 = sum(p[i - 99:i + 1]) / 100.0
    if p[i] < sma100:
        return None
    m20 = p[i] / p[i - 20] - 1.0
    m60 = p[i] / p[i - 60] - 1.0
    var = sum(math.log(p[k] / p[k - 1]) ** 2 for k in range(i - 59, i + 1)) / 60.0
    return (m20 + m60) / 2.0 / max(math.sqrt(var), 0.002)


def run() -> None:
    dates, px = load()
    n = len(dates)
    ret = lambda s, a, b: px[s][b] / px[s][a] - 1.0  # noqa: E731

    rows = []
    for i in range(101, n - WINDOW):
        j = i + WINDOW

        me = (1.0 + ret("SOXL", i, j)) * (1.0 - FEE) - 1.0
        own = 0.95 * ret("TQQQ", i, j) - FEE

        best, score = None, -1e9
        for s in SAM_UNIVERSE:
            v = momentum(px, s, i)
            if v is not None and v > score:
                best, score = s, v
        if best is None:
            sam = 0.0
        else:
            locked = None
            for k in range(i + 1, j + 1):
                if px[best][k] / px[best][i] - 1.0 >= SAM_LOCK:
                    locked = SAM_LOCK
                    break
            sam = (locked if locked is not None else ret(best, i, j)) - FEE

        stopped = None
        for k in range(i + 1, j + 1):
            if px["AMAT"][k] / px["AMAT"][i] - 1.0 <= -0.12:
                stopped = -0.12
                break
        ms = 0.85 * (stopped if stopped is not None else ret("AMAT", i, j)) - FEE

        wz = ret("SPY", i, j) - FEE

        top5 = sorted(JK_UNIVERSE, key=lambda s: px[s][i] / px[s][i - 20],
                      reverse=True)[:5]
        jk = 0.9 * sum(ret(s, i, j) for s in top5) / 5.0 - FEE

        rows.append({"d": dates[i], "me": me, "own": own, "sam": sam,
                     "ms": ms, "wz": wz, "jk": jk})

    names = ["own", "sam", "ms", "wz", "jk"]
    wins = lambda r: r["me"] > max(r[k] for k in names)  # noqa: E731
    pct = lambda a, b: f"{100.0 * a / b:5.1f}%" if b else "  n/a"  # noqa: E731

    print(f"\nWindows: {len(rows):,}  ({rows[0]['d']} -> {rows[-1]['d']}, "
          f"{WINDOW} trading days each)\n")

    print("Terminal-return distribution across all windows")
    print(f"{'entry':6} {'p5':>8} {'p25':>8} {'median':>8} {'p75':>8} "
          f"{'p95':>8} {'max':>8}")
    for k in ["me"] + names:
        a = sorted(r[k] for r in rows)
        q = lambda p: a[int(p * (len(a) - 1))]  # noqa: E731
        print(f"{k:6} {q(.05):+8.1%} {q(.25):+8.1%} {q(.50):+8.1%} "
              f"{q(.75):+8.1%} {q(.95):+8.1%} {max(a):+8.1%}")

    print(f"\nUnconditional P(this submission finishes first): "
          f"{pct(sum(1 for r in rows if wins(r)), len(rows))}  "
          f"(6-way baseline 16.7%)")

    print("\nConditional on the bet paying off")
    print(f"{'threshold':>10} {'windows':>9} {'frequency':>10} "
          f"{'P(beat whole field)':>21}")
    for thr in (0.25, 0.40, 0.50):
        sub = [r for r in rows if r["me"] >= thr]
        w = sum(1 for r in sub if wins(r))
        print(f"{thr:>+10.0%} {len(sub):>9,} {pct(len(sub), len(rows)):>10} "
              f"{pct(w, len(sub)):>21}")

    print("\nYear by year, P(finish first | SOXL >= +25%)")
    years: dict[str, list[int]] = {}
    for r in rows:
        y = r["d"][:4]
        acc = years.setdefault(y, [0, 0])
        if r["me"] >= 0.25:
            acc[0] += 1
            acc[1] += int(wins(r))
    for y in sorted(years):
        hit, won = years[y]
        print(f"  {y}: {hit:>4} qualifying windows, {pct(won, hit)} won")

    losses = [r for r in rows if r["me"] >= 0.25 and not wins(r)]
    print(f"\nWindows where the bet paid off and still lost: {len(losses)}")
    for r in losses:
        beat = max(names, key=lambda k: r[k])
        print(f"  {r['d']}: me {r['me']:+.1%} vs {beat} {r[beat]:+.1%}")


if __name__ == "__main__":
    run()
