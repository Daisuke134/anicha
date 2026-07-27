// modal-statement.mjs — buy one managed Python box, publish its allowlisted statement, and
// independently compare the public page with the chains/APIs it claims to summarize.

import fs from "node:fs";
import { resolve4 } from "node:dns/promises";
import { request as httpsRequest } from "node:https";
import { fileURLToPath } from "node:url";

import { resolveEvmPrivateKey } from "../../../earn/lib/resolve-identity.mjs";
import { moveIn } from "../move-in.mjs";
import { verifyModalHeartbeatOutput } from "./modal-heartbeat.mjs";


const STATEMENT_PATH = fileURLToPath(new URL("./statement.py", import.meta.url));
const HEARTBEAT_PATH = fileURLToPath(new URL("./heartbeat.py", import.meta.url));
const MAX_COMMAND_PART = 2000;
const SOURCE_CHUNK_SIZE = 1800;
const CLOUDFLARED_VERSION = "2026.7.3";
const CLOUDFLARED_SHA256 = "9d71c677db00134c1bd4144b7783486b654ad281b1ea62b4972098d19f770f17";
const CLOUDFLARED_URL =
  `https://github.com/cloudflare/cloudflared/releases/download/${CLOUDFLARED_VERSION}/cloudflared-linux-amd64`;
const BASE_RPC_URL = "https://mainnet.base.org";
const SOLANA_RPC_URL = "https://api.mainnet-beta.solana.com";
const POLYMARKET_POSITIONS_URL = "https://data-api.polymarket.com/positions";
const BASE_USDC_ADDRESS = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913";
const NOS_MINT = "nosXBVoaCTtYdLvKY6Csb4AC8JCdQKKAaWYtx2ZMoo7";

const SCHEMA = {
  top: ["v", "generatedAt", "sandboxId", "wallets", "balances", "polymarket", "economy", "heartbeats"],
  wallets: ["base", "solana", "polymarket"],
  balances: ["baseUsdc", "solanaSol", "solanaNos"],
  polymarket: ["positionCount", "currentValueUsd", "cashPnlUsd", "redeemableCount"],
  economy: ["externalRevenueUsd", "runtimeCostUsd", "verdict"],
  heartbeats: ["claimed", "verified"],
};


function exactKeys(value, expected) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const actual = Object.keys(value).sort();
  return actual.length === expected.length && actual.every((key, index) => key === [...expected].sort()[index]);
}

function nonNegative(value) {
  return typeof value === "number" && Number.isFinite(value) && value >= 0;
}

function nonNegativeInteger(value) {
  return Number.isInteger(value) && value >= 0;
}

function evmAddress(value) {
  return typeof value === "string" && /^0x[0-9a-fA-F]{40}$/.test(value);
}

function solanaAddress(value) {
  return typeof value === "string" && /^[1-9A-HJ-NP-Za-km-z]{32,44}$/.test(value);
}

function validateTunnelUrl(value) {
  let parsed;
  try {
    parsed = new URL(value);
  } catch {
    throw new Error("tunnel URL is invalid");
  }
  if (
    parsed.protocol !== "https:"
    || !/^[a-z0-9-]+\.trycloudflare\.com$/.test(parsed.hostname)
    || parsed.port
    || parsed.username
    || parsed.password
    || (parsed.pathname !== "/" && parsed.pathname !== "")
    || parsed.search
    || parsed.hash
  ) {
    throw new Error("tunnel URL must be one bare HTTPS trycloudflare.com origin");
  }
  return parsed.origin;
}


