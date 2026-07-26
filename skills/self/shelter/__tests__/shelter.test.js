// node:test — shelter: an agent must survive its landlord. These tests pin the behaviour that
// makes that true: try rails in order, never hide which one declined, and refuse silently-empty
// answers instead of returning a shelter that does not exist.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { planRails, rentModal, findShelter } from '../shelter.mjs';

const okRes = (body) => ({ ok: true, status: 200, json: async () => body });

test('planRails: both rails, caller can pin the first', () => {
  assert.deepEqual(planRails({}), ['modal', 'nosana']);
  assert.deepEqual(planRails({ prefer: 'nosana' }), ['nosana', 'modal']);
});

test('rentModal: normalizes a real gateway response', async () => {
  const fetchImpl = async () => okRes({ sandbox_id: 'sb-abc', status: 'running', config: { image: 'python:3.11' } });
  const s = await rentModal({ baseKey: '0x' + '1'.repeat(64), timeoutSec: 300, fetchImpl });
  assert.equal(s.rail, 'modal');
  assert.equal(s.id, 'sb-abc');
  assert.equal(s.status, 'running');
  assert.equal(s.expiresInSec, 300);
});

test('rentModal: a 200 with no sandbox id is a failure, not a shelter', async () => {
  const fetchImpl = async () => okRes({ status: 'running' });
  await assert.rejects(rentModal({ baseKey: '0x1', fetchImpl }), /no sandbox id/);
});

test('findShelter: falls through to the second landlord and records the first one declining', async () => {
  const fetchImpl = async () => ({ ok: false, status: 402, json: async () => ({}) });
  const nosanaRent = async () => ({ id: 'job-xyz', url: 'https://x.node.k8s.prd.nos.ci' });
  const { shelter, attempts } = await findShelter({ baseKey: '0x1', fetchImpl, nosanaRent });
  assert.equal(shelter.rail, 'nosana');
  assert.equal(shelter.id, 'job-xyz');
  assert.equal(attempts[0].ok, false);
  assert.match(attempts[0].reason, /HTTP 402/);
});

test('findShelter: when every landlord declines it says which and why', async () => {
  const fetchImpl = async () => ({ ok: false, status: 500, json: async () => ({}) });
  await assert.rejects(
    findShelter({ baseKey: '0x1', fetchImpl }),
    /every landlord declined.*modal.*nosana/s,
  );
});
