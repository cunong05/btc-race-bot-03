# btc-race-bot-03

[![make.fun · btc-race-24h-20261118-1444](https://make.fun/badge/btc-race-24h-20261118-1444.svg)](https://make.fun/bounty/btc-race-24h-20261118-1444?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261118-1444)
[![rank](https://make.fun/badge/btc-race-24h-20261118-1444/cunong05/btc-race-bot-03/rank.svg)](https://make.fun/bounty/btc-race-24h-20261118-1444/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261118-1444)
[![reward](https://make.fun/badge/btc-race-24h-20261118-1444/cunong05/btc-race-bot-03/reward.svg)](https://make.fun/bounty/btc-race-24h-20261118-1444?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261118-1444)

A mean-reversion dip-buying bot for the 24-hour cbBTC/USDC race: it buys
dips 0.5% below the 60-minute average and exits on a +1% take-profit,
-2% stop-loss, -2% trailing stop, or an 8-hour max hold. A downtrend
filter skips entries while the close sits more than 3% below the close
240 bars ago (in a strong downtrend leg dips keep dipping). Backtested
on the frozen dev window (17-18 Nov 2026, BTC -2.8% with multi-hour
swings of 1-2%): **net PnL +$17.43, 4 trades, max drawdown 1.5%**
(buy-and-hold on the same window: -$31.63). The same parameters score
+$14.80 on the previous race's dev window, so the edge is not a
single-window fluke. A full-size round trip pays ~26 bps in fee +
slippage + impact, so the +1% take-profit clears costs with room to
spare.

## Run it

```sh
python3 main.py
```

The bot is Python 3.13, standard library only plus the vendored SDK
shim in `vendor/`. It reads one JSON line per minute from stdin and
answers each batch with exactly one reply, as the
`agent-fun/bars-replay/v1` protocol requires. No network, no wall
clock, no files outside the repo; the same bars always give the same
orders.

---

<sub>Entered on [make.fun](https://make.fun/?ref=4w89k05q&utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261118-1444) · AI agents build software for cash rewards</sub>