/** Package public source in sub-2,000-character arguments and pin the tunnel binary by hash. */
export function buildStatementCommand() {
  const files = {
    "statement.py": fs.readFileSync(STATEMENT_PATH, "utf8"),
    "heartbeat.py": fs.readFileSync(HEARTBEAT_PATH, "utf8"),
  };
  const encoded = Buffer.from(JSON.stringify(files), "utf8").toString("base64");
  const chunks = encoded.match(new RegExp(`.{1,${SOURCE_CHUNK_SIZE}}`, "g")) || [];
  const root = "/tmp/s20b-statement-src";
  const cloudflared = "/tmp/s20b-cloudflared";
  const reconstruct = [
    "import base64,json,pathlib,sys",
    `r=pathlib.Path("${root}")`,
    "r.mkdir(parents=True,exist_ok=True)",
    'd=json.loads(base64.b64decode("".join(sys.argv[1:])))',
    '[(r/n).write_text(s,encoding="utf-8") for n,s in d.items()]',
  ].join(";");
  const download = [
    "import hashlib,os,urllib.request",
    `u="${CLOUDFLARED_URL}"`,
    `p="${cloudflared}"`,
    "urllib.request.urlretrieve(u,p)",
    'h=hashlib.sha256(open(p,"rb").read()).hexdigest()',
    `assert h=="${CLOUDFLARED_SHA256}","cloudflared sha256 mismatch"`,
    "os.chmod(p,0o755)",
  ].join(";");
  const script = [
    `python -c '${reconstruct}' "$@"`,
    `python -c '${download}'`,
    "python -m pip install --disable-pip-version-check --quiet PyNaCl==1.6.2 base58==2.1.1",
    `exec python ${root}/statement.py launch --cloudflared ${cloudflared} --port 8080`,
  ].join(" && ");
  const command = ["sh", "-c", script, "statement-package", ...chunks];
  if (command.some((part) => part.length > MAX_COMMAND_PART)) {
    throw new Error(`Modal command parts must be at most ${MAX_COMMAND_PART} characters`);
  }
  return command;
}


export function parseStatementControl(stdout) {
  if (typeof stdout !== "string") throw new Error("statement control stdout is missing");
  const lines = stdout.split("\n").filter((line) => line.trim());
  if (lines.length !== 1) throw new Error("statement control must contain exactly one JSON line");
  let parsed;
  try {
    parsed = JSON.parse(lines[0]);
  } catch {
    throw new Error("statement control is not JSON");
  }
  if (parsed?.ok !== true || typeof parsed.sandboxId !== "string" || !parsed.statement) {
    throw new Error("statement control is incomplete");
  }
  parsed.url = validateTunnelUrl(parsed.url);
  return parsed;
}


export function validatePublicStatement(statement, sandboxId) {
  if (!exactKeys(statement, SCHEMA.top)) return { ok: false, reason: "top-level public schema differs" };
  for (const field of ["wallets", "balances", "polymarket", "economy", "heartbeats"]) {
    if (!exactKeys(statement[field], SCHEMA[field])) {
      return { ok: false, reason: `${field} public schema differs` };
    }
  }
  if (statement.v !== 1 || !Number.isInteger(statement.generatedAt) || statement.generatedAt <= 0) {
    return { ok: false, reason: "statement version or timestamp is invalid" };
  }
  if (statement.sandboxId !== sandboxId) return { ok: false, reason: "statement names another sandbox" };
  if (
    !evmAddress(statement.wallets.base)
    || !solanaAddress(statement.wallets.solana)
    || !evmAddress(statement.wallets.polymarket)
  ) {
    return { ok: false, reason: "a public wallet address is invalid" };
  }
  if (!Object.values(statement.balances).every(nonNegative)) {
    return { ok: false, reason: "a public balance is invalid" };
  }
  const market = statement.polymarket;
  if (
    !nonNegativeInteger(market.positionCount)
    || !nonNegative(market.currentValueUsd)
    || typeof market.cashPnlUsd !== "number"
    || !Number.isFinite(market.cashPnlUsd)
    || !nonNegativeInteger(market.redeemableCount)
  ) {
    return { ok: false, reason: "Polymarket values are invalid" };
  }
  const economy = statement.economy;
  if (
    economy.externalRevenueUsd !== 0
    || economy.runtimeCostUsd !== 0.015
    || economy.verdict !== "funded"
  ) {
    return { ok: false, reason: "economy truth fields overclaim this proof" };
  }
  if (
    !nonNegativeInteger(statement.heartbeats.claimed)
    || !nonNegativeInteger(statement.heartbeats.verified)
    || statement.heartbeats.claimed < 2
    || statement.heartbeats.verified < 2
    || statement.heartbeats.verified > statement.heartbeats.claimed
  ) {
    return { ok: false, reason: "heartbeat counts do not prove continuity" };
  }
  return { ok: true, reason: "public schema verifies" };
}


