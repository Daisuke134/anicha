import { test } from 'node:test';
import assert from 'node:assert/strict';
import { buildStatement, renderStatement, PUBLIC_FIELDS } from '../statement.mjs';

const FACTS = {
  solanaAddress: '71FfqFniYoMsWZb1qFeQDb1fk2xqvajzivpsnMb44gTf',
  baseAddress: '0xd072CDDda8371D97834859E9c840F9B0F1e51a1d',
  jobAddress: '7cu6bmHzRnnEdetrzh3QYeWFuGjgKm8J9x5rufhxDdCs',
  leaseSeconds: 600,
  spent: [
    { what: 'lease, decentralized market', usd: 0.008, chain: 'solana', ref: '7cu6bmHz' },
    { what: 'one frontier model call', usd: 0.003, chain: 'base', ref: '0x081973' },
    { what: 'second house, managed gateway', usd: 0.01, chain: 'base', ref: 'sb-85ok' },
  ],
  earned: [],
  heartbeats: [
    { cycle: 1, slot: 100, verified: true },
    { cycle: 2, slot: 200, verified: true },
  ],
};

test('buildStatement: totals what was spent and refuses to invent revenue', () => {
  const s = buildStatement(FACTS);
  assert.equal(s.spentUsd, 0.021);
  assert.equal(s.earnedUsd, 0);
  assert.equal(s.solvent, false); // funded, not earning — the honest verdict
  assert.equal(s.verdict, 'funded');
});

test('buildStatement: says "earning" only when an outsider actually paid', () => {
  const s = buildStatement({ ...FACTS, earned: [{ what: 'prompt-sanitizer call', usd: 0.005, from: 'outside' }] });
  assert.equal(s.earnedUsd, 0.005);
  assert.equal(s.verdict, 'earning');
});

test('buildStatement: self-payment is never counted as revenue', () => {
  const s = buildStatement({ ...FACTS, earned: [{ what: 'own test call', usd: 5.0, from: 'self' }] });
  assert.equal(s.earnedUsd, 0);
  assert.equal(s.verdict, 'funded');
});

test('buildStatement: liveness is the count that passed verification, not the count claimed', () => {
  const s = buildStatement({
    ...FACTS,
    heartbeats: [{ cycle: 1, verified: true }, { cycle: 2, verified: false }, { cycle: 3, verified: true }],
  });
  assert.equal(s.heartbeatsClaimed, 3);
  assert.equal(s.heartbeatsVerified, 2);
});

test('renderStatement: an undeclared field cannot reach the page, even if it is handed in', () => {
  const html = renderStatement(
    buildStatement({ ...FACTS, secretNote: 'SOLANA_SESSION=5Kd3...', apiKey: 'sk-live-abcdef' }),
  );
  assert.equal(html.includes('5Kd3'), false);
  assert.equal(html.includes('sk-live'), false);
  assert.equal(html.includes('apiKey'), false);
});

test('renderStatement: every field it does render is on the public allowlist', () => {
  const s = buildStatement(FACTS);
  const rendered = Object.keys(s);
  for (const k of rendered) assert.ok(PUBLIC_FIELDS.includes(k), `${k} is rendered but not declared public`);
});

test('renderStatement: escapes text so a hostile value cannot become markup', () => {
  const html = renderStatement(
    buildStatement({ ...FACTS, spent: [{ what: '<script>alert(1)</script>', usd: 1, chain: 'base' }] }),
  );
  assert.equal(html.includes('<script>'), false);
  assert.ok(html.includes('&lt;script&gt;'));
});

test('renderStatement: prints the zero out loud instead of hiding it', () => {
  const html = renderStatement(buildStatement(FACTS));
  assert.ok(html.includes('$0.00'));
  assert.ok(/from outside/i.test(html));
});

test('renderStatement: gives a stranger the addresses needed to check the claims', () => {
  const html = renderStatement(buildStatement(FACTS));
  assert.ok(html.includes('71FfqFniYoMsWZb1qFeQDb1fk2xqvajzivpsnMb44gTf'));
  assert.ok(html.includes('0xd072CDDda8371D97834859E9c840F9B0F1e51a1d'));
});
