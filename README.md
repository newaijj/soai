# All-in SOXL — SoAI 2026 AI Algorithmic Trading Competition

**Entrypoint:** [`strategies/strategy.py`](strategies/strategy.py) · class `Strategy(lumibot.strategies.Strategy)`

The strategy buys **SOXL** (Direxion Daily Semiconductor Bull 3X) with the entire
book on the first tradable minute of the window, holds it for thirty days, and
liquidates into cash in the last half hour before the cutoff. There is no
signal, no model, and no rebalance. That is the whole design, and the rest of
this document is the argument for why it is the right one *for this particular
scoring rule* — and what it costs.

---

## 1. The scoring rule makes this a tournament, not a portfolio

From the competition's judging criteria, verbatim:

> **Terminal Return** — Final portfolio value after full liquidation at market
> close on 15 September 2026 (23:59:59 SGT). *The single metric that determines
> the leaderboard.*

There is no Sharpe term, no drawdown penalty, no volatility target, no
capital-preservation floor, and no credit for the path taken. One number, one
draw, one ~30-day window, and prizes only at the top.

That changes the objective. A fund manager maximises risk-adjusted expected
return because they keep playing and they answer for losses. A contestant
scored purely on rank over a single draw maximises **P(finishing first)**, and
those two objectives point in different directions. Under a rank payoff the
useful quantity is not expected return but the mass of your return
distribution above the *field's* best plausible outcome. Variance you would
never accept as an investor is close to free here, because finishing 6th with
−45% and finishing 6th with −5% pay identically: nothing.

So the design question is only: **what is the highest-variance thing the rules
permit, and where is the bar?**

## 2. Where the bar is

Every other entry is a public fork of the official template, so the field is
readable rather than hypothetical. Eleven forks exist; six are unmodified
copies. The five real submissions:

| Fork | What it trades | Effective leverage | Structural ceiling |
| --- | --- | --- | --- |
| `owennpine` | 95% TQQQ, static buy-and-hold, 5-minute cadence | ~2.85× Nasdaq-100 | none, but 3× *NDX* |
| `samuelcheongws` | top-1 vol-adjusted momentum over ten 3× ETFs + 34 crypto majors | ~3×, one name at a time | **hard-capped at +25%** by a Browne target-lock (`TARGET_RETURN = 0.25` in their `params.py`: on touching +25% it liquidates and holds cash) |
| `msamhz` | AMAT only, long/flat, Donchian 10/20/55 vote | ~0.85×, unlevered | −12% circuit breaker, 85% cash cap |
| `weizhouzshiba` | top-5 of 90 S&P names, LGBM+XGB alpha | <1× | 20% per-name cap, regime gates cut exposure to 30–50% |
| `joshuakimkwan` | top-5 of 12 names, per-asset XGBoost, hourly | ~0.9× | 35% per-name cap, 10% cash reserve, ATR + trailing stops, 30% drawdown brake |

The single most important fact in that table is the second row.
`samuelcheongws` is the most sophisticated entry in the field — they ran the
same tournament analysis, reached the same conclusion about variance, and then
deliberately capped their own upside at +25% because that maximised their
probability of a *top-decile* finish. Top decile is not first place. Their
ceiling is our floor: anything that clears roughly +25–30% beats the best-
designed strategy in the competition by construction.

Nobody else in the field carries more than 3× index beta, and only
`owennpine` carries anything comparable to ours.

## 3. Why SOXL specifically

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

Three things make the current setup unusually favourable for the long side:

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
about ±52%. Fair value for the bet is roughly: SOX +10% over the window pays
about +21% after the ~9% volatility drag a 3× fund incurs at these vol levels;
SOX +20% pays about +57%; a full round-trip to the June high pays about +60%.

## 4. Does it actually win if it works?

This is the question that decides whether the design is sound, so it is
measured rather than asserted. [`research/field_study.py`](research/field_study.py)
rebuilds a replica of all five competitor strategies from their published
code, runs all six entries over **every overlapping 21-trading-day window of
the last five years** (1,133 windows), and scores them the way the organisers
will: terminal return, 2 bps each way, nothing else.

```bash
pip install yfinance
python research/field_study.py
```

Terminal-return distribution, all 1,133 windows:

| entry | p5 | p25 | median | p75 | p95 | max |
| --- | --- | --- | --- | --- | --- | --- |
| **this submission** | −40.4% | −16.6% | +1.7% | +25.1% | **+65.5%** | **+193.2%** |
| owennpine | −28.5% | −8.7% | +2.9% | +13.7% | +33.0% | +65.8% |
| samuelcheongws | −24.4% | −5.5% | +0.0% | +14.2% | +25.0% | **+25.0%** |
| msamhz | −10.2% | −6.4% | +1.8% | +9.3% | +20.5% | +51.5% |
| weizhouzshiba | −7.3% | −1.7% | +1.6% | +4.2% | +7.8% | +15.3% |
| joshuakimkwan | −10.6% | −2.3% | +2.3% | +7.6% | +18.2% | +36.5% |

**Conditional on the bet paying off:**

| if the window returns | happens | P(this submission finishes first) |
| --- | --- | --- |
| ≥ +25% | 25.2% of windows | **99.0%** |
| ≥ +40% | 14.7% of windows | **99.4%** |
| ≥ +50% | 9.9% of windows | **100.0%** |

Stable in every year of the sample — 95.3%, 100%, 100%, 100%, 98.1% for
2022 through 2026. In the 286 windows where the bet paid off, it lost exactly
three times, always to `owennpine`'s TQQQ in a 2022 stretch when the Nasdaq
outran semis, or to a single idiosyncratic AMAT rip in May 2026. Median margin
over the runner-up, when the bet works, is +18.9 percentage points.

Unconditionally it finishes first in **33.8%** of windows against a 16.7%
six-way baseline — so even before conditioning, concentrating into the
highest-vol instrument roughly doubles the chance of winning outright.

Every replica is drawn generously: where a competitor has an exposure gate, a
cash reserve or a stop that would drag their return down, the replica mostly
ignores it. The conclusion survives that handicap comfortably.

## 5. What this costs — stated plainly

The same table says the 5th percentile is **−40.4%** and the worst window in
five years was **−61%**. The median outcome is +1.7%, barely distinguishable
from cash, and the strategy finishes *last* more often than any other entry in
the field. Three specific things to be clear about:

- **This is not a good investment strategy.** It is a good *tournament* entry
  under a rule that ignores risk. Do not read the 33.8% win rate as an edge —
  it is a variance argument, not an alpha argument.
- **Roughly three windows in four, the bet does not pay off.** "Wins 99% of
  the time given it works" and "works 25% of the time" are both true and the
  second one matters just as much.
- **The organisers reserve the right to adjust evaluation criteria** for
  "operational, technical, regulatory, or fairness considerations." A naked
  maximum-variance entry is the most likely kind to attract that discretion,
  even though it breaks no stated rule.

The design is also honest about what it is *not* doing: no attempt is made to
time the entry, because any timing filter would break the correspondence
between the strategy that ships and the study in §4 that validates it. The
study measures buy-at-window-open-and-hold, and that is exactly what runs.

## 6. Rules compliance

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

## 7. Running it

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python backtest.py
```

`backtest.py` is a **smoke test**, not performance evidence. Lumibot refuses to
backtest future dates and the competition window has not happened yet, so the
harness generates a deterministic minute series calibrated to SOXL's measured
price, volatility and per-minute volume, dates it into the recent past, and
moves the cutoff to the end of it. What it proves is that the code path works:
the entry slices against bar volume, the position is held, the liquidation
fires before the cutoff, and the book ends flat.

```bash
python backtest.py --drift 0.5    # watch the winning branch execute
python backtest.py --drift -0.4   # watch the losing branch execute
```

## 8. Repository map

| Path | Purpose |
| --- | --- |
| `strategies/strategy.py` | **The submission.** |
| `strategies/params.py` | Instrument, sizing, cutoff. |
| `research/field_study.py` | The evidence in §4. Reproduces every number. |
| `backtest.py` | Local smoke harness. Not used by the official run. |
| `tools/make_smoke_data.py` | Deterministic minute series for the smoke test. |

---

### A note on execution timing

The cutoff, 15 September 2026 23:59:59 SGT, is 11:59:59 New York time — the US
cash session is open, so the position can always be unwound. The strategy
starts liquidating 30 minutes before that in volume-capped slices and sends
whatever remains in a single order inside the last 8 minutes, so it is flat
before the organisers' own liquidation runs regardless of how that is
implemented.