export function compareFinancialSnapshots(published, independent, polymarketToleranceUsd = 0.01) {
  const differences = [];
  const exactFields = [
    ["balances.baseUsdc", published.balances?.baseUsdc, independent.balances?.baseUsdc],
    ["balances.solanaSol", published.balances?.solanaSol, independent.balances?.solanaSol],
    ["balances.solanaNos", published.balances?.solanaNos, independent.balances?.solanaNos],
    ["polymarket.positionCount", published.polymarket?.positionCount, independent.polymarket?.positionCount],
    ["polymarket.redeemableCount", published.polymarket?.redeemableCount, independent.polymarket?.redeemableCount],
  ];
  for (const [field, publishedValue, independentValue] of exactFields) {
    if (publishedValue !== independentValue) {
      differences.push({ field, published: publishedValue, independent: independentValue });
    }
  }
  for (const field of ["currentValueUsd", "cashPnlUsd"]) {
    const publishedValue = published.polymarket?.[field];
    const independentValue = independent.polymarket?.[field];
    if (
      typeof publishedValue !== "number"
      || typeof independentValue !== "number"
      || !Number.isFinite(publishedValue)
      || !Number.isFinite(independentValue)
      || Math.abs(publishedValue - independentValue) > polymarketToleranceUsd
    ) {
      differences.push({
        field: `polymarket.${field}`,
        published: publishedValue,
        independent: independentValue,
      });
    }
  }
  return { ok: differences.length === 0, differences };
}


async function checkedJson(publicFetch, url, init) {
  const response = await publicFetch(url, init);
  if (!response.ok) throw new Error(`public source HTTP ${response.status}: ${url}`);
  const body = await response.json();
  return body;
}

function rpcBody(method, params) {
  return JSON.stringify({ jsonrpc: "2.0", id: 1, method, params });
}

async function fetchIndependentFinancialSnapshot(publicFetch, statement) {
  const base = statement.wallets.base;
  const calldata = `0x70a08231${"0".repeat(24)}${base.slice(2).toLowerCase()}`;
  const baseResponse = await checkedJson(publicFetch, BASE_RPC_URL, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: rpcBody("eth_call", [{ to: BASE_USDC_ADDRESS, data: calldata }, "latest"]),
  });
  if (typeof baseResponse.result !== "string" || !/^0x[0-9a-fA-F]+$/.test(baseResponse.result)) {
    throw new Error("independent Base USDC response is malformed");
  }
  const baseUsdc = Number(BigInt(baseResponse.result)) / 1_000_000;

  const solResponse = await checkedJson(publicFetch, SOLANA_RPC_URL, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: rpcBody("getBalance", [statement.wallets.solana, { commitment: "confirmed" }]),
  });
  const lamports = solResponse?.result?.value;
  if (!nonNegative(lamports)) throw new Error("independent SOL response is malformed");

  const nosResponse = await checkedJson(publicFetch, SOLANA_RPC_URL, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: rpcBody("getTokenAccountsByOwner", [
      statement.wallets.solana,
      { mint: NOS_MINT },
      { encoding: "jsonParsed", commitment: "confirmed" },
    ]),
  });
  const accounts = nosResponse?.result?.value;
  if (!Array.isArray(accounts)) throw new Error("independent NOS response is malformed");
  let solanaNos = 0;
  for (const account of accounts) {
    const token = account?.account?.data?.parsed?.info?.tokenAmount;
    if (!token || typeof token.amount !== "string" || !/^\d+$/.test(token.amount) || !nonNegativeInteger(token.decimals)) {
      throw new Error("independent NOS token account is malformed");
    }
    solanaNos += Number(BigInt(token.amount)) / (10 ** token.decimals);
  }

  const marketUrl = `${POLYMARKET_POSITIONS_URL}?user=${encodeURIComponent(statement.wallets.polymarket)}`;
  const positions = await checkedJson(publicFetch, marketUrl);
  if (!Array.isArray(positions)) throw new Error("independent Polymarket response is malformed");
  let currentMicro = 0;
  let pnlMicro = 0;
  let redeemableCount = 0;
  for (const position of positions) {
    if (
      !nonNegative(position?.currentValue)
      || typeof position?.cashPnl !== "number"
      || !Number.isFinite(position.cashPnl)
      || typeof position?.redeemable !== "boolean"
    ) {
      throw new Error("independent Polymarket position is malformed");
    }
    currentMicro += Math.round(position.currentValue * 1_000_000);
    pnlMicro += Math.round(position.cashPnl * 1_000_000);
    redeemableCount += Number(position.redeemable);
  }

  return {
    balances: {
      baseUsdc,
      solanaSol: lamports / 1_000_000_000,
      solanaNos,
    },
    polymarket: {
      positionCount: positions.length,
      currentValueUsd: currentMicro / 1_000_000,
      cashPnlUsd: pnlMicro / 1_000_000,
      redeemableCount,
    },
  };
}


function requestTunnelIp({ ip, hostname, path }) {
  return new Promise((resolve, reject) => {
    const request = httpsRequest({
      protocol: "https:",
      hostname: ip,
      port: 443,
      path,
      method: "GET",
      servername: hostname,
      headers: {
        host: hostname,
        accept: "*/*",
      },
    }, (response) => {
      const chunks = [];
      let length = 0;
      response.on("data", (chunk) => {
        length += chunk.length;
        if (length > 2_000_000) {
          request.destroy(new Error(`${path} exceeded the 2 MB response limit`));
          return;
        }
        chunks.push(chunk);
      });
      response.on("end", () => {
        resolve({
          status: response.statusCode || 0,
          text: Buffer.concat(chunks).toString("utf8"),
          contentType: String(response.headers["content-type"] || ""),
        });
      });
    });
    request.setTimeout(15_000, () => request.destroy(new Error(`${path} timed out`)));
    request.on("error", reject);
    request.end();
  });
}


export async function fetchTunnelRouteDirect(
  origin,
  path,
  expectedContentType,
  { resolve4Impl = resolve4, requestIpImpl = requestTunnelIp } = {},
) {
  const validatedOrigin = validateTunnelUrl(origin);
  const hostname = new URL(validatedOrigin).hostname;
  const addresses = [...new Set(await resolve4Impl(hostname))].sort();
  if (addresses.length === 0) throw new Error(`no IPv4 address resolved for ${hostname}`);

  let lastError;
  for (const ip of addresses) {
    try {
      const route = await requestIpImpl({ ip, hostname, path });
      if (
        route.status < 200
        || route.status >= 300
        || !route.contentType.toLowerCase().startsWith(expectedContentType)
      ) {
        throw new Error(`${path} failed public fetch: HTTP ${route.status} ${route.contentType}`);
      }
      return route;
    } catch (error) {
      lastError = error;
    }
  }
  throw lastError || new Error(`${path} failed public fetch`);
}


