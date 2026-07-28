// A short-lived paid Modal sandbox is the confidential Nosana poster.
// The sandbox receives public source first, creates its own sealed-box key,
// then receives only ciphertext in the second exec.

import fs from "node:fs";
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
const SANDBOX_RECEIPT = `${SANDBOX_ROOT}/bootstrap.receipt`;
const SANDBOX_STDERR = `${SANDBOX_ROOT}/bootstrap.stderr`;
const DEFAULT_MARKET = "7AtiXMSH6R1jjBxrcYjehCkkSF7zvYWte63gwEDBcGHq";


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
    `rm -f ${SANDBOX_RECEIPT} ${SANDBOX_STDERR};`,
    `nohup python ${SANDBOX_SOURCE} bootstrap`,
    `--key-path ${SANDBOX_KEY}`,
    '"$@"',
    `>${SANDBOX_RECEIPT} 2>${SANDBOX_STDERR} &`,
    `printf '{"ok":true,"sandboxId":"%s","started":true}\\n' "$MODAL_SANDBOX_ID"`,
  ].join(" ");
  return assertBounded(["sh", "-c", script, "nosana-bootstrap-ciphertext", ...ciphertextChunks]);
}


export function buildCollectCommand() {
  const script =
    `for i in $(seq 1 55); do if [ -s ${SANDBOX_RECEIPT} ]; then ` +
    `cat ${SANDBOX_RECEIPT}; exit 0; fi; sleep 1; done; ` +
    `printf '{"ok":false,"sandboxId":"%s","error":"bootstrap receipt is still pending"}\\n' "$MODAL_SANDBOX_ID"`;
  return assertBounded(["sh", "-c", script]);
}


function parseControlLine(stdout, kind) {
  if (typeof stdout !== "string") throw new Error(`${kind} stdout is missing`);
  const lines = stdout.split("\n").filter((line) => line.trim());
  const controls = [];
  for (const line of lines) {
    try {
      const parsed = JSON.parse(line);
      if (
        parsed
        && typeof parsed === "object"
        && typeof parsed.ok === "boolean"
        && typeof parsed.sandboxId === "string"
      ) controls.push(parsed);
    } catch {
      // Provider/runtime diagnostic lines are not trusted or returned to the caller.
    }
  }
  if (controls.length !== 1) {
    throw new Error(`${kind} must return exactly one JSON control line`);
  }
  const [value] = controls;
  if (!value || value.ok !== true) {
    const detail = typeof value?.error === "string" ? `: ${value.error.slice(0, 200)}` : "";
    throw new Error(`${kind} reported failure${detail}`);
  }
  return value;
}


function safeBootstrapReceipt(value, { sandboxId, market }) {
  if (
    value.sandboxId !== sandboxId
    || value.market !== market
    || !["listed", "recovered"].includes(value.action)
    || typeof value.payer !== "string"
    || !value.payer
    || typeof value.jobAddress !== "string"
    || !value.jobAddress
    || !value.delivery
    || (
      value.delivery.delivered !== true
      && value.delivery.reconciled !== true
    )
    || !Number.isInteger(Number(value.delivery.attempts))
    || Number(value.delivery.attempts) < 0
    || !Number.isInteger(Number(value.delivery.httpStatus))
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
      delivered: value.delivery.delivered === true,
      reconciled: value.delivery.reconciled === true,
      attempts: Number(value.delivery.attempts),
      httpStatus: Number(value.delivery.httpStatus),
      serviceUrl:
        typeof value.delivery.serviceUrl === "string"
          ? value.delivery.serviceUrl
          : null,
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
  waitImpl = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds)),
  collectDelayMs = 90_000,
} = {}) {
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
  const started = parseControlLine(
    String(bootstrapped.json?.stdout ?? bootstrapped.json?.output ?? ""),
    "bootstrap-start",
  );
  if (started.sandboxId !== sandboxId || started.started !== true) {
    throw new Error("bootstrap-start receipt is incomplete");
  }
  await waitImpl(collectDelayMs);
  const collected = await postModal(doFetch, "sandbox/exec", {
    sandbox_id: sandboxId,
    command: buildCollectCommand(),
  });
  if (!collected.ok) {
    throw new Error(`Modal collect exec failed with HTTP ${collected.status}`);
  }
  const receipt = safeBootstrapReceipt(
    parseControlLine(
      String(collected.json?.stdout ?? collected.json?.output ?? ""),
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
      collectHttpStatus: collected.status,
      execCount: 3,
    },
  };
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
