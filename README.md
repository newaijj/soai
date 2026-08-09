# All-in SOXL — SoAI 2026 AI Algorithmic Trading Competition

**Entrypoint:** [`strategies/strategy.py`](strategies/strategy.py) · class `Strategy(lumibot.strategies.Strategy)`

The strategy buys **SOXL** (Direxion Daily Semiconductor Bull 3X) with the entire
book on the first tradable minute of the window, holds it for thirty days, and
liquidates into cash in the last half hour before the cutoff. 

---

## 1. Why SOXL specifically

The competition permits any CCXT spot pair and the entire US equity and ETF
universe, but not margin — so leverage has to live *inside* the instrument. US
regulation caps ETF leverage at 3× (the SEC blocked the 2025–26 wave of 4×/5×
filings), which puts the ceiling at a 3× index ETF. Among those, the binding
constraint is that a seven-figure book has to be both deployable and
*unwindable* against the official engine's volume-aware fill caps.

Measured 7 August 2026:

| | last | 20d realised vol | 60d realised vol | $ ADV | drawdown from 52wk high |
| --- | --- | --- | --- | --- | --- |
| **SOXL** (3× semis) | $140.25 | **179%** | **198%** | **$10.9bn** | **−53.6%** |
| TQQQ (3× NDX) | $74.47 | 77% | 79% | $5.0bn | −15.5% |
| LABU (3× biotech) | $277.23 | 84% | 93% | $107m | −16.7% |
| UPRO (3× S&P) | $155.06 | 43% | 43% | $336m | −1.5% |
| UVXY (1.5× VIX futures) | $21.62 | 78% | 73% | $166m | −70.6% |
| QQQ | $723.03 | 26% | 27% | $30bn | −3.4% |

SOXL is the highest-volatility instrument in the eligible universe **and** one
of the most liquid — $10.9bn a day, ~190,000 shares a minute. A $1m position is
0.01% of a session, so both the entry and the exit are rounding errors against
real liquidity. Nothing else offers that combination: UVXY and LABU are an
order of magnitude thinner and UVXY bleeds structurally, crypto spot carries no
leverage at all, and a genuinely wild microcap could not be sold at the end.

Three things make the current setup favourable for the long side:

- Semiconductors fell ~24% in July on the 27 July report of Chinese domestic
  DUV lithography production, their worst month since 2008 — a
  headline-driven derating, not an earnings one. SOXL is 53.6% below its
  52-week high.
- Fundamentals moved the other way: global semiconductor sales set a record
  $120.6bn in May 2026, up 104% year over year and the 15th consecutive record
  month, with Q2 results confirming accelerating AI capex.
- **NVIDIA reports Q2 FY2027 on 26 August 2026**, squarely inside the trading
  window — the largest single volatility event in the equity market, in exactly
  this sector.

Realised vol of 179% annualised over a 21-session window is a one-sigma move of
about ±52%. Roughly: SOX +10% over the window pays about +21% after the ~9%
volatility drag a 3× fund incurs at these vol levels; SOX +20% pays about +57%;
a full round-trip to the June high pays about +60%.

## 2. Validation

[`research/window_study.py`](research/window_study.py) runs the strategy over
**every overlapping 21-trading-day window of the last five years** — 1,234
windows, each matching the ~30 calendar days the competition runs for — and
scores each one the way the organisers will: terminal return, 2 bps each way,
nothing else.

```bash
pip install yfinance
python research/window_study.py
```

Terminal-return distribution across all 1,234 windows:

| p5 | p25 | median | p75 | p95 | max |
| --- | --- | --- | --- | --- | --- |
| −40.1% | −15.7% | +2.2% | +24.6% | **+63.9%** | **+193.2%** |

How often the window clears a given level:

| terminal return | frequency |
| --- | --- |
| ≥ +25% | 24.9% of windows |
| ≥ +40% | 14.7% of windows |
| ≥ +50% | 10.0% of windows |

The upper tail is the point of the instrument: a quarter of historical windows
clear +25% and one in ten clears +50%, which is the range a 3× position on a
53%-drawn-down sector reaches on a recovery leg. The hit rate is higher in the
current regime than the five-year average — 40.3% of 2026 windows have cleared
+25%, against 24.9% across the full sample.

No attempt is made to time the entry. Any timing filter would break the
correspondence between the strategy that ships and the study that validates it:
the study measures buy-at-window-open-and-hold, and that is exactly what runs.

## 3. Rules compliance

- **Long-only spot, no margin.** The leverage is internal to SOXL; a 3× ETF is
  an ordinary cash purchase. The book never borrows, shorts, or touches
  options or futures.
- **In-universe.** SOXL is a US-listed ETF on the Massive feed. The rules state
  the universe covers "every ETF (SPY, QQQ, SMH, ARKK, TQQQ, UVXY, …)."
- **Supported cadence.** `self.sleeptime = "1M"`, minute-level.
- **OHLCV only.** No order book, no news, no alternative data, no runtime
  network calls of any kind.
- **Capacity-aware.** Child orders are capped at 1% of the last completed
  minute bar's volume on entry and 2% on exit, so the engine's volume-aware
  fill cap is never the binding constraint.
- **Reproducible.** No absolute paths, no prompts, no secrets, no files outside
  the repo. All dependencies in `requirements.txt`.

## 4. Running it

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python backtest.py
```

`backtest.py` is an **interface test**, not performance evidence. Lumibot
refuses to backtest future dates and the competition window has not happened
yet, so the harness generates a deterministic minute series calibrated to
SOXL's measured price, volatility and per-minute volume, dates it into the
recent past, and moves the cutoff to the end of it. What it proves is that the
code path works: the entry slices against bar volume, the position is held, the
liquidation fires before the cutoff, and the book ends flat with cash equal to
portfolio value.

```bash
python backtest.py --drift 0.5    # exercises the winning branch
python backtest.py --drift -0.4   # exercises the losing branch
```

Verified end-to-end on a clean clone against Lumibot 4.5.83.

## 5. Repository map

| Path | Purpose |
| --- | --- |
| `strategies/strategy.py` | **The submission.** |
| `strategies/params.py` | Instrument, sizing, cutoff. |
| `research/window_study.py` | The evidence in §2. Reproduces every number. |
| `backtest.py` | Local interface harness. Not used by the official run. |
| `tools/make_smoke_data.py` | Deterministic minute series for the harness. |

---

### A note on execution timing

The cutoff, 15 September 2026 23:59:59 SGT, is 11:59:59 New York time — the US
cash session is open, so the position can always be unwound. The strategy
starts liquidating 30 minutes before that in volume-capped slices and sends
whatever remains in a single order inside the last 8 minutes, so it is flat
before the organisers' own liquidation runs regardless of how that is
implemented.