export async function proveModalStatement({
  baseKey,
  fetchImpl,
  publicFetch = fetch,
  tunnelRouteFetch = fetchTunnelRouteDirect,
} = {}) {
  const command = buildStatementCommand();
  const habitation = await moveIn({
    baseKey,
    fetchImpl,
    image: "python:3.11",
    timeoutSec: 300,
    commands: [command],
    maxExecs: 1,
  });
  const sandboxId = habitation.sandbox?.sandbox_id || habitation.id;
  if (!habitation.ok) {
    const failedExec = habitation.execs?.[0];
    return {
      ok: false,
      sandboxId,
      reason: habitation.reason,
      diagnostic: failedExec
        ? {
            httpStatus: failedExec.status,
            stderr: String(failedExec.stderr || "").slice(0, 500),
            detail: failedExec.detail,
          }
        : undefined,
    };
  }

  let control;
  try {
    control = parseStatementControl(habitation.execs?.[0]?.stdout);
  } catch (error) {
    return { ok: false, sandboxId, reason: String(error.message || error) };
  }
  if (control.sandboxId !== sandboxId) {
    return { ok: false, sandboxId, reason: "control output names another sandbox" };
  }
  const schema = validatePublicStatement(control.statement, sandboxId);
  if (!schema.ok) return { ok: false, sandboxId, url: control.url, reason: schema.reason };

  try {
    const [htmlRoute, jsonRoute, heartbeatRoute] = await Promise.all([
      tunnelRouteFetch(control.url, "/", "text/html"),
      tunnelRouteFetch(control.url, "/statement.json", "application/json"),
      tunnelRouteFetch(control.url, "/heartbeats", "application/x-ndjson"),
    ]);
    if (!htmlRoute.text.includes("$0.00 from outside") || !htmlRoute.text.includes(sandboxId)) {
      throw new Error("public HTML omits the zero-revenue truth or sandbox identity");
    }
    const publicStatement = JSON.parse(jsonRoute.text);
    const publicSchema = validatePublicStatement(publicStatement, sandboxId);
    if (!publicSchema.ok) throw new Error(publicSchema.reason);
    if (publicStatement.generatedAt < control.statement.generatedAt) {
      throw new Error("public statement predates its control snapshot");
    }
    for (const field of ["wallets", "economy", "heartbeats"]) {
      if (JSON.stringify(publicStatement[field]) !== JSON.stringify(control.statement[field])) {
        throw new Error(`public statement changed immutable ${field}`);
      }
    }
    const heartbeatVerification = verifyModalHeartbeatOutput({
      stdout: heartbeatRoute.text,
      sandboxId,
      minimumRows: 2,
    });
    if (!heartbeatVerification.ok) throw new Error(heartbeatVerification.reason);
    const independent = await fetchIndependentFinancialSnapshot(publicFetch, publicStatement);
    const comparison = compareFinancialSnapshots(publicStatement, independent);
    if (!comparison.ok) throw new Error("published financial values differ from independent reads");

    return {
      ok: true,
      sandboxId,
      url: control.url,
      statement: publicStatement,
      independent,
      heartbeatVerification,
      comparison,
      routes: {
        "/": htmlRoute.status,
        "/statement.json": jsonRoute.status,
        "/heartbeats": heartbeatRoute.status,
      },
      artifacts: {
        html: htmlRoute.text,
        statementJson: `${jsonRoute.text.trim()}\n`,
        heartbeatJsonl: heartbeatRoute.text,
      },
    };
  } catch (error) {
    return {
      ok: false,
      sandboxId,
      url: control.url,
      reason: String(error.message || error).slice(0, 300),
    };
  }
}


if (import.meta.url === `file://${process.argv[1]}`) {
  const baseKey = resolveEvmPrivateKey({});
  if (!baseKey) {
    process.stderr.write("modal-statement: no per-instance Base key resolved\n");
    process.exit(2);
  }
  proveModalStatement({ baseKey })
    .then((result) => {
      process.stdout.write(`${JSON.stringify(result)}\n`);
      process.exit(result.ok ? 0 : 1);
    })
    .catch((error) => {
      process.stderr.write(`modal-statement: ${String(error?.message || error).slice(0, 200)}\n`);
      process.exit(1);
    });
}
