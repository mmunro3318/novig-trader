> ## Documentation Index
> Fetch the complete documentation index at: https://docs.novig.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Tape

> Every execution on a market.

The `trades` channel reports every execution on a market.
It costs 4 tokens per market.
It includes [`lifecycle`](/api/streaming/lifecycle), but not [`book`](/api/streaming/book).

```json snapshot theme={"dark"}
"trades": {
  "seq": 9042,
  "trades": [
    {
      "seq": 9041,
      "deltas": [
        {
          "tradeId": "9b2e4c1a-…",
          "takeId": "5d80e2b7-…",
          "outcomeId": "3f2504e0-…",
          "price": "0.665",
          "qty": 40,
          "ts": 1757894399870
        }
      ]
    },
    {
      "seq": 9042,
      "deltas": [
        {
          "tradeId": "c41d7f08-…",
          "takeId": "a62f0c19-…",
          "outcomeId": "5a1c9e73-…",
          "price": "0.335",
          "qty": 100,
          "ts": 1757894400120
        }
      ]
    }
  ]
}
```

```json delta theme={"dark"}
"trades": {
  "seq": 9043,
  "deltas": [
    {
      "tradeId": "e7a03b5d-…",
      "takeId": "30c9b4e6-…",
      "outcomeId": "3f2504e0-…",
      "price": "0.670",
      "qty": 60,
      "ts": 1757894400456
    }
  ]
}
```

A trade carries its ID, outcome, price, quantity, and engine timestamp.
It doesn't name the orders.

`tradeId` is the `fillId` of the resting order's fill.
If your order rested, match the trade to your fill on that ID.

`takeId` is the `fillId` of the taker's fill.
It matches `tradeId` in `GET /v3/history/trades`, so you can join the stream to trade history.
An order that fills against several resting orders prints one trade for each, all with the same `takeId`.

The snapshot always carries `seq`. It carries recent batches, oldest first, only when you ask.
Set `replay` on `subscribe` or `snapshot` to the number of batches you want, from 0 to 64. It defaults to 0.
The example above asked for `"replay": 2`.

The snapshot isn't a history.
For older trades, call `GET /v3/catalog/markets/{id}/trades`.
For trades across markets or in a time window, call `GET /v3/history/trades`. It lists each trade once, from the taker's side.

## Gaps

* For a small gap, send `snapshot` with `replay` and take the batches after your last `seq`. You don't need to resync.
* For a large gap, [resync](/api/streaming/connection#gaps) as usual.


This documentation is built and hosted on [Mintlify](https://mintlify.com), a developer documentation platform.