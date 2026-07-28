# S21 Modal-to-Nosana Bootstrap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans and superpowers:test-driven-development task-by-task.

**Goal:** A paid managed Python sandbox, not the Mac, posts or recovers Franklin's confidential Nosana job, delivers its private definition, and exits after the Nosana runtime proves signed heartbeat, financial statement, and self-renewal.

**Architecture:** Modal is a short-lived bootstrap/poster rail. Exec 1 installs pinned Python dependencies and creates an ephemeral sealed-box keypair inside the sandbox. The caller encrypts the capped Solana/Base sub-wallet material to that public key. Exec 2 receives only ciphertext, decrypts in the sandbox, reconciles an existing active Nosana job before spending, otherwise hand-builds and signs the official Anchor `list` instruction, then repeatedly delivers the confidential definition to the claimed node. Nosana chain/API is the durable restart state; the sandbox and Mac are not.

**Tech Stack:** Python 3.11, solders 0.27.1, PyNaCl 1.6.2, requests 2.34.2, base58 2.1.1, Node 20+, BlockRun x402 Modal adapter, Solana JSON-RPC, Nosana Jobs program.

## Verified constraints and copied behavior

- Official CLI confidential behavior: `src/cli/job/post/action.ts` pins `privateBlankJobDefintion` instead of the secret flow, then `postJobDefinitionUntilSuccess` POSTs the real definition to the claimed node and retries every 5 seconds.  
  Source: https://github.com/nosana-ci/nosana-cli/blob/main/src/cli/job/post/action.ts  
  Quote: `options.confidential ? privateBlankJobDefintion : json_flow`.
- Official on-chain account contract: `list(ipfs_job: [u8; 32], timeout: i64)` creates the job, requires `job`, `market`, `run`, `user`, `vault`, `payer`, rewards accounts, authority, token program, and system program.  
  Source: https://github.com/nosana-ci/nosana-programs/blob/main/programs/nosana-jobs/src/instructions/list.rs  
  Quote: `pub fn handler(&mut self, ipfs_job: [u8; 32], timeout: i64)`.
- Official CLI output proves a posted job exposes a provider URL and reports job, market, duration, and cost.  
  Source: https://learn.nosana.com/inference/quick_start.html  
  Quote: `Service will be exposed at https://...node.k8s.prd.nos.ci`.
- The confidential public stub is immutable and already pinned by prior live posts at CID `QmYBbVdWFgfoTEdPT7mnaXJz6zQzfKb1Pts4A5B9kDMBph`. S21 verifies both the CID digest and gateway body before listing; it does not use Nosana's embedded Pinata JWT or require a new human credential.
- Modal accepts managed Python for at most 300 seconds and exposes create/exec, not a persistent deployment primitive. Modal therefore bootstraps and hands off; Nosana hosts the continuing runtime.

## Global constraints

- No private key, seed, decrypted bundle, command, or job definition containing a secret may enter stdout, stderr, evidence, Git, Telegram, or the public IPFS stub.
- The second exec receives only sealed ciphertext. The corresponding private decryption key is generated and remains inside the named sandbox.
- Before any list transaction, reconcile all payer jobs. An active queued/running job is recovered; a new job is listed only when none exists.
- Listing must use the current market's fixed escrow requirement and preserve the `0.34 NOS` move-out reserve plus `0.005 SOL` fee floor.
- Every transaction requires RPC confirmation and a fresh Nosana API readback binding payer, job, market, and state.
- A delivery loop is finite and succeeds only after the node returns 2xx and the job transitions to running.
- Completion requires two bootstrap passes for one job, exactly one list transaction, the Mac Franklin loop still loaded but holding no cloud writer lease, continuing cloud heartbeat/statement, one in-container renewal, secret scan clean, and provider receipts. This is the non-destructive replacement for the stale “stop the Mac loop” proof: cloud authority is demonstrated by a lease/receipt invariant, not by unloading a working local service.

---

### Task 1: Lock the Python Solana instruction contract

**Files:**
- Create: `skills/self/shelter/python/nosana_bootstrap.py`
- Create: `skills/self/shelter/python/test_nosana_bootstrap.py`
- Create: `skills/self/shelter/python/requirements-nosana-bootstrap.txt`

