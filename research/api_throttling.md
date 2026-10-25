> ## Documentation Index
> Fetch the complete documentation index at: https://docs.novig.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Throttling

> How we limit your request rate, and how to pace your requests.

We limit how fast you can send requests, in two places.
Our servers throttle each API key, and an edge filter in front of them limits each IP address.

## Limits on our servers

Each throttle is a bucket of tokens.
A request spends tokens from its bucket.
The bucket holds up to its capacity, which is your burst, and refills at its refill rate, in tokens per second.

Throttle
Burst
Capacity
Refill

`place`

{PLACE_CAPACITY.toLocaleString("en-US")}

8 Hz

`cancel`

{CANCEL_CAPACITY.toLocaleString("en-US")}

16 Hz

`read`

{READ_CAPACITY.toLocaleString("en-US")}

16 Hz

`account`

{ACCOUNT_CAPACITY.toLocaleString("en-US")}

8 Hz

`stream`

{STREAM_CAPACITY.toLocaleString("en-US")}

32 Hz

`history`

{HISTORY_CAPACITY.toLocaleString("en-US")}

4 Hz

The `history` bucket meters the record reads: fills, transactions, settled orders, and the history routes. Each such read costs a base plus one token per page of rows, so a larger page spends more. `GET /v3/limits` reports every bucket's numbers.

`GET /v3/limits`, `GET /v3/time`, and `GET /v3/exchange/status` spend no tokens.

## Websocket subscriptions

The `stream` bucket meters how fast you subscribe. A second limit caps how much you hold: a connection may watch up to  markets at once. An event counts as the markets it contains. A subscribe that would take you over that answers `SUBSCRIPTION_LIMIT_EXCEEDED`, and it subscribes to nothing. A `snapshot` that names more markets than the cap answers the same. Such a request also costs more than the `stream` bucket holds, so you get `RATE_LIMIT_EXCEEDED` until the bucket is full. `GET /v3/limits` reports the cap.

The key routes and the subaccount routes spend the `account` bucket, one token a request. A transfer spends from it too.

## Limits at the edge

The edge is a filter in front of our servers.
It checks every request on every route before the request reaches them.

| Check | Limit | Counted per |
| - | - | - |
| Request rate | {EDGE_REQUESTS_PER_MINUTE.toLocaleString("en-US")} a minute | IP address |
| Body size | 8 KiB | Request |

> [!WARNING]
>
> The edge refuses a request with a `403` and an HTML body, with no `code` and no `message`. The request never reaches our servers.

## Pace your requests

A throttle refills over time, up to its capacity:

$$
\text{tokens}(t + \Delta t) = \min\bigl(C,\; \text{tokens}(t) + r\,\Delta t\bigr)
$$

Here $C$ is the capacity, $r$ is the refill rate, and $\Delta t$ is the time that has passed.

1. Model each throttle in your client.
2. When you send a request, subtract its cost from your model.
3. While your model holds too few tokens, queue the request instead of sending it.

## Error response

When you go over a limit, we answer `429` with a `Retry-After` header:

```http theme={"dark"}
HTTP/1.1 429 Too Many Requests
Retry-After: 3

{
  "code": "RATE_LIMIT_EXCEEDED",
  "message": "Rate limit exceeded. Please wait before retrying."
}
```

* Wait `Retry-After` seconds before you retry. Retrying sooner hits the same empty throttle.
* Split your work across keys. The throttle counts per key, not per connection.
* Handle a `429` even if you model the throttles. Our servers share token counts with each other gradually, so your model is never exact.


This documentation is built and hosted on [Mintlify](https://mintlify.com), a developer documentation platform.