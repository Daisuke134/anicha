"""Contract tests for the public financial statement served by the Python second house."""

import math
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import unittest

from statement import (
    allowlist_public_statement,
    build_public_statement,
    extract_tunnel_url,
    launch_public_statement,
    make_statement_handler,
    render_statement_html,
)


BASE_ADDRESS = "0x810f6d61f7606deee2657d3083e150a222bc29c5"
SOLANA_ADDRESS = "71FfqFniYoMsWZb1qFeQDb1fk2xqvajzivpsnMb44gTf"
PM_ADDRESS = "0x904B50d2e214Da947d83D6a2D32c4E3Ffc17Eb74"

BASE_RESULT = {"jsonrpc": "2.0", "id": 1, "result": "0x1c1768"}
SOL_RESULT = {
    "jsonrpc": "2.0",
    "id": 1,
    "result": {"context": {"slot": 435535380}, "value": 26094157},
}
NOS_RESULT = {
    "jsonrpc": "2.0",
    "id": 1,
    "result": {
        "context": {"slot": 435535380},
        "value": [
            {
                "account": {
                    "data": {
                        "parsed": {
                            "info": {
                                "tokenAmount": {
                                    "amount": "500000",
                                    "decimals": 6,
                                    "uiAmount": 0.5,
                                    "uiAmountString": "0.5",
                                }
                            }
                        }
                    }
                }
            }
        ],
    },
}
PM_RESULT = [
    {
        "proxyWallet": PM_ADDRESS.lower(),
        "asset": "111",
        "size": 8,
        "currentValue": 6.376,
        "cashPnl": 0.8375,
        "realizedPnl": -0.9615,
        "redeemable": False,
        "title": "Fed decision",
    },
    {
        "proxyWallet": PM_ADDRESS.lower(),
        "asset": "222",
        "size": 7.9761,
        "currentValue": 1.6191,
        "cashPnl": 0.2791,
        "realizedPnl": 1.2,
        "redeemable": False,
        "title": "Fed decision",
    },
]


def complete_transport(url, payload=None):
    if "base.org" in url:
        if payload["method"] != "eth_call":
            raise AssertionError(f"unexpected Base method: {payload['method']}")
        return BASE_RESULT
    if "solana.com" in url:
        if payload["method"] == "getBalance":
            return SOL_RESULT
        if payload["method"] == "getTokenAccountsByOwner":
            return NOS_RESULT
        raise AssertionError(f"unexpected Solana method: {payload['method']}")
    if "data-api.polymarket.com/positions" in url:
        return PM_RESULT
    raise AssertionError(f"unexpected URL: {url}")


def build_fixture(**overrides):
    values = {
        "sandbox_id": "sb-test",
        "base_address": BASE_ADDRESS,
        "solana_address": SOLANA_ADDRESS,
        "polymarket_address": PM_ADDRESS,
        "request_json": complete_transport,
        "heartbeats": [{"verified": True}, {"verified": True}],
        "now_ms": lambda: 1785150000123,
    }
    values.update(overrides)
    return build_public_statement(**values)


class PublicSnapshot(unittest.TestCase):
    def test_collects_literal_public_values_without_calling_them_revenue(self):
        statement = build_fixture()

        self.assertEqual(
            statement["balances"],
            {"baseUsdc": 1.841, "solanaSol": 0.026094157, "solanaNos": 0.5},
        )
        self.assertEqual(
            statement["polymarket"],
            {
                "positionCount": 2,
                "currentValueUsd": 7.9951,
                "cashPnlUsd": 1.1166,
                "redeemableCount": 0,
            },
        )
        self.assertEqual(
            statement["economy"],
            {
                "externalRevenueUsd": 0.0,
                "runtimeCostUsd": 0.015,
                "verdict": "funded",
            },
        )
        self.assertEqual(statement["heartbeats"], {"claimed": 2, "verified": 2})
        self.assertEqual(statement["generatedAt"], 1785150000123)

    def test_allowlist_drops_unknown_fields_at_every_level(self):
        candidate = {
            **build_fixture(),
            "apiKey": "sk-live-must-not-render",
            "wallets": {
                **build_fixture()["wallets"],
                "privateKey": "0x" + "11" * 32,
            },
            "polymarket": {
                **build_fixture()["polymarket"],
                "titles": ["private strategy"],
            },
        }

        public = allowlist_public_statement(candidate)
        rendered = str(public)

        self.assertNotIn("apiKey", rendered)
        self.assertNotIn("privateKey", rendered)
        self.assertNotIn("sk-live", rendered)
        self.assertNotIn("private strategy", rendered)
        self.assertEqual(
            set(public),
            {
                "v",
                "generatedAt",
                "sandboxId",
                "wallets",
                "balances",
                "polymarket",
                "economy",
                "heartbeats",
            },
        )

    def test_malformed_public_numbers_fail_closed(self):
        bad_values = (-1, True, math.nan, "not-a-number", None)
        for bad in bad_values:
            def bad_transport(url, payload=None, value=bad):
                if "base.org" in url:
                    return {"jsonrpc": "2.0", "id": 1, "result": value}
                return complete_transport(url, payload)

            with self.subTest(value=bad), self.assertRaises(ValueError):
                build_fixture(request_json=bad_transport)


class StatementHtml(unittest.TestCase):
    def test_escapes_public_text_and_contains_no_active_content(self):
        statement = build_fixture()
        statement["wallets"]["base"] = '<script src="https://bad.example/x.js"></script>'

        html = render_statement_html(statement)

        self.assertNotIn("<script", html)
        self.assertNotIn("<form", html)
        self.assertNotIn("file://", html)
        self.assertIn("&lt;script", html)

    def test_prints_external_zero_and_labels_polymarket_as_marked_not_net(self):
        html = render_statement_html(build_fixture())

        self.assertIn("$0.00 from outside", html)
        self.assertIn("$7.9951", html)
        self.assertIn("marked position value", html.lower())
        self.assertIn("not closed net profit", html.lower())


class StatementRoutes(unittest.TestCase):
    def setUp(self):
        self.statement = build_fixture()
        self.current_statement = self.statement
        self.heartbeat_jsonl = (
            '{"v":1,"kind":"shelter-heartbeat","cycle":1}\n'
            '{"v":1,"kind":"shelter-heartbeat","cycle":2}\n'
        )
        handler = make_statement_handler(
            self.statement,
            self.heartbeat_jsonl,
            statement_provider=lambda: self.current_statement,
        )
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.origin = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def fetch(self, path, method="GET"):
        request = Request(f"{self.origin}{path}", method=method)
        try:
            with urlopen(request, timeout=2) as response:
                return response.status, dict(response.headers), response.read()
        except HTTPError as error:
            body = error.read()
            error.close()
            return error.code, dict(error.headers), body

    def test_serves_only_the_three_public_get_routes_from_memory(self):
        html_status, html_headers, html = self.fetch("/")
        json_status, json_headers, statement_json = self.fetch("/statement.json")
        heartbeat_status, heartbeat_headers, heartbeats = self.fetch("/heartbeats")
        missing_status, _, _ = self.fetch("/private-key")
        post_status, _, _ = self.fetch("/", method="POST")

        self.assertEqual((html_status, json_status, heartbeat_status), (200, 200, 200))
        self.assertTrue(html_headers["Content-Type"].startswith("text/html"))
        self.assertTrue(json_headers["Content-Type"].startswith("application/json"))
        self.assertTrue(heartbeat_headers["Content-Type"].startswith("application/x-ndjson"))
        self.assertIn(b"$0.00 from outside", html)
        self.assertEqual(json.loads(statement_json)["sandboxId"], "sb-test")
        self.assertEqual(heartbeats, self.heartbeat_jsonl.encode("utf-8"))
        self.assertEqual(missing_status, 404)
        self.assertEqual(post_status, 501)

    def test_statement_routes_refresh_public_values_at_request_time(self):
        self.current_statement = {
            **self.statement,
            "generatedAt": self.statement["generatedAt"] + 1,
            "balances": {**self.statement["balances"], "baseUsdc": 1.811},
        }

        _, _, statement_json = self.fetch("/statement.json")
        _, _, html = self.fetch("/")

        self.assertEqual(json.loads(statement_json)["balances"]["baseUsdc"], 1.811)
        self.assertIn(b"$1.811000", html)


