// shelter.mjs — buying a place to live, from inside the agent, across more than one landlord.
//
// The point of two rails is survival, not price. Conway proved an agent can buy a real VM with a
// wallet, and is shutting that service down on 2026-10-01 — an agent whose shelter comes from one
// vendor dies when that vendor does. So this module treats shelter as a market: ask each landlord
// in turn, take the first that answers, and record which one answered.
//
// Rail A — BlockRun/Modal (Base USDC over x402): one HTTP call, no Solana, no NOS, no confidential
//   channel, no posting process that must stay alive. An agent inside any container can do it with
//   nothing but its Base key. Ephemeral (<=24h), Python 3.11, optional GPU.
// Rail B — Nosana (NOS/SOL on Solana): a decentralized GPU market with no owner who can switch it
//   off. Cheaper per GPU-hour, and the lease can be extended in place. Costs more moving parts.
//
// Money-safety: every call pays from a capped wallet. The cap is the balance; nothing here can
// spend more than what was deliberately put in front of it.

export const MODAL_CREATE_URL = 'https://blockrun.ai/api/v1/modal/sandbox/create';

/** Pure: pick the rails to try, in order. Explicit so a caller can pin one for a test. */
export function planRails({ prefer } = {}) {
  const all = ['modal', 'nosana'];
  if (!prefer) return all;
  return [prefer, ...all.filter((r) => r !== prefer)];
}

/**
 * Rail A: rent from BlockRun's Modal gateway with a Base key. Returns a normalized shelter record.
 * fetchImpl is injected so tests never touch the network or a wallet.
 */
export async function rentModal({ baseKey, image = 'python:3.11', timeoutSec = 300, gpu, fetchImpl }) {
  const body = { image, timeout: timeoutSec, ...(gpu ? { gpu } : {}) };
  const doFetch = fetchImpl || (await payingFetch(baseKey));
  const res = await doFetch(MODAL_CREATE_URL, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`modal rail refused: HTTP ${res.status}`);
  const j = await res.json();
  if (!j.sandbox_id) throw new Error('modal rail returned no sandbox id');
  return {
    rail: 'modal',
    id: j.sandbox_id,
    status: j.status,
    expiresInSec: timeoutSec,
    // Modal sandboxes are reached through the gateway, not a public hostname of their own.
    url: null,
    config: j.config,
  };
}

/** Build a fetch that settles x402 payments from the given Base key. Never logs the key. */
async function payingFetch(baseKey) {
  if (!baseKey) throw new Error('no Base key available for the modal rail');
  const { wrapFetchWithPaymentFromConfig } = await import('@x402/fetch');
  const { ExactEvmScheme } = await import('@x402/evm/exact/client');
  const { privateKeyToAccount } = await import('viem/accounts');
  const account = privateKeyToAccount(baseKey.startsWith('0x') ? baseKey : `0x${baseKey}`);
  return wrapFetchWithPaymentFromConfig(fetch, {
    schemes: [{ network: 'eip155:8453', client: new ExactEvmScheme(account) }],
  });
}

/**
 * Try each rail until one gives us a place to live. Returns {shelter, attempts} so a caller can
 * see which landlords declined and why — a silent fallback hides exactly the failure that matters.
 */
export async function findShelter({ rails, baseKey, nosanaRent, image, timeoutSec, gpu, fetchImpl } = {}) {
  const order = rails || planRails({});
  const attempts = [];
  for (const rail of order) {
    try {
      if (rail === 'modal') {
        const shelter = await rentModal({ baseKey, image, timeoutSec, gpu, fetchImpl });
        attempts.push({ rail, ok: true });
        return { shelter, attempts };
      }
      if (rail === 'nosana') {
        if (!nosanaRent) { attempts.push({ rail, ok: false, reason: 'no nosana renter wired' }); continue; }
        const shelter = await nosanaRent({ image, timeoutSec, gpu });
        attempts.push({ rail, ok: true });
        return { shelter: { rail: 'nosana', ...shelter }, attempts };
      }
      attempts.push({ rail, ok: false, reason: 'unknown rail' });
    } catch (e) {
      attempts.push({ rail, ok: false, reason: String(e.message || e).slice(0, 120) });
    }
  }
  const why = attempts.map((a) => `${a.rail}: ${a.reason || 'failed'}`).join('; ');
  throw new Error(`every landlord declined — ${why}`);
}
