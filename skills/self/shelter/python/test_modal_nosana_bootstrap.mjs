import { test } from "node:test";
import assert from "node:assert/strict";

import { blake2b } from "@noble/hashes/blake2";
import nacl from "tweetnacl";

import {
  bootstrapNosanaFromModal,
  buildBootstrapCommand,
  buildCollectCommand,
  buildPrepareCommand,
  sealBootstrapBundle,
} from "./modal-nosana-bootstrap.mjs";


const keypair = nacl.box.keyPair();
const sandboxPublicKey = Buffer.from(keypair.publicKey).toString("base64");
const secretBundle = {
  solanaSecret: "solana-secret-must-never-appear",
  baseKey: "base-secret-must-never-appear",
  market: "7AtiXMSH6R1jjBxrcYjehCkkSF7zvYWte63gwEDBcGHq",
  timeoutSec: 600,
  definition: {
    version: "0.1",
    type: "container",
    ops: [{
      id: "franklin",
      type: "container/run",
      args: { image: "node:20", env: { PRIVATE: "definition-secret" } },
    }],
  },
};


test("prepare command carries only pinned public source in bounded arguments", () => {
  const command = buildPrepareCommand();

  assert.deepEqual(command.slice(0, 2), ["sh", "-c"]);
  assert.match(command[2], /solders==0\.27\.1/);
  assert.match(command[2], /PyNaCl==1\.6\.2/);
  assert.match(command[2], /prepare-key --key-path/);
  assert.equal(command.every((part) => part.length <= 2000), true);
  assert.equal(command.join(" ").includes(secretBundle.solanaSecret), false);
  assert.equal(command.join(" ").includes(secretBundle.baseKey), false);
});


test("sealed bundle and bootstrap command contain ciphertext, never plaintext", () => {
  const sealed = sealBootstrapBundle({ sandboxPublicKey, ...secretBundle });
  const command = buildBootstrapCommand({ ciphertextChunks: sealed.chunks });
  const transport = command.join(" ");

  assert.equal(sealed.chunks.every((part) => part.length <= 1800), true);
  assert.equal(command.every((part) => part.length <= 2000), true);
  assert.equal(transport.includes(secretBundle.solanaSecret), false);
  assert.equal(transport.includes(secretBundle.baseKey), false);
  assert.equal(transport.includes("definition-secret"), false);
  assert.match(command[2], /bootstrap/);
  assert.match(command[2], /nohup/);
  assert.match(buildCollectCommand()[2], /bootstrap\.receipt/);

  const wire = Buffer.from(sealed.chunks.join(""), "base64");
  const ephemeralPublic = wire.subarray(0, nacl.box.publicKeyLength);
  const nonce = blake2b(
    Buffer.concat([ephemeralPublic, Buffer.from(keypair.publicKey)]),
    { dkLen: nacl.box.nonceLength },
  );
  const opened = nacl.box.open(
    wire.subarray(nacl.box.publicKeyLength),
    nonce,
    ephemeralPublic,
    keypair.secretKey,
  );
  const payload = JSON.parse(Buffer.from(opened).toString("utf8"));
  assert.equal(payload.market, secretBundle.market);
  assert.equal(payload.timeoutSec, 600);
});


test("paid adapter creates once and performs both execs in the same sandbox", async () => {
  const requests = [];
  const responses = [
    { sandbox_id: "sb-s21", status: "running" },
    { stdout: `${JSON.stringify({ ok: true, sandboxId: "sb-s21", publicKey: sandboxPublicKey })}\n`, returncode: 0 },
    { stdout: `${JSON.stringify({ ok: true, sandboxId: "sb-s21", started: true })}\n`, returncode: 0 },
    {
      stdout: `${JSON.stringify({
        ok: true,
        sandboxId: "sb-s21",
        action: "listed",
        payer: "payer",
        market: secretBundle.market,
        jobAddress: "job-one",
        listSignature: "tx-one",
        listStatus: "finalized",
        delivery: { delivered: true, attempts: 2, httpStatus: 200 },
      })}\n`,
      returncode: 0,
    },
  ];
  const fetchImpl = async (url, init) => {
    requests.push({ url, body: JSON.parse(init.body) });
    const body = responses.shift();
    return {
      ok: true,
      status: 200,
      text: async () => JSON.stringify(body),
    };
  };

  const result = await bootstrapNosanaFromModal({
    baseKey: secretBundle.baseKey,
    solanaSecret: secretBundle.solanaSecret,
    definition: secretBundle.definition,
    market: secretBundle.market,
    timeoutSec: secretBundle.timeoutSec,
    fetchImpl,
    waitImpl: async () => {},
  });

  assert.equal(result.ok, true);
  assert.equal(result.sandboxId, "sb-s21");
  assert.equal(result.receipt.jobAddress, "job-one");
  assert.equal(result.receipt.action, "listed");
  assert.deepEqual(
    requests.map(({ url }) => new URL(url).pathname),
    [
      "/api/v1/modal/sandbox/create",
      "/api/v1/modal/sandbox/exec",
      "/api/v1/modal/sandbox/exec",
      "/api/v1/modal/sandbox/exec",
    ],
  );
  assert.equal(requests[1].body.sandbox_id, "sb-s21");
  assert.equal(requests[2].body.sandbox_id, "sb-s21");
  assert.equal(requests[3].body.sandbox_id, "sb-s21");
  assert.equal(requests[0].body.timeout, 300);
  const paidPayloads = JSON.stringify(requests);
  assert.equal(paidPayloads.includes(secretBundle.solanaSecret), false);
  assert.equal(paidPayloads.includes(secretBundle.baseKey), false);
  assert.equal(paidPayloads.includes("definition-secret"), false);
});


test("a later sandbox can reconcile the same job without a second list", async () => {
  const responses = [
    { sandbox_id: "sb-restart", status: "running" },
    { stdout: `${JSON.stringify({ ok: true, sandboxId: "sb-restart", publicKey: sandboxPublicKey })}\n`, returncode: 0 },
    { stdout: `${JSON.stringify({ ok: true, sandboxId: "sb-restart", started: true })}\n`, returncode: 0 },
    {
      stdout: `provider diagnostic that is not part of the control receipt\n${JSON.stringify({
        ok: true,
        sandboxId: "sb-restart",
        action: "recovered",
        payer: "payer",
        market: secretBundle.market,
        jobAddress: "job-one",
        listSignature: null,
        listStatus: null,
        delivery: { delivered: true, attempts: 1, httpStatus: 200 },
      })}\n`,
      returncode: 0,
    },
  ];
  const result = await bootstrapNosanaFromModal({
    baseKey: secretBundle.baseKey,
    solanaSecret: secretBundle.solanaSecret,
    definition: secretBundle.definition,
    market: secretBundle.market,
    timeoutSec: secretBundle.timeoutSec,
    waitImpl: async () => {},
    fetchImpl: async () => ({
      ok: true,
      status: 200,
      text: async () => JSON.stringify(responses.shift()),
    }),
  });

  assert.equal(result.ok, true);
  assert.equal(result.receipt.action, "recovered");
  assert.equal(result.receipt.jobAddress, "job-one");
});


test("prepare response must be bound to the sandbox being paid for", async () => {
  const responses = [
    { sandbox_id: "sb-right", status: "running" },
    {
      stdout: `${JSON.stringify({
        ok: true,
        sandboxId: "sb-wrong",
        publicKey: sandboxPublicKey,
      })}\n`,
    },
    { stdout: `${JSON.stringify({ ok: true, sandboxId: "sb-right", started: true })}\n` },
  ];
  await assert.rejects(
    bootstrapNosanaFromModal({
      baseKey: secretBundle.baseKey,
      solanaSecret: secretBundle.solanaSecret,
      definition: secretBundle.definition,
      market: secretBundle.market,
      timeoutSec: secretBundle.timeoutSec,
      fetchImpl: async () => ({
        ok: true,
        status: 200,
        text: async () => JSON.stringify(responses.shift()),
      }),
    }),
    /different sandbox/,
  );
});
