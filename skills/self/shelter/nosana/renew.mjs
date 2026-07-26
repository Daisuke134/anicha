// renew.mjs — extend a running Nosana lease before it expires (S15: the 24/7 piece).
//
// Why not the CLI: `nosana job extend` crashes before it does any work —
// dist/src/cli/job/extend/action.js:23 calls `nosana.solana.config.network.includes('devnet')`
// on an undefined config.network, purely to build a display URL (measured 2026-07-26). The SDK's
// own `jobs.extend(job, seconds, instructionOnly, payer)` is fine, so we call that directly.
//
// The lease is what keeps a self-paying agent alive. Renewing costs only the extra runtime
// (the escrow for the added minutes), which is far cheaper than posting a fresh confidential job
// and re-delivering its definition — and it keeps the SAME container, so nothing restarts.
//
// Money-safety: pays from the SAME capped sub-wallet that posted the job. Never touches the
// canonical key. Refuses to extend past a total-lease ceiling so a runaway loop cannot drain it.

import fs from "node:fs";

export const DEFAULT_RENEW_MARGIN_SEC = 180; // start renewing when this much lease is left
export const DEFAULT_EXTEND_SEC = 600; // add 10 minutes per renewal
export const DEFAULT_MAX_TOTAL_SEC = 6 * 60 * 60; // never let one lease exceed 6h without a human

/** Pure: should we renew now? Returns {renew, reason, remainingSec}. */
export function evaluateRenewal({ job, nowTs, marginSec = DEFAULT_RENEW_MARGIN_SEC, maxTotalSec = DEFAULT_MAX_TOTAL_SEC }) {
  if (!job || typeof job !== "object") return { renew: false, reason: "no job", remainingSec: null };
  const state = Number(job.state);
  if (state !== 1) return { renew: false, reason: `job not running (state ${state})`, remainingSec: null };
  const timeStart = Number(job.timeStart || 0);
  const timeout = Number(job.timeout || 0);
  if (!timeStart || !timeout) return { renew: false, reason: "lease bounds unknown", remainingSec: null };
  const remainingSec = timeStart + timeout - nowTs;
  if (timeout >= maxTotalSec) {
    return { renew: false, reason: `lease already ${timeout}s, at/over the ${maxTotalSec}s ceiling`, remainingSec };
  }
  if (remainingSec > marginSec) {
    return { renew: false, reason: `${Math.round(remainingSec)}s left, margin is ${marginSec}s`, remainingSec };
  }
  return { renew: true, reason: `${Math.round(remainingSec)}s left — renewing`, remainingSec };
}

/** Load a Solana Keypair from a 64-byte JSON-array keypair file. Never logs the bytes. */
async function loadKeypair(keypairPath) {
  const { Keypair } = await import("@solana/web3.js");
  const bytes = Uint8Array.from(JSON.parse(fs.readFileSync(keypairPath, "utf8")));
  if (bytes.length !== 64) throw new Error("renew: keypair file must contain 64 bytes");
  return Keypair.fromSecretKey(bytes);
}

/**
 * Extend a live job via the SDK (CLI-free). Returns the tx signature.
 * sdkPath defaults to the globally-installed CLI's bundled SDK, which is the copy proven to work
 * against mainnet on this machine.
 */
export async function extendLease({
  jobAddress,
  keypairPath,
  extendSec = DEFAULT_EXTEND_SEC,
  network = "mainnet",
  sdkPath = "/opt/homebrew/lib/node_modules/@nosana/cli/node_modules/@nosana/sdk/dist/index.js",
  sdkFactory,
}) {
  if (!jobAddress || !keypairPath) throw new Error("renew: jobAddress and keypairPath are required");
  const payer = await loadKeypair(keypairPath);
  const sdk = sdkFactory
    ? sdkFactory({ payer, network })
    : await (async () => {
        const mod = await import(sdkPath);
        const Client = mod.Client || mod.default;
        const bs58 = (await import("bs58")).default;
        return new Client(network, bs58.encode(payer.secretKey));
      })();
  return sdk.jobs.extend(jobAddress, extendSec, false, payer);
}
