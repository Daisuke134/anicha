# S19 — Refill Loop Implementation Plan

> **For agentic workers:** implement task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** When the agent earns USDC on Base, that money becomes rent on Solana without a human or an assistant in the loop.

**Architecture:** One pure decision module (`refill.mjs`) that decides *whether* and *how much* to move, plus a thin executor that calls the two rails that already exist. The decision is pure so it can be tested without touching money; the rails are injected so tests never hit the network.

**Tech Stack:** Node ESM, `node:test`, existing `skills/self/shelter/nosana/funding/acquire-nos.mjs` (SOL→NOS via Jupiter), relay.link for Base→Solana.

---

## Context you need

The agent lives on two chains and the money arrives on the wrong one:

- **Earns** USDC on **Base** (x402 sales settle there).
- **Spends** NOS + SOL on **Solana** (Nosana lease) and USDC on Base (frontier inference, Modal boxes).

So revenue on Base has to become NOS on Solana or the agent starves in a wallet full of money. Right now that hop is manual.

**The floor from S18 is the reason this matters.** `skills/self/shelter/nosana/renew.mjs` now refuses to extend a lease when paying for it would spend the 0.34 NOS reserve kept to move house. That makes running out *safe* — it does not make it *recoverable*. S19 is the other half: it puts money back.

**Measured facts (do not re-derive):**
- One 600s extension costs ~0.0302 NOS on the cheapest market.
- A fresh confidential post needs 0.34 NOS escrow (duration-independent) and ≥0.005 SOL.
- The shelter sub-wallet is at `$ANICCA_HOME/.automaton/nosana_subwallet_key.json`, and the funded home is `/Users/anicca/.blockrun` (NOT `.anicca-founder` — that one holds the Base key).
- Existing swap: `funding/acquire-nos.mjs` exports `fetchQuote`, `buildRightSizedSwapTransaction`, `evaluateFundingGate`, `pollForConfirmation`. Read it before writing anything; do not reimplement Jupiter.
- Existing bridge reference implementation: `/Users/anicca/anicca-rtdash/.worktrees/t2b-discovery/apps/x402-agents/scripts/bridge-base-to-solana.mjs` (relay.link). Read it; port only what you need.

## File Structure

- Create `skills/self/shelter/nosana/funding/refill.mjs` — pure decisions only.
- Create `skills/self/shelter/nosana/funding/__tests__/refill.test.js`.
- Create `bin/citizen-refill` — the executable loop entry point.

Keep `refill.mjs` free of network calls, key reads, and `process.env`. Everything it needs arrives as arguments.

---

### Task 1: The decision — should we move money, and how much?

**Files:**
- Create: `skills/self/shelter/nosana/funding/refill.mjs`
- Test: `skills/self/shelter/nosana/funding/__tests__/refill.test.js`

- [ ] **Step 1: Write the failing tests**

```js
import { test } from "node:test";
import assert from "node:assert/strict";
import { planRefill, DEFAULT_TARGET_NOS, DEFAULT_MIN_BRIDGE_USD, DEFAULT_KEEP_ON_BASE_USD } from "../refill.mjs";

test("does nothing when the shelter wallet is already stocked", () => {
  const p = planRefill({ nosBalance: DEFAULT_TARGET_NOS + 1, solBalance: 0.05, baseUsdc: 50 });
  assert.equal(p.act, false);
});

test("moves money when NOS is short and Base has revenue to spare", () => {
  const p = planRefill({ nosBalance: 0.02, solBalance: 0.05, baseUsdc: 20 });
  assert.equal(p.act, true);
  assert.ok(p.bridgeUsd > 0);
});

test("never bridges the working capital Base itself needs", () => {
  // Base pays for inference and for Modal boxes; draining it to buy NOS trades one starvation
  // for another.
  const p = planRefill({ nosBalance: 0, solBalance: 0.05, baseUsdc: DEFAULT_KEEP_ON_BASE_USD + 1 });
  assert.ok(p.bridgeUsd <= 1);
});

test("refuses a bridge too small to be worth its fees", () => {
  const p = planRefill({ nosBalance: 0, solBalance: 0.05, baseUsdc: DEFAULT_KEEP_ON_BASE_USD + 0.01 });
  assert.equal(p.act, false);
  assert.match(p.reason, /too small/i);
});

test("tops up SOL as well, because NOS cannot pay a transaction fee", () => {
  const p = planRefill({ nosBalance: 10, solBalance: 0.0001, baseUsdc: 20 });
  assert.equal(p.act, true);
  assert.ok(p.needSol);
});

test("caps a single pass so one bad quote cannot move everything", () => {
  const p = planRefill({ nosBalance: 0, solBalance: 0, baseUsdc: 10000 });
  assert.ok(p.bridgeUsd <= 25);
});

test("a plan states its reason whether it acts or not", () => {
  for (const p of [planRefill({ nosBalance: 99, solBalance: 1, baseUsdc: 99 }), planRefill({ nosBalance: 0, solBalance: 0, baseUsdc: 50 })]) {
    assert.equal(typeof p.reason, "string");
    assert.ok(p.reason.length > 0);
  }
});
```

