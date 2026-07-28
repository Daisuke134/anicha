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
  // Nosana's official schema has no cmd maxLength; this local ceiling catches accidental growth.
  assert.ok(Buffer.byteLength(args.cmd) < 30_000);
  assert.equal(args.cmd.includes(SECRET), false);
  assert.equal(args.env.SOLANA_SESSION, SECRET);
  assert.equal(args.env.NOSANA_JOB_ADDRESS, JOB_ADDRESS_PLACEHOLDER);
  assert.equal(args.env.RENEW_MARGIN_SEC, "1700");
  assert.equal(args.env.SHELTER_LEASE_CEILING_SEC, "21600");
  assert.equal(args.env.REPLACEMENT_MARGIN_SEC, "1500");
  assert.equal(args.env.SUCCESSOR_TIMEOUT_SEC, "600");
  assert.match(args.cmd, /solders==0\.27\.1/);
  assert.equal(args.env.BASE_PUBLIC_ADDRESS, BASE);
  assert.equal(args.expose, 8080);
});
