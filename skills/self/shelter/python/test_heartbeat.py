"""Contract tests for the Python half of the second-house heartbeat.

The expected message and signature are a fixed vector produced by the existing JavaScript
`heartbeat.mjs` implementation. Keeping the expected bytes literal makes this test fail if Python
adds JSON whitespace, changes field order, or signs a different set of fields.
"""

import io
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

from nacl.signing import SigningKey

from heartbeat import build_heartbeat_message, emit_heartbeats, make_heartbeat_entry


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


class TimedHeartbeat(unittest.TestCase):
    def test_two_cycles_keep_one_identity_and_sleep_between_rows(self):
        rpc_values = iter(
            [
                ("EkSnNWid2cvwEVnVx9aBqawnmiCNiDgp3gUdkDPTKN1N", 2792),
                ("9xQeWvG816bUx9EPfEZ5fC9AkQW6NQQyFjcU6VJHkT7k", 2793),
            ]
        )
        times = iter([1785144000123, 1785144005123])
        sleeps = []
        output = io.StringIO()

        entries = emit_heartbeats(
            job_address="sb-natural",
            cycles=2,
            interval_seconds=5,
            signing_key=SigningKey(SEED),
            fetcher=lambda: next(rpc_values),
            now_ms=lambda: next(times),
            sleep=sleeps.append,
            output=output,
        )

        rows = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual(rows, entries)
        self.assertEqual([row["cycle"] for row in rows], [1, 2])
        self.assertEqual([row["ts"] for row in rows], [1785144000123, 1785144005123])
        self.assertEqual({row["payer"] for row in rows}, {PAYER})
        self.assertEqual({row["jobAddress"] for row in rows}, {"sb-natural"})
        self.assertEqual(sleeps, [5])

    def test_cli_refuses_to_emit_without_the_modal_sandbox_id(self):
        env = dict(os.environ)
        env.pop("MODAL_SANDBOX_ID", None)
        result = subprocess.run(
            [sys.executable, str(Path(__file__).with_name("heartbeat.py")), "--cycles", "1"],
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertIn("MODAL_SANDBOX_ID", result.stderr)


if __name__ == "__main__":
    unittest.main()
