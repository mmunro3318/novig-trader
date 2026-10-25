> ## Documentation Index
> Fetch the complete documentation index at: https://docs.novig.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Trading fees

> Takers pay a fee on each fill. Game markets and futures markets have separate schedules.

The taker pays a fee on each fill.
The taker is the side whose order matched a resting order, and the maker is the side whose order was resting.
A maker never pays.

$$
\text{Fee} = c \cdot P\,(1 - P) \cdot N \cdot 1\text{¢}
$$

| Term | Meaning | Field |
| - | - | - |
| $P$ | Price of the fill | `fill.price` |
| $c$ | Fee coefficient | `market.fee.coefficient` |
| $N$ | Contracts in the fill | `fill.qty` |

$P$ is the price the fill executed at, not your limit price.

A winning contract pays full value, 1¢.

The coefficient depends on the market's schedule, below.

## The fee schedules

> [!NOTE]
>
> On Thursday, October 22, 2026, the maker credit will drop from `0.5` to `0.25` on game markets, and from `0.7` to `0.5` on futures markets.
> The taker fee doesn't change.

| Schedule | `coefficient` | `makerCredit` | `charged` |
| - | - | - | - |
| Game market, until Oct 22 | `0.06` | `0.5` | `WHEN_LIVE` |
| Game market, from Oct 22 | `0.06` | `0.25` | `WHEN_LIVE` |
| Futures market, until Oct 22 | `0.06` | `0.7` | `ALWAYS` |
| Futures market, from Oct 22 | `0.06` | `0.5` | `ALWAYS` |

Each market carries its schedule in `fee`:

```json GET /v3/catalog/markets/{id} theme={"dark"}
"fee": {
  "coefficient": "0.06",
  "makerCredit": "0.5",
  "charged": "ALWAYS"
}
```

`WHEN_LIVE` charges the taker only while the event is `OPEN_INGAME`.

`ALWAYS` charges in every phase, because a futures event never goes live.

`makerCredit` is the maker's share of the taker's fee on the same fill.

![Taker fee against execution price for 10,000 contracts: a symmetric arc peaking at \$1.50 on both the game and futures schedules](https://mintcdn.com/novig/H6ansc67CUSqe8sv/images/fee-curve.svg?fit=max\&auto=format\&n=H6ansc67CUSqe8sv\&q=85\&s=1025f0e8889171a3d663efe74ec45dc1)

## Which schedule a market is on

| Market type | League | Schedule | Charges |
| - | - | - | - |
| Game line | any | Game | When live |
| Futures | `NFL` `NCAAF` `MLB` `NBA` `WNBA` `NHL` | Futures | Always |
| Futures | `PGA` `ATP` `WTA` `UFC` `F1` `NASCAR` | Game | Never |
| Series winner | any | Game | Never |

A futures market settles on a season, not a game.

In `PGA`, `ATP`, `WTA`, `UFC`, `F1` and `NASCAR`, a futures market carries no futures fee.
Its event never goes live, so it charges nothing.

Read `fee` from the market. Never work it out from this table.

## Worked examples

Each fill below is a number of contracts at a price.

Both schedules charge the same coefficient, so a fill costs the taker the same on either.

| Fill | Taker fee |
| - | - |
| 10 000 @ 0.50 | \$1.5000 |
| 10 000 @ 0.30 or 0.70 | \$1.2600 |
| 10 000 @ 0.10 | \$0.5400 |
| 100 @ 0.50 | \$0.0150 |

From October 22, the maker on the other side of the first fill earns a \$0.3750 credit on the game schedule.
On the futures schedule, it earns \$0.7500.

> [!WARNING]
>
> We decide whether an event is live at match time. A `WHEN_LIVE` market charges fills on the live side of a `GOLIVE`, not the pregame side.

Every `GOLIVE` voids every resting order, and the live window can open more than once.
See [Event lifecycle](/api/concepts/event-lifecycle#event-states).

## Where to read fees

* `GET /v3/catalog/markets/{id}` returns `fee`: the coefficient, the credit, and when it charges.
* `GET /v3/portfolio/fills` returns `fee` on every charged fill, and leaves it out otherwise.
* `GET /v3/account/subaccounts/{keyId}/transactions` returns the ledger rows behind a fee.
* The private stream's `fill` event carries no fee.

A fee rounds half up to the millicent, the same way as a balance.
See [Monetary representations](/api/concepts/money).


This documentation is built and hosted on [Mintlify](https://mintlify.com), a developer documentation platform.