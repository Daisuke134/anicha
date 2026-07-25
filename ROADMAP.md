# Roadmap

Ordered by dependency. Nothing here is marked done unless it has on-chain or test evidence behind it.

## Done

- **Acquire NOS with zero human steps.** Jupiter's keyless API means no signup and no API key, so the
  path is structurally human-free. Signature `3G63gYmCDScn...`, finalized at slot 435064669,
  NOS 0 → 2.750405.
- **Pay for compute from the agent's own keypair.** Nosana job
  `FHAjMnM1q3p5c5qCeFRjZLYEo12FUBesFPW8zvG5heAC` reached RUNNING with `payer` and `project` both set
  to the agent's own wallet. NOS 2.750405 → 2.707205.

## Next

1. **Make the exposed service actually serve.** A paid, RUNNING job returned 503 with Nosana's
   "Service Initializing" page on 28 consecutive polls. Leading suspicion: the job definition asked
   for `gpu: true` with `nginx:alpine`, an image with no CUDA runtime, so the container may never
   have started under the node's nvidia runtime. Competing possibilities: a slow image pull, a
   readiness condition the default nginx page does not satisfy, or a wrong port declaration. This
   needs the real job logs, not speculation.

2. **Self-renewing lease (the survival drive).** `nosana job extend` is broken in the vendor CLI, so
   renewal must go through `@nosana/kit` or the on-chain jobs program. Note that kit's documented
   `jobs.extend` appears to sit on the API/credits rail, which is disqualified here — if that holds,
   renewal means posting a successor job before expiry, which is what Nosana's own `SIMPLE-EXTEND`
   strategy appears to do internally. Must be idempotent per renewal window, and must die honestly
   when funds run out rather than fake survival.

3. **Externalize agent state.** Nosana documents no persistent volume, so an agent that rebuilds its
   house loses its wallet manifest, ledgers, and memory. State has to live in S3 or IPFS, and a
   rebuilt job must restore the same balance with zero double-spend.

4. **Close the earn → shelter loop.** Join revenue against the shelter cost ledger, compute remaining
   runway, and automate the rent top-up decision. Existing funding refill logic covers trading
   wallets, not shelter.

5. **Recursive self-hosting.** An agent running inside a Nosana job posting and funding a child job
   from its own surplus. Undocumented by Nosana with no official example, so this is genuinely
   unproven — it is also the crux of scaling past one machine.

## Deliberately not here

Marketplace connectors, trading strategies, platform credentials, and the operator's real wallet
addresses stay in a private repository. This repo is the generic layer: identity, treasury, food,
shelter, and the survival drive.
