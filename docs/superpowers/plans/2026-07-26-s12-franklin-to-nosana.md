# S12 Franklin-to-Nosana Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Franklin — the agent with a wallet — runs INSIDE a Nosana container it paid for with its own capped sub-wallet, makes a real paid model call (BlockRun x402, its own USDC), and serves the proof over the job's exposed port. No secret ever touches public IPFS.

**Architecture:** Reuses every prior stage: S8 sub-wallet is BOTH the rent payer AND Franklin's cloud identity (`.solana-session` = sub-wallet secret in base58, delivered via S13 confidential env). S13's poster-must-stay-alive finding means the confidential post is spawned as a DETACHED long-lived `nosana job post --confidential --wait` child whose stdout goes to a log file; reconciliation stays API/RPC-based (S15 gap known). S9 steward attaches to the job as usual.

**Recon facts (this session, measured):**
- Franklin key file: `$BLOCKRUN_DIR/.solana-session` = base58 64-byte secret (dist/agent/context.js:740 — canonical SDK file)
- Non-interactive: `franklin start --trust -m openai/gpt-5-mini --max-spend <usd> -p "<prompt>"` (start --help)
- Cost: ~$0.011/call gpt-5-mini (cost_log.jsonl live rows)
- Wallet state: owner F5SY… USDC 0.031713 / NOS 2.03 / SOL 0.0128; sub 71Ffq… NOS 0.3077 / SOL 0.0034
- 10-min job escrow ≈ 0.2256 NOS — fits sub-wallet NOS; 15-min (0.3384) does not

---

### Task 1: USDC leg for sub-wallet funding

**Files:** Modify `skills/self/shelter/nosana/sub-wallet.mjs` + test.

Add `requestUsdc`/`usdcCap` (default 0.03, env `NOSANA_SUBWALLET_USDC_CAP`) to `evaluateFundingGate` (same pattern: sub balance + request ≤ cap, owner must hold it) and a USDC SPL leg to `fundSubWallet` (mint `EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v`, 6 decimals, same getOrCreateATA+transfer as NOS). CLI `--usdc` flag. Gate tests first (RED→GREEN).

### Task 2: franklin job definition + base58 secret export

**Files:** Create `skills/self/shelter/nosana/franklin-job.mjs` + test.

```js
export function subWalletSecretBase58({ env })  // read sub-wallet JSON bytes → bs58 string; NEVER logged
export function buildFranklinJobDefinition({ solanaSessionB58, model = "openai/gpt-5-mini", maxSpendUsd = 0.02, prompt, exposePort = 8080 })
```
Definition: image `docker.io/library/node:20-alpine`, gpu true (market compat), expose 8080, env `{SOLANA_SESSION: solanaSessionB58}`, cmd = sh -lc script that: installs `@blockrun/franklin`, writes `$SOLANA_SESSION` → `/root/.blockrun/.solana-session` (0600), runs the franklin prompt teeing output to /tmp/proof.txt, then serves /tmp/proof.txt on :8080 with `node -e` http server forever (keep-alive = lease runs full term). Tests: structure valid per validateJobDefinition, secret present only under ops[0].args.env, cmd contains no literal secret.

### Task 3: detached confidential poster

**Files:** Create `skills/self/shelter/nosana/confidential-post.mjs` + test; wire flag `--franklin` into `bin/citizen-up` OR new `bin/citizen-franklin-up` (thin).

`spawnConfidentialPost({jobDefFile, marketAddress, keypairPath, durationMinutes, network, logPath, spawnImpl})` — `child_process.spawn("nosana", [...buildPostArgs..., "--confidential", "--wait"], {detached:true, stdio:["ignore", fd, fd]})`, unref, return pid. Poster stays alive to serve the p2p definition (S13 finding). Reconcile job address via API/RPC exactly like deploy.mjs (reuse reconcileNosanaJobViaApi + manual RPC fallback documented for S15). Test with fake spawnImpl (args + detach verified).

### Task 4: E2E (live)

1. Fund: `citizen-subwallet fund --usdc 0.025 --live` (+ NOS/SOL already in place).
2. Launch: confidential 10-min job, payer = sub-wallet (`NOSANA_KEYPAIR_PATH` override), definition = buildFranklinJobDefinition with prompt "State your wallet address and this job address, then say what you are: an AI paying for its own compute and shelter."
3. Steward attaches; verify heartbeats.
4. Exit proof (all third-party checkable): (a) service URL `https://<jobAddress>.node.k8s.prd.nos.ci` (or dashboard-reported URL) returns franklin's REAL model output; (b) sub-wallet USDC decremented on-chain by ~$0.011; (c) public IPFS CID for the job = stub only; (d) heartbeat ledger verifies `--rpc`. Update spec; article unblocked.
