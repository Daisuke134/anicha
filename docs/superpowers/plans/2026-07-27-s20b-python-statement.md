# S20b-c Python Statement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish a secret-free financial statement from one paid managed Python sandbox and prove its Base, Solana, and Polymarket values against independent public reads.

**Architecture:** A Python module collects public balances and positions, applies recursive allowlists, renders three GET-only routes, and detaches a five-minute local server plus a Cloudflare Quick Tunnel. A Node adapter packages only public source through BlockRun's paid create/exec path, fetches the public routes from outside the sandbox, verifies heartbeat signatures with the existing JavaScript verifier, and independently re-reads every financial source.

**Tech Stack:** Python 3.11 standard library, PyNaCl 1.6.2, base58 2.1.1, Node 20+, BlockRun Modal x402 adapter, Cloudflare `cloudflared` 2026.7.3, Base JSON-RPC, Solana JSON-RPC, Polymarket Data API.

## Global Constraints

- Implement only S20b-c. Keep 13c-PM, REDEEM-1, AE-X4, S21, and later tasks out of scope.
- Use public addresses only. No private key, seed, API key, cookie, Telegram credential, or wallet file may cross the sandbox command boundary.
- BlockRun command array elements must be at most 2,000 characters.
- Sandbox lifetime is at most 300 seconds; the public URL is temporary evidence, not production hosting.
- Public output is allowlist-only. Do not add a blacklist or secret scrubber.
- `cashPnlUsd` is a Polymarket public position field, not net profit and not external revenue.
- External revenue remains `$0.00` until a provenance-backed outside ledger row exists.
- Cloudflare Quick Tunnel is proof infrastructure only. Pin `cloudflared` 2026.7.3 Linux amd64 SHA-256 `9d71c677db00134c1bd4144b7783486b654ad281b1ea62b4972098d19f770f17`.
- Sources: BlockRun public Modal API (`https://github.com/BlockRunAI/awesome-blockrun/blob/main/docs/api-reference/modal-sandbox.md`), Cloudflare Quick Tunnels (`https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/do-more-with-tunnels/trycloudflare/`), Python `http.server` warning (`https://docs.python.org/3/library/http.server.html`).

---

### Task 1: Public financial snapshot and recursive allowlist

**Files:**
- Create: `skills/self/shelter/python/statement.py`
- Create: `skills/self/shelter/python/test_statement.py`

**Interfaces:**
- Consumes: public Base, Solana, and Polymarket addresses plus an injectable JSON HTTP transport.
- Produces: `fetch_base_usdc(address, request_json=...) -> float`
- Produces: `fetch_solana_balances(address, request_json=...) -> dict[str, float]`
- Produces: `fetch_polymarket(address, request_json=...) -> dict[str, int | float]`
- Produces: `build_public_statement(*, sandbox_id, base_address, solana_address, polymarket_address, request_json=..., heartbeats=[]) -> dict`
- Produces: `render_statement_html(statement) -> str`

- [ ] **Step 1: Write failing parser and allowlist tests**

Add fixtures shaped like the live public APIs and assert exact output:

```python
BASE_RESULT = {"result": "0x1c1768"}
SOL_RESULT = {"result": {"value": 26094157}}
NOS_RESULT = {
    "result": {"value": [{
        "account": {"data": {"parsed": {"info": {"tokenAmount": {
            "amount": "500000", "decimals": 6
        }}}}}
    }]}
}
PM_RESULT = [
    {"currentValue": 6.376, "cashPnl": 0.8375, "redeemable": False},
    {"currentValue": 1.6191, "cashPnl": 0.2791, "redeemable": False},
]

def test_public_snapshot_is_exact_and_allowlisted():
    statement = build_public_statement(
        sandbox_id="sb-test",
        base_address=BASE_ADDRESS,
        solana_address=SOLANA_ADDRESS,
        polymarket_address=PM_ADDRESS,
        request_json=fake_transport,
        heartbeats=[{"verified": True}, {"verified": True}],
    )
    assert statement["balances"] == {
        "baseUsdc": 1.841,
        "solanaSol": 0.026094157,
        "solanaNos": 0.5,
    }
    assert statement["polymarket"] == {
        "positionCount": 2,
        "currentValueUsd": 7.9951,
        "cashPnlUsd": 1.1166,
        "redeemableCount": 0,
    }
    assert statement["economy"] == {
        "externalRevenueUsd": 0.0,
        "runtimeCostUsd": 0.015,
        "verdict": "funded",
    }
```

