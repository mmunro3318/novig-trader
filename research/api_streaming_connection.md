> ## Documentation Index
> Fetch the complete documentation index at: https://docs.novig.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Connection

> The connection that carries every channel: verbs, nonces, seq, and gaps.

Every channel runs over one websocket connection.

| Detail | Value |
| - | - |
| Route | `GET /v3/ws` |
| Key | `trading` or `trading::read` |
| Throttle | [`stream`](/api/throttling) |
| Cost | `32 /request`, then `weight /pair` |
| Reply | 101 |

## Verbs

You send a verb to tell us what to do on the connection.

| Verb | Does | Reply |
| - | - | - |
| `subscribe` | Sets a channel per subject | Snapshot |
| `unsubscribe` | Drops subjects | Ack |
| `snapshot` | Returns state and `seq` | Snapshot |
| `status` | Lists your subscriptions | Ack |
| `query_markets` | Pages open markets | Ack |
| `query_events` | Pages open events | Ack |
| `place` | Books a batch of orders | Ack |
| `cancel` | Cancels orders by id | Ack |
| `cancel_all` | Cancels your resting orders by scope | Ack |

`subscribe` also adds channels to `private`.

`snapshot` returns the current state and its `seq`, and leaves your subscriptions unchanged.

`query_markets` returns one page of open markets, filtered the same way as `GET /v3/catalog/markets`.
`query_events` returns one page of open events, filtered the same way as `GET /v3/catalog/events`.
Both debit the `read` throttle.

## Choose what to subscribe to

`subscribe` and `snapshot` name a selection in three optional fields.
An empty selection gets `EMPTY_SELECTION`.

```json theme={"dark"}
{
  "nonce": 1,
  "subscribe": {
    "markets": {
      "6f9619ff-…": "book"
    },
    "events": {
      "110e8400-…": "lifecycle"
    },
    "private": ["orders", "positions"]
  }
}
```

| Field | Takes | Covers |
| - | - | - |
| `markets` | ID → channel | One market |
| `events` | ID → channel | Every market of the event |
| `private` | A list of channels | Your own orders and positions |

An `events` selection also covers markets that open later.

`unsubscribe` takes a list of subject strings instead.

```json theme={"dark"}
{
  "nonce": 9,
  "unsubscribe": [
    "market:6f9619ff-…",
    "event:110e8400-…",
    "PRIVATE"
  ]
}
```

`PRIVATE` drops every private channel.
To drop just one, unsubscribe `PRIVATE`, then subscribe to the channel you keep.

## Trade

Three verbs place and cancel orders over the connection. They need a `trading` key; a `trading::read` key gets `SCOPE_INSUFFICIENT`. Payloads match the REST [orders](/api/execution/orders) bodies, and they debit the `place` and `cancel` throttles, not `stream`.

`place` books a batch of orders, all or none, for 1 `place` token each. The ack is `placed`, one entry per accepted order.

```json theme={"dark"}
{
  "nonce": 17,
  "place": { "orders": [{ "outcomeId": "6f9619ff-…", "price": "0.54", "qty": 10, "tif": "GTC" }] }
}
```

`cancel` cancels orders by id, 1 `cancel` token each. It is partial: an unknown id does not stop the rest. The ack is `canceled`, naming the ids that canceled and those that did not.

```json theme={"dark"}
{
  "nonce": 18,
  "cancel": { "orderIds": ["6f9619ff-…"] }
}
```

`cancel_all` cancels your resting orders for 1 `cancel` token, narrowed by `market`, `event`, or `outcome`. An empty filter cancels them all. The ack is `canceled_all`, the count queued.

```json theme={"dark"}
{
  "nonce": 19,
  "cancel_all": { "market": "6f9619ff-…" }
}
```

An ack is our intent, not the fill. An order's fills and final state arrive on the `orders` channel, so subscribe `private` to see them.

## Channels and cost

| Channel | Cost | Includes | Named in |
| - | - | - | - |
| `lifecycle` | `1 /pair` | — | `markets` `events` |
| `trades` | `4 /pair` | `lifecycle` | `markets` `events` |
| `bbo` | `8 /pair` | `lifecycle` | `markets` `events` |
| `book` | `16 /pair` | `lifecycle` | `markets` `events` |
| `orders` | `1 /pair` | — | `private` |
| `positions` | `1 /pair` | — | `private` |

