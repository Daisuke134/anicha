// move-in.mjs — actually live in the house the agent bought.
//
// buy-house.mjs proved the agent can sign a lease on the managed rail. It did not prove the agent
// can LIVE there: the sandbox came up empty and nobody ever moved in. A house you own and never
// enter is not shelter, it is an asset — and an agent whose first landlord disappears needs the
// second address to be somewhere it has actually slept.
//
// The gateway exposes three verbs past create — exec, status, terminate — each taking a sandbox_id.
// So habitation here means: buy the box, run a command inside it, and read back something only a
// process running in that box could have produced.
//
// Money-safety: every call settles from whatever capped Base key it is handed. Each exec is billed,
// so the caller passes a hard ceiling on how many it may make.

export const MODAL_BASE = 'https://blockrun.ai/api/v1/modal';
export const DEFAULT_MAX_EXECS = 12; // a loop that shells forever would bill forever

/** Pure: refuse a command that cannot be executed, before paying to find out. */
export function validateCommand(command) {
  if (!Array.isArray(command) || command.length === 0) {
    return { ok: false, reason: 'command must be a non-empty array, e.g. ["sh","-c","echo hi"]' };
  }
  if (!command.every((c) => typeof c === 'string')) {
    return { ok: false, reason: 'every element of command must be a string' };
  }
  return { ok: true };
}

/**
 * Pure: decide whether this box is somewhere the agent can be said to live.
 *
 * The test is deliberately not "the API said running". A box that answers status but cannot run a
 * command is a room with the door locked. Habitation requires output that came from inside.
 */
export function assessHabitation({ created, execs }) {
  if (!created || !created.sandbox_id) return { livable: false, reason: 'no box was created' };
  const succeeded = (execs || []).filter((e) => e.ok && typeof e.stdout === 'string' && e.stdout.length > 0);
  if (succeeded.length === 0) {
    return { livable: false, reason: 'the box exists but nothing ran inside it', id: created.sandbox_id };
  }
  return { livable: true, reason: `${succeeded.length} command(s) produced output from inside`, id: created.sandbox_id };
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

async function post(doFetch, path, body) {
  const res = await doFetch(`${MODAL_BASE}/${path}`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  });
  const text = await res.text();
  let json;
  try { json = JSON.parse(text); } catch { json = { raw: text.slice(0, 300) }; }
  return { status: res.status, ok: res.ok, json };
}

/**
 * Move in: create the box, then run each command inside it and collect what came back.
 *
 * Stops at the first failure rather than pressing on, because every later exec is billed and a box
 * that refused one command is unlikely to honour the next.
 */
export async function moveIn({
  baseKey = process.env.BASE_KEY,
  commands = [['sh', '-c', 'echo alive-from-inside']],
  image = 'python:3.11',
  timeoutSec = 300,
  gpu,
  maxExecs = DEFAULT_MAX_EXECS,
  fetchImpl,
} = {}) {
  if (commands.length > maxExecs) {
    return { ok: false, reason: `${commands.length} commands exceeds the ${maxExecs} allowed in one move-in` };
  }
  for (const c of commands) {
    const v = validateCommand(c);
    if (!v.ok) return { ok: false, reason: v.reason };
  }
  if (!baseKey && !fetchImpl) return { ok: false, reason: 'no key to pay with' };

  const doFetch = fetchImpl || (await payingFetch(baseKey));
  const createBody = { image, timeout: timeoutSec, ...(gpu ? { gpu } : {}) };
  const created = await post(doFetch, 'sandbox/create', createBody);
  if (!created.ok || !created.json.sandbox_id) {
    return { ok: false, reason: `the landlord refused: HTTP ${created.status}`, detail: created.json };
  }

  const execs = [];
  for (const command of commands) {
    const r = await post(doFetch, 'sandbox/exec', { sandbox_id: created.json.sandbox_id, command });
    const stdout = r.json.stdout ?? r.json.output ?? r.json.result ?? '';
    execs.push({ ok: r.ok, status: r.status, command, stdout: String(stdout), stderr: String(r.json.stderr ?? ''), detail: r.ok ? undefined : r.json });
    if (!r.ok) break;
  }

  const verdict = assessHabitation({ created: created.json, execs });
  return { ok: verdict.livable, ...verdict, sandbox: created.json, execs };
}

/** CLI: node move-in.mjs "shell command" [seconds] */
if (import.meta.url === `file://${process.argv[1]}`) {
  const cmd = process.argv[2] || 'echo alive-from-inside';
  const seconds = Number(process.argv[3] || 300);
  moveIn({ commands: [['sh', '-c', cmd]], timeoutSec: seconds })
    .then((r) => {
      console.log(JSON.stringify(r, null, 2));
      process.exit(r.ok ? 0 : 1);
    })
    .catch((e) => { console.error(String(e.message || e)); process.exit(1); });
}
