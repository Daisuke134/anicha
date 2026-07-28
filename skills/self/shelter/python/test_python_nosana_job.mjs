import { test } from "node:test";
import assert from "node:assert/strict";

import {
  buildPythonNosanaJobDefinition,
  JOB_ADDRESS_PLACEHOLDER,
} from "./python-nosana-job.mjs";


const SECRET = "secret-session-material-that-stays-in-env";
const BASE = "0xd072CDDda8371D97834859E9c840F9B0F1e51a1d";


test("Python Nosana definition embeds audited sources and keeps secret out of cmd", () => {
  const definition = buildPythonNosanaJobDefinition({
    solanaSessionB58: SECRET,
    basePublicAddress: BASE,
  });
  const args = definition.ops[0].args;
  assert.equal(args.image, "docker.io/library/python:3.11");
  assert.match(args.cmd, /nosana_runtime\.py/);
  assert.match(args.cmd, /PyNaCl==1\.6\.2/);
  assert.ok(Buffer.byteLength(args.cmd) < 20_000);
  assert.equal(args.cmd.includes(SECRET), false);
  assert.equal(args.env.SOLANA_SESSION, SECRET);
  assert.equal(args.env.NOSANA_JOB_ADDRESS, JOB_ADDRESS_PLACEHOLDER);
  assert.equal(args.env.BASE_PUBLIC_ADDRESS, BASE);
  assert.equal(args.expose, 8080);
});
