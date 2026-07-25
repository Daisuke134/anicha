// node:test — franklin-job: S12 definition builder. The secret must live ONLY in env (delivered
// confidentially), never in cmd; the definition must pass the structural validator.
import { test } from "node:test";
import assert from "node:assert/strict";
import { buildFranklinJobDefinition, buildFranklinBootScript } from "../franklin-job.mjs";
import { validateJobDefinition } from "../job-definition.mjs";

const FAKE_SECRET = "5".repeat(88); // base58-shaped, clearly fake

test("definition is structurally valid, exposes one port, env-carries the secret", () => {
  const def = buildFranklinJobDefinition({ solanaSessionB58: FAKE_SECRET });
  const v = validateJobDefinition(def);
  assert.equal(v.valid, true, v.errors.join("; "));
  assert.equal(def.ops[0].args.env.SOLANA_SESSION, FAKE_SECRET);
  assert.equal(def.ops[0].args.expose, 8080);
  assert.equal(def.ops[0].args.image, "docker.io/library/node:20-alpine");
});

test("secret never appears in cmd — env is the only channel", () => {
  const def = buildFranklinJobDefinition({ solanaSessionB58: FAKE_SECRET });
  const cmdText = JSON.stringify(def.ops[0].args.cmd);
  assert.equal(cmdText.includes(FAKE_SECRET), false);
  assert.match(cmdText, /\$SOLANA_SESSION/); // script reads it from env at runtime
  assert.equal(typeof def.ops[0].args.cmd, "string"); // string cmd — array form died on the node (live A/B)
});

test("boot script: installs franklin, hard spend cap, keep-alive proof server", () => {
  const s = buildFranklinBootScript({ model: "openai/gpt-5-mini", maxSpendUsd: 0.02, prompt: "hello", exposePort: 8080 });
  assert.match(s, /npm i -g @blockrun\/franklin/);
  assert.match(s, /--max-spend 0\.02/);
  assert.match(s, /\.solana-session/);
  assert.match(s, /createServer/);
});

test("missing secret refused", () => {
  assert.throws(() => buildFranklinJobDefinition({}), /solanaSessionB58/);
});
