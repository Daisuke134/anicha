// buy-house.mjs — the tool an agent calls to house ITSELF.
//
// Until this existed, a human posted the first job and the agent only inherited the result. That
// is an allowance, not an income: the agent could pay rent but could not sign a lease. This module
// is the missing verb. Give an agent its own key and this file, and it can go from "no machine" to
// "a machine that is running me" without anyone else in the chain.
//
// Two landlords, tried in order, because an agent that can only rent from one company dies when
// that company does (Conway Research proved shelter was purchasable and is closing 2026-10-01).
//
// Money-safety: it pays from whatever capped wallet it was handed. The balance is the ceiling, and
// a hard per-call maximum stops a loop from emptying it in one pass.

export const MODAL_CREATE_URL = 'https://blockrun.ai/api/v1/modal/sandbox/create';
export const DEFAULT_MAX_SPEND_USD = 0.50; // one call can never cost more than this

/**
 * Pure: decide what to ask for, and refuse anything that could cost more than the cap.
 * Prices are the gateway's published tiers (flat for <=300s, hourly beyond).
 */
export function planPurchase({ seconds = 300, gpu, maxSpendUsd = DEFAULT_MAX_SPEND_USD } = {}) {
  const FLAT = { CPU: 0.01, T4: 0.05, L4: 0.08, A10G: 0.1, A100: 0.2, H100: 0.4 };
  const HOURLY = { CPU: 0.04, T4: 1.5, L4: 2, A10G: 2.5, A100: 4, H100: 8 };
  if (!Number.isInteger(seconds) || seconds < 1 || seconds > 86400) {
    return { ok: false, reason: 'seconds must be an integer 1..86400' };
  }
  const tier = gpu || 'CPU';
  if (!(tier in FLAT)) return { ok: false, reason: `unknown tier ${tier}` };
  const estimateUsd = seconds <= 300 ? FLAT[tier] : (HOURLY[tier] * seconds) / 3600;
  if (estimateUsd > maxSpendUsd) {
    return { ok: false, reason: `that would cost about $${estimateUsd.toFixed(4)}, over the $${maxSpendUsd} cap` };
  }
  return { ok: true, seconds, gpu, estimateUsd };
}

/** Build a fetch that settles x402 from the agent's own key. Never logs key material. */
async function payingFetch(baseKey) {
  const { wrapFetchWithPaymentFromConfig } = await import('@x402/fetch');
  const { ExactEvmScheme } = await import('@x402/evm/exact/client');
  const { privateKeyToAccount } = await import('viem/accounts');
  const account = privateKeyToAccount(baseKey.startsWith('0x') ? baseKey : `0x${baseKey}`);
  return wrapFetchWithPaymentFromConfig(fetch, {
    schemes: [{ network: 'eip155:8453', client: new ExactEvmScheme(account) }],
  });
}

/**
 * THE TOOL: an agent buys itself a machine and gets back somewhere to run.
 *
 * `payload` is what the agent wants running in the new house — a shell command. It is passed to
 * the sandbox so the new box does something the moment it exists, instead of being an empty room
 * the agent bought and never moved into.
 */
export async function buyHouse({
  baseKey = process.env.BASE_KEY,
  seconds = 300,
  gpu,
  image = 'python:3.11',
  payload,
  maxSpendUsd = DEFAULT_MAX_SPEND_USD,
  fetchImpl,
} = {}) {
  const plan = planPurchase({ seconds, gpu, maxSpendUsd });
  if (!plan.ok) return { ok: false, reason: plan.reason };
  if (!baseKey && !fetchImpl) return { ok: false, reason: 'no key to pay with' };

  const doFetch = fetchImpl || (await payingFetch(baseKey));
  const body = { image, timeout: seconds, ...(gpu ? { gpu } : {}), ...(payload ? { command: payload } : {}) };

  let res;
  try {
    res = await doFetch(MODAL_CREATE_URL, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(body),
    });
  } catch (e) {
    return { ok: false, reason: `the landlord did not answer: ${String(e.message || e).slice(0, 120)}` };
  }
  if (!res.ok) return { ok: false, reason: `the landlord refused: HTTP ${res.status}` };

  const j = await res.json();
  if (!j.sandbox_id) return { ok: false, reason: 'got a 200 with no house in it' };
  return {
    ok: true,
    rail: 'modal',
    id: j.sandbox_id,
    status: j.status,
    seconds,
    spentUsd: plan.estimateUsd,
    config: j.config,
  };
}

/** CLI so an agent with a shell can just run it: `node buy-house.mjs [seconds] [gpu]`. */
if (import.meta.url === `file://${process.argv[1]}`) {
  const seconds = Number(process.argv[2] || 300);
  const gpu = process.argv[3];
  buyHouse({ seconds, gpu, payload: process.env.HOUSE_PAYLOAD })
    .then((r) => {
      console.log(JSON.stringify(r));
      process.exit(r.ok ? 0 : 1);
    })
    .catch((e) => {
      console.error(String(e.message || e));
      process.exit(1);
    });
}
