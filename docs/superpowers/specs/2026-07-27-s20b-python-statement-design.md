# S20b-c Python Statement Design

## Goal

Prove that the managed Python second house can publish a secret-free financial statement that a stranger can open and independently compare with Base, Solana, and Polymarket public data.

S20b-c is complete only when one paid BlockRun Modal sandbox:

1. collects the public values itself without wallet credentials;
2. serves allowlisted HTML, JSON, and heartbeat evidence;
3. exposes those routes through a temporary public URL;
4. remains reachable long enough for an outside process to fetch every route; and
5. reports values equal to fresh independent RPC/API reads.

The proof is temporary. It does not claim that BlockRun exposes an inbound port or that a Cloudflare Quick Tunnel is production hosting.

## Constraints and sources

- BlockRun's public beta accepts only managed Python 3.11, runs for at most 300 seconds, and documents only create, exec, status, and terminate. Its create request has no port or tunnel parameter.  
  Source: [BlockRun Modal Sandbox](https://github.com/BlockRunAI/awesome-blockrun/blob/main/docs/api-reference/modal-sandbox.md)  
  Quote: “Managed Python 3.11 sandbox” and “5 minute sandbox lifetime.”
- A Cloudflare Quick Tunnel can expose a localhost server at a random public URL without an account, but it has no SLA and is for testing and development.  
  Source: [Cloudflare Quick Tunnels](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/do-more-with-tunnels/trycloudflare/)  
  Quote: “Requests to that subdomain will be proxied through the Cloudflare network to your web server running on localhost.”
- Python documents `http.server` as a basic server that is not recommended for production. This use is therefore GET-only, five-minute proof infrastructure, not a deployment architecture.  
  Source: [Python `http.server`](https://docs.python.org/3/library/http.server.html)  
  Quote: “`http.server` is not recommended for production. It only implements basic security checks.”
- The public tunnel binary is pinned to the official Cloudflare GitHub release `2026.7.3`, Linux amd64 SHA-256 `9d71c677db00134c1bd4144b7783486b654ad281b1ea62b4972098d19f770f17`.

## Selected architecture

### Python statement runtime

`skills/self/shelter/python/statement.py` owns all statement behavior:

- public Base USDC balance via Base JSON-RPC `eth_call`;
- public Solana SOL balance via `getBalance`;
- public NOS balance via `getTokenAccountsByOwner`;
- public Polymarket positions via `data-api.polymarket.com/positions`;
- recursive allowlisting into one immutable public snapshot;
- escaped HTML rendering;
- GET-only routes; and
- detached launch of the local server and Quick Tunnel.

The runtime accepts only public addresses:

| Rail | Address |
|---|---|
| Base payer | `0x810f6d61f7606deee2657d3083e150a222bc29c5` |
| Solana shelter payer | `71FfqFniYoMsWZb1qFeQDb1fk2xqvajzivpsnMb44gTf` |
| Polymarket proxy | `0x904B50d2e214Da947d83D6a2D32c4E3Ffc17Eb74` |

No seed, private key, API key, cookie, Telegram credential, or wallet file is accepted by the Python CLI.

### Public schema

Only these top-level fields may be emitted:

```text
v
generatedAt
sandboxId
wallets
balances
polymarket
economy
heartbeats
```

Nested allowlists are exact:

```text
wallets: base, solana, polymarket
balances: baseUsdc, solanaSol, solanaNos
polymarket: positionCount, currentValueUsd, cashPnlUsd, redeemableCount
economy: externalRevenueUsd, runtimeCostUsd, verdict
heartbeats: claimed, verified
```

`cashPnlUsd` is presented as Polymarket's public position field, not as net profit. It is not added to `externalRevenueUsd`; 13c-PM remains responsible for separating deployed capital, recovered capital, fees, and realized PnL in the ledger.

The statement must print external revenue `$0.00` until an externally attributable ledger row exists. A self-payment or marked position value is not external revenue.

### Routes

| Route | Response |
|---|---|
| `/` | Escaped, self-contained HTML statement |
| `/statement.json` | Compact allowlisted JSON snapshot |
| `/heartbeats` | Canonical JSONL heartbeat evidence generated in the same sandbox |
| anything else | `404` |

Only `GET` and `HEAD` are supported. Directory listing, file serving, upload, forms, scripts, and POST are absent.

### Modal adapter

`skills/self/shelter/python/modal-statement.mjs`:

1. packages only public Python source into command arguments shorter than BlockRun's observed 2,000-character limit;
2. downloads the pinned `cloudflared` binary and verifies its SHA-256 before execution;
3. creates one capped 300-second Python sandbox;
4. runs one paid exec that starts the statement server and tunnel as detached processes;
5. extracts exactly one `https://*.trycloudflare.com` URL from stdout;
6. fetches `/`, `/statement.json`, and `/heartbeats` from outside the sandbox;
7. rejects missing routes, non-HTTPS URLs, unexpected hosts, secret-shaped field names, schema drift, or sandbox-ID mismatch; and
8. compares the published numeric values with separately fetched public data.

The adapter may tolerate only normal observation drift:

- Base USDC, Solana SOL, and NOS must match exactly at their native precision because no task action mutates them during verification.
- Polymarket position values must match the independent API snapshot within `$0.01`, because market prices can change between reads.

## Failure behavior

The proof fails closed when:

- any public data source is unavailable or malformed;
- any required numeric value is negative or non-finite;
- a field outside the allowlist reaches JSON or HTML;
- the tunnel binary hash differs;
- the tunnel URL is not HTTPS on `trycloudflare.com`;
- fewer than two valid heartbeat rows are served;
- a heartbeat names another sandbox or fails the existing JavaScript verifier;
- any route is unreachable; or
- independent public values disagree beyond the defined tolerance.

The safe CLI result may include sandbox ID, URL, public statement, verifier result, HTTP status, and bounded stderr. It must never include the payment key or packaged command.

## Tests

Python unit tests cover:

- Base, Solana, NOS, and Polymarket response parsing;
- malformed and missing public data;
- exact recursive allowlisting;
- HTML escaping and explicit `$0.00` external revenue;
- route behavior and content types;
- no file-system access or directory listing; and
- detached-launch output parsing with injected subprocesses.

Node tests cover:

- 2,000-character command elements;
- pinned binary URL and SHA;
- absence of caller key material in the command;
- strict tunnel URL parsing;
- public schema and secret-name rejection;
- heartbeat verification through the existing JavaScript verifier;
- exact/tolerant public-value comparison; and
- a mocked paid create/exec/fetch lifecycle.

The live exit proof records:

- sandbox ID and temporary public URL;
- fetched HTML, JSON, and heartbeat evidence;
- independent Base/Solana/Polymarket snapshots;
- comparison verdict;
- provider spend; and
- the explicit limitation that the URL expires with the five-minute sandbox and Quick Tunnel has no SLA.