class FakeProcess:
    def poll(self):
        return None


class PublicLaunch(unittest.TestCase):
    def test_accepts_exactly_one_https_trycloudflare_url(self):
        url = extract_tunnel_url(
            "INF Requesting new quick Tunnel\n"
            "INF +https://spring-river-123.trycloudflare.com ready\n"
        )
        self.assertEqual(url, "https://spring-river-123.trycloudflare.com")

        for bad in (
            "http://spring-river-123.trycloudflare.com",
            "https://spring-river-123.example.com",
            "https://one.trycloudflare.com https://two.trycloudflare.com",
            "",
        ):
            with self.subTest(log=bad), self.assertRaises(ValueError):
                extract_tunnel_url(bad)

    def test_launches_detached_server_and_tunnel_with_public_arguments_only(self):
        calls = []

        def fake_popen(args, **kwargs):
            calls.append({"args": args, "kwargs": kwargs})
            return FakeProcess()

        def heartbeat_emitter(**kwargs):
            rows = [
                {
                    "v": 1,
                    "kind": "shelter-heartbeat",
                    "ts": 1785150000000,
                    "cycle": 1,
                    "jobAddress": "sb-test",
                    "payer": "FAe4sisG95oZ42w7buUn5qEE4TAnfTTFPiguZUHmhiF",
                    "slot": 10,
                    "blockhash": "EkSnNWid2cvwEVnVx9aBqawnmiCNiDgp3gUdkDPTKN1N",
                    "sig": "27d8Q6rkEPqwVqM2oLePY3U12eDTjdioRW7wwN6KmqGXURccEZYF3vYxDcoBXdJGqbbAmbt9b9cr1bQMdGmvdkkA",
                },
                {
                    "v": 1,
                    "kind": "shelter-heartbeat",
                    "ts": 1785150005000,
                    "cycle": 2,
                    "jobAddress": "sb-test",
                    "payer": "FAe4sisG95oZ42w7buUn5qEE4TAnfTTFPiguZUHmhiF",
                    "slot": 11,
                    "blockhash": "9xQeWvG816bUx9EPfEZ5fC9AkQW6NQQyFjcU6VJHkT7k",
                    "sig": "3Zyt3i7AYhUPG3RXLL6fys3UNoGJDPyLQkKjcqCmCAuhME6jaMsdx6k22HfpNBLhPuhbym9JEqA6SaKQNUwZvmt9",
                },
            ]
            for row in rows:
                kwargs["output"].write(json.dumps(row, separators=(",", ":")) + "\n")
            return rows

        with tempfile.TemporaryDirectory() as temporary:
            result = launch_public_statement(
                cloudflared_path="/tmp/cloudflared",
                port=8080,
                sandbox_id="sb-test",
                base_address=BASE_ADDRESS,
                solana_address=SOLANA_ADDRESS,
                polymarket_address=PM_ADDRESS,
                request_json=complete_transport,
                heartbeat_emitter=heartbeat_emitter,
                heartbeat_verifier=lambda _row: True,
                popen=fake_popen,
                sleep=lambda _: None,
                read_text=lambda _: "https://spring-river-123.trycloudflare.com",
                temporary_root=Path(temporary),
                now_ms=lambda: 1785150000123,
            )

        self.assertEqual(result["url"], "https://spring-river-123.trycloudflare.com")
        self.assertEqual(result["statement"]["heartbeats"], {"claimed": 2, "verified": 2})
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0]["args"][1:3], [str(Path(__file__).with_name("statement.py")), "serve"])
        self.assertEqual(
            calls[1]["args"][:5],
            [
                "/tmp/cloudflared",
                "tunnel",
                "--no-autoupdate",
                "--url",
                "http://127.0.0.1:8080",
            ],
        )
        self.assertTrue(calls[0]["kwargs"]["start_new_session"])
        self.assertTrue(calls[1]["kwargs"]["start_new_session"])
        flattened = json.dumps(calls)
        self.assertNotIn("BASE_KEY", flattened)
        self.assertNotIn("SOLANA_SESSION", flattened)


if __name__ == "__main__":
    unittest.main()
