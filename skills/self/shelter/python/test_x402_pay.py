"""Tests for the Python x402 client. No network, no money — the signing path is pure once the
key and the clock are supplied."""

import base64
import json
import unittest

from x402_pay import (
    PAYMENT_HEADER,
    build_payment_header,
    choose_requirement,
    pay_and_post,
    read_payment_required,
)

# A real 402 captured from blockrun.ai on 2026-07-27.
ACCEPTED = {
    "scheme": "exact",
    "network": "eip155:8453",
    "amount": "3727",
    "asset": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
    "payTo": "0xe9030014F5DAe217d0A152f02A043567b16c1aBf",
    "maxTimeoutSeconds": 300,
    "extra": {"name": "USD Coin", "version": "2"},
}
TERMS = {"x402Version": 2, "accepts": [ACCEPTED]}
KEY = "0x" + "11" * 32


def decode(header):
    return json.loads(base64.b64decode(header))


class FakeResponse:
    def __init__(self, status_code, body=None, headers=None, text=""):
        self.status_code = status_code
        self._body = body or {}
        self.headers = headers or {}
        self.text = text

    def json(self):
        return self._body


class FakeSession:
    """Records every POST so a test can assert what was sent, and when."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def post(self, url, json=None, headers=None):
        self.calls.append({"url": url, "json": json, "headers": headers or {}})
        return self.responses.pop(0)


class BuildHeader(unittest.TestCase):
    def test_envelope_matches_what_the_server_parses(self):
        payload = decode(build_payment_header(ACCEPTED, KEY, now=1_000_000))
        self.assertEqual(payload["x402Version"], 2)
        self.assertEqual(payload["accepted"], ACCEPTED, "the chosen offer is echoed back verbatim")
        self.assertEqual(set(payload["payload"]), {"authorization", "signature"})

    def test_amount_is_never_converted(self):
        # The 402 quotes base units. Any decimal maths here would pay the wrong number and the
        # signature would still be valid — an error that settles rather than failing loudly.
        auth = decode(build_payment_header(ACCEPTED, KEY, now=1_000_000))["payload"]["authorization"]
        self.assertEqual(auth["value"], "3727")

    def test_validity_window_starts_at_zero_and_ends_at_the_quoted_timeout(self):
        auth = decode(build_payment_header(ACCEPTED, KEY, now=1_000_000))["payload"]["authorization"]
        self.assertEqual(auth["validAfter"], "0")
        self.assertEqual(auth["validBefore"], str(1_000_000 + 300))

    def test_nonce_is_thirty_two_fresh_random_bytes(self):
        seen = set()
        for _ in range(5):
            auth = decode(build_payment_header(ACCEPTED, KEY, now=1))["payload"]["authorization"]
            self.assertTrue(auth["nonce"].startswith("0x"))
            self.assertEqual(len(auth["nonce"]), 66)
            seen.add(auth["nonce"])
        self.assertEqual(len(seen), 5, "a repeated nonce would let the same authorisation replay")

    def test_signature_carries_its_prefix(self):
        # HexBytes.hex() omits 0x on some versions; a bare hex string is rejected downstream and the
        # only symptom is a second 402.
        sig = decode(build_payment_header(ACCEPTED, KEY, now=1))["payload"]["signature"]
        self.assertTrue(sig.startswith("0x"))
        self.assertEqual(len(sig), 132)


class ChooseRequirement(unittest.TestCase):
    def test_skips_offers_this_wallet_cannot_settle(self):
        terms = {
            "accepts": [
                {"scheme": "upto", "network": "eip155:8453", "extra": {"name": "x", "version": "2"}},
                {"scheme": "exact", "network": "solana:mainnet", "extra": {"name": "x", "version": "2"}},
                ACCEPTED,
            ]
        }
        self.assertEqual(choose_requirement(terms), ACCEPTED)

    def test_refuses_an_offer_missing_the_token_domain(self):
        # Signing without the token's own EIP-712 name/version produces a valid signature for the
        # wrong domain, which the facilitator reads as a forgery.
        terms = {"accepts": [dict(ACCEPTED, extra={})]}
        self.assertIsNone(choose_requirement(terms))


class ReadPaymentRequired(unittest.TestCase):
    def test_reads_the_header_form(self):
        encoded = base64.b64encode(json.dumps(TERMS).encode()).decode()
        got = read_payment_required(FakeResponse(402, headers={"PAYMENT-REQUIRED": encoded}))
        self.assertEqual(got, TERMS)

    def test_falls_back_to_the_body_form(self):
        # Measured: blockrun.ai answers with the terms in the body. A client that only reads the
        # header cannot see the price and looks like it was refused.
        self.assertEqual(read_payment_required(FakeResponse(402, body=TERMS)), TERMS)


class PayAndPost(unittest.TestCase):
    def test_pays_once_and_repeats_the_request(self):
        session = FakeSession([FakeResponse(402, body=TERMS), FakeResponse(200, text="{}")])
        result = pay_and_post("https://x/y", {"a": 1}, KEY, session=session)
        self.assertTrue(result["ok"])
        self.assertTrue(result["paid"])
        self.assertEqual(session.calls[0]["headers"], {}, "the first attempt must not pre-pay")
        self.assertIn(PAYMENT_HEADER, session.calls[1]["headers"])
        self.assertEqual(session.calls[1]["json"], {"a": 1}, "the retry sends the same body")

    def test_does_not_pay_when_the_resource_is_free(self):
        session = FakeSession([FakeResponse(200, text="{}")])
        result = pay_and_post("https://x/y", {}, KEY, session=session)
        self.assertFalse(result["paid"])
        self.assertEqual(len(session.calls), 1)

    def test_refuses_a_price_over_the_ceiling_before_signing(self):
        session = FakeSession([FakeResponse(402, body=TERMS)])
        result = pay_and_post("https://x/y", {}, KEY, session=session, max_price=1000)
        self.assertFalse(result["ok"])
        self.assertFalse(result["paid"])
        self.assertIn("over the 1000 allowed", result["reason"])
        self.assertEqual(len(session.calls), 1, "it must not send a second request it cannot afford")

    def test_reports_the_settlement_transaction(self):
        receipt = base64.b64encode(json.dumps({"transaction": "0xdead"}).encode()).decode()
        session = FakeSession([
            FakeResponse(402, body=TERMS),
            FakeResponse(200, headers={"PAYMENT-RESPONSE": receipt}, text="{}"),
        ])
        self.assertEqual(pay_and_post("https://x/y", {}, KEY, session=session)["tx"], "0xdead")


if __name__ == "__main__":
    unittest.main()
