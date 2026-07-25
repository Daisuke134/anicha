# S8 Capped Sub-Wallet Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An on-chain-enforced spend cap for a cloud-resident hot key: a sub-wallet funded with exactly `cap` NOS + a small SOL fee budget, whose secret is the ONLY key that ever leaves the Mac. If the cloud key leaks, the attacker gets at most the cap.

**Architecture (research-verified 2026-07-26):** SPL Approve delegation is IMPOSSIBLE here — nosana-jobs `list.rs` constrains `user == payer's own ATA` (primary source: nosana-ci/nosana-programs), so the payer must own the NOS it spends. The cap therefore IS the balance: `sub-wallet.mjs` generates a fresh keypair (sanctioned exception to "never a new wallet" — this wallet exists precisely so the canonical secret never goes to the cloud), funds it from Franklin's wallet (NOS SPL transfer + SOL transfer, ATA creation included), records every funding movement in a ledger, and refuses to fund beyond caps. Deploy path already supports a different payer via env (`ANICCA_HOME`-independent keypair injection).

**Tech Stack:** @solana/web3.js (SystemProgram.transfer, getLatestBlockhash, sendAndConfirm), @solana/spl-token (getOrCreateAssociatedTokenAccount, transfer) — check it is installed; if not, `npm i @solana/spl-token`. node:test with injected connection fakes.

**Caps (env-overridable):** `NOSANA_SUBWALLET_NOS_CAP` default 0.5 NOS (~$0.13), `NOSANA_SUBWALLET_SOL_CAP` default 0.005 SOL. Fail-closed: refuses to fund if requested amount exceeds cap, if sub-wallet balance would exceed cap after funding, or if Franklin's remaining balance would drop below safety floors (reuse DEFAULT_SOL_FEE_FLOOR from spend-gate.mjs).

---

### Task 1: sub-wallet.mjs (pure decision logic + injected I/O) + tests

**Files:**
- Create: `skills/self/shelter/nosana/sub-wallet.mjs`
- Test: `skills/self/shelter/nosana/__tests__/sub-wallet.test.js`

Exports:
```js
export function evaluateFundingGate({ requestNos, requestSol, subNosBalance, subSolBalance, ownerNosBalance, ownerSolBalance, config })
// pure — {allowed, reason}; refuse when: request<=0, sub balance would exceed caps, owner would drop below floors
export function materializeSubWalletFile({ secretBytes, subWalletPath }) // 0600/0700, same as keypair.mjs
export function ensureSubWallet({ env, home }) // load-or-create at $ANICCA_HOME/.automaton/nosana_subwallet_key.json; returns {address, keypairPath, created}
export async function fundSubWallet({ env, requestNos, requestSol, connection?, ownerKeypair?, subAddress?, appendImpl?, now? })
// gate → SOL SystemProgram.transfer → NOS SPL transfer (create sub ATA if needed) → append {kind:"subwallet-funding", ts, from, to, nos, sol, sig...} to nosana-subwallet-funding.jsonl
```
TDD: gate tests (cap exceeded / owner floor / happy path), file-permission test, load-or-create idempotency test. All fakes; no network.

### Task 2: bin/citizen-subwallet CLI

**Files:**
- Create: `bin/citizen-subwallet` (755)

Modes: `status` (addresses + balances via RPC), `fund --nos <amt> --sol <amt> [--live]` (dry default: run gate + print exactly what would move, stop), `export-path` (print sub-wallet keypair path for S12 wiring). Smoke: `status` against mainnet reads real balances.

### Task 3: E2E (live, capped)

1. `bin/citizen-subwallet fund --nos 0.2 --sol 0.004 --live` — real transfer from Franklin wallet, confirmed sigs recorded to ledger.
2. `bin/citizen-subwallet status` — sub-wallet shows 0.2 NOS / 0.004 SOL on-chain.
3. Post one real 15-min job PAID BY THE SUB-WALLET (`ANICCA_HOME` trick or explicit keypair path override on citizen-up — smallest change: `NOSANA_KEYPAIR_PATH` env override in ensureNosanaKeypair, added in this task with a test) and steward it: job succeeds, payer == sub-wallet address, cost deducted from sub-wallet only.
4. Exit proof: jobs API shows the job with `payer == <sub-address>`; Franklin's main balance untouched by the job itself; ledger rows complete. Update spec + README.
