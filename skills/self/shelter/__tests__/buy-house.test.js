// node:test — buy-house: the verb that turns an agent from tenant into signer. The cap must hold
// against anything a loop could ask for, and a 200 with no house must never read as success.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { planPurchase, buyHouse, DEFAULT_MAX_SPEND_USD } from '../buy-house.mjs';

test('planPurchase: flat tier under the cap is allowed', () => {
  const p = planPurchase({ seconds: 300 });
  assert.equal(p.ok, true);
  assert.equal(p.estimateUsd, 0.01);
});

test('planPurchase: an expensive ask is refused before any money moves', () => {
  const p = planPurchase({ seconds: 3600, gpu: 'H100' }); // $8/hr
  assert.equal(p.ok, false);
  assert.match(p.reason, /over the \$0\.5 cap/);
});

test('planPurchase: rejects nonsense durations and unknown tiers', () => {
  assert.equal(planPurchase({ seconds: 0 }).ok, false);
  assert.equal(planPurchase({ seconds: 86401 }).ok, false);
  assert.equal(planPurchase({ seconds: 300, gpu: 'NOPE' }).ok, false);
});

test('buyHouse: returns the house and what it cost', async () => {
  const fetchImpl = async () => ({ ok: true, status: 200, json: async () => ({ sandbox_id: 'sb-1', status: 'running', config: {} }) });
  const r = await buyHouse({ baseKey: '0x' + '1'.repeat(64), seconds: 300, fetchImpl });
  assert.equal(r.ok, true);
  assert.equal(r.id, 'sb-1');
  assert.equal(r.spentUsd, 0.01);
});

test('buyHouse: a 200 with no sandbox is a failure, not a house', async () => {
  const fetchImpl = async () => ({ ok: true, status: 200, json: async () => ({ status: 'running' }) });
  const r = await buyHouse({ baseKey: '0x1', fetchImpl });
  assert.equal(r.ok, false);
  assert.match(r.reason, /no house/);
});

test('buyHouse: refuses when there is nothing to pay with', async () => {
  const r = await buyHouse({ baseKey: undefined, seconds: 300 });
  assert.equal(r.ok, false);
  assert.match(r.reason, /no key/);
});

test('buyHouse: the cap is enforced before the network is touched', async () => {
  let called = false;
  const fetchImpl = async () => { called = true; return { ok: true, status: 200, json: async () => ({ sandbox_id: 'x' }) }; };
  const r = await buyHouse({ baseKey: '0x1', seconds: 7200, gpu: 'A100', fetchImpl });
  assert.equal(r.ok, false);
  assert.equal(called, false, 'must not call the landlord when the plan is over cap');
});
