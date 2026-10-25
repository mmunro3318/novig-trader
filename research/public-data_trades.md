> ## Documentation Index
> Fetch the complete documentation index at: https://docs.novig.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Trades

> Every executed trade, one row per side

### Each row is one side of a trade

Every trade appears once per side.
It has one `TAKER` row, for the order or quote request that executed the trade, and one `MAKER` row for each counterparty.

```csv trades.csv theme={"dark"}
timestamp,outcomeId,marketId,contractSeries,league,marketType,tradeType,legs,cost,qty,side
2026-08-04T17:03:11Z,0b1c…,7f2e…,Basketball Moneyline,NBA,MONEY,STRAIGHT,1,45.5,100,TAKER
2026-08-04T17:03:11Z,44d9…,7f2e…,Basketball Moneyline,NBA,MONEY,STRAIGHT,1,54.5,100,MAKER
2026-08-04T18:41:52Z,9d8c…,9d8c…,Parlay,,,COMBO,3,50,200,TAKER
2026-08-04T18:41:52Z,9d8c…,9d8c…,Parlay,,,COMBO,3,150,200,MAKER
```

> [!TIP]
>
> **Working with the data:**
>
> * To count trades, count the `TAKER` rows.
> * The price one side paid is `cost / qty`, a probability between 0 and 1.
> * The total amount staked is the sum of `cost` over all rows.
> * Notional volume in dollars is the sum of `qty` over the `TAKER` rows.

### Columns

**timestamp** `timestamp`

The execution time, in ISO-8601 (UTC).

**outcomeId** `string`

The outcome that traded.
For a `COMBO`, it's the contract the combination cleared against, which is unique to that trade.
So you can't use it to group two trades of the same legs.

**marketId** `string`

The market of the trade.
For a `COMBO`, it's the same value as `outcomeId`.

**contractSeries** `string`

The product group: a sport and a family, like `Basketball Moneyline`.
Multi-leg trades read `Parlay`, and an unrecognized sport or family reads `Other`.
Group by this column to total volume per product.

**league** `string`

The league the contract is listed under, like `NBA`.
It's empty for a `COMBO`.

**marketType** `string`

The market type the contract is listed under, like `MONEY`.
It's empty for a `COMBO`.

**tradeType** `STRAIGHT | COMBO`

`STRAIGHT` is a single-outcome trade matched on the order book.
`COMBO` is a trade on a combination of outcomes, filled against a requested quote.

**legs** `integer`

The number of outcomes the contract combines.
Every `STRAIGHT` trade has `1`.

**cost** `string`

The dollars this side staked.
Together, the two sides of a trade stake its notional value.

**qty** `string`

The quantity in contracts, where one contract pays \$1.
It can be a fraction.

**side** `TAKER | MAKER`

The side of the trade this row reports.

> [!NOTE]
>
> `cost` and `qty` are strings with full numeric precision and no trailing zeros.
> **Fees are not included** in `cost` on either side.


This documentation is built and hosted on [Mintlify](https://mintlify.com), a developer documentation platform.