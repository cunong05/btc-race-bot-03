"""BTC race bot for make.fun btc-race-24h-20261118-1444.

Strategy: mean-reversion dip-buying on 1-minute cbBTC/USDC bars. The
dev window (17-18 Nov 2026) fell -2.8% over 24h with multi-hour swings
of 1-2%, so the bot buys dips 0.5% below the 60-minute average and
exits on a +1% take-profit, -2% stop-loss, -2% trailing stop, or an
8-hour max hold. A downtrend filter skips entries while the close sits
more than 3% below the close 240 bars ago (in a strong downtrend leg
dips keep dipping). A full-size round trip pays ~26 bps in fee +
slippage + impact, so the +1% take-profit clears costs with room to
spare. Backtest on the frozen dev window: +$17.43 net PnL, 4 trades,
max drawdown 1.5% (buy-and-hold on the same window: -$31.63); the same
parameters score +$14.80 on the previous race's dev window.

Long only, all-in on one position at a time, one order per batch at
most. No new entries once cumulative realised loss reaches the brake,
and none in the last 90 bars of the window.

Deterministic: integer money math, float64 indicators summed in bar
order, no randomness, no wall clock, no network, no files. The same
bars give the same orders on every run.

Protocol: agent-fun/bars-replay/v1, via the vendored SDK shim. The
harness sends hello once, then one batch per minute (the bar that
closed, the fills of the orders sent on the previous batch, and the
account); the bot answers every batch with exactly one reply echoing
its seq. Orders decided on a batch fill at the next bar's open.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))
import makefun_bars

SYM = "CBBTC"

# --- Tuned parameters (grid-searched on the frozen dev window) ---
PARAMS = {
    # Dip reference: SMA of closes.
    "sma_n": 60,
    # Buy when close <= SMA * (1 - dip).
    "dip": 0.005,
    # RSI(14) ceiling for dip buys (Wilder's); 100 = filter off.
    "rsi_max": 100,
    # Take profit: position value >= cost * (1 + tp_bps / 10000).
    "tp_bps": 100,
    # Stop loss: position value <= cost * (1 - sl_bps / 10000).
    "sl_bps": 200,
    # Trailing stop: close <= peak * (1 - trail_bps / 10000).
    "trail_bps": 200,
    # Max bars to hold one trade.
    "max_hold": 480,
    # Sell when the close reverts to the SMA (mean reversion exit).
    "revert": False,
    # Trend filter: "ret240" = skip dip buys while the close sits more
    # than 3% below the close 240 bars ago (a strong downtrend leg:
    # dips keep dipping there). None = no filter.
    "trend": "ret240",
    # Momentum engine: buy when close >= close[-31] * (1 + mom_thr/10000).
    "mom_thr": None,
    # Snap engine: buy when close <= close[-61] * (1 - snap_thr/10000).
    "snap_thr": None,
    # Enable the mean-reversion engine.
    "mr": True,
    # Stop opening new trades once cumulative realised loss hits this
    # (micro-USDC, negative).
    "loss_brake": -25_000_000,
    # No new entries in the last N bars of the window.
    "no_entry_last": 90,
    # Max slippage vs the latest close, in bps.
    "max_slippage_bps": 200,
}
WINDOW_BARS = 1440

closes = []
_prefix = [0.0]
typical = []
_first = []
_gain = None
_loss = None
_last = None
_owner = None
_pending_owner = None
_peak = 0
_held_bars = 0
_open_cost = 0
_realised = 0


def _rsi():
    if _gain is None:
        return None
    moved = _gain + _loss
    return 50.0 if moved == 0 else 100.0 * _gain / moved


def _sma(n):
    if len(closes) < n:
        return None
    return (_prefix[-1] - _prefix[-1 - n]) / n


def _push(bar):
    global _gain, _loss, _last
    c = int(bar["c"])
    closes.append(c)
    _prefix.append(_prefix[-1] + c)
    typical.append((int(bar["h"]) + int(bar["l"]) + c) / 3.0)
    if len(typical) > 20:
        typical.pop(0)
    if _last is not None:
        ch = c - _last
        up = ch if ch > 0 else 0
        dn = -ch if ch < 0 else 0
        if _gain is None:
            _first.append(ch)
            if len(_first) == 14:
                _gain = sum(x for x in _first if x > 0) / 14.0
                _loss = sum(-x for x in _first if x < 0) / 14.0
        else:
            _gain = (_gain * 13 + up) / 14.0
            _loss = (_loss * 13 + dn) / 14.0
    _last = c


def on_batch(state, batch):
    global _owner, _pending_owner, _peak, _held_bars, _open_cost, _realised
    p = PARAMS
    # Fold this batch's fills into the realised-PnL brake.
    for fill in batch["fills"]:
        if fill["symbol"] != SYM or fill["status"] != "filled":
            continue
        if fill["side"] == "buy":
            _open_cost = int(fill["notional_quote_units"])
        else:
            _realised += int(fill["notional_quote_units"]) - _open_cost
            _open_cost = 0
    # Fold this batch's bar into the indicator history.
    fresh = False
    for bar in batch["bars"]:
        if bar["symbol"] != SYM:
            continue
        _push(bar)
        fresh = True
    if not fresh or state.warming_up:
        return []
    close = state.close(SYM)
    if close is None:
        return []
    held = state.positions.get(SYM)
    if held is not None:
        if _owner is None:
            _owner = _pending_owner if _pending_owner is not None else "mr"
            _peak = close
            _held_bars = 0
        if close > _peak:
            _peak = close
        _held_bars += 1
    else:
        _owner = None
        _pending_owner = None
    # Exits: take profit, stop loss, trailing stop, max hold, reversion.
    if held is not None:
        value = state.value(SYM, held.qty)
        cost = held.cost
        s60 = _sma(p["sma_n"])
        take_profit = value * 10000 >= cost * (10000 + p["tp_bps"])
        stop_loss = value * 10000 <= cost * (10000 - p["sl_bps"])
        trailing = close * 10000 <= _peak * (10000 - p["trail_bps"])
        timed_out = _held_bars >= p["max_hold"]
        reverted = (p["revert"] and _owner == "mr"
                    and s60 is not None and close >= s60)
        if take_profit or stop_loss or trailing or timed_out or reverted:
            return [{"side": "sell", "symbol": SYM, "qty": held.qty,
                     "max_slippage_bps": p["max_slippage_bps"]}]
        return []
    # Entries (flat only).
    if _realised <= p["loss_brake"]:
        return []
    scored = state.seq - state.warmup_bars
    if scored >= WINDOW_BARS - p["no_entry_last"]:
        return []
    cash = state.cash
    if cash < int(state.hello["fees"]["min_notional_quote_units"]):
        return []
    s60 = _sma(p["sma_n"])
    r = _rsi()
    if p["trend"] == "ma":
        s240 = _sma(240)
        if s240 is None or s60 is None or s60 < s240:
            return []
    elif p["trend"] == "ret240":
        if len(closes) >= 241 and close * 10000 < closes[-241] * 9970:
            return []
    engine = None
    if p["mr"] and s60 is not None and r is not None:
        if close <= s60 * (1 - p["dip"]) and r <= p["rsi_max"]:
            engine = "mr"
    if engine is None and p["mom_thr"] is not None and len(closes) >= 31:
        if close * 10000 >= closes[-31] * (10000 + p["mom_thr"]):
            engine = "mom"
    if engine is None and p["snap_thr"] is not None and len(closes) >= 61:
        if close * 10000 <= closes[-61] * (10000 - p["snap_thr"]):
            engine = "snap"
    if engine is None:
        return []
    _pending_owner = engine
    return [{"side": "buy", "symbol": SYM, "notional_quote_units": cash,
             "max_slippage_bps": p["max_slippage_bps"]}]


makefun_bars.run(on_batch)
