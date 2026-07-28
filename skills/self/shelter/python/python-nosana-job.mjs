import fs from "node:fs";
import { fileURLToPath } from "node:url";
import { gzipSync } from "node:zlib";

import { buildServiceJobDefinition } from "../nosana/job-definition.mjs";


const FILES = [
  "heartbeat.py",
  "statement.py",
  "nosana_bootstrap.py",
  "nosana_runtime.py",
];
const ROOT = "/tmp/f";
export const JOB_ADDRESS_PLACEHOLDER = "__NOSANA_JOB_ADDRESS__";


export function buildPythonNosanaJobDefinition({
  solanaSessionB58,
  basePublicAddress,
} = {}) {
  if (typeof solanaSessionB58 !== "string" || solanaSessionB58.length < 32) {
    throw new Error("Solana session is required");
  }
  if (typeof basePublicAddress !== "string" || !/^0x[0-9a-fA-F]{40}$/.test(basePublicAddress)) {
    throw new Error("Base public address is required");
  }
  const here = new URL("./", import.meta.url);
  const sources = Object.fromEntries(
    FILES.map((name) => [
      name,
      fs.readFileSync(fileURLToPath(new URL(name, here)), "utf8"),
    ]),
  );
  const encoded = gzipSync(Buffer.from(JSON.stringify(sources), "utf8"), {
    level: 9,
  }).toString("base64");
  const reconstruct = [
    "import base64,gzip,json,pathlib",
    `r=pathlib.Path("${ROOT}")`,
    "r.mkdir(parents=True,exist_ok=True)",
    `d=json.loads(gzip.decompress(base64.b64decode("${encoded}")))`,
    '[(r/n).write_text(s,encoding="utf-8") for n,s in d.items()]',
  ].join(";");
  const command = [
    "set -e",
    `python -c '${reconstruct}'`,
    "python -m pip install -q PyNaCl==1.6.2 base58==2.1.1 solders==0.27.1 requests==2.34.2",
    `exec python ${ROOT}/nosana_runtime.py`,
  ].join("; ");
  return buildServiceJobDefinition({
    image: "docker.io/library/python:3.11",
    exposePort: 8080,
    gpu: true,
    cmd: command,
    env: {
      SOLANA_SESSION: solanaSessionB58,
      NOSANA_JOB_ADDRESS: JOB_ADDRESS_PLACEHOLDER,
      NOSANA_MARKET: "7AtiXMSH6R1jjBxrcYjehCkkSF7zvYWte63gwEDBcGHq",
      RENEW_MARGIN_SEC: "1700",
      SHELTER_LEASE_CEILING_SEC: "21600",
      REPLACEMENT_MARGIN_SEC: "1500",
      SUCCESSOR_TIMEOUT_SEC: "600",
      BASE_PUBLIC_ADDRESS: basePublicAddress,
    },
    id: "franklin-python",
  });
}
