"""Contract tests for the Python half of the second-house heartbeat.

The expected message and signature are a fixed vector produced by the existing JavaScript
`heartbeat.mjs` implementation. Keeping the expected bytes literal makes this test fail if Python
adds JSON whitespace, changes field order, or signs a different set of fields.
"""

import unittest

from nacl.signing import SigningKey

from heartbeat import build_heartbeat_message, make_heartbeat_entry


SEED = bytes(range(32))
BLOCKHASH = "EkSnNWid2cvwEVnVx9aBqawnmiCNiDgp3gUdkDPTKN1N"
PAYER = "FAe4sisG95oZ42w7buUn5qEE4TAnfTTFPiguZUHmhiF"
EXPECTED_MESSAGE = (
    '{"blockhash":"EkSnNWid2cvwEVnVx9aBqawnmiCNiDgp3gUdkDPTKN1N",'
    '"cycle":1,"jobAddress":"sb-test-heartbeat",'
    '"payer":"FAe4sisG95oZ42w7buUn5qEE4TAnfTTFPiguZUHmhiF",'
    '"slot":2792,"ts":1785144000123}'
)
EXPECTED_SIG = (
    "27d8Q6rkEPqwVqM2oLePY3U12eDTjdioRW7wwN6KmqGXURccEZYF3vYxDcoBXdJG"
    "qbbAmbt9b9cr1bQMdGmvdkkA"
)


class CanonicalHeartbeat(unittest.TestCase):
    def test_matches_the_existing_javascript_verifier_vector(self):
        entry = make_heartbeat_entry(
            job_address="sb-test-heartbeat",
            blockhash=BLOCKHASH,
            slot=2792,
            ts=1785144000123,
            cycle=1,
            signing_key=SigningKey(SEED),
        )

        self.assertEqual(entry["payer"], PAYER)
        self.assertEqual(build_heartbeat_message(entry), EXPECTED_MESSAGE)
        self.assertEqual(entry["sig"], EXPECTED_SIG)
        self.assertEqual(
            list(entry),
            ["v", "kind", "ts", "cycle", "jobAddress", "payer", "slot", "blockhash", "sig"],
        )

    def test_rejects_invalid_public_fields_before_signing(self):
        valid = {
            "job_address": "sb-test-heartbeat",
            "blockhash": BLOCKHASH,
            "slot": 2792,
            "ts": 1785144000123,
            "cycle": 1,
            "signing_key": SigningKey(SEED),
        }
        for field, bad_value in (
            ("job_address", ""),
            ("blockhash", ""),
            ("slot", -1),
            ("ts", 0),
            ("cycle", 1.5),
        ):
            with self.subTest(field=field), self.assertRaises((TypeError, ValueError)):
                make_heartbeat_entry(**{**valid, field: bad_value})


if __name__ == "__main__":
    unittest.main()
