# S20b Python Heartbeat Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the second-landlord `python:3.11` sandbox emit at least two naturally timed, canonical `shelter-heartbeat` rows that the existing JavaScript verifier accepts.

**Architecture:** A dependency-thin Python module owns canonical JSON construction, an in-sandbox ephemeral Ed25519 identity, Solana `getLatestBlockhash`, and the timed JSONL loop. A Node adapter packages that public source into one Modal exec command, then treats the existing `heartbeat.mjs` verifier as the independent authority. No long-lived wallet secret crosses the Modal command boundary.

**Tech Stack:** Python 3.11, PyNaCl 1.6.2, base58 2.1.1, Node 20+, existing x402 Modal adapter, existing `heartbeat.mjs` and `citizen-steward --verify`.

## Global Constraints

- Canonical signed JSON key order is exactly `blockhash,cycle,jobAddress,payer,slot,ts`, compact UTF-8 with no spaces.
- Output entry shape is exactly `{v:1,kind:"shelter-heartbeat",ts,cycle,jobAddress,payer,slot,blockhash,sig}`.
- `jobAddress` comes from `MODAL_SANDBOX_ID`; the process fails closed if it is absent.
- The signing key is generated inside the sandbox and never appears in command arguments, repo state, logs, Telegram, or evidence.
- One live proof uses at least two cycles, one payer, increasing cycle/timestamp, fresh Solana RPC values, and the existing JavaScript verifier.
- Live spend is capped to one CPU sandbox create plus one exec. No GPU and no duration above 300 seconds.
- Sources: PyNaCl documents that `SigningKey` uses a 32-byte seed (`https://pynacl.readthedocs.io/en/latest/signing/`); Modal documents `MODAL_SANDBOX_ID` (`https://modal.com/docs/guide/environment_variables`); Solana documents `getLatestBlockhash` returning `context.slot` and `value.blockhash` (`https://solana.com/docs/rpc/http/getlatestblockhash`); BlockRun documents create/exec and the 300-second managed Python sandbox (`https://github.com/BlockRunAI/awesome-blockrun/blob/main/docs/api-reference/modal-sandbox.md`).

---

### Task 1: Canonical Python signing core

**Files:**
- Create: `skills/self/shelter/python/heartbeat.py`
- Create: `skills/self/shelter/python/test_heartbeat.py`
- Create: `skills/self/shelter/python/requirements-heartbeat.txt`

**Interfaces:**
- Produces: `build_heartbeat_message(fields: dict) -> str`
- Produces: `make_heartbeat_entry(*, job_address: str, blockhash: str, slot: int, ts: int, cycle: int, signing_key: SigningKey) -> dict`
- Produces: `fetch_latest_blockhash(rpc_url: str = DEFAULT_RPC_URL, opener=urlopen) -> tuple[str, int]`
- Produces: `emit_heartbeats(*, job_address: str, cycles: int, interval_seconds: float, signing_key: SigningKey | None = None, fetcher=fetch_latest_blockhash, now_ms=..., sleep=time.sleep, output=sys.stdout) -> list[dict]`
- Consumes: no wallet key; an optional deterministic `SigningKey` is injectable only for tests.

- [ ] **Step 1: Write the failing canonical-vector tests**

```python
SEED = bytes(range(32))
EXPECTED_MESSAGE = (
    '{"blockhash":"EkSnNWid2cvwEVnVx9aBqawnmiCNiDgp3gUdkDPTKN1N",'
    '"cycle":1,"jobAddress":"sb-test-heartbeat",'
    '"payer":"FAe4sisG95oZ42w7buUn5qEE4TAnfTTFPiguZUHmhiF",'
    '"slot":2792,"ts":1785144000123}'
)
EXPECTED_SIG = "27d8Q6rkEPqwVqM2oLePY3U12eDTjdioRW7wwN6KmqGXURccEZYF3vYxDcoBXdJGqbbAmbt9b9cr1bQMdGmvdkkA"

def test_matches_the_existing_javascript_verifier_vector():
    key = SigningKey(SEED)
    entry = make_heartbeat_entry(
        job_address="sb-test-heartbeat",
        blockhash="EkSnNWid2cvwEVnVx9aBqawnmiCNiDgp3gUdkDPTKN1N",
        slot=2792,
        ts=1785144000123,
        cycle=1,
        signing_key=key,
    )
    assert build_heartbeat_message(entry) == EXPECTED_MESSAGE
    assert entry["sig"] == EXPECTED_SIG
```

