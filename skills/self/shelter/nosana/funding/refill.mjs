// refill.mjs — S19: when Base revenue should become Solana rent.
//
// The agent earns USDC on Base (x402 settles there) and spends NOS + SOL on Solana (Nosana
// lease) plus USDC on Base (frontier inference, Modal boxes). Revenue therefore piles up on the
// wrong chain from the shelter's point of view — a wallet can be rich in USDC and homeless at
// the same time. This module is the pure "should we move money, and how much" decision behind
// that hop; skills/self/shelter/nosana/funding/acquire-nos.mjs already owns the real SOL->NOS
// swap and this feature's bridge leg reuses the relay.link flow proven in
// bridge-base-to-solana.mjs (apps/x402-agents/scripts) — neither is reimplemented here.
//
// Kept free of network calls, key reads, and process.env on purpose (see the module docstring in
// the plan this file implements): every number it needs arrives as an argument, so it can be
// exercised exhaustively without ever touching a wallet. The thin executor (bin/citizen-refill)
// is what reads real balances and injects real rails.

// Enough to post one fresh confidential lease (0.34 NOS escrow, measured 2026-07-26, S19 plan)
// AND still have room to extend it repeatedly (~0.03 NOS/extend) before the next refill pass —
// aiming for the bare 0.34 floor would mean every refill immediately needs another refill.
export const DEFAULT_TARGET_NOS = 1.0;

// relay.link (and the destination-chain landing fee) take a real cut of a bridge; below this
// floor, a "successful" transfer would arrive smaller than what it cost to send.
export const DEFAULT_MIN_BRIDGE_USD = 0.5;

// Base is not just a source of NOS money — it is where the agent pays for frontier inference and
// Modal boxes directly. Bridging it down to zero to feed Solana just relocates the starvation
// from one chain to the other, so this much always stays behind regardless of how short Solana is.
export const DEFAULT_KEEP_ON_BASE_USD = 1.0;

// One pass never moves more than this, no matter how large the shortfall or the Base balance
// looks — a bad quote, a bad price read, or a bug in this function can only cost one bounded
// pass, not the whole treasury. Extra passes are always available on the next tick.
export const DEFAULT_MAX_PASS_USD = 25;

// The relay leg lands as NATIVE SOL on Solana (see bridge-base-to-solana.mjs: destinationCurrency
// is the native-SOL pseudo-mint, not a token) before any of it is swapped into NOS — so a wallet
// can be "stocked" on NOS and still be unable to sign the transaction that spends it. This is the
// floor below which SOL itself, not NOS, is the thing that is short. Set well above the ~0.005
// SOL the nosana CLI/SDK refuses to sign under (skills/self/shelter/nosana/spend-gate.mjs's
// DEFAULT_SOL_FEE_FLOOR) so a refill leaves margin for more than one future signature.
export const DEFAULT_MIN_SOL_RESERVE = 0.01;

function isFiniteNumber(v) {
  return typeof v === "number" && Number.isFinite(v);
}

/**
 * Pure: should we move Base USDC to Solana right now, and how much?
 *
 * Balances are REQUIRED, not defaulted — a caller that forgets to pass one gets a refusal, not a
 * silent "assume it's fine" (same fail-closed shape as renew.mjs's evaluateRenewal).
 *
 * @returns {{act: boolean, bridgeUsd: number, needSol: boolean, needNos: boolean, reason: string}}
 */
export function planRefill({
  nosBalance,
  solBalance,
  baseUsdc,
  targetNos = DEFAULT_TARGET_NOS,
  minBridgeUsd = DEFAULT_MIN_BRIDGE_USD,
  keepOnBaseUsd = DEFAULT_KEEP_ON_BASE_USD,
  maxPassUsd = DEFAULT_MAX_PASS_USD,
  minSolReserve = DEFAULT_MIN_SOL_RESERVE,
} = {}) {
  if (!isFiniteNumber(nosBalance) || !isFiniteNumber(solBalance) || !isFiniteNumber(baseUsdc)) {
    return {
      act: false,
      bridgeUsd: 0,
      needSol: false,
      needNos: false,
      reason: "refusing to plan without real nosBalance/solBalance/baseUsdc numbers (fail-closed)",
    };
  }

  const needNos = nosBalance < targetNos;
  const needSol = solBalance < minSolReserve;

  if (!needNos && !needSol) {
    return {
      act: false,
      bridgeUsd: 0,
      needSol: false,
      needNos: false,
      reason: `stocked: ${nosBalance} NOS >= target ${targetNos} and ${solBalance} SOL >= reserve ${minSolReserve} — nothing to do`,
    };
  }

  // What Base can spare without touching its own working capital, then bounded to one pass. The
  // exact USD->NOS conversion is deliberately NOT computed here — acquire-nos.mjs already prices
  // that for real against a live Jupiter quote once the bridged SOL has landed; this module only
  // decides how large a pass is worth attempting.
  const availableUsd = Math.max(0, baseUsdc - keepOnBaseUsd);
  const bridgeUsd = Math.min(availableUsd, maxPassUsd);

  if (bridgeUsd < minBridgeUsd) {
    return {
      act: false,
      bridgeUsd: 0,
      needSol,
      needNos,
      reason: `available bridge $${availableUsd.toFixed(2)} (after keeping $${keepOnBaseUsd} on Base) is too small to be worth its fees — need at least $${minBridgeUsd}`,
    };
  }

  const what = [needNos && "NOS", needSol && "SOL"].filter(Boolean).join(" and ");
  return {
    act: true,
    bridgeUsd,
    needSol,
    needNos,
    reason: `bridging $${bridgeUsd.toFixed(2)} from Base to refill ${what} while keeping $${keepOnBaseUsd} working capital on Base`,
  };
}

/**
 * Carry out a decided plan: bridge Base USDC to Solana, then (only if NOS is what was short) swap
 * the landed SOL into NOS. Every rail is injected — this function never touches the network
 * itself; bin/citizen-refill supplies the real bridge (relay.link, mirroring
 * bridge-base-to-solana.mjs) and the real swap (acquire-nos.mjs's acquireNos).
 *
 * The bridge leg lands as NATIVE SOL on Solana, not a token (see DEFAULT_MIN_SOL_RESERVE's doc
 * comment) — so a SOL-only shortfall is already satisfied the moment the bridge confirms, and
 * swapToNos only needs to run when NOS itself was short. It runs at most once per pass, and never
 * runs at all when the bridge did not confirm: money that never arrived cannot be spent, so
 * treating a failed bridge as "try the swap anyway" would be spending funds that do not exist.
 */
export async function executeRefill({ plan, bridge, swapToNos }) {
  if (!plan || plan.act !== true) {
    return { ok: true, skipped: true, reason: (plan && plan.reason) || "no plan to act on" };
  }

  const bridgeResult = await bridge(plan.bridgeUsd);
  if (!bridgeResult || bridgeResult.ok !== true) {
    return {
      ok: false,
      skipped: false,
      reason: `bridge failed: ${(bridgeResult && bridgeResult.reason) || "unknown"}`,
      bridge: bridgeResult,
      swap: null,
    };
  }

  if (!plan.needNos) {
    return { ok: true, skipped: false, bridge: bridgeResult, swap: null };
  }

  const swapResult = await swapToNos();
  if (!swapResult || swapResult.ok !== true) {
    return {
      ok: false,
      skipped: false,
      reason: `swap failed: ${(swapResult && swapResult.reason) || "unknown"}`,
      bridge: bridgeResult,
      swap: swapResult,
    };
  }

  return { ok: true, skipped: false, bridge: bridgeResult, swap: swapResult };
}
