import { test } from 'node:test';
import assert from 'node:assert/strict';
import { moveIn, validateCommand, assessHabitation, DEFAULT_MAX_EXECS } from '../move-in.mjs';

const okFetch = (log = []) => async (url, init) => {
  const body = JSON.parse(init.body);
  log.push(url);
  if (url.endsWith('/sandbox/create')) {
    return { ok: true, status: 200, text: async () => JSON.stringify({ sandbox_id: 'sb-1', status: 'running' }) };
  }
  return { ok: true, status: 200, text: async () => JSON.stringify({ stdout: `ran:${body.command.join(' ')}` }) };
};

test('validateCommand refuses shapes the gateway would reject', () => {
  assert.equal(validateCommand([]).ok, false);
  assert.equal(validateCommand('echo hi').ok, false);
  assert.equal(validateCommand(['sh', 2]).ok, false);
  assert.equal(validateCommand(['sh', '-c', 'echo hi']).ok, true);
});

test('a box that answers status but runs nothing is not somewhere the agent lives', () => {
  const v = assessHabitation({ created: { sandbox_id: 'sb-1', status: 'running' }, execs: [] });
  assert.equal(v.livable, false);
  assert.match(v.reason, /nothing ran inside/);
});

test('habitation means output that came from inside', () => {
  const v = assessHabitation({ created: { sandbox_id: 'sb-1' }, execs: [{ ok: true, stdout: 'alive' }] });
  assert.equal(v.livable, true);
});

test('an exec that succeeds with empty output does not count as living there', () => {
  const v = assessHabitation({ created: { sandbox_id: 'sb-1' }, execs: [{ ok: true, stdout: '' }] });
  assert.equal(v.livable, false);
});

test('moveIn creates the box then runs inside it, in that order', async () => {
  const log = [];
  const r = await moveIn({ fetchImpl: okFetch(log), commands: [['sh', '-c', 'echo hi']] });
  assert.equal(r.ok, true);
  assert.match(log[0], /sandbox\/create$/);
  assert.match(log[1], /sandbox\/exec$/);
});

test('moveIn stops at the first failed exec instead of billing for the rest', async () => {
  let execCount = 0;
  const fetchImpl = async (url) => {
    if (url.endsWith('/sandbox/create')) return { ok: true, status: 200, text: async () => JSON.stringify({ sandbox_id: 'sb-1' }) };
    execCount++;
    return { ok: false, status: 500, text: async () => JSON.stringify({ error: 'boom' }) };
  };
  const r = await moveIn({ fetchImpl, commands: [['sh', '-c', 'a'], ['sh', '-c', 'b'], ['sh', '-c', 'c']] });
  assert.equal(r.ok, false);
  assert.equal(execCount, 1, 'it must not keep paying after a refusal');
});

test('moveIn refuses more commands than the exec ceiling allows', async () => {
  const many = Array.from({ length: DEFAULT_MAX_EXECS + 1 }, () => ['sh', '-c', 'echo x']);
  const r = await moveIn({ fetchImpl: okFetch(), commands: many });
  assert.equal(r.ok, false);
  assert.match(r.reason, /exceeds/);
});

test('moveIn reports the landlord refusing rather than pretending it moved in', async () => {
  const fetchImpl = async () => ({ ok: false, status: 402, text: async () => JSON.stringify({ error: 'Payment Required' }) });
  const r = await moveIn({ fetchImpl, commands: [['sh', '-c', 'echo hi']] });
  assert.equal(r.ok, false);
  assert.match(r.reason, /HTTP 402/);
});

test('moveIn asks for the image it was given, not the one it prefers', async () => {
  // A silently ignored image is expensive to find: the box comes up, every exec returns ok, and
  // the only symptom is "command not found" in stderr from a runtime that was never installed.
  let sent;
  const fetchImpl = async (url, init) => {
    if (url.endsWith('/sandbox/create')) { sent = JSON.parse(init.body); return { ok: true, status: 200, text: async () => JSON.stringify({ sandbox_id: 'sb-1' }) }; }
    return { ok: true, status: 200, text: async () => JSON.stringify({ stdout: 'ok' }) };
  };
  await moveIn({ fetchImpl, image: 'node:20-slim', commands: [['sh', '-c', 'node -v']] });
  assert.equal(sent.image, 'node:20-slim');
});