Add independent tests that missing `jobAddress`, negative slot, zero timestamp, and non-integer cycle fail before signing. The production mutation caught is default `json.dumps` whitespace/order or signing a different field set.

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```bash
.venv/bin/python -m unittest skills/self/shelter/python/test_heartbeat.py -v
```

Expected: import failure because `heartbeat.py` does not exist.

- [ ] **Step 3: Implement the minimum signing core**

Use:

```python
json.dumps(ordered, separators=(",", ":"), ensure_ascii=False)
signature = signing_key.sign(message.encode("utf-8")).signature
base58.b58encode(signature).decode("ascii")
```

Derive `payer` only from `signing_key.verify_key`; never accept a caller-supplied payer.

- [ ] **Step 4: Run the focused test and verify GREEN**

Run the same unittest command. Expected: all Task 1 tests PASS.

- [ ] **Step 5: Commit Task 1**

```bash
git add skills/self/shelter/python/heartbeat.py \
  skills/self/shelter/python/test_heartbeat.py \
  skills/self/shelter/python/requirements-heartbeat.txt
git commit -m "feat(shelter): sign canonical heartbeats in Python"
```

---

### Task 2: Timed loop and fail-closed CLI

**Files:**
- Modify: `skills/self/shelter/python/heartbeat.py`
- Modify: `skills/self/shelter/python/test_heartbeat.py`

**Interfaces:**
- Consumes: `MODAL_SANDBOX_ID`, optional `SOLANA_RPC_URL`, CLI `--cycles`, `--interval`.
- Produces: one compact JSON object per stdout line; stderr contains bounded field names only.

- [ ] **Step 1: Write failing loop tests**

Use a deterministic fetcher returning two literal `(blockhash, slot)` pairs, a fake clock returning `1000` then `2000`, and a sleep recorder. Assert two parseable rows, cycles `[1,2]`, one payer, the requested sandbox ID, and exactly one sleep between rows. Add a subprocess test proving missing `MODAL_SANDBOX_ID` exits non-zero and emits no heartbeat row.

- [ ] **Step 2: Run the focused test and verify RED**

Expected failure: `emit_heartbeats` or CLI behavior is missing.

- [ ] **Step 3: Implement RPC, timed emission, and CLI**

Use stdlib `urllib.request` for JSON-RPC so runtime networking adds no dependency. Flush each JSONL row immediately. Generate `SigningKey.generate()` once per process, not once per cycle.

- [ ] **Step 4: Run focused Python tests and the existing Python suite**

```bash
.venv/bin/python -m unittest skills/self/shelter/python/test_heartbeat.py -v
.venv/bin/python -m unittest discover -s skills/self/shelter/python -p 'test_*.py' -v
```

Expected: heartbeat tests and existing 13 x402 tests PASS.

- [ ] **Step 5: Commit Task 2**

```bash
git add skills/self/shelter/python/heartbeat.py skills/self/shelter/python/test_heartbeat.py
git commit -m "feat(shelter): emit timed Python heartbeat rows"
```

---

### Task 3: Modal packaging and independent verification

**Files:**
- Create: `skills/self/shelter/python/modal-heartbeat.mjs`
- Create: `skills/self/shelter/python/test_modal_heartbeat.mjs`

**Interfaces:**
- Produces: `buildHeartbeatCommand({cycles, intervalSeconds}) -> string[]`
- Produces: `verifyModalHeartbeatOutput({stdout, sandboxId, minimumRows = 2}) -> {ok, entries, reason}`
- Produces: `proveModalHeartbeat({baseKey, fetchImpl, cycles, intervalSeconds}) -> Promise<{ok, sandboxId, entries, ...}>`
- Consumes: existing `moveIn()` and `verifyHeartbeatEntry()`.

- [ ] **Step 1: Write failing adapter tests**

Tests execute observable behavior:

1. Two literal valid rows for one sandbox/payer and increasing cycles pass.
2. A valid signature naming a different sandbox fails.
3. Two individually valid rows with different payer keys fail.
4. One row fails the natural-heartbeat minimum.
5. A tampered row fails through the real JavaScript verifier.
6. The built command carries public source and dependency pins but contains no key-like environment value.

- [ ] **Step 2: Run the Node test and verify RED**

```bash
node --test skills/self/shelter/python/test_modal_heartbeat.mjs
```

Expected: module-not-found for `modal-heartbeat.mjs`.

- [ ] **Step 3: Implement the minimum adapter**

Package `heartbeat.py` as base64 public source, install exact heartbeat requirements inside the disposable sandbox, and execute:

```text
python /tmp/heartbeat.py --cycles 2 --interval 5
```

Pass no signing secret. `proveModalHeartbeat` delegates create/exec to `moveIn`, parses only stdout from the successful exec, and verifies every row with the existing JavaScript verifier.

- [ ] **Step 4: Run adapter, Python, and shelter regression tests**

```bash
node --test skills/self/shelter/python/test_modal_heartbeat.mjs
.venv/bin/python -m unittest discover -s skills/self/shelter/python -p 'test_*.py' -v
node --test skills/self/shelter/__tests__/*.test.js skills/self/shelter/nosana/__tests__/*.test.js
```

- [ ] **Step 5: Commit Task 3**

```bash
git add skills/self/shelter/python/modal-heartbeat.mjs \
  skills/self/shelter/python/test_modal_heartbeat.mjs
git commit -m "feat(shelter): verify Modal Python heartbeat continuity"
```

---

### Task 4: Live second-house proof and SSOT close

**Files:**
- Modify: `specs/00-SHELTER-INDEPENDENCE.md`
- Create: `specs/evidence/s20b-python-heartbeat-<sandbox-id>.jsonl`
- Modify: `/Users/anicca/Projects/life-manager-main/docs/superpowers/specs/2026-07-19-anicca-one-repo-consolidation-spec.md` after the anicha commit is pushed

**Interfaces:**
- Consumes: agent-owned capped Base subwallet via `resolveIdentity`; no user wallet.
- Produces: one paid Modal sandbox, two natural Python heartbeat rows, JavaScript signature verification, optional RPC blockhash/slot verification.

- [ ] **Step 1: Run one capped live proof**

Create one CPU `python:3.11` sandbox with `timeout <= 300`, execute two heartbeats five seconds apart, and save only public JSONL rows. Never print the Base key or any private seed.

- [ ] **Step 2: Verify with the independent existing CLI**

```bash
bin/citizen-steward --verify specs/evidence/s20b-python-heartbeat-<sandbox-id>.jsonl --job <sandbox-id> --rpc
```

Expected: two PASS, zero FAIL. If RPC cannot return the historical block, record the explicit sig-only downgrade; do not call it RPC-verified.

- [ ] **Step 3: Update both SSOTs**

Mark only `S20b-b` done with sandbox ID, cycles, slots, verifier output, spend receipt/amount, and evidence path. Keep `S20b-c` pending and advance the current cursor to it.

- [ ] **Step 4: Run verification-before-completion**

Run the full commands from Task 3 again, `git diff --check`, secret-pattern scan over changed/evidence files, and confirm the evidence contains exactly two public heartbeat rows.

- [ ] **Step 5: Commit and push**

```bash
git add -A
git commit -m "docs(shelter): prove Python heartbeat in the second house"
git push -u origin feature/s20b-python-heartbeat
```

Integrate to `main` using the repository's normal non-destructive flow, then update the Life Manager SSOT against the pushed anicha evidence.

## Self-Review

| Check | Result |
|---|---|
| Spec coverage | S20b-b canonical signature, natural cadence, external verifier, sandbox binding, and evidence are each mapped to a task |
| Placeholder scan | Every implementation step contains concrete files, interfaces, commands, and expected results; S20b-c is explicitly out of scope |
| Type consistency | Python entry keys match `heartbeat.mjs`; adapter consumes stdout JSONL and returns verified entries |
| Security | No long-lived Solana/Base signing secret enters the sandbox; ephemeral signer continuity is proven across rows |
| Scope | Statement serving and x402 payment are not reimplemented; S20b-c stays next |
