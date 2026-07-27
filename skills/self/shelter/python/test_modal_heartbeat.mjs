import { test } from "node:test";
import assert from "node:assert/strict";

import {
  buildHeartbeatCommand,
  proveModalHeartbeat,
  verifyModalHeartbeatOutput,
} from "./modal-heartbeat.mjs";


const FIRST = {
  v: 1,
  kind: "shelter-heartbeat",
  ts: 1785144000123,
  cycle: 1,
  jobAddress: "sb-natural",
  payer: "FAe4sisG95oZ42w7buUn5qEE4TAnfTTFPiguZUHmhiF",
  slot: 2792,
  blockhash: "EkSnNWid2cvwEVnVx9aBqawnmiCNiDgp3gUdkDPTKN1N",
  sig: "2cki6PMm3oCYoVKhAK8TGeCZfS8FEJhMQJd78U2kwTbbRyj7JH3kAz4ZvivyeUDPNf6iLdXnJ3hoiC3JyEHKjXq4",
};
const SECOND = {
  v: 1,
  kind: "shelter-heartbeat",
  ts: 1785144005123,
  cycle: 2,
  jobAddress: "sb-natural",
  payer: FIRST.payer,
  slot: 2793,
  blockhash: "9xQeWvG816bUx9EPfEZ5fC9AkQW6NQQyFjcU6VJHkT7k",
  sig: "3b5EwnXtLaJ7CLRLiKfSCnC8sMmxqy9vBgGwLmdmC1XpnzrJMbC2LgWFUXhHsYLWQ6ZypEGwjDiYwWq7xGNppgNW",
};
const OTHER_PAYER = {
  ...SECOND,
  payer: "3ogUn1GNXoASaRbxPNeVJnVv5rG4EPBtmQmX61jVorUe",
  sig: "2eiPksgjzscfpdWuoS3NdUFhqu1b81sfHwwjdRyCGb2AZxEeiauGi2tUTt8nbXwspdknkFek8DwVUEjrSQFufSZJ",
};

const jsonl = (...rows) => `${rows.map((row) => JSON.stringify(row)).join("\n")}\n`;


test("two independently verifiable rows prove one sandbox process stayed alive", () => {
  const result = verifyModalHeartbeatOutput({
    stdout: jsonl(FIRST, SECOND),
    sandboxId: "sb-natural",
  });

  assert.equal(result.ok, true);
  assert.equal(result.entries.length, 2);
  assert.deepEqual(result.entries.map((entry) => entry.cycle), [1, 2]);
});

test("a valid signature for a different sandbox does not prove this lease", () => {
  const result = verifyModalHeartbeatOutput({
    stdout: jsonl(FIRST, SECOND),
    sandboxId: "sb-someone-else",
  });

  assert.equal(result.ok, false);
  assert.match(result.reason, /sandbox/);
});

test("rotating the signer between valid rows does not prove process continuity", () => {
  const result = verifyModalHeartbeatOutput({
    stdout: jsonl(FIRST, OTHER_PAYER),
    sandboxId: "sb-natural",
  });

  assert.equal(result.ok, false);
  assert.match(result.reason, /payer/);
});

test("one valid row is a signature, not a natural heartbeat", () => {
  const result = verifyModalHeartbeatOutput({
    stdout: jsonl(FIRST),
    sandboxId: "sb-natural",
  });

  assert.equal(result.ok, false);
  assert.match(result.reason, /at least 2/);
});

test("the real JavaScript verifier rejects a field changed after Python signed", () => {
  const result = verifyModalHeartbeatOutput({
    stdout: jsonl(FIRST, { ...SECOND, slot: SECOND.slot + 1 }),
    sandboxId: "sb-natural",
  });

  assert.equal(result.ok, false);
  assert.match(result.reason, /signature/);
});

test("the packaged command contains public code and no caller wallet secret", () => {
  const key = `0x${"11".repeat(32)}`;
  const command = buildHeartbeatCommand({ cycles: 2, intervalSeconds: 5 });

  assert.deepEqual(command.slice(0, 2), ["sh", "-c"]);
  assert.match(command[2], /PyNaCl==1\.6\.2/);
  assert.match(command[2], /"--cycles","2","--interval","5"/);
  assert.equal(command.every((part) => part.length <= 2000), true);
  assert.equal(command.join(" ").includes(key), false);
  assert.equal(command.join(" ").includes("SOLANA_SESSION"), false);
  assert.equal(command.join(" ").includes("BASE_KEY"), false);
});

test("the adapter verifies stdout returned by the existing paid move-in path", async () => {
  const key = `0x${"11".repeat(32)}`;
  const responses = [
    {
      ok: true,
      status: 200,
      text: async () => JSON.stringify({ sandbox_id: "sb-natural", status: "running" }),
    },
    {
      ok: true,
      status: 200,
      text: async () => JSON.stringify({
        sandbox_id: "sb-natural",
        stdout: jsonl(FIRST, SECOND),
        stderr: "",
        returncode: 0,
      }),
    },
  ];
  const fetchImpl = async () => responses.shift();

  const result = await proveModalHeartbeat({
    baseKey: key,
    fetchImpl,
    cycles: 2,
    intervalSeconds: 5,
  });

  assert.equal(result.ok, true);
  assert.equal(result.sandboxId, "sb-natural");
  assert.equal(result.entries.length, 2);
});

test("a failed live exec preserves bounded diagnostics without echoing the command", async () => {
  const responses = [
    {
      ok: true,
      status: 200,
      text: async () => JSON.stringify({ sandbox_id: "sb-failed", status: "running" }),
    },
    {
      ok: false,
      status: 422,
      text: async () => JSON.stringify({ detail: "command is too long" }),
    },
  ];

  const result = await proveModalHeartbeat({
    baseKey: `0x${"11".repeat(32)}`,
    fetchImpl: async () => responses.shift(),
  });

  assert.equal(result.ok, false);
  assert.equal(result.sandboxId, "sb-failed");
  assert.deepEqual(result.diagnostic, {
    httpStatus: 422,
    stderr: "",
    detail: { detail: "command is too long" },
  });
  assert.equal(JSON.stringify(result.diagnostic).includes("heartbeat.py"), false);
});
