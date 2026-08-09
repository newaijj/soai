"""
SoAI 2026 AI Algorithmic Trading Competition - official entrypoint.

Strategy: all-in, buy-and-hold SOXL (3x semiconductors) for the whole window,
unwound into cash immediately before the cutoff.

Why this shape
--------------
The competition scores exactly one number: terminal portfolio value after
liquidation on 15 September 2026. There is no Sharpe term, no drawdown
penalty, no capital-preservation constraint, and no credit for the path. That
makes it a rank tournament over a single ~30-day draw, and the object that
maximises P(finishing first) in a rank tournament is not the object that
maximises expected utility - it is the one with the fattest right tail.

So the design reduces to: hold the most volatile instrument the rules allow,
for as long as the rules allow, and be certain of getting out at the end.
Everything below is execution plumbing around that one decision. The measured
distribution of what a single window pays is in ``research/window_study.py``.

Constraint compliance
---------------------
* Long-only spot. The leverage is *inside* SOXL - the book never borrows,
  never shorts, never touches margin, options or futures.
* SOXL is a US-listed ETF on the Massive feed, explicitly inside the stated
  universe ("every ETF (SPY, QQQ, SMH, ARKK, TQQQ, UVXY, ...)").
* Minute cadence, which the official environment supports.
* OHLCV bars only. No order book, no news, no alternative data, no external
  network calls at runtime.

Operational notes
-----------------
* An exception raised out of ``on_trading_iteration`` kills the entire run, so
  every iteration is wrapped.
* Orders are split into child orders capped against the last completed bar's
  volume, because the official engine will not fill an order larger than the
  available liquidity.
* State is reconstructed from broker positions each iteration rather than kept
  in local variables, so a restart mid-window cannot double-buy.
* Once fully invested the iteration is a couple of attribute reads and an
  early return - it does no data fetching for the ~43,000 idle minutes in the
  middle of the window.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from lumibot.entities import Asset
from lumibot.strategies import Strategy as _LumibotStrategy

from strategies import params as P


class Strategy(_LumibotStrategy):
    """All-in SOXL for the window, flat before the cutoff."""

    # ------------------------------------------------------------------
    # Lifecycle: setup
    # ------------------------------------------------------------------
    def initialize(self):
        # Minute cadence. We only actually trade in the first few minutes of
        # the window and the last half hour; the cadence exists so both the
        # entry and the exit can be sliced against real bar volume rather than
        # dumped in one print.
        self.sleeptime = "1M"

        self._chain = (P.PRIMARY_SYMBOL,) + tuple(P.FALLBACK_SYMBOLS)
        self._asset: Asset | None = None
        self._resolved_symbol: str | None = None

        # The cutoff is fixed by the competition. It is overridable only so
        # the local harness can exercise the liquidation path inside a
        # historical window (Lumibot refuses to backtest future dates); the
        # official run passes no parameters and gets P.CUTOFF_UTC.
        override = (getattr(self, "parameters", None) or {}).get("cutoff_utc")
        self._cutoff = datetime.fromisoformat(str(override or P.CUTOFF_UTC))
        if self._cutoff.tzinfo is None:
            self._cutoff = self._cutoff.replace(tzinfo=timezone.utc)
        self._exit_from = self._cutoff - timedelta(
            minutes=int(P.LIQUIDATE_MINUTES_BEFORE_CUTOFF)
        )
        self._emergency_from = self._cutoff - timedelta(
            minutes=int(P.EMERGENCY_MINUTES_BEFORE_CUTOFF)
        )

        self._fully_invested = False
        self._flat = False

        # Live fills do not necessarily register in ``get_position`` by the
        # next minute. Without a cooldown the strategy would re-send the same
        # child order against stale state - harmless on the buy side (the cash
        # cap stops it) but on the sell side it could oversell into a short.
        self._last_order_at: datetime | None = None

        self.log_message(
            f"[init] all-in {P.PRIMARY_SYMBOL} "
            f"(fallbacks {', '.join(P.FALLBACK_SYMBOLS)}), "
            f"target={P.TARGET_EXPOSURE:.0%}, "
            f"exit_from={self._exit_from.isoformat()}"
        )

    # ------------------------------------------------------------------
    # Lifecycle: per-step decision making
    # ------------------------------------------------------------------
    def on_trading_iteration(self):
        # A raised exception here aborts the whole competition run.
        try:
            self._step()
        except Exception as exc:  # noqa: BLE001 - deliberately broad
            import traceback

            self.log_message(f"[error] iteration failed: {exc}", color="red")
            self.log_message(traceback.format_exc(), color="red")

    # ------------------------------------------------------------------
    # Core
    # ------------------------------------------------------------------
    def _step(self) -> None:
        now = self._now()

        if now >= self._exit_from:
            self._exit(now)
            return

        if self._fully_invested:
            # Hot path for the ~43,000 idle minutes in the middle of the
            # window: no data fetch, no allocation, just return.
            return

        self._enter(now)

    # -- entry ---------------------------------------------------------
    def _enter(self, now: datetime) -> None:
        asset = self._resolve_asset()
        if asset is None:
            self.log_message("[entry] no tradable symbol priced yet; waiting")
            return

        price = self._price(asset)
        if price is None:
            return

        portfolio = float(self.get_portfolio_value() or 0.0)
        cash = float(self.get_cash() or 0.0)
        if portfolio <= 0.0:
            return

        held = self._held_quantity(asset)
        target = int((portfolio * float(P.TARGET_EXPOSURE)) // price)
        delta = target - held

        if delta <= 0:
            self._fully_invested = True
            self.log_message(
                f"[entry] complete: {held} {self._resolved_symbol} "
                f"@~{price:,.2f}, portfolio=${portfolio:,.0f}"
            )
            return

        # Cap 1: available cash.
        affordable = int(
            (cash * float(P.MAX_CASH_FRACTION_PER_ORDER)) // price
        )
        # Cap 2: participation in the last completed bar.
        capacity = self._bar_capacity(asset, float(P.ENTRY_BAR_PARTICIPATION), price)

        quantity = min(delta, affordable, capacity)
        if quantity <= 0 or quantity * price < float(P.MIN_ORDER_NOTIONAL):
            if affordable <= 0:
                # Cash is spent but share count is short of target only
                # because of fees/fill drift. That is fully invested.
                self._fully_invested = True
                self.log_message(
                    f"[entry] cash exhausted at {held} shares; treating as complete"
                )
            return

        if self._cooling_down(now, int(P.ORDER_COOLDOWN_MINUTES)):
            return

        self._last_order_at = now
        self.submit_order(self.create_order(asset, int(quantity), "buy"))
        self.log_message(
            f"[entry] buy {quantity} {self._resolved_symbol} @~{price:,.2f} "
            f"({held + quantity}/{target} shares, cash=${cash:,.0f})"
        )

    # -- exit ----------------------------------------------------------
    def _exit(self, now: datetime) -> None:
        if self._flat:
            return

        asset = self._resolve_asset()
        if asset is None:
            self._flat = True
            return

        held = self._held_quantity(asset)
        if held <= 0:
            self._flat = True
            self.cancel_open_orders()
            self.log_message("[exit] flat")
            return

        if now >= self._emergency_from:
            # Dump whatever is left, ignoring the participation cap. Still
            # cooled down by a minute: ``held`` only counts *filled* shares, so
            # firing every iteration against a fill that has not yet registered
            # would sell the same block twice and leave the book short.
            if self._cooling_down(now, int(P.EMERGENCY_COOLDOWN_MINUTES)):
                return
            quantity = held
            mode = "emergency"
        else:
            if self._cooling_down(now, int(P.ORDER_COOLDOWN_MINUTES)):
                return
            price = self._price(asset) or 0.0
            quantity = min(
                held, self._bar_capacity(asset, float(P.EXIT_BAR_PARTICIPATION), price)
            )
            mode = "sliced"
            if quantity <= 0:
                self.log_message(f"[exit] no bar capacity yet; {held} remaining")
                return

        self.cancel_open_orders()
        self._last_order_at = now
        self.submit_order(self.create_order(asset, int(quantity), "sell"))
        self.log_message(
            f"[exit:{mode}] sell {quantity} {self._resolved_symbol} "
            f"({held - quantity} remaining)"
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _cooling_down(self, now: datetime, minutes: int) -> bool:
        if self._last_order_at is None or minutes <= 0:
            return False
        return (now - self._last_order_at) < timedelta(minutes=minutes)

    def _now(self) -> datetime:
        now = self.get_datetime()
        if now.tzinfo is None:
            return now.replace(tzinfo=timezone.utc)
        return now.astimezone(timezone.utc)

    def _resolve_asset(self) -> Asset | None:
        """First symbol in the chain the feed can actually price. Cached."""
        if self._asset is not None:
            return self._asset
        for symbol in self._chain:
            candidate = Asset(symbol=symbol, asset_type=Asset.AssetType.STOCK)
            if self._price(candidate) is not None:
                self._asset = candidate
                self._resolved_symbol = symbol
                if symbol != P.PRIMARY_SYMBOL:
                    self.log_message(
                        f"[resolve] {P.PRIMARY_SYMBOL} unavailable; using {symbol}",
                        color="yellow",
                    )
                return candidate
        return None

    def _price(self, asset: Asset) -> float | None:
        try:
            price = self.get_last_price(asset)
        except Exception:  # noqa: BLE001 - feed hiccup must not abort
            return None
        if price is None:
            return None
        price = float(price)
        return price if price > 0 else None

    def _held_quantity(self, asset: Asset) -> int:
        try:
            position = self.get_position(asset)
        except Exception:  # noqa: BLE001
            position = None
        if position is None:
            return 0
        try:
            return max(0, int(float(position.quantity)))
        except (TypeError, ValueError):
            return 0

    def _bar_capacity(self, asset: Asset, participation: float, price: float) -> int:
        """
        Shares we allow ourselves against the last completed minute bar.

        If the feed cannot give us a volume - no history yet at the very start
        of the window, or a feed that omits the column - fall back to a fixed
        notional slice rather than stalling. SOXL turns over roughly $26m a
        minute, so the fallback is still a rounding error against real
        liquidity, and it guarantees the position gets built either way.
        """
        volume = 0.0
        try:
            bars = self.get_historical_prices(asset, 5, timestep="minute")
            frame = getattr(bars, "df", None) if bars is not None else None
            if frame is not None and len(frame) and "volume" in frame:
                volume = float(frame["volume"].iloc[-1])
        except Exception:  # noqa: BLE001 - feed hiccup must not abort
            volume = 0.0

        if volume > 0:
            return max(0, int(volume * participation))
        if price > 0:
            return max(0, int(float(P.FALLBACK_SLICE_NOTIONAL) // price))
        return 0