**Interfaces:**
- `decode_confidential_stub_cid(cid) -> bytes`
- `derive_list_accounts(payer, job, run, market) -> list[AccountMeta]`
- `build_list_instruction(payer, job, run, market, timeout_sec, cid) -> Instruction`
- `build_authorization(hash_string, secret_bytes, now_ms) -> str`

- [x] Write RED tests for the known CID digest, Anchor discriminator/data, exact account order/signer/writable flags, PDA/ATA derivation, and authorization signature.
- [x] Generate one independent golden instruction with the installed official `@nosana/sdk` `instructionOnly` path and require byte-for-byte parity.
- [x] Implement the minimum solders-based builder copied from the official Rust account struct and JS SDK account derivation.
- [x] Run focused Python tests GREEN and commit.

### Task 2: Implement exactly-once post, recovery, and confidential delivery

**Files:**
- Modify: `skills/self/shelter/python/nosana_bootstrap.py`
- Modify: `skills/self/shelter/python/test_nosana_bootstrap.py`

**Interfaces:**
- `reconcile_active_job(payer, jobs_api) -> job | None`
- `evaluate_post_gate(market, balances, reserve) -> decision`
- `list_job(...) -> {signature, jobAddress, runAddress}`
- `deliver_definition_until_running(...) -> delivery receipt`
- CLI modes: `prepare-key`, `bootstrap`

- [x] Write RED tests proving active-job recovery sends no transaction, empty state sends one transaction, unknown confirmation never retries, fixed escrow/reserve enforcement, bounded delivery retry, and payer/job/market readback validation.
- [x] Implement sealed-box key generation/decryption with 0600 sandbox files and output allowlisting.
- [x] Implement Solana RPC transaction submission/confirmation and Nosana API reconciliation.
- [x] Implement official authorization header and 5-second confidential delivery retry.
- [x] Run the full Python shelter suite GREEN and commit.

### Task 3: Add the paid Modal adapter

**Files:**
- Create: `skills/self/shelter/python/modal-nosana-bootstrap.mjs`
- Create: `skills/self/shelter/python/test_modal_nosana_bootstrap.mjs`

**Interfaces:**
- `buildPrepareCommand() -> string[]`
- `sealBootstrapBundle({sandboxPublicKey, solanaSecret, baseKey, definition}) -> chunks`
- `buildBootstrapCommand({ciphertextChunks}) -> string[]`
- `bootstrapNosanaFromModal(...) -> safe receipt`

- [ ] Write RED tests for two-exec order, 2,000-character command parts, pinned dependencies, no plaintext secret in either command, sandbox-ID binding, allowlisted output, and restart recovery.
- [ ] Package only public Python source in exec 1; encrypt secrets after its public key returns.
- [ ] Reuse `moveIn`'s paying fetch while extending it with an explicit same-sandbox exec helper; cap at create + two execs.
- [ ] Run Node/Python/shelter regression suites GREEN and commit.

### Task 4: Live proof and Mac cutover

**Files:**
- Create: `specs/evidence/s21-modal-nosana-bootstrap-<sandbox-id>.json`
- Modify: `specs/00-SHELTER-INDEPENDENCE.md`
- Modify after anicha push: `/Users/anicca/Projects/life-manager-main/docs/superpowers/specs/2026-07-19-anicca-one-repo-consolidation-spec.md`

- [ ] Fresh-read sub-wallet SOL/NOS/Base balances; use the existing S19 refill rail only if the fixed escrow plus move-out reserve is not funded.
- [ ] Run one paid Modal bootstrap. Require create/exec receipts, list signature `finalized`, Nosana job readback, confidential delivery 2xx, and public IPFS body equal only to the stub.
- [ ] Fetch the Nosana service statement and at least two signed heartbeats; verify signatures and Solana slots independently.
- [ ] Keep `ai.anicca.franklin-loop` loaded; prove the cloud job owns the writer lease, the Mac emits no duplicate cloud writes, and the same cloud job continues heartbeats and serves the statement.
- [ ] Run a second paid Modal bootstrap after the first sandbox is gone. Require recovery of the same job, zero second list transaction, and successful re-delivery/reconciliation.
- [ ] Observe one in-container lease extension and independently verify its transaction plus increased timeout.
- [ ] Run secret-pattern scans, all test suites, `git diff --check`, and fresh provider/API/RPC readbacks.
- [ ] Mark S21 complete in both SSOTs, advance the cursor to `EARN-HC-1`, commit task-owned files, and push both repositories.
