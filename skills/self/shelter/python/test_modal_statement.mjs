import test from "node:test";
import assert from "node:assert/strict";

import {
  buildStatementCommand,
  compareFinancialSnapshots,
  fetchTunnelRouteDirect,
  parseStatementControl,
  proveModalStatement,
  validatePublicStatement,
} from "./modal-statement.mjs";


const SANDBOX_ID = "sb-0l4DnecMvMpXm4OzLLcFTn";
const PUBLIC_URL = "https://spring-river-123.trycloudflare.com";
const BASE_ADDRESS = "0x810f6d61f7606deee2657d3083e150a222bc29c5";
const SOLANA_ADDRESS = "71FfqFniYoMsWZb1qFeQDb1fk2xqvajzivpsnMb44gTf";
const PM_ADDRESS = "0x904B50d2e214Da947d83D6a2D32c4E3Ffc17Eb74";

const HEARTBEATS = [
  {
    v: 1,
    kind: "shelter-heartbeat",
    ts: 1785149903381,
    cycle: 1,
    jobAddress: SANDBOX_ID,
    payer: "8jKHY8328rrTge57et8C6mcrigZJFnnHw7Gm6kReKHkT",
    slot: 435525136,
    blockhash: "CQrdXq9h6uPTfceevZzKpmSeC1c9RiTeEFzfuEX3xXRC",
    sig: "3Zyt3i7AYhUPG3RXLL6fys3UNoGJDPyLQkKjcqCmCAuhME6jaMsdx6k22HfpNBLhPuhbym9JEqA6SaKQNUwZvmt9",
  },
  {
    v: 1,
    kind: "shelter-heartbeat",
    ts: 1785149908693,
    cycle: 2,
    jobAddress: SANDBOX_ID,
    payer: "8jKHY8328rrTge57et8C6mcrigZJFnnHw7Gm6kReKHkT",
    slot: 435525148,
    blockhash: "CXbVTwNANwDRgn4rLbKeM5UowJoob9hKToM4Ner1ZLdH",
    sig: "2TT9DGjQSSuQUaQzgWWUWgqRyAFZhqtag9nuMVRWTKfDPuMdS95JRb7a5zR8EYZeAHtbcEVkDBiRF41GDEdarx4f",
  },
];

const STATEMENT = {
  v: 1,
  generatedAt: 1785150000123,
  sandboxId: SANDBOX_ID,
  wallets: {
    base: BASE_ADDRESS,
    solana: SOLANA_ADDRESS,
    polymarket: PM_ADDRESS,
  },
  balances: {
    baseUsdc: 1.841,
    solanaSol: 0.026094157,
    solanaNos: 0.5,
  },
  polymarket: {
    positionCount: 2,
    currentValueUsd: 7.9951,
    cashPnlUsd: 1.1166,
    redeemableCount: 0,
  },
  economy: {
    externalRevenueUsd: 0,
    runtimeCostUsd: 0.015,
    verdict: "funded",
  },
  heartbeats: {
    claimed: 2,
    verified: 2,
  },
};

const INDEPENDENT = {
  balances: {
    baseUsdc: 1.841,
    solanaSol: 0.026094157,
    solanaNos: 0.5,
  },
  polymarket: {
    positionCount: 2,
    currentValueUsd: 7.9951,
    cashPnlUsd: 1.1166,
    redeemableCount: 0,
  },
};

const heartbeatJsonl = `${HEARTBEATS.map((row) => JSON.stringify(row)).join("\n")}\n`;


function response(body, { status = 200, contentType = "application/json" } = {}) {
  const textBody = typeof body === "string" ? body : JSON.stringify(body);
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: {
      get(name) {
        return name.toLowerCase() === "content-type" ? contentType : null;
      },
    },
    async text() {
      return textBody;
    },
    async json() {
      return JSON.parse(textBody);
    },
  };
}


