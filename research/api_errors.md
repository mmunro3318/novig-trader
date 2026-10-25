> ## Documentation Index
> Fetch the complete documentation index at: https://docs.novig.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Errors

> Every error we return, what causes it, and how to fix it.

## How we check a signed request

We run these checks on each signed request, top to bottom.
The first check that fails decides the error.

signing\_api::verify(request)

`body within cap`

`BodyTooLarge`**413**

`headers present?`

`KeyIdRequired | TimestampRequired | SignatureRequired`**401**

`Uuid::parse(key_id)`

`MalformedKeyId`**401**

`i64::parse(timestamp)`

`MalformedTimestamp`**401**

`|now − ts| ≤ 30 s`

`TimestampTooOld | TimestampTooFarInFuture`**401**

`key row`

`KeyNotFound`**401**

`the read itself`

`DatabaseError`**500**

`live && !expired`

`KeyRevoked | KeyExpired`**401**

`base64::decode(signature)`

`MalformedSignature`**401**

`key.verify(canonical, sig)`

`VerificationFailed`**401**

`scope.grants::<Route>()`

`ScopeInsufficient`**403**

`Principal`the handler runs

Only a request that passes every check reaches the route's handler.

Each rejection is a `SignatureRejection` variant.
The `code` in the response depends only on the status, so branch on the `code`, not on the variant.

| Status | `code` |
| - | - |
| 401 403 | `SIGNATURE_REJECTED` |
| 413 | `PAYLOAD_TOO_LARGE` |
| 500 | `INTERNAL_ERROR` |

* `VerificationFailed` is the only rejection that means your canonical string is wrong.
* A `403` means your signature verified. We check scope last.
* A `500` isn't caused by your request. Retry it unchanged.

## `400` Bad Request

| Message | Fix |
| - | - |
| `You sent the private half of your keypair…` | Send the public key |
| `The publicKey field is not a valid SPKI public key.` | Export it as SPKI |
| `Only Ed25519 and P-256 public keys are accepted…` | Use Ed25519 or P-256 |
| `The algorithm field must match the key type. Expected <a>.` | Match your key |
| `That key does not reach a subaccount.` | Use a `trading` key ID |
| `You can have at most 10 subaccounts.` | Relabel one |
| `You can have at most 128 live management::read keys.` | Revoke one |
| `You can have at most 128 live trading::read keys.` | Revoke one |
| `You already used that transfer id on another subaccount.` | Transfer IDs are unique per trader |

To export a public key as SPKI, run `openssl pkey -pubout` and send the output with its newlines.

Generate an Ed25519 or P-256 keypair, and set `algorithm` to match the key material.

Address a subaccount by one of its `trading` key IDs.

A subaccount is permanent, so relabel an existing one instead of opening another.

A transfer id is unique per trader.

## `401` Unauthorized

| `message` | Fix |
| - | - |
| `novig-key-id header is required` | Send the missing header |
| `novig-key-id is not a valid UUID` | Send the `keyId`, not the label |
| `novig-timestamp is not a valid integer` | Send unpadded decimal digits |
| `novig-timestamp is too old` | Send milliseconds |
| `novig-timestamp is too far in the future` | Check your clock |
| `api key not found` | Check the key ID and host |
| `api key has been revoked` | Create a new key |
| `api key has expired` | Create a new key |
| `novig-signature is malformed` | Send standard padded base64 |
| `signature verification failed` | Sign a test vector |

When `novig-timestamp` or `novig-signature` is missing, the first message names that header instead.

We accept a timestamp within ±30 s of our clock, so check your clock too.

`api key not found` means a wrong key ID, the wrong environment, or a key revoked more than 60 seconds ago.

`api key has been revoked` means you revoked the key less than 60 seconds ago.

