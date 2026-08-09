"""
Tuned constants for the submission.

``strategies/strategy.py`` imports everything it needs from here so the
official entrypoint and the local harness never disagree about the
instrument, the sizing or the cutoff.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Instrument
# ---------------------------------------------------------------------------
# SOXL - Direxion Daily Semiconductor Bull 3X Shares. 3x daily exposure to the
# NYSE Semiconductor Index. It is an ordinary long-only spot purchase: the
# leverage lives inside the fund, so the book never borrows and never shorts,
# which keeps the strategy inside the competition's cash-spot constraint.
#
# Measured 7 Aug 2026: price $140.25, 20-day realised vol 179% annualised,
# 60-day 198%, $10.9bn average daily dollar volume, AUM $23.8bn. It is by a
# wide margin the highest-volatility instrument in the eligible universe that
# can still absorb and unwind a seven-figure position inside a single minute.
PRIMARY_SYMBOL: str = "SOXL"

# Ordered fallbacks, used only if the official feed cannot price the primary.
# Both are 3x/liquid; TQQQ is 3x Nasdaq-100, QQQ is the unlevered backstop.
FALLBACK_SYMBOLS: tuple[str, ...] = ("TQQQ", "QQQ")

# ---------------------------------------------------------------------------
# Sizing
# ---------------------------------------------------------------------------
# Fraction of portfolio value to hold in the instrument. The residual is a
# working buffer so a market order is never rejected for insufficient cash
# after the 2 bps fee and any adverse fill.
TARGET_EXPOSURE: float = 0.99

# Never spend more than this share of *available cash* on a single child
# order. Belt-and-braces against a fill printing above the sizing price.
MAX_CASH_FRACTION_PER_ORDER: float = 0.98

# Cap each child order at this share of the last completed minute bar's
# volume. The official engine applies its own volume-aware cap and simply will
# not fill the excess, so we stay well under it and top up on the next bar.
# SOXL trades ~190,000 shares/minute, so 1% is ~1,900 shares (~$265k) per
# minute: a $1m book is fully deployed in about four minutes.
ENTRY_BAR_PARTICIPATION: float = 0.01
EXIT_BAR_PARTICIPATION: float = 0.02

# Skip dust orders.
MIN_ORDER_NOTIONAL: float = 500.0

# Used when the feed cannot supply a bar volume (no history yet at the start of
# the window, or a feed without the column). SOXL turns over roughly $26m per
# minute, so a $50k slice stays far inside any plausible engine cap.
FALLBACK_SLICE_NOTIONAL: float = 50_000.0

# Minutes to wait after sending a child order before sending another, so a
# live fill has time to register in the position before we size the next one.
ORDER_COOLDOWN_MINUTES: int = 2

# The same, for the emergency exit. Shorter, because at that point getting
# flat matters more than order-count discipline - but not zero, or an
# unregistered fill would be sold twice and leave the book short.
EMERGENCY_COOLDOWN_MINUTES: int = 1

# ---------------------------------------------------------------------------
# Window
# ---------------------------------------------------------------------------
# Official trading window per the competition site (soc-ai.org):
#   opens  16 August 2026, 00:00:00 SGT
#   closes 15 September 2026, 23:59:59 SGT, full liquidation at the close.
# 23:59:59 SGT is 15:59:59 UTC, i.e. 11:59:59 New York time - the US cash
# session is open at the cutoff, so the position can always be unwound.
CUTOFF_UTC: str = "2026-09-15T15:59:59+00:00"

# Begin unwinding this many minutes before the cutoff. SOXL turns over
# ~$10.9bn a day, so a $1m position is ~0.01% of a session; 30 minutes is far
# more room than the exit needs and costs almost no upside.
LIQUIDATE_MINUTES_BEFORE_CUTOFF: int = 30

# Inside this many minutes of the cutoff, drop the participation cap and send
# the whole remaining position in one order.
EMERGENCY_MINUTES_BEFORE_CUTOFF: int = 8

# ---------------------------------------------------------------------------
# Local backtest harness only (backtest.py)
# ---------------------------------------------------------------------------
STOCK_SLEEVE_SYMBOLS: list[str] = [PRIMARY_SYMBOL]
CRYPTO_SLEEVE_SYMBOLS: list[str] = []
STOCK_BENCH: str = PRIMARY_SYMBOL
CRYPTO_BENCH: str = PRIMARY_SYMBOL
CRYPTO_SYMBOLS: set[str] = set(CRYPTO_SLEEVE_SYMBOLS)