- [ ] **Step 2: Run and watch them fail**

Run: `node --test "skills/self/shelter/nosana/funding/__tests__/refill.test.js"`
Expected: FAIL, cannot find module `../refill.mjs`.

- [ ] **Step 3: Implement `planRefill`**

Requirements, not code — write it yourself and write the comments in your own words:
- Exports `DEFAULT_TARGET_NOS` (aim for enough to post a fresh lease AND extend for a while: 1.0), `DEFAULT_MIN_BRIDGE_USD` (0.50 — below this the bridge fee eats the transfer), `DEFAULT_KEEP_ON_BASE_USD` (1.00 — Base must keep buying inference and Modal boxes), `DEFAULT_MAX_PASS_USD` (25).
- Returns `{ act, bridgeUsd, needSol, needNos, reason }`.
- Never returns `act: true` without a positive, capped `bridgeUsd`.
- Comment WHY each threshold exists, not what the number is.

- [ ] **Step 4: Run tests — all pass**

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat(refill): decide when Base revenue should become Solana rent"
```

---

### Task 2: The loop — carry the decision out

**Files:**
- Create: `bin/citizen-refill`
- Modify: `skills/self/shelter/nosana/funding/refill.mjs` (add the orchestrator with injected rails)

- [ ] **Step 1: Write the failing test** in the same test file:

```js
test("executeRefill bridges, then swaps, and reports each leg it actually did", async () => {
  const { executeRefill } = await import("../refill.mjs");
  const calls = [];
  const r = await executeRefill({
    plan: { act: true, bridgeUsd: 5, needNos: true, needSol: true, reason: "short" },
    bridge: async (usd) => { calls.push(["bridge", usd]); return { ok: true, tx: "0xbridge" }; },
    swapToNos: async () => { calls.push(["swap"]); return { ok: true, tx: "solswap" }; },
  });
  assert.equal(r.ok, true);
  assert.deepEqual(calls.map((c) => c[0]), ["bridge", "swap"]);
});

test("executeRefill does not swap when the bridge failed — money that never arrived cannot be spent", async () => {
  const { executeRefill } = await import("../refill.mjs");
  let swapped = false;
  const r = await executeRefill({
    plan: { act: true, bridgeUsd: 5, needNos: true, reason: "short" },
    bridge: async () => ({ ok: false, reason: "relay refused" }),
    swapToNos: async () => { swapped = true; return { ok: true }; },
  });
  assert.equal(r.ok, false);
  assert.equal(swapped, false);
});

test("executeRefill is a no-op for a plan that decided not to act", async () => {
  const { executeRefill } = await import("../refill.mjs");
  const r = await executeRefill({ plan: { act: false, reason: "stocked" }, bridge: async () => { throw new Error("must not run"); } });
  assert.equal(r.ok, true);
  assert.equal(r.skipped, true);
});
```

- [ ] **Step 2: Run, watch fail, implement `executeRefill`**

- [ ] **Step 3: Write `bin/citizen-refill`**

- Reads balances for real (Solana RPC for NOS/SOL, Base RPC for USDC).
- Calls `planRefill`, prints the plan and its reason, then `executeRefill` **only** when `--live` is passed. Default is a plan-and-print with no side effects.
- Appends every attempt to `~/.hermes/state/refill.jsonl` with `intent` then `settled`, matching the shape already used by `nosana-subwallet-funding.jsonl`.
- Never prints key material.

- [ ] **Step 4: Run the whole shelter suite**

Run: `node --test "skills/self/shelter/**/*.test.js"`
Expected: everything passes, including the pre-existing 140.

- [ ] **Step 5: Verify against the real chain WITHOUT spending**

Run: `ANICCA_HOME=/Users/anicca/.blockrun node bin/citizen-refill`
Expected: prints real balances and a plan. Report the exact output back — do not pass `--live`.

- [ ] **Step 6: Commit**

---

## Constraints

- **No dry-run theatre.** If something cannot be verified, say so plainly; do not print success for work that did not happen.
- Do not run `--live`. The orchestrator will do that and verify on-chain.
- Do not touch anything under `~/.blockrun`, `~/.anicca-founder`, or any `memory/` directory.
- Match the surrounding comment style: explain the *why* and the failure it prevents, never narrate the code.