test("packaged command obeys the live gateway limit and carries no caller key", () => {
  const command = buildStatementCommand();

  assert.deepEqual(command.slice(0, 2), ["sh", "-c"]);
  assert.equal(command.every((part) => part.length <= 2000), true);
  assert.match(command[2], /2026\.7\.3/);
  assert.match(command[2], /9d71c677db00134c1bd4144b7783486b654ad281b1ea62b4972098d19f770f17/);
  assert.equal(command.join(" ").includes("BASE_KEY"), false);
  assert.equal(command.join(" ").includes("SOLANA_SESSION"), false);
  assert.equal(command.join(" ").includes("PRIVATE_KEY"), false);
});


test("control output accepts one exact HTTPS Quick Tunnel origin", () => {
  const parsed = parseStatementControl(`${JSON.stringify({
    ok: true,
    sandboxId: SANDBOX_ID,
    url: PUBLIC_URL,
    statement: STATEMENT,
  })}\n`);
  assert.equal(parsed.url, PUBLIC_URL);

  for (const url of [
    "http://spring-river-123.trycloudflare.com",
    "https://spring-river-123.example.com",
    "https://spring-river-123.trycloudflare.com/path",
  ]) {
    assert.throws(
      () => parseStatementControl(JSON.stringify({ ok: true, sandboxId: SANDBOX_ID, url, statement: STATEMENT })),
      /tunnel URL/,
    );
  }
});


test("public statement requires the exact recursive schema and sandbox identity", () => {
  assert.deepEqual(validatePublicStatement(STATEMENT, SANDBOX_ID), { ok: true, reason: "public schema verifies" });

  const wrongSandbox = { ...STATEMENT, sandboxId: "sb-other" };
  assert.equal(validatePublicStatement(wrongSandbox, SANDBOX_ID).ok, false);

  const topSecret = { ...STATEMENT, privateKey: `0x${"11".repeat(32)}` };
  assert.equal(validatePublicStatement(topSecret, SANDBOX_ID).ok, false);

  const nestedSecret = {
    ...STATEMENT,
    wallets: { ...STATEMENT.wallets, cookie: "session=secret" },
  };
  assert.equal(validatePublicStatement(nestedSecret, SANDBOX_ID).ok, false);
});


test("financial comparison is exact except for one cent of live Polymarket drift", () => {
  assert.deepEqual(compareFinancialSnapshots(STATEMENT, INDEPENDENT), { ok: true, differences: [] });

  const driftingMarket = {
    ...INDEPENDENT,
    polymarket: { ...INDEPENDENT.polymarket, currentValueUsd: 8.0049 },
  };
  assert.equal(compareFinancialSnapshots(STATEMENT, driftingMarket).ok, true);

  const wrongBase = {
    ...INDEPENDENT,
    balances: { ...INDEPENDENT.balances, baseUsdc: 1.84 },
  };
  assert.deepEqual(
    compareFinancialSnapshots(STATEMENT, wrongBase).differences,
    [{ field: "balances.baseUsdc", published: 1.841, independent: 1.84 }],
  );

  const excessiveMarketDrift = {
    ...INDEPENDENT,
    polymarket: { ...INDEPENDENT.polymarket, cashPnlUsd: 1.13 },
  };
  assert.equal(compareFinancialSnapshots(STATEMENT, excessiveMarketDrift).ok, false);
});


test("tunnel fetch bypasses a stale system DNS cache while preserving TLS hostname", async () => {
  const calls = [];
  const route = await fetchTunnelRouteDirect(
    PUBLIC_URL,
    "/statement.json",
    "application/json",
    {
      resolve4Impl: async (hostname) => {
        assert.equal(hostname, "spring-river-123.trycloudflare.com");
        return ["104.16.231.132", "104.16.230.132"];
      },
      requestIpImpl: async (options) => {
        calls.push(options);
        return {
          status: 200,
          text: JSON.stringify(STATEMENT),
          contentType: "application/json; charset=utf-8",
        };
      },
    },
  );

  assert.equal(route.status, 200);
  assert.deepEqual(calls, [{
    ip: "104.16.230.132",
    hostname: "spring-river-123.trycloudflare.com",
    path: "/statement.json",
  }]);
});


test("paid proof fetches three live routes and independently re-reads every rail", async () => {
  const paidResponses = [
    response({ sandbox_id: SANDBOX_ID, status: "running" }),
    response({
      sandbox_id: SANDBOX_ID,
      stdout: `${JSON.stringify({
        ok: true,
        sandboxId: SANDBOX_ID,
        url: PUBLIC_URL,
        statement: {
          ...STATEMENT,
          generatedAt: STATEMENT.generatedAt - 1,
          balances: { ...STATEMENT.balances, baseUsdc: 1.844 },
        },
      })}\n`,
      stderr: "",
      returncode: 0,
    }),
  ];
  const paidFetch = async () => paidResponses.shift();
  const publicCalls = [];

  const publicFetch = async (url, init = {}) => {
    publicCalls.push({ url, init });
    if (url === `${PUBLIC_URL}/`) {
      return response(
        `<!doctype html><p>${SANDBOX_ID}</p><p>$0.00 from outside</p>`,
        { contentType: "text/html; charset=utf-8" },
      );
    }
    if (url === `${PUBLIC_URL}/statement.json`) {
      return response(STATEMENT);
    }
    if (url === `${PUBLIC_URL}/heartbeats`) {
      return response(heartbeatJsonl, { contentType: "application/x-ndjson; charset=utf-8" });
    }
    if (url === "https://mainnet.base.org") {
      return response({ jsonrpc: "2.0", id: 1, result: "0x1c1768" });
    }
    if (url === "https://api.mainnet-beta.solana.com") {
      const body = JSON.parse(init.body);
      if (body.method === "getBalance") {
        return response({ jsonrpc: "2.0", id: 1, result: { context: { slot: 1 }, value: 26094157 } });
      }
      return response({
        jsonrpc: "2.0",
        id: 1,
        result: {
          value: [{
            account: {
              data: {
                parsed: {
                  info: { tokenAmount: { amount: "500000", decimals: 6 } },
                },
              },
            },
          }],
        },
      });
    }
    if (url.startsWith("https://data-api.polymarket.com/positions?")) {
      return response([
        { currentValue: 6.376, cashPnl: 0.8375, redeemable: false },
        { currentValue: 1.6191, cashPnl: 0.2791, redeemable: false },
      ]);
    }
    throw new Error(`unexpected public URL: ${url}`);
  };

  const result = await proveModalStatement({
    baseKey: `0x${"11".repeat(32)}`,
    fetchImpl: paidFetch,
    publicFetch,
    tunnelRouteFetch: async (origin, path, expectedContentType) => {
      const publicResponse = await publicFetch(`${origin}${path}`);
      const text = await publicResponse.text();
      const contentType = publicResponse.headers.get("content-type") || "";
      assert.equal(contentType.startsWith(expectedContentType), true);
      return { status: publicResponse.status, text, contentType };
    },
  });

  assert.equal(result.ok, true);
  assert.equal(result.sandboxId, SANDBOX_ID);
  assert.equal(result.url, PUBLIC_URL);
  assert.equal(result.heartbeatVerification.entries.length, 2);
  assert.deepEqual(result.comparison, { ok: true, differences: [] });
  assert.deepEqual(result.routes, { "/": 200, "/statement.json": 200, "/heartbeats": 200 });
  assert.equal(publicCalls.some((call) => call.url === "https://mainnet.base.org"), true);
  assert.equal(publicCalls.filter((call) => call.url === "https://api.mainnet-beta.solana.com").length, 2);
  assert.equal(publicCalls.some((call) => call.url.includes("data-api.polymarket.com/positions")), true);
});
