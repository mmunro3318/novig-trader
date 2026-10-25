> ## Documentation Index
> Fetch the complete documentation index at: https://docs.novig.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Book

> Every order-book change on a market.

The `book` channel reports every change to a market's order book.
It costs 16 tokens per market and includes [`lifecycle`](/api/streaming/lifecycle).

Each outcome has its own ladder, a list of resting orders by price.
The two ladders show one market from opposite ends.

A bid resting at `0.665` on one outcome is liquidity for the other outcome.
A taker on the other outcome trades against it at `0.335`.
A taker is an order that trades against a resting order.

Kansas City Chiefs*3f2504e0…01***0.670***250***0.665***110***0.660***250*

Buffalo Bills*3f2504e0…02***0.340***90***0.335***180***0.325***400*

Each outcome's array lists the best price first.
Within a price, it lists the earlier order first.
The array order **is** the queue.

## Snapshot

```json theme={"dark"}
"book": {
  "seq": 48120,
  "orders": {
    "3f2504e0-…": [
      {
        "order": "7c9e6679-…",
        "price": "0.665",
        "qty": 110
      },
      {
        "order": "1b4e28ba-…",
        "price": "0.660",
        "qty": 250
      }
    ],
    "5a1c9e73-…": [
      {
        "order": "6ba7b810-…",
        "price": "0.340",
        "qty": 90
      }
    ]
  }
}
```

Each key in `orders` is an outcome ID.

## Delta

```json theme={"dark"}
"book": {
  "seq": 48121,
  "deltas": [
    {
      "kind": "add",
      "order": "aa0e8400-…",
      "outcome": "3f2504e0-…",
      "price": "0.670",
      "qty": 250
    },
    {
      "kind": "remove",
      "order": "7c9e6679-…",
      "reason": "fill"
    }
  ]
}
```

| `kind` | `reason` | Means |
| - | - | - |
| `add` | — | Joins the back of its price level |
| `remove` | `fill` | A trade |
| `remove` | `cancel` | Not a trade |

Only `book` reports a cancel.

A partial fill arrives as a `remove`, then an `add` of the remainder.
The `add` keeps the same price and queue position.

## Go-live and your own orders

* At go-live, you get a `remove` with `reason: "cancel"` for each resting order, then `GOLIVE`. See [Event states](/api/concepts/event-lifecycle#event-states).
* Your own orders appear here like any other order. Match them on the [private stream](/api/streaming/private).


This documentation is built and hosted on [Mintlify](https://mintlify.com), a developer documentation platform.