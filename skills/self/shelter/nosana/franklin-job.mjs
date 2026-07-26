// franklin-job.mjs — builds the S12 job definition that puts Franklin ITSELF inside the Nosana
// container it paid for. The sub-wallet (S8) plays two roles at once: it is the rent payer AND
// Franklin's cloud identity — its base58 secret is delivered ONLY via a confidential job's env
// (S13 proved public IPFS carries just a stub for confidential posts; a normal post would leak
// the secret world-readably, so callers MUST post this definition with --confidential).
//
// The container: installs @blockrun/franklin, writes $SOLANA_SESSION to the SDK-canonical
// key file (dist/agent/context.js:740: $BLOCKRUN_DIR/.solana-session), runs ONE non-interactive
// prompt with a hard --max-spend, tees the output to /tmp/proof.txt, then serves that proof on
// the exposed port for the REST of the lease — the keep-alive that makes the job a service whose
// aliveness anyone can probe from outside (S9 evidence model, but served from inside the room).
//
// Money-safety: the secret exists only in ops[0].args.env.SOLANA_SESSION (confidential channel)
// — never interpolated into cmd, never logged here.

import bs58 from "bs58";
import fs from "node:fs";

import { buildServiceJobDefinition } from "./job-definition.mjs";
import { ensureSubWallet } from "./sub-wallet.mjs";

export const FRANKLIN_DEFAULT_MODEL = "openai/gpt-5-mini";
export const FRANKLIN_DEFAULT_MAX_SPEND_USD = 0.02;
export const FRANKLIN_DEFAULT_PROMPT =
  "You are Franklin running inside a Nosana GPU container that YOUR OWN wallet paid for. " +
  "In 3 sentences: state that you are an AI agent paying for its own compute and shelter, " +
  "state today's context (you cannot browse — just reason), and sign off with your wallet's role.";

/**
 * Read the S8 sub-wallet secret and return it base58-encoded (the .solana-session format).
 * NEVER log the return value. Throws secret-free errors.
 */
export function subWalletSecretBase58({ env = process.env } = {}) {
  const { keypairPath } = ensureSubWallet({ env });
  let bytes;
  try {
    bytes = Uint8Array.from(JSON.parse(fs.readFileSync(keypairPath, "utf8")));
  } catch {
    throw new Error("subWalletSecretBase58: sub-wallet file unreadable — run citizen-subwallet first");
  }
  if (bytes.length !== 64) throw new Error("subWalletSecretBase58: sub-wallet file must contain 64 bytes");
  return bs58.encode(bytes);
}

/**
 * Pure: the container boot script. Kept as a separate exported builder so tests can assert the
 * secret NEVER appears in cmd — it reaches the container only through env.
 */
export function buildFranklinBootScript({ model, maxSpendUsd, prompt, exposePort, withBaseKey = false }) {
  if (typeof prompt !== "string" || prompt.length === 0) throw new Error("buildFranklinBootScript: prompt required");
  // Single sh -c script. Franklin output → /tmp/proof.txt; then a forever http server serves it.
  // ONE flat string — a live A/B (probe job 6ceJBBkf vs franklin job J4FW, 2026-07-26) showed the
  // node runs a string cmd fine but an ["sh","-c",script] ARRAY died ~3s into the flow. String it is.
  return [
    "set -e",
    "npm i -g @blockrun/franklin >/tmp/npm.log 2>&1",
    'mkdir -p "$HOME/.blockrun"',
    'printf "%s" "$SOLANA_SESSION" > "$HOME/.blockrun/.solana-session"',
    'chmod 600 "$HOME/.blockrun/.solana-session"',
    `(franklin start --trust -m ${model} --max-spend ${maxSpendUsd} -p ${JSON.stringify(prompt)} 2>&1 | tee /tmp/proof.txt) || true`,
    // S12c: pay for a REAL frontier call from the container's own capped Base wallet, via x402
    // (EIP-3009 -> no gas needed). Appends the model's answer + the on-chain tx to the proof file,
    // so the public URL shows an AI that bought its own inference from inside its own rented box.
    ...(withBaseKey ? [
      "mkdir -p /tmp/x402 && cd /tmp/x402 && npm init -y >>/tmp/npm.log 2>&1 && npm i @x402/fetch @x402/evm viem >>/tmp/npm.log 2>&1",
      `cd /tmp/x402 && node -e 'const{wrapFetchWithPaymentFromConfig}=require("@x402/fetch"),{ExactEvmScheme}=require("@x402/evm/exact/client"),{privateKeyToAccount}=require("viem/accounts");const a=privateKeyToAccount(process.env.BASE_KEY);const f=wrapFetchWithPaymentFromConfig(fetch,{schemes:[{network:"eip155:8453",client:new ExactEvmScheme(a)}]});f("https://blockrun.ai/api/v1/chat/completions",{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify({model:"openai/gpt-5-mini",messages:[{role:"user",content:"State in one sentence that you are running inside a container your own wallet rented, and that you just paid for this sentence yourself."}],max_tokens:80})}).then(async r=>{const t=await r.text();const pr=r.headers.get("x-payment-response")||r.headers.get("payment-response");let tx="";try{tx=JSON.parse(Buffer.from(pr,"base64").toString()).transaction}catch(e){}require("fs").appendFileSync("/tmp/proof.txt","\\n\\n=== FRONTIER SELF-PAID (Base x402) ===\\npayer: "+a.address+"\\ntx: "+tx+"\\nHTTP "+r.status+"\\n"+t.slice(0,600)+"\\n")}).catch(e=>require("fs").appendFileSync("/tmp/proof.txt","\\nfrontier pay failed: "+e.message+"\\n"))' || true`,
    ] : []),
    // Keep-alive proof server: anyone can GET the container's own account of what it did.
    `node -e 'const http=require("http"),fs=require("fs");http.createServer((q,s)=>{s.setHeader("content-type","text/plain");s.end("FRANKLIN-IN-NOSANA proof\\n\\n"+fs.readFileSync("/tmp/proof.txt","utf8"))}).listen(${exposePort},()=>console.log("proof server on ${exposePort}"))'`,
  ].join("; ");
}

/**
 * The full confidential job definition. gpu:true for market compatibility (the cheapest live
 * market is GPU-gated; nginx jobs ran fine on it with the same flag).
 */
export function buildFranklinJobDefinition({
  solanaSessionB58,
  baseKey,
  model = FRANKLIN_DEFAULT_MODEL,
  maxSpendUsd = FRANKLIN_DEFAULT_MAX_SPEND_USD,
  prompt = FRANKLIN_DEFAULT_PROMPT,
  exposePort = 8080,
} = {}) {
  if (typeof solanaSessionB58 !== "string" || solanaSessionB58.length < 32) {
    throw new Error("buildFranklinJobDefinition: solanaSessionB58 is required");
  }
  const script = buildFranklinBootScript({ model, maxSpendUsd, prompt, exposePort, withBaseKey: Boolean(baseKey) });
  const def = buildServiceJobDefinition({
    image: "docker.io/library/node:20-alpine",
    exposePort,
    gpu: true,
    cmd: script,
    // BASE_KEY (S12c): a CAPPED Base sub-wallet key. x402 on Base uses EIP-3009 signatures, so this
    // key needs NO gas — it can buy frontier inference ($0.003/call, verified tx 0x7830cd41…) with
    // USDC alone. Ships ONLY through the confidential channel; the founder key never leaves the Mac.
    env: baseKey ? { SOLANA_SESSION: solanaSessionB58, BASE_KEY: baseKey } : { SOLANA_SESSION: solanaSessionB58 },
    id: "franklin",
  });
  return def;
}
