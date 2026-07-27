"""Contract tests for the public financial statement served by the Python second house."""

import math
import unittest

from statement import (
    allowlist_public_statement,
    build_public_statement,
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


if __name__ == "__main__":
    unittest.main()