Also assert:

- unknown top-level and nested source fields cannot appear;
- a negative, boolean, NaN, missing, or malformed numeric response raises `ValueError`;
- a hostile address/title is HTML escaped;
- the page contains `$0.00 from outside`;
- PM marked value and `cashPnlUsd` are not added to external revenue; and
- rendered output contains no scripts, forms, or directory paths.

- [ ] **Step 2: Run the tests to verify RED**

Run:

```bash
.venv/bin/python -m unittest skills/self/shelter/python/test_statement.py
```

Expected: FAIL with `ModuleNotFoundError: No module named 'statement'`.

- [ ] **Step 3: Implement strict public parsers**

In `statement.py`, define exact constants:

```python
BASE_RPC_URL = "https://mainnet.base.org"
SOLANA_RPC_URL = "https://api.mainnet-beta.solana.com"
POLYMARKET_POSITIONS_URL = "https://data-api.polymarket.com/positions"
BASE_USDC_ADDRESS = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
NOS_MINT = "nosXBVoaCTtYdLvKY6Csb4AC8JCdQKKAaWYtx2ZMoo7"
RUNTIME_COST_USD = 0.015
```

Implement one standard-library JSON transport with 15-second timeout. Base uses `eth_call` with selector `0x70a08231`; Solana uses `getBalance` and `getTokenAccountsByOwner`; Polymarket uses the positions endpoint with URL-encoded `user`.

Reject booleans, non-finite values, negative values, missing response paths, and malformed lists. Sum integer native units before applying decimals.

- [ ] **Step 4: Implement recursive allowlisting and HTML**

Define exact field tuples:

```python
PUBLIC_TOP = ("v", "generatedAt", "sandboxId", "wallets", "balances",
              "polymarket", "economy", "heartbeats")
PUBLIC_NESTED = {
    "wallets": ("base", "solana", "polymarket"),
    "balances": ("baseUsdc", "solanaSol", "solanaNos"),
    "polymarket": ("positionCount", "currentValueUsd", "cashPnlUsd", "redeemableCount"),
    "economy": ("externalRevenueUsd", "runtimeCostUsd", "verdict"),
    "heartbeats": ("claimed", "verified"),
}
```

Build the statement from internally created values only. Render with `html.escape`, no interpolation of undeclared facts, no JavaScript, and explicit labels distinguishing marked position values from net earnings.

- [ ] **Step 5: Run focused and Python regression tests**

Run:

```bash
.venv/bin/python -m unittest skills/self/shelter/python/test_statement.py
.venv/bin/python -m unittest discover -s skills/self/shelter/python -p 'test_*.py'
```

Expected: statement tests PASS; full Python suite reports 0 failures.

- [ ] **Step 6: Commit and push**

```bash
git add skills/self/shelter/python/statement.py skills/self/shelter/python/test_statement.py
git commit -m "feat(shelter): build allowlisted Python statement"
git push
```

---

### Task 2: GET-only server and detached Quick Tunnel launcher

**Files:**
- Modify: `skills/self/shelter/python/statement.py`
- Modify: `skills/self/shelter/python/test_statement.py`

**Interfaces:**
- Consumes: one allowlisted statement dict, canonical heartbeat rows, port, and pinned `cloudflared` path.
- Produces: `make_statement_handler(statement, heartbeat_jsonl) -> type[BaseHTTPRequestHandler]`
- Produces: `serve_statement(*, statement_file, heartbeats_file, port) -> None`
- Produces: `launch_public_statement(*, cloudflared_path, port, addresses, popen=..., sleep=..., read_text=...) -> dict`
- CLI: `statement.py launch --cloudflared PATH --port 8080` prints one compact public control JSON object.