A pair is one subject on one channel.
An event counts one pair for each market it holds, and at least one.
A subscribe to 100 markets on `book` weighs ` /request`, whether you name the markets or their event.

We charge at most the `stream` capacity of 512 tokens.
A request above that cap passes only when the throttle is full, and it empties the throttle.

* `snapshot` costs the same as `subscribe`.
* `unsubscribe` costs 1 token per subject.
* `status` costs 1 token.
* A subject we can't resolve still costs tokens.

## Nonces

A nonce is the number you put on each request.

* Start nonces at 1.
* Send them in increasing order within a connection. Gaps are allowed.
* The largest nonce is $2^{53}-1$.

We answer a repeated or lower nonce with `STALE_NONCE`.

A frame that fails to parse or hits the throttle gets a reply with no nonce.
That frame leaves your newest nonce unchanged.

## Each subscription starts with a snapshot

A snapshot is the current state of what you subscribed to.
Deltas, the changes after it, follow.

We number the messages on each market channel **per market**, and on `orders` and `positions` **per subaccount**.
That number is `seq`.

The snapshot carries the `seq` at which we took it.
The first delta carries the next `seq`, with no gap.

Changes that happen together arrive in one message.
Apply each batch atomically.

```json snapshot theme={"dark"}
{
  "ts": 1757894400123,
  "nonce": 1,
  "subscribed": {
    "markets": {
      "6f9619ff-…": "book"
    },
    "events": {},
    "private": []
  },
  "snapshot": {
    "6f9619ff-…": {
      "eventId": "110e8400-…",
      "book": {
        "seq": 48120,
        "orders": {}
      },
      "lifecycle": {
        "seq": 3,
        "status": "OPEN"
      }
    }
  }
}
```

```json delta theme={"dark"}
{
  "ts": 1757894400456,
  "delta": {
    "6f9619ff-…": {
      "eventId": "110e8400-…",
      "book": {
        "seq": 48121,
        "deltas": []
      }
    }
  }
}
```

## Compression

Set `X-Novig-WS-Compress: deflate` on the upgrade request to receive compressed messages.

Every message then — snapshots, deltas, and acks — arrives as one binary frame of raw DEFLATE data ([RFC 1951](https://www.rfc-editor.org/rfc/rfc1951)). Inflate each frame on its own, then parse the JSON.

## Gaps

A gap is a skipped `seq`. It means you missed a message.

Gap recovery. The exchange sends delta seq 48122. The next delta to arrive is 48124, so 48123 is missing, and the client buffers 48124. The client sends snapshot for the market on book. The exchange replies with a snapshot at seq 48125. The client drops buffered deltas at or below 48125 and replays the rest.

Arrows are messages, top to bottom in time. After the new snapshot, drop the buffered deltas it already covers.

* A market `seq` is per market, per channel. There's no global sequence.
* A private `seq` is per subaccount, per channel. It's independent of every market `seq`.
* To recover from a gap, send `snapshot`. It leaves your subscriptions unchanged.
* After a reconnect, subscribe again. The reply carries the snapshot.
* Never compare a `seq` across connections.

A market that opens under an `events` subscription arrives with no snapshot. That's not a gap.
Its first delta is `OPEN`, and its `book`, `bbo`, and `trades` channels start at seq 0, so each one's first delta carries seq 1.

## Why a connection closes

| Code | Reason | Do |
| - | - | - |
| `1008` | `SLOW_CONSUMER` | Reconnect and subscribe again |
| `1008` | A `451` geolocation `code` | Open the app, then reconnect |
| none | — | Answer every Ping |

* `SLOW_CONSUMER` means a write to you stalled for 15 s.
* A geolocation close means the companion check refused you while you were connected: your last device geolocation is missing, failed, named no region, or came from a restricted state. The reason is the [`451` code](/api/errors#451-geolocation-unavailable), such as `GEOLOCATION_OUT_OF_BOUNDARY`, `GEOLOCATION_BLOCKED_NETWORK`, or `GEOLOCATION_BLOCKED_SOFTWARE`. A stale geolocation never closes a socket.
* If you send no Pong between two of our Pings, we drop the connection without a close frame. Your client usually reports `1006`. We ping every 15 s.


This documentation is built and hosted on [Mintlify](https://mintlify.com), a developer documentation platform.