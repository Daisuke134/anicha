// A short-lived paid Modal sandbox is the confidential Nosana poster.
// The sandbox receives public source first, creates its own sealed-box key,
// then receives only ciphertext in the second exec.

import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { randomUUID } from "node:crypto";
import { fileURLToPath } from "node:url";

import { blake2b } from "@noble/hashes/blake2";
import nacl from "tweetnacl";

import { resolveEvmPrivateKey } from "../../../earn/lib/resolve-identity.mjs";
import { payingFetch, postModal } from "../move-in.mjs";


const SOURCE_PATH = fileURLToPath(new URL("./nosana_bootstrap.py", import.meta.url));
const REQUIREMENTS_PATH = fileURLToPath(
  new URL("./requirements-nosana-bootstrap.txt", import.meta.url),
);
const SOURCE_CHUNK_SIZE = 1800;
const MAX_COMMAND_PART = 2000;
const SANDBOX_ROOT = "/tmp/s21-nosana";
const SANDBOX_SOURCE = `${SANDBOX_ROOT}/nosana_bootstrap.py`;
const SANDBOX_KEY = `${SANDBOX_ROOT}/bootstrap.key`;
const DEFAULT_MARKET = "7AtiXMSH6R1jjBxrcYjehCkkSF7zvYWte63gwEDBcGHq";
const WRITER_LEASE_MAX_AGE_MS = 15 * 60 * 1000;


function defaultWriterLeasePath() {
  const stateDir = process.env.ANICCA_STATE_DIR
    || path.join(process.env.ANICCA_HOME || path.join(os.homedir(), ".anicca"), "state");
  return path.join(stateDir, "s21-nosana-bootstrap.writer.lock");
}


export function acquireBootstrapWriterLease({
  leasePath = defaultWriterLeasePath(),
  nowMs = Date.now(),
  token = randomUUID(),
  maxAgeMs = WRITER_LEASE_MAX_AGE_MS,
} = {}) {
  if (!path.isAbsolute(leasePath) || path.basename(leasePath) !== "s21-nosana-bootstrap.writer.lock"
    && !path.basename(leasePath).endsWith(".lock")) {
    throw new Error("writer lease path must be one absolute .lock file");
  }
  fs.mkdirSync(path.dirname(leasePath), { recursive: true, mode: 0o700 });

  const create = () => {
    const fd = fs.openSync(leasePath, "wx", 0o600);
    try {
      fs.writeFileSync(fd, JSON.stringify({ token, createdAt: nowMs }));
    } finally {
      fs.closeSync(fd);
    }
  };

  try {
    create();
  } catch (error) {
    if (error?.code !== "EEXIST") throw error;
    const ageMs = nowMs - fs.statSync(leasePath).mtimeMs;
    if (Number.isFinite(ageMs) && ageMs > maxAgeMs) {
      fs.unlinkSync(leasePath);
      create();
    } else {
      throw new Error("Nosana bootstrap writer lease is already held");
    }
  }

  return {
    leasePath,
    release() {
      try {
        const current = JSON.parse(fs.readFileSync(leasePath, "utf8"));
        if (current.token === token) fs.unlinkSync(leasePath);
      } catch {
        // A missing/replaced lease belongs to neither this process nor its cleanup path.
      }
    },
  };
}


function chunks(value, size = SOURCE_CHUNK_SIZE) {
  return value.match(new RegExp(`.{1,${size}}`, "g")) || [];
}


function assertBounded(command) {
  if (!Array.isArray(command) || command.length === 0) {
    throw new Error("Modal command must be a non-empty string array");
  }
  if (command.some((part) => typeof part !== "string" || part.length > MAX_COMMAND_PART)) {
    throw new Error(`Modal command parts must be at most ${MAX_COMMAND_PART} characters`);
  }
  return command;
}


export function buildPrepareCommand() {
  const source = fs.readFileSync(SOURCE_PATH, "utf8");
  const encoded = Buffer.from(source, "utf8").toString("base64");
  const sourceChunks = chunks(encoded);
  const dependencies = fs
    .readFileSync(REQUIREMENTS_PATH, "utf8")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .join(" ");
  const reconstruct = [
    "import base64,pathlib,sys",
    `p=pathlib.Path("${SANDBOX_SOURCE}")`,
    "p.parent.mkdir(parents=True,exist_ok=True)",
    'p.write_bytes(base64.b64decode("".join(sys.argv[1:])))',
  ].join(";");
  const script = [
    `python -c '${reconstruct}' "$@"`,
    `python -m pip install --disable-pip-version-check --quiet ${dependencies}`,
    `exec python ${SANDBOX_SOURCE} prepare-key --key-path ${SANDBOX_KEY}`,
  ].join(" && ");
  return assertBounded(["sh", "-c", script, "nosana-bootstrap-source", ...sourceChunks]);
}


/**
 * libsodium crypto_box_seal compatible format:
 * ephemeral Curve25519 public key || crypto_box_easy(ciphertext).
 */
export function sealBootstrapBundle({
  sandboxPublicKey,
  solanaSecret,
  baseKey,
  definition,
  market = DEFAULT_MARKET,
  timeoutSec = 600,
}) {
  const recipient = Buffer.from(String(sandboxPublicKey || ""), "base64");
  if (recipient.length !== nacl.box.publicKeyLength) {
    throw new Error("sandbox public key must be one 32-byte base64 Curve25519 key");
  }
  if (typeof solanaSecret !== "string" || !solanaSecret) {
    throw new Error("Solana session secret is required");
  }
  if (typeof baseKey !== "string" || !baseKey) {
    throw new Error("Base key is required");
  }
  if (!definition || typeof definition !== "object" || Array.isArray(definition)) {
    throw new Error("Nosana definition is required");
  }
  if (typeof market !== "string" || market.length < 32) {
    throw new Error("Nosana market is required");
  }
  if (!Number.isInteger(timeoutSec) || timeoutSec <= 0) {
    throw new Error("Nosana timeout must be a positive integer");
  }

  const plaintext = Buffer.from(
    JSON.stringify({
      solanaSecret,
      baseKey,
      definition,
      market,
      timeoutSec,
    }),
    "utf8",
  );
  const ephemeral = nacl.box.keyPair();
  const ephemeralPublic = Buffer.from(ephemeral.publicKey);
  const nonce = blake2b(
    Buffer.concat([ephemeralPublic, recipient]),
    { dkLen: nacl.box.nonceLength },
  );
  const boxed = nacl.box(
    plaintext,
    nonce,
    new Uint8Array(recipient),
    ephemeral.secretKey,
  );
  const encoded = Buffer.concat([ephemeralPublic, Buffer.from(boxed)]).toString("base64");
  return { chunks: chunks(encoded), byteLength: ephemeralPublic.length + boxed.length };
}


export function buildBootstrapCommand({ ciphertextChunks } = {}) {
  if (
    !Array.isArray(ciphertextChunks)
    || ciphertextChunks.length === 0
    || ciphertextChunks.some((part) => typeof part !== "string" || !part)
  ) {
    throw new Error("ciphertext chunks are required");
  }
  const script = [
    `exec python ${SANDBOX_SOURCE} bootstrap`,
    `--key-path ${SANDBOX_KEY}`,
    '"$@"',
  ].join(" ");
  return assertBounded(["sh", "-c", script, "nosana-bootstrap-ciphertext", ...ciphertextChunks]);
}


function parseControlLine(stdout, kind) {
  if (typeof stdout !== "string") throw new Error(`${kind} stdout is missing`);
  const lines = stdout.split("\n").filter((line) => line.trim());
  if (lines.length !== 1) throw new Error(`${kind} must return exactly one JSON line`);
  let value;
  try {
    value = JSON.parse(lines[0]);
  } catch {
    throw new Error(`${kind} control line is not JSON`);
  }
  if (!value || value.ok !== true) throw new Error(`${kind} reported failure`);
  return value;
}


function safeBootstrapReceipt(value, { sandboxId, market }) {
  const deliveredNow = value.delivery?.delivered === true
    && Number.isInteger(Number(value.delivery.attempts))
    && Number(value.delivery.attempts) >= 1
    && Number.isInteger(Number(value.delivery.httpStatus));
  const recoveredRunning = value.action === "recovered"
    && value.delivery?.delivered === false
    && value.delivery?.alreadyRunning === true
    && Number(value.delivery.attempts) === 0
    && value.delivery.httpStatus == null;
  if (
    value.sandboxId !== sandboxId
    || value.market !== market
    || !["listed", "recovered"].includes(value.action)
    || typeof value.payer !== "string"
    || !value.payer
    || typeof value.jobAddress !== "string"
    || !value.jobAddress
    || !value.delivery
    || (!deliveredNow && !recoveredRunning)
  ) {
    throw new Error("bootstrap receipt is incomplete");
  }
  if (
    value.action === "listed"
    && (
      typeof value.listSignature !== "string"
      || !value.listSignature
      || value.listStatus !== "finalized"
    )
  ) {
    throw new Error("listed bootstrap receipt lacks finalized list proof");
  }
  if (
    value.action === "recovered"
    && (value.listSignature != null || value.listStatus != null)
  ) {
    throw new Error("recovered bootstrap receipt unexpectedly contains a list transaction");
  }
  return {
    ok: true,
    action: value.action,
    payer: value.payer,
    market: value.market,
    jobAddress: value.jobAddress,
    listSignature: value.listSignature ?? null,
    listStatus: value.listStatus ?? null,
    delivery: {
      delivered: deliveredNow,
      attempts: Number(value.delivery.attempts),
      httpStatus: deliveredNow ? Number(value.delivery.httpStatus) : null,
      alreadyRunning: recoveredRunning,
    },
  };
}


export async function bootstrapNosanaFromModal({
  baseKey,
  solanaSecret,
  definition,
  market = DEFAULT_MARKET,
  fetchImpl,
  timeoutSec = 600,
  modalTimeoutSec = 300,
  writerLeasePath = defaultWriterLeasePath(),
} = {}) {
  const writerLease = acquireBootstrapWriterLease({ leasePath: writerLeasePath });
  try {
  if (!baseKey && !fetchImpl) throw new Error("no Base key to pay for Modal");
  const doFetch = fetchImpl || (await payingFetch(baseKey));
  const created = await postModal(doFetch, "sandbox/create", {
    image: "python:3.11",
    timeout: modalTimeoutSec,
  });
  if (!created.ok || typeof created.json?.sandbox_id !== "string") {
    throw new Error(`Modal create failed with HTTP ${created.status}`);
  }
  const sandboxId = created.json.sandbox_id;

  const prepared = await postModal(doFetch, "sandbox/exec", {
    sandbox_id: sandboxId,
    command: buildPrepareCommand(),
  });
  if (!prepared.ok) throw new Error(`Modal prepare exec failed with HTTP ${prepared.status}`);
  const prepareControl = parseControlLine(
    String(prepared.json?.stdout ?? prepared.json?.output ?? ""),
    "prepare-key",
  );
  if (typeof prepareControl.publicKey !== "string") {
    throw new Error("prepare-key returned no public key");
  }
  if (prepareControl.sandboxId !== sandboxId) {
    throw new Error("prepare-key response came from a different sandbox");
  }

  const sealed = sealBootstrapBundle({
    sandboxPublicKey: prepareControl.publicKey,
    solanaSecret,
    baseKey,
    definition,
    market,
    timeoutSec,
  });
  const bootstrapped = await postModal(doFetch, "sandbox/exec", {
    sandbox_id: sandboxId,
    command: buildBootstrapCommand({ ciphertextChunks: sealed.chunks }),
  });
  if (!bootstrapped.ok) {
    throw new Error(`Modal bootstrap exec failed with HTTP ${bootstrapped.status}`);
  }
  const receipt = safeBootstrapReceipt(
    parseControlLine(
      String(bootstrapped.json?.stdout ?? bootstrapped.json?.output ?? ""),
      "bootstrap",
    ),
    { sandboxId, market },
  );
  return {
    ok: true,
    sandboxId,
    receipt,
    provider: {
      createHttpStatus: created.status,
      prepareHttpStatus: prepared.status,
      bootstrapHttpStatus: bootstrapped.status,
      execCount: 2,
    },
  };
  } finally {
    writerLease.release();
  }
}


if (import.meta.url === `file://${process.argv[1]}`) {
  const baseKey = resolveEvmPrivateKey({});
  if (!baseKey) {
    process.stderr.write("modal-nosana-bootstrap: no per-instance Base key resolved\n");
    process.exit(2);
  }
  process.stderr.write(
    "modal-nosana-bootstrap: invoke through the shelter orchestrator with the capped Solana session and confidential definition\n",
  );
  process.exit(2);
}