- [ ] **Step 1: Write failing route and launch tests**

Start `ThreadingHTTPServer(("127.0.0.1", 0), handler)` in a test thread and assert:

```python
assert GET("/").status == 200
assert GET("/").headers["Content-Type"].startswith("text/html")
assert json.loads(GET("/statement.json").body)["sandboxId"] == "sb-test"
assert GET("/heartbeats").body.count(b"\n") == 2
assert GET("/missing").status == 404
assert POST("/").status == 501
```

With injected `popen`, `read_text`, and `sleep`, assert the launcher:

- starts `serve` bound to `127.0.0.1`;
- starts `cloudflared tunnel --no-autoupdate --url http://127.0.0.1:8080`;
- uses `start_new_session=True`;
- extracts only `https://<random>.trycloudflare.com`;
- rejects HTTP, another host, multiple URLs, early child exit, and timeout; and
- never includes a secret-bearing environment variable in subprocess arguments.

- [ ] **Step 2: Run the route tests to verify RED**

Run:

```bash
.venv/bin/python -m unittest skills/self/shelter/python/test_statement.py
```

Expected: FAIL because `make_statement_handler` and `launch_public_statement` do not exist.

- [ ] **Step 3: Implement GET-only routes**

Use `BaseHTTPRequestHandler`, not `SimpleHTTPRequestHandler`, so no filesystem path can be served. Return fixed byte bodies from memory, explicit `Content-Length`, `Cache-Control: no-store`, and `X-Content-Type-Options: nosniff`. Silence request logging.

- [ ] **Step 4: Implement detached launch**

The launch flow:

1. creates two canonical heartbeat rows in-process with `heartbeat.emit_heartbeats`;
2. writes only public statement JSON and heartbeat JSONL under `/tmp/s20b-statement`;
3. starts `statement.py serve` with stdout/stderr redirected to bounded files;
4. starts pinned `cloudflared` with `start_new_session=True`;
5. polls the tunnel log for at most 25 seconds;
6. validates exactly one HTTPS `trycloudflare.com` URL; and
7. prints `{ok, sandboxId, url, statement}`.

The CLI requires `MODAL_SANDBOX_ID`; it accepts only public address arguments and has no private-key option.

- [ ] **Step 5: Run focused and Python regression tests**

Run:

```bash
.venv/bin/python -m unittest skills/self/shelter/python/test_statement.py
.venv/bin/python -m unittest discover -s skills/self/shelter/python -p 'test_*.py'
```

Expected: all PASS.

- [ ] **Step 6: Commit and push**

```bash
git add skills/self/shelter/python/statement.py skills/self/shelter/python/test_statement.py
git commit -m "feat(shelter): serve Python statement through a tunnel"
git push
```

---

### Task 3: Paid Modal adapter and independent verification

**Files:**
- Create: `skills/self/shelter/python/modal-statement.mjs`
- Create: `skills/self/shelter/python/test_modal_statement.mjs`

**Interfaces:**
- Consumes: outer Base payment key, injectable paid fetch, injectable public fetch.
- Produces: `buildStatementCommand() -> string[]`
- Produces: `parseStatementControl(stdout) -> {sandboxId, url, statement}`
- Produces: `validatePublicStatement(statement, sandboxId) -> {ok, reason}`
- Produces: `compareFinancialSnapshots(published, independent, polymarketToleranceUsd=0.01) -> {ok, differences}`
- Produces: `proveModalStatement({baseKey, fetchImpl, publicFetch}) -> Promise<{ok, sandboxId, url, statement, heartbeats, comparison, ...}>`

- [ ] **Step 1: Write failing command and verifier tests**

Assert:

```javascript
const command = buildStatementCommand();
assert.equal(command.every((part) => part.length <= 2000), true);
assert.match(command[2], /2026\\.7\\.3/);
assert.match(command[2], /9d71c677db00134c1bd4144b7783486b654ad281b1ea62b4972098d19f770f17/);
assert.equal(command.join(" ").includes("BASE_KEY"), false);
assert.equal(command.join(" ").includes("SOLANA_SESSION"), false);
```

