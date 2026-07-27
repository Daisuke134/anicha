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
