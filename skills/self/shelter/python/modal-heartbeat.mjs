// modal-heartbeat.mjs — carry the Python heartbeat into the second landlord and judge its output
// with the verifier that already judges Nosana. The sandbox gets public source, never a wallet key.

import fs from "node:fs";
import { fileURLToPath } from "node:url";

import { resolveEvmPrivateKey } from "../../../earn/lib/resolve-identity.mjs";
import { moveIn } from "../move-in.mjs";
import { verifyHeartbeatEntry } from "../nosana/heartbeat.mjs";


const HEARTBEAT_PATH = fileURLToPath(new URL("./heartbeat.py", import.meta.url));
const REQUIREMENTS_PATH = fileURLToPath(new URL("./requirements-heartbeat.txt", import.meta.url));

function positiveInteger(value, name) {
  if (!Number.isInteger(value) || value < 1) throw new Error(`${name} must be a positive integer`);
  return value;
}

function nonNegativeNumber(value, name) {
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0) {
    throw new Error(`${name} must be a non-negative number`);
  }
  return value;
}

function writePublicFileCommand(path, contents) {
  const encoded = Buffer.from(contents, "utf8").toString("base64");
  return `python -c 'import base64;open("${path}","wb").write(base64.b64decode("${encoded}"))'`;
}

/** Build the one public, secret-free command executed by the paid Modal exec endpoint. */
export function buildHeartbeatCommand({ cycles = 2, intervalSeconds = 5 } = {}) {
  positiveInteger(cycles, "cycles");
  nonNegativeNumber(intervalSeconds, "intervalSeconds");
  const source = fs.readFileSync(HEARTBEAT_PATH, "utf8");
  const requirements = fs.readFileSync(REQUIREMENTS_PATH, "utf8");
  const root = "/tmp/s20b-heartbeat";
  const script = [
    `mkdir -p ${root}`,
    writePublicFileCommand(`${root}/heartbeat.py`, source),
    writePublicFileCommand(`${root}/requirements-heartbeat.txt`, requirements),
    `python -m pip install --disable-pip-version-check --quiet -r ${root}/requirements-heartbeat.txt`,
    `exec python ${root}/heartbeat.py --cycles ${cycles} --interval ${intervalSeconds}`,
  ].join(" && ");
  return ["sh", "-c", script];
}

/**
 * Treat stdout as untrusted evidence. Every row must verify independently, name this exact sandbox,
 * keep one payer, and advance in time/cycle. Two rows are the minimum proof of natural cadence.
 */
export function verifyModalHeartbeatOutput({ stdout, sandboxId, minimumRows = 2 } = {}) {
  if (typeof sandboxId !== "string" || sandboxId.length === 0) {
    return { ok: false, entries: [], reason: "sandbox id is missing" };
  }
  if (typeof stdout !== "string") {
    return { ok: false, entries: [], reason: "sandbox stdout is missing" };
  }
  const entries = [];
  for (const [index, line] of stdout.split("\n").filter((row) => row.trim()).entries()) {
    let entry;
    try {
      entry = JSON.parse(line);
    } catch {
      return { ok: false, entries, reason: `line ${index + 1} is not JSON` };
    }
    const verdict = verifyHeartbeatEntry(entry);
    if (!verdict.valid) {
      return { ok: false, entries, reason: `line ${index + 1} failed signature verification: ${verdict.reason}` };
    }
    entries.push(entry);
  }
  if (entries.length < minimumRows) {
    return { ok: false, entries, reason: `at least ${minimumRows} heartbeat rows are required` };
  }
  if (entries.some((entry) => entry.jobAddress !== sandboxId)) {
    return { ok: false, entries, reason: "a heartbeat names a different sandbox" };
  }
  if (new Set(entries.map((entry) => entry.payer)).size !== 1) {
    return { ok: false, entries, reason: "payer changed between heartbeat rows" };
  }
  for (let index = 1; index < entries.length; index += 1) {
    if (entries[index].cycle <= entries[index - 1].cycle || entries[index].ts <= entries[index - 1].ts) {
      return { ok: false, entries, reason: "heartbeat cycle and timestamp must increase" };
    }
  }
  return { ok: true, entries, reason: `${entries.length} canonical heartbeat rows verify` };
}

/** Buy one capped Python box, let it beat naturally, then independently verify the returned rows. */
export async function proveModalHeartbeat({
  baseKey,
  fetchImpl,
  cycles = 2,
  intervalSeconds = 5,
  timeoutSec = 300,
} = {}) {
  const command = buildHeartbeatCommand({ cycles, intervalSeconds });
  const habitation = await moveIn({
    baseKey,
    fetchImpl,
    image: "python:3.11",
    timeoutSec,
    commands: [command],
    maxExecs: 1,
  });
  if (!habitation.ok) {
    return { ok: false, reason: habitation.reason, habitation, entries: [] };
  }
  const sandboxId = habitation.sandbox?.sandbox_id || habitation.id;
  const stdout = habitation.execs?.[0]?.stdout;
  const verified = verifyModalHeartbeatOutput({ stdout, sandboxId, minimumRows: cycles });
  return { ...verified, sandboxId, habitation };
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const baseKey = resolveEvmPrivateKey({});
  if (!baseKey) {
    process.stderr.write("modal-heartbeat: no per-instance Base key resolved\n");
    process.exit(2);
  }
  proveModalHeartbeat({ baseKey })
    .then((result) => {
      const safe = {
        ok: result.ok,
        sandboxId: result.sandboxId,
        reason: result.reason,
        entries: result.entries,
      };
      process.stdout.write(`${JSON.stringify(safe)}\n`);
      process.exit(result.ok ? 0 : 1);
    })
    .catch((error) => {
      process.stderr.write(`modal-heartbeat: ${String(error?.message || error).slice(0, 160)}\n`);
      process.exit(1);
    });
}
