// node:test — sub-wallet: the S8 on-chain spend cap. Because nosana-jobs' `list` constrains the
// NOS source to the payer's OWN ATA (delegate path is structurally impossible — see the S8 plan),
// the cap is enforced by balance: a sub-wallet holds at most cap NOS + cap SOL, and only ITS
// secret ever leaves the Mac. These tests cover the pure funding gate, keypair file handling,
// and load-or-create idempotency — all offline, throwaway keys only.
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import {
  evaluateFundingGate,
  materializeSubWalletFile,
  ensureSubWallet,
  DEFAULT_NOS_CAP,
  DEFAULT_SOL_CAP,
} from "../sub-wallet.mjs";

const BASE = {
  requestNos: 0.2,
  requestSol: 0.004,
  subNosBalance: 0,
  subSolBalance: 0,
  ownerNosBalance: 2.4,
  ownerSolBalance: 0.02,
};

test("funding gate: happy path within caps and floors", () => {
  const verdict = evaluateFundingGate(BASE);
  assert.equal(verdict.allowed, true, verdict.reason);
});

test("funding gate: refuses non-positive and non-finite requests", () => {
  for (const bad of [{ requestNos: 0, requestSol: 0 }, { requestNos: -1 }, { requestNos: NaN }, { requestSol: Infinity }]) {
    const verdict = evaluateFundingGate({ ...BASE, ...bad });
    assert.equal(verdict.allowed, false);
  }
});

test("funding gate: refuses when sub-wallet would exceed NOS cap (existing balance counts)", () => {
  const verdict = evaluateFundingGate({ ...BASE, subNosBalance: 0.4, requestNos: 0.2 });
  assert.equal(verdict.allowed, false);
  assert.match(verdict.reason, /NOS cap/);
});

test("funding gate: refuses when sub-wallet would exceed SOL cap", () => {
  const verdict = evaluateFundingGate({ ...BASE, subSolBalance: 0.004, requestSol: 0.003 });
  assert.equal(verdict.allowed, false);
  assert.match(verdict.reason, /SOL cap/);
});

test("funding gate: refuses when owner would drop below SOL fee floor", () => {
  const verdict = evaluateFundingGate({ ...BASE, ownerSolBalance: 0.006, requestSol: 0.004 });
  assert.equal(verdict.allowed, false);
  assert.match(verdict.reason, /floor/);
});

test("funding gate: refuses when owner lacks the NOS being sent", () => {
  const verdict = evaluateFundingGate({ ...BASE, ownerNosBalance: 0.1, requestNos: 0.2 });
  assert.equal(verdict.allowed, false);
});

test("funding gate: custom caps via config override defaults", () => {
  const verdict = evaluateFundingGate({ ...BASE, requestNos: 0.9, config: { nosCap: 1.0, solCap: DEFAULT_SOL_CAP } });
  assert.equal(verdict.allowed, true, verdict.reason);
  assert.equal(evaluateFundingGate({ ...BASE, requestNos: 0.9 }).allowed, false); // default cap 0.5 refuses the same request
});

test("materializeSubWalletFile: 0600 file in 0700 dir", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "subw-"));
  const p = path.join(dir, "inner", "sub_key.json");
  materializeSubWalletFile({ secretBytes: new Uint8Array(64).fill(7), subWalletPath: p });
  assert.equal(fs.statSync(p).mode & 0o777, 0o600);
  assert.equal(fs.statSync(path.dirname(p)).mode & 0o777, 0o700);
  assert.equal(JSON.parse(fs.readFileSync(p, "utf8")).length, 64);
});

test("ensureSubWallet: creates once, then loads the SAME key (idempotent)", () => {
  const home = fs.mkdtempSync(path.join(os.tmpdir(), "subw-home-"));
  const first = ensureSubWallet({ env: {}, home });
  assert.equal(first.created, true);
  assert.equal(typeof first.address, "string");
  const second = ensureSubWallet({ env: {}, home });
  assert.equal(second.created, false);
  assert.equal(second.address, first.address); // never silently rotates the cloud identity
  assert.equal(fs.statSync(first.keypairPath).mode & 0o777, 0o600);
});
