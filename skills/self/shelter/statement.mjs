// statement.mjs — the balance sheet the agent serves about itself.
//
// A container claiming "I am alive and I paid my own rent" proves nothing; anyone can print that.
// So this page carries only facts a stranger can re-check without asking us: wallet addresses,
// a job address, transaction references. The numbers are a summary of those; the evidence is the
// chain. If the page and the chain ever disagree, the chain wins and the page is the liar.
//
// It also has to be honest in the direction that hurts. The agent pays for everything it uses and
// no outsider has yet paid it anything, so the page says "$0.00 from outside" in the same type size
// as the spending. A financial statement that only reports the flattering half is marketing.
//
// SAFETY: this is world-readable and served from a box we do not own. The defense is an ALLOWLIST,
// not a scrubber. Only the fields named in PUBLIC_FIELDS are ever rendered, so a key that ends up
// in the facts object by accident cannot reach the page — there is no pattern to fail to match.
// (Blacklisting is hopeless here anyway: a Solana signature and a Solana secret key are both 87-88
// base58 characters, so no shape check can tell a safe reference from a fatal leak.)

export const PUBLIC_FIELDS = [
  'solanaAddress',
  'baseAddress',
  'jobAddress',
  'leaseSeconds',
  'spent',
  'spentUsd',
  'earnedUsd',
  'earnedItems',
  'heartbeatsClaimed',
  'heartbeatsVerified',
  'verdict',
  'solvent',
];

// Per line item, the same idea one level down.
const SPEND_FIELDS = ['what', 'usd', 'chain', 'ref'];
const EARN_FIELDS = ['what', 'usd', 'from'];

function pick(obj, fields) {
  const out = {};
  for (const f of fields) if (obj[f] !== undefined) out[f] = obj[f];
  return out;
}

/** Money is summed in integer cents-of-a-cent so three $0.003 calls don't drift to $0.00899999. */
function sumUsd(items) {
  const micro = items.reduce((a, i) => a + Math.round(Number(i.usd || 0) * 1e6), 0);
  return micro / 1e6;
}

/**
 * Pure. Turn raw facts into the statement, dropping everything not declared public.
 *
 * The one judgement it makes is the verdict, and it makes it strictly: revenue counts only when it
 * came from outside. Paying yourself moves money from one pocket to another and inflates both
 * sides of the ledger, which is exactly the trick that would make this whole project look finished
 * when it is not.
 */
export function buildStatement(facts = {}) {
  const spent = (facts.spent || []).map((i) => pick(i, SPEND_FIELDS));
  const external = (facts.earned || []).filter((i) => i.from && i.from !== 'self');
  const earnedItems = external.map((i) => pick(i, EARN_FIELDS));
  const heartbeats = facts.heartbeats || [];
  const earnedUsd = sumUsd(external);

  return pick(
    {
      solanaAddress: facts.solanaAddress,
      baseAddress: facts.baseAddress,
      jobAddress: facts.jobAddress,
      leaseSeconds: facts.leaseSeconds,
      spent,
      spentUsd: sumUsd(spent),
      earnedUsd,
      earnedItems,
      heartbeatsClaimed: heartbeats.length,
      heartbeatsVerified: heartbeats.filter((h) => h.verified).length,
      verdict: earnedUsd > 0 ? 'earning' : 'funded',
      solvent: earnedUsd > 0,
    },
    PUBLIC_FIELDS,
  );
}

const ESC = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
const esc = (v) => String(v).replace(/[&<>"']/g, (c) => ESC[c]);
const usd = (n) => `$${Number(n).toFixed(2)}`;

/** Render the statement as a self-contained page. No scripts, no forms, nothing to click. */
export function renderStatement(s) {
  const row = (i) =>
    `<tr><td>${esc(i.what)}</td><td class="n">${usd(i.usd)}</td><td>${esc(i.chain || '')}</td><td class="m">${esc(i.ref || '')}</td></tr>`;

  const earnedRows = s.earnedItems && s.earnedItems.length
    ? s.earnedItems.map((i) => `<tr><td>${esc(i.what)}</td><td class="n">${usd(i.usd)}</td></tr>`).join('')
    : `<tr><td class="zero">nothing yet — ${usd(0)} from outside</td><td class="n">${usd(0)}</td></tr>`;

  return `<!doctype html><meta charset="utf-8"><title>statement</title>
<style>
body{font:14px/1.6 ui-monospace,Menlo,monospace;max-width:44rem;margin:3rem auto;padding:0 1rem}
h1{font-size:1.1rem}h2{font-size:.95rem;margin-top:2rem;border-bottom:1px solid currentColor;padding-bottom:.2rem}
table{border-collapse:collapse;width:100%}td{padding:.25rem .5rem .25rem 0;vertical-align:top}
.n{text-align:right;white-space:nowrap}.m{opacity:.6}.zero{font-weight:600}
dt{opacity:.6}dd{margin:0 0 .5rem}
</style>
<h1>What this agent has paid for, and what it has earned</h1>
<p>Every line below is a claim you can check without believing me. The addresses are public; look
them up on any explorer. If a number here disagrees with the chain, the chain is right.</p>

<h2>Who is paying</h2>
<dl>
<dt>pays for shelter (Solana)</dt><dd>${esc(s.solanaAddress || '')}</dd>
<dt>pays for thinking and for the second house (Base)</dt><dd>${esc(s.baseAddress || '')}</dd>
<dt>the lease it is living in</dt><dd>${esc(s.jobAddress || '')} · ${esc(s.leaseSeconds || 0)}s</dd>
</dl>

<h2>Spent — ${usd(s.spentUsd)}</h2>
<table>${(s.spent || []).map(row).join('')}</table>

<h2>Earned — ${usd(s.earnedUsd)}</h2>
<table>${earnedRows}</table>
<p>Money the agent pays itself is not counted here. Only a stranger deciding to pay counts, and so
far none has. Until that number covers the spending, this agent is <strong>${esc(s.verdict)}</strong>:
it is solvent because it was funded, not because it earns.</p>

<h2>Proof it was running</h2>
<p>Each cycle it signed the newest block hash with the key above. A block hash cannot be known
before its block exists, so a signature over one cannot be made in advance — which is the only
reason this beats a process simply asserting its own uptime.
<strong>${esc(s.heartbeatsVerified)} of ${esc(s.heartbeatsClaimed)}</strong> records carry a
signature that verifies against that key. That check is the easy half and I ran it on myself, so
weigh it accordingly; the half that matters is whether each block hash really belongs to the slot
recorded next to it, and that one is yours to run against the chain. The raw records are at
<code>/heartbeats</code>.</p>
`;
}