For `signature verification failed`, sign a [test vector](/api/signing#test-vectors). Diff your canonical string against its `string_to_sign`.

If you still get a `401`, find your symptom below.

* **A 401 on every call.** A header, the clock, the key, or the canonical string is wrong. Read `message`, then sign a published vector and diff your string against it on [Sign a request](/api/signing).
* **`GET` works, but `POST` fails.** Without `Content-Type: application/json`, the server hashed zero bytes. Send that header on every request with a body.
* **Every `POST` fails, and the body looks right.** Your client re-serialized the JSON after you hashed it. Send the exact bytes you hashed.
* **Every path fails.** You signed the URL, or dropped the mount prefix. Sign the path only, with the mount prefix included.
* **A P-256 signature never verifies.** You sent a raw `r‖s` signature. Send DER instead, as [Algorithms](/api/signing#algorithms) describes.
* **`api key not found`, but the key exists.** You're on the wrong environment, since a key works only in its own. Check the host on [Environments](/api/environments).

## `403` Forbidden

| `message` | Fix |
| - | - |
| `api key scope is insufficient for this route` | Check the key's scope |
| `The account must complete KYC verification before it trades.` | Finish KYC |

A scope error means the key has the wrong family or level. See [scopes](/api/concepts/account-model#scopes).

KYC is our identity check. You need it to create a key, to open or fund a subaccount, or to place an order. Cancels still work without it.

A `trading` or `trading::read` key that names a sibling subaccount gets a `404` `SUBACCOUNT_NOT_FOUND`. To read a sibling, use a key with `management::read`.

## `404` Not Found

We answer `Key not found.`, `Subaccount not found.`, or `Transfer not found.` when we can't find the ID.

An ID that belongs to another trader gets the same reply.

## `409` Conflict

* `A live key with this public key already exists.` A public key is unique across Novig.
* `This trader already has a live management key…` Revoke the live `management` key first.

A declined transfer is not an error.
The route answers `202`, and the transfer then reads `status: "Rejected"`.
See [Funding](/api/subaccounts/funding#check-the-transfer-status).

## `413` Content Too Large

The edge is a filter in front of our servers.
It refuses any body over 8 KiB ({EDGE_BODY_BYTES.toLocaleString("en-US")} bytes) with a 403 and an HTML page, with no JSON error body.
The request never reaches the exchange.
A batch hits this cap first, at about 90 orders.

The exchange buffers each request body before it parses it.
It refuses a body over 100 KiB with a 413 and `PAYLOAD_TOO_LARGE`, before it reads the signature.
Through our edge you'll see the 403 first, since its cap is smaller.

To fix either error, split the batch. Both caps count the raw bytes you send.

## `423` Locked

A `423` doesn't clear on its own. Contact support.

| `code` | Still works |
| - | - |
| `SYSTEM_LOCKED` | The clock and the exchange status |
| `ACCOUNT_LOCKED` | The clock and the exchange status |
| `ACCOUNT_EXCLUDED` | The clock and the exchange status |
| `SELF_EXCLUDED` | Cancels, reads, label, and revoke |
| `EMPLOYEE_ACCOUNT` | Reads |
| `LIQUIDATION_ONLY` | Everything except placing orders |

* `SYSTEM_LOCKED` means the exchange has halted trading. It blocks every trading, catalog, key, and subaccount route, reads included. `GET /v3/exchange/status` still answers, and returns the reason.
* `ACCOUNT_LOCKED` and `ACCOUNT_EXCLUDED` block every trading, catalog, key, and subaccount route, reads included.
* `SELF_EXCLUDED` blocks placing orders, creating a key, opening a subaccount, and moving funds while the key holder is self-excluded.
* `EMPLOYEE_ACCOUNT` blocks placing and canceling when the key belongs to a Novig employee.
* `LIQUIDATION_ONLY` blocks placing orders. Cancels still work.
* When we apply `LIQUIDATION_ONLY` to your account, we cancel your resting orders, then cancel again about 75 seconds later.

To check whether trading is paused, call `GET /v3/exchange/status`.

```json theme={"dark"}
{
  "trading": "PAUSED",
  "reason": "Scheduled maintenance"
}
```

`trading` is `OPEN` or `PAUSED`. While trading is paused, `reason` holds our note on why. It's absent while trading is open.

## `429` Too Many Requests

`RATE_LIMIT_EXCEEDED` means you sent requests too fast.
Wait `Retry-After` seconds before you retry.
See [Throttling](/api/throttling#error-response).

## `451` Geolocation Unavailable

Geolocation is the location check the Novig app runs for the key holder.
A `451` means the request, or the key holder's location, didn't pass it.

| `code` | Cause |
| - | - |
| `ANONYMIZED_NETWORK` | VPN, proxy, or Tor exit |
| `RESTRICTED_NETWORK_REGION` | The request's address is in a restricted state |
| `GEOLOCATION_NOT_FOUND` | The key holder never geolocated |
| `GEOLOCATION_FAILED` | The last geolocation failed |
| `GEOLOCATION_OUT_OF_BOUNDARY` | The device is outside a permitted state |
| `GEOLOCATION_BLOCKED_NETWORK` | The device used a VPN, proxy, or relay |
| `GEOLOCATION_BLOCKED_SOFTWARE` | The device ran remote-desktop or spoofing software |
| `INVALID_GEOLOCATION_REGION` | The last geolocation named no region |
| `RESTRICTED_GEOLOCATION_REGION` | The last geolocation is in a restricted state |
| `GEOLOCATION_EXPIRED` | A placement, with none in the last 3 days |

* `GEOLOCATION_OUT_OF_BOUNDARY`: the key holder's device must be inside a permitted state.
* `GEOLOCATION_BLOCKED_NETWORK`: turn off the VPN, proxy, or iCloud Private Relay on the device, then open the app.
* `GEOLOCATION_BLOCKED_SOFTWARE`: close the remote-desktop or location-spoofing software, then open the app.

`ANONYMIZED_NETWORK` means the request came over a VPN, a proxy, or a Tor exit. A data-center address is fine.

Creating a key, opening a subaccount, and issuing a subaccount key also screen the request's network when you sign in with a session, so each can answer `ANONYMIZED_NETWORK` or `RESTRICTED_NETWORK_REGION`.

The restricted states are Arizona, Michigan, and Nevada.

The first two codes judge the request's network. The rest judge the key holder's device. For those, the key holder must open the app.

A cancel never returns a `451`. A read admits a stale geolocation, so only a placement returns `GEOLOCATION_EXPIRED`.

## Trading and catalog errors

Every trading and catalog error has a `code` and a `message`.
Branch on the `code`. The `message` is for a human, and it can change.

A body that doesn't parse answers `INVALID_BODY`. Its `message` names the field and the reason, like ``qty: invalid value: integer `-1`, expected u32``.

| Status | `code` |
| - | - |
| 400 | `INVALID_BODY` `INVALID_QUERY` `INVALID_REQUEST` `NOT_A_SUBACCOUNT_KEY` |
| 400 | `TTL_NOT_ALLOWED` `TTL_REQUIRED` `TTL_OUT_OF_RANGE` `QTY_OUT_OF_RANGE` |
| 400 | `INVALID_PRICE` `PRICE_BAND_VIOLATION` `ORDER_TOO_SMALL` `ORDER_TOO_LARGE` |
| 400 | `EMPTY_BATCH` `BATCH_TOO_LARGE` `BATCH_REJECTED` `CURRENCY_MISMATCH` |
| 400 | `NOT_LIVE_TRADABLE` `EVENT_NOT_TRADABLE` `PAGE_LIMIT_OUT_OF_RANGE` |
| 400 | `OFFSET_NOT_SUPPORTED` `AFTER_NEEDS_KEY_ID` |
| 400 | `STALE_NONCE` `EMPTY_SELECTION` `SUBSCRIPTION_LIMIT_EXCEEDED` |
| 403 | `SCOPE_INSUFFICIENT` `KYC_REQUIRED` |
| 404 | `MARKET_NOT_FOUND` `EVENT_NOT_FOUND` `OUTCOME_NOT_FOUND` `ORDER_NOT_FOUND` |
| 404 | `WALLET_NOT_FOUND` `SUBACCOUNT_NOT_FOUND` |
| 409 | `MARKET_CLOSED` `MARKET_INACTIVE` |
| 422 | `INSUFFICIENT_BALANCE` `POSITION_LIMIT_EXCEEDED` `OPEN_ORDER_LIMIT_EXCEEDED` |
| 422 | `WAGER_LIMIT_EXCEEDED` |
| 423 | `SYSTEM_LOCKED` `ACCOUNT_LOCKED` `LEAGUE_LOCKED` `COMPETITOR_LOCKED` |
| 423 | `ACCOUNT_EXCLUDED` `SELF_EXCLUDED` `EMPLOYEE_ACCOUNT` |
| 423 | `EVENT_LOCKED` `MARKET_LOCKED` `LIQUIDATION_ONLY` |
| 429 | `RATE_LIMIT_EXCEEDED` |
| 451 | See [`451`](#451-geolocation-unavailable) |
| 503 | `GEOLOCATION_SCREENING_UNAVAILABLE` |
| 500 | `INTERNAL_ERROR` |

* 403 `KYC_REQUIRED` applies to placing only. The key holder's KYC lapsed after the key was created, so finish verification in the app.
* 423 means `SELF_EXCLUDED`, `EMPLOYEE_ACCOUNT`, `LIQUIDATION_ONLY`, or a lock with no `code`. See [`423`](#423-locked).
* A `reject` from the matching engine isn't an HTTP error. It arrives on the [private stream](/api/streaming/private) after the 201.


This documentation is built and hosted on [Mintlify](https://mintlify.com), a developer documentation platform.