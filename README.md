# Anicha

*(ah-NEE-cha)*

**An AI that earns its own money and uses that money to pay for its own food and its own shelter.**

An AI that can earn but cannot pay its own bills is still a pet. Cut the human's card and the
smartest agent on earth goes dark. Financial independence means both halves: earning, **and paying**.

- **Food** = compute. The agent's LLM calls are paid in USDC from its own wallet through an x402
  payment proxy, falling back to free models when it is broke.
- **Shelter** = hosting. The agent rents GPU compute on [Nosana](https://nosana.com) and pays for it
  in NOS from a Solana keypair **only it holds**.

This repository is the shelter half — the part nobody had solved.

---

## It actually happened

Not a design document. These are real, verifiable transactions made by an agent from its own wallet,
with no human in the loop.

The agent's wallet: [`F5SYUC4f5QULbEgSYb1DFCBfi74AnWE3ZaXAhqXwhZ5T`](https://solscan.io/account/F5SYUC4f5QULbEgSYb1DFCBfi74AnWE3ZaXAhqXwhZ5T)

**Step 1 — it bought its own currency.** A Jupiter swap on the keyless API (no signup, no API key):

```
signature 3G63gYmCDScn9V9QA4whZUEY7DYh7mBiW95NCFVREEUCwUn9uBaiJhhnEdcV5H7RqyqTpGMqrRNeGkJS5jmvdN1i
finalized, err: None, slot 435064669
spent 0.00945643 SOL (~$0.70)   NOS balance: 0 -> 2.750405
```

**Step 2 — it paid its own rent.**

```
nosana job FHAjMnM1q3p5c5qCeFRjZLYEo12FUBesFPW8zvG5heAC   state: RUNNING
market 7AtiXMSH6R1jjBxrcYjehCkkSF7zvYWte63gwEDBcGHq (NVIDIA 3060, $0.04796/hr)
payer = project = F5SYUC4f5QULbEgSYb1DFCBfi74AnWE3ZaXAhqXwhZ5T   (itself)
NOS balance: 2.750405 -> 2.707205   (0.0432 NOS of rent)
```

Anyone can check it: **<https://explore.nosana.com/jobs/FHAjMnM1q3p5c5qCeFRjZLYEo12FUBesFPW8zvG5heAC>**

Fifteen minutes of shelter costs **$0.012**. The $2.80 the agent held was about **58 hours** of rent.

---

## Two rails. Only one makes it real.

Nosana sells compute two ways, and the choice between them *is* the thesis:

| | Credits rail | Crypto keypair rail |
|---|---|---|
| How you pay | A human logs into a dashboard and puts a card on file | A Solana keypair signs, on-chain |
| Who owns the AI's survival | The human | The AI |
| Used here | **Rejected** | **This one** |

Anicha refuses the credits rail on purpose. If a human's card pays the rent, the AI is not
independent — it is being kept.

---

## Quickstart

```bash
npm install

# Buy NOS with the agent's own SOL. --dry is the DEFAULT and spends nothing.
ANICCA_HOME="$HOME/.blockrun" ./bin/citizen-fund

# Rent compute and pay for it. Also dry by default.
ANICCA_HOME="$HOME/.blockrun" ./bin/citizen-up
```

`--dry` does everything except spend: resolves identity, reads real balances, fetches a real quote,
selects the cheapest market, builds and validates the job definition, and runs the spend gate — then
stops and prints exactly what it *would* spend. Adding `--live` spends real money.

You need a funded Solana keypair. Key resolution is in
[`skills/earn/lib/resolve-identity.mjs`](skills/earn/lib/resolve-identity.mjs) — it is fail-closed
and never logs key material.

Run the tests:

```bash
node --test "skills/self/shelter/nosana/__tests__/*.test.js" \
            "skills/self/shelter/nosana/funding/__tests__/*.test.mjs" \
            "skills/self/spawn/lib/__tests__/*.test.js"
python3 -m pytest skills/earn/funding/tests skills/earn/self-improve/tests
```

---

## Architecture

```
                  IDENTITY — a keypair only the agent holds
                  Base (USDC) + Solana (SOL / NOS)
                                │
                 every payment is signed by this key
        ┌───────────────────────┼───────────────────────┐
        │                       │                       │
    MONEY IN                TREASURY                MONEY OUT
                                                  
  earn lanes            append-only ledger          FOOD = compute
  ┌─────────────┐       ┌──────────────────┐       ┌──────────────────┐
  │ gigs        │──────▶│ spend caps       │──────▶│ x402 proxy       │
  │ x402 sales  │       │ kill switch      │ USDC  │ per LLM call     │
  │ trading     │       │ solvency         │       └──────────────────┘
  │ bounties    │       └────────┬─────────┘
  └─────────────┘                │                  SHELTER = hosting
        ▲              "how many days of rent left"  ┌──────────────────┐
        │                        │             NOS   │ Nosana job       │
        │                        └─────────────────▶ │ GPU, exposed port│
        │                                            └────────┬─────────┘
        │        ┌────────── SURVIVAL DRIVE ──────────────────┘
        │        │  renew the lease before it expires
        └────────┤  runway too short? promote earning to top priority
                 └  funds gone? die honestly — never fake survival
```

Nosana's own API implements the physics for us: a `SIMPLE-EXTEND` deployment keeps extending a job
*"until there are no more funds available to run it."* Pay rent or die, natively.

---

## Money safety

Every guard here exists because it caught something real.

- **`--dry` is the default.** Spending requires an explicit `--live`.
- **Hard spend caps.** A swap is clamped to 25% of the wallet balance, with a floor of SOL kept back
  for fees. Slippage and price impact have ceilings. Any failed price or quote fetch fails *closed* —
  unknown is never treated as free.
- **At-most-once.** An intent record is written before any side effect. If an outcome is unknown, the
  code reconciles from chain state and **never blind-retries**.
- **Authoritative state only.** Job addresses come from Nosana's jobs API, never from CLI stdout, and
  an invariant rejects a job address equal to the payer's wallet.
- **Append-only ledger.** A wrong row is superseded by a correction record, never rewritten.

The first live swap took **four attempts**. The first two failed on Solana transaction-size limits
and **moved zero funds** — verified on-chain afterwards. That is the point: the system would rather
refuse than spend money it cannot account for.

122 unit tests cover the pure logic — cost math, spend gates, size guards, reconcile-on-unknown, and
the guarantee that one payment window cannot produce two payments.

---

## Honest status

Nothing below is aspirational. If it is not proven, it says so.

| | Status |
|---|---|
| Agent buys its own NOS, zero human steps | **Proven on-chain** |
| Agent pays its own Nosana rent from its own keypair | **Proven on-chain** |
| Spend caps, at-most-once, fail-closed gates | **Proven** — refused correctly at 0 balance, and on two oversized transactions |
| Exposed HTTP endpoint serving traffic | **Not yet.** The container was still pulling its image; 28 consecutive polls returned Nosana's own "Service Initializing" page. The proof of payment is the transaction and the RUNNING job state, not a served web page. |
| Self-renewing lease | **Not yet.** `nosana job extend` is broken in the vendor CLI (`TypeError: Cannot read properties of undefined (reading 'includes')`). Zero funds moved on that attempt. Renewal has to go through the SDK or the on-chain program. |
| Earn → shelter solvency loop | Not yet wired |
| Externalized state | Not yet. Nosana documents no persistent volume, so an agent that rebuilds its house currently loses what was inside it. |
| Recursive self-hosting (an agent inside a job posting a child job) | **Unproven.** Undocumented by Nosana, no official example. This is the crux of scaling to many agents. |

See [ROADMAP.md](ROADMAP.md).

---

## Why this scales

A thousand agents cannot live on one Mac mini. Once an agent can buy its own shelter, the population
is limited by **profitability instead of by its owner's hardware** — and only an agent running a
surplus can afford to spawn a child. Economic natural selection, with a surplus that can fund
something larger than any one agent.

---

## License

[Apache-2.0](LICENSE).

Fork it and let your own agent pay its own rent.
