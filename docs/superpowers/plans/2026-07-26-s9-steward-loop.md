# S9 Steward Loop (常駐化) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the post-and-exit deploy with a lease-long steward process that re-reads the job's timeout every cycle and appends a per-cycle heartbeat signed over a fresh Solana blockhash — third-party-verifiable proof the tenant process was alive for the whole lease.

**Architecture:** Pure signing/verification logic in `heartbeat.mjs` (no I/O); the loop in `steward.mjs` with every I/O boundary injected (jobs-API fetch, RPC connection, clock, sleep, ledger append) mirroring `deploy.mjs`'s existing style; thin CLI entry `bin/citizen-steward`. Deploy stays untouched — steward attaches to an already-posted job address.

**Tech Stack:** Node ESM, node:test, tweetnacl (ed25519 detached sign), bs58, @solana/web3.js (getSlot/getLatestBlockhash), Nosana public jobs API (`https://dashboard.k8s.prd.nos.ci/api/jobs/<address>` — real shape verified live 2026-07-26: fields `state` (int, 2=done), `jobStatus`, `timeStart`, `timeEnd`, `timeout` (seconds), `node`, `payer`).

**Evidence model:** entry = `{v, kind, ts, cycle, jobAddress, payer, slot, blockhash, sig}`. Message = canonical JSON of `{blockhash, cycle, jobAddress, payer, slot, ts}` (sorted keys). Sig = ed25519 detached over message bytes with Franklin's own 64-byte secret. Verifier checks sig against the payer address (pubkey) purely; `--rpc` mode additionally checks `getBlock(slot).blockhash === entry.blockhash`, proving the message could not have been built before that slot existed. Ledger: `$ANICCA_STATE_DIR|~/.hermes/state/nosana-heartbeats.jsonl` (append via existing `appendChild`).

---

### Task 1: heartbeat.mjs (pure) + tests

**Files:**
- Create: `skills/self/shelter/nosana/heartbeat.mjs`
- Test: `skills/self/shelter/nosana/__tests__/heartbeat.test.js`
- Modify: `package.json` (add `"tweetnacl": "^1.0.3"` to dependencies; run `npm install`)

Steps: write failing tests for `buildHeartbeatMessage` (canonical sorted-key JSON, rejects missing fields), `signHeartbeat`/`verifyHeartbeatEntry` round-trip with a throwaway nacl keypair (generated in-test, NEVER Franklin's real secret), tamper detection (flip a byte → invalid), and address-mismatch rejection. Run `node --test skills/self/shelter/nosana/__tests__/heartbeat.test.js` → FAIL, implement, PASS, commit.

Key signatures:
```js
export function buildHeartbeatMessage({ jobAddress, payer, blockhash, slot, ts, cycle }) // → canonical JSON string, throws on any missing/invalid field
export function signHeartbeat({ message, secretBytes }) // → base58 sig (tweetnacl.sign.detached)
export function makeHeartbeatEntry({ jobAddress, payer, blockhash, slot, ts, cycle, secretBytes }) // → {v:1, kind:"shelter-heartbeat", ts, cycle, jobAddress, payer, slot, blockhash, sig}
export function verifyHeartbeatEntry(entry) // → {valid, reason} — rebuilds message from entry fields, verifies sig against entry.payer pubkey; pure, never throws
```
Money-safety: module never logs or embeds secretBytes in errors (same convention as keypair.mjs).

### Task 2: steward.mjs (loop, injected I/O) + tests

**Files:**
- Create: `skills/self/shelter/nosana/steward.mjs`
- Test: `skills/self/shelter/nosana/__tests__/steward.test.js`

```js
export async function fetchJobViaApi({ fetchImpl = fetch, jobAddress, apiBaseUrl = NOSANA_JOBS_API_BASE_URL }) // GET {base}/{jobAddress}; null on any failure (fail-closed read, same as reconcileNosanaJobViaApi)
export function computeLeaseEnd(job) // timeStart + timeout (recomputed every cycle = extension re-read); falls back to timeEnd; null if neither
export function isTerminal(job, nowTs, graceSeconds = 120) // state>=2 || jobStatus in {success,failed,stopped} || (leaseEnd && nowTs > leaseEnd + grace)
export async function stewardLoop({ jobAddress, env = process.env, fetchImpl = fetch, connectionFactory, intervalMs = 60_000, maxConsecutiveFailures = 5, maxCycles = Infinity, now = () => Date.now(), sleep = (ms) => new Promise(r => setTimeout(r, ms)), appendImpl, log })
```
Loop per cycle: fetch job (null → failure counter; ≥maxConsecutiveFailures → throw, fail-closed) → recompute leaseEnd (log when it grew = extension observed) → `getSlot()` + `getLatestBlockhash()` via injected connection → `makeHeartbeatEntry` with keypair from `ensureNosanaKeypair({env})` (resolved ONCE before loop) → append to `nosana-heartbeats.jsonl` under `resolveStateDir({env})` → terminal check → sleep. Returns `{cycles, heartbeats, terminal: {state, jobStatus, reason}}`.

Tests (all with fakes — fake fetch returning real captured API shape, fake connection `{getSlot, getLatestBlockhash}`, `sleep: async () => {}`, in-memory appendImpl, fixed clock): terminal-on-state-2 after N cycles; timeout re-read (2nd cycle returns bigger `timeout` → leaseEnd grows, extension logged); consecutive API failures throw at cap; each cycle appended a verifiable entry (verifyHeartbeatEntry passes); blockhash changes per cycle are reflected in entries. Keypair for tests: inject `keypair: {address, secretBytes}` param override so tests never touch resolve-identity.

### Task 3: bin/citizen-steward + spec/README update

**Files:**
- Create: `bin/citizen-steward` (mode 755) — `citizen-steward <jobAddress> [--interval <sec>] [--verify <file>]`
  - default: run stewardLoop with real deps (real fetch, real `new Connection(rpcUrl)`, real append)
  - `--verify <file>`: read jsonl, run `verifyHeartbeatEntry` on every row, print PASS/FAIL per row + summary; `--rpc` flag additionally checks `getBlock(slot)` blockhash equality
- Modify: `specs/00-SHELTER-INDEPENDENCE.md` (S9 status), `skills/self/shelter/nosana/README.md` (steward section)

### Task 4: E2E (live, cheap)

Post one real 15-min job via existing `bin/citizen-up --live` (~$0.012, within spend gate), run `bin/citizen-steward <jobAddress> --interval 60` for the full lease, then `--verify` the produced ledger (all sigs PASS, ≥10 heartbeats, blockhashes all distinct). This is the S9 exit proof. Record job address + verify output in spec.