Add tests that reject:

- non-HTTPS and non-`trycloudflare.com` URLs;
- control JSON naming another sandbox;
- missing/extra top-level or nested fields;
- secret-shaped field names such as `privateKey`, `seed`, `token`, or `cookie`;
- one or tampered heartbeat;
- exact Base/Solana mismatches; and
- Polymarket drift above `$0.01`.

Mock the full paid lifecycle: create response, exec response with control JSON, three public route fetches, independent Base/Solana/PM fetches.

- [ ] **Step 2: Run the Node test to verify RED**

Run:

```bash
node --test skills/self/shelter/python/test_modal_statement.mjs
```

Expected: FAIL with `ERR_MODULE_NOT_FOUND` for `modal-statement.mjs`.

- [ ] **Step 3: Implement safe command packaging**

Read `statement.py` and `heartbeat.py`, serialize them into one public JSON package, base64 encode it, and split into 1,800-character command arguments. The shell control string:

1. reconstructs the two source files;
2. downloads the official pinned Linux amd64 binary;
3. computes SHA-256 and exits on mismatch;
4. installs only `PyNaCl==1.6.2 base58==2.1.1`; and
5. executes `statement.py launch`.

Throw before payment if any command element exceeds 2,000 characters.

- [ ] **Step 4: Implement outside-the-box verification**

After `moveIn` succeeds:

1. parse one control JSON line;
2. fetch `/`, `/statement.json`, and `/heartbeats` from the tunnel URL;
3. require HTTP 200 and correct content types;
4. validate the exact public schema and sandbox ID;
5. pass heartbeat JSONL to `verifyModalHeartbeatOutput`;
6. independently query Base, Solana, NOS, and Polymarket from Node;
7. compare exact balances and `$0.01` Polymarket tolerance; and
8. return a bounded safe result.

Do not include `habitation.execs[].command`, the payment key, or response headers in CLI output.

- [ ] **Step 5: Run focused and shelter regression tests**

Run:

```bash
node --test skills/self/shelter/python/test_modal_statement.mjs
node --test skills/self/shelter/__tests__/*.test.js \
  skills/self/shelter/nosana/__tests__/*.test.js \
  skills/self/shelter/nosana/funding/__tests__/*.test.js \
  skills/self/shelter/nosana/funding/__tests__/*.test.mjs \
  skills/self/shelter/python/test_modal_heartbeat.mjs \
  skills/self/shelter/python/test_modal_statement.mjs
```

Expected: 0 failures.

- [ ] **Step 6: Commit and push**

```bash
git add skills/self/shelter/python/modal-statement.mjs skills/self/shelter/python/test_modal_statement.mjs
git commit -m "feat(shelter): verify public Modal statement"
git push
```

---

### Task 4: Live proof, evidence, and SSOT

**Files:**
- Create: `specs/evidence/s20b-python-statement-<sandbox-id>.html`
- Create: `specs/evidence/s20b-python-statement-<sandbox-id>.json`
- Create: `specs/evidence/s20b-python-statement-<sandbox-id>-heartbeats.jsonl`
- Create: `specs/evidence/s20b-python-statement-<sandbox-id>-verification.json`
- Modify: `specs/00-SHELTER-INDEPENDENCE.md`
- Modify in Life Manager repo after anicha evidence is pushed: `docs/superpowers/specs/2026-07-19-anicca-one-repo-consolidation-spec.md`

**Interfaces:**
- Consumes: per-instance founder Base key only in the outer x402 client.
- Produces: one paid sandbox, temporary public statement URL, three fetched public artifacts, independent financial comparison, and updated current cursor.

- [ ] **Step 1: Measure public balances before the paid run**

Read:

- founder Base USDC at `0x810f6d61f7606deee2657d3083e150a222bc29c5`;
- shelter SOL and NOS at `71FfqFniYoMsWZb1qFeQDb1fk2xqvajzivpsnMb44gTf`; and
- Polymarket positions at `0x904B50d2e214Da947d83D6a2D32c4E3Ffc17Eb74`.

Record only public values.

- [ ] **Step 2: Run one live paid proof**

Run:

```bash
ANICCA_HOME=/Users/anicca/.anicca-founder \
  node skills/self/shelter/python/modal-statement.mjs
```

Expected:

- `ok:true`;
- one `sb-...` sandbox;
- one HTTPS `trycloudflare.com` URL;
- `/`, `/statement.json`, and `/heartbeats` fetched from outside;
- two heartbeat rows independently verified;
- Base/Solana/NOS exact comparison PASS;
- Polymarket difference at or below `$0.01`.

If the provider or tunnel fails, preserve the safe diagnostic, fix with a RED regression test, and repeat within the existing per-job spend cap.

- [ ] **Step 3: Save public evidence**

Use `apply_patch` to save the fetched HTML, JSON, heartbeat JSONL, and a bounded verification JSON. Force-add JSONL if required by `.gitignore`.

The verification JSON includes:

```json
{
  "sandboxId": "sb-...",
  "temporaryUrl": "https://....trycloudflare.com",
  "routes": {"/": 200, "/statement.json": 200, "/heartbeats": 200},
  "heartbeatVerification": {"pass": 2, "fail": 0},
  "financialComparison": {"ok": true, "differences": []},
  "successfulProofCostUsd": 0.015,
  "limitations": [
    "URL expires with the five-minute sandbox",
    "Cloudflare Quick Tunnel has no SLA",
    "Polymarket cashPnl is not a closed net-profit ledger"
  ]
}
```

- [ ] **Step 4: Run independent evidence verification**

Run:

```bash
bin/citizen-steward --verify \
  specs/evidence/s20b-python-statement-<sandbox-id>-heartbeats.jsonl \
  --job <sandbox-id> --rpc
```

Re-read the saved JSON and independently query all three financial sources again. Report drift honestly; do not overwrite the captured snapshot with later values.

- [ ] **Step 5: Update both SSOT files**

In anicha:

- mark only S20b-c complete;
- record sandbox ID, temporary URL, routes, values, verifier result, spend, and evidence paths;
- state the tunnel and five-minute limitations;
- mark S20b complete only if x402, heartbeat, and statement are all evidenced; and
- advance the shelter-local cursor to S21.

In Life Manager:

- mark S20b-c done with the same evidence;
- advance portfolio current cursor to 13c-PM;
- preserve REDEEM-1 as waiting for a real redeemable condition; and
- do not claim PM net profit before 13c-PM.

- [ ] **Step 6: Run fresh completion verification**

Run:

```bash
.venv/bin/python -m unittest discover -s skills/self/shelter/python -p 'test_*.py'
node --test skills/self/shelter/__tests__/*.test.js \
  skills/self/shelter/nosana/__tests__/*.test.js \
  skills/self/shelter/nosana/funding/__tests__/*.test.js \
  skills/self/shelter/nosana/funding/__tests__/*.test.mjs \
  skills/self/shelter/python/test_modal_heartbeat.mjs \
  skills/self/shelter/python/test_modal_statement.mjs
git diff --check
```

Expected: 0 failures and no whitespace errors.

- [ ] **Step 7: Commit, push, and integrate**

Commit anicha evidence/spec, push the feature branch, integrate to `main`, rerun the same tests on merged `main`, and push `main`. Commit and push the Life Manager SSOT update separately.

## Plan self-review

| Check | Result |
|---|---|
| Spec coverage | Public collection, recursive allowlist, GET-only routes, temporary live URL, heartbeat proof, independent comparison, evidence, and both SSOT updates are covered |
| Placeholder scan | No unresolved or unspecified implementation steps; live identifiers use runtime placeholders only where the provider creates them |
| Type consistency | Python statement schema is identical to Node validator and evidence schema |
| Scope | Only S20b-c is implemented; 13c-PM and S21 remain subsequent work |
