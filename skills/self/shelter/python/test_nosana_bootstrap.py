import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest

from nacl.public import PublicKey, SealedBox
from solders.keypair import Keypair
from solders.pubkey import Pubkey

from nosana_bootstrap import (
    CONFIDENTIAL_STUB_CID,
    JOBS_PROGRAM,
    build_authorization,
    build_list_instruction,
    bootstrap_once,
    decrypt_bootstrap_bundle,
    decode_confidential_stub_cid,
    deliver_definition_until_running,
    evaluate_post_gate,
    prepare_ephemeral_key,
    parse_market_account,
    select_active_job,
    submit_list_job,
)


MARKET = "7AtiXMSH6R1jjBxrcYjehCkkSF7zvYWte63gwEDBcGHq"


class NosanaInstructionTests(unittest.TestCase):
    def setUp(self):
        self.payer = Keypair.from_seed(bytes(range(32)))
        self.job = Keypair.from_seed(bytes(range(32, 64)))
        self.run = Keypair.from_seed(bytes(range(64, 96)))

    def test_confidential_stub_cid_is_the_known_sha256_digest(self):
        self.assertEqual(
            decode_confidential_stub_cid(CONFIDENTIAL_STUB_CID).hex(),
            "924301b36fefe50cd83c93a0686d2e25ce05da34b50cd79d04328ef3d0ec8cf6",
        )

    def test_list_instruction_matches_official_account_contract(self):
        instruction = build_list_instruction(
            payer=self.payer.pubkey(),
            job=self.job.pubkey(),
            run=self.run.pubkey(),
            market=Pubkey.from_string(MARKET),
            timeout_sec=600,
            cid=CONFIDENTIAL_STUB_CID,
        )
        self.assertEqual(str(instruction.program_id), JOBS_PROGRAM)
        self.assertEqual(
            instruction.data,
            hashlib.sha256(b"global:list").digest()[:8]
            + decode_confidential_stub_cid(CONFIDENTIAL_STUB_CID)
            + struct.pack("<q", 600),
        )
        self.assertEqual(
            [
                (str(meta.pubkey), meta.is_signer, meta.is_writable)
                for meta in instruction.accounts
            ],
            [
                ("3ogUn1GNXoASaRbxPNeVJnVv5rG4EPBtmQmX61jVorUe", True, True),
                (MARKET, False, True),
                ("3WTypo2uYrwMHJ5yFFwUPX6T25n39PwNwke7pz22P4Ut", True, True),
                ("CiuGyhh6szsputL7MahWqvfRteFdL8WFhv64dgYmCrBu", False, True),
                ("EYZESGGY1rn2mEqMkzokKP4fxHcFePqhgwxp3ruacU5V", False, True),
                ("FAe4sisG95oZ42w7buUn5qEE4TAnfTTFPiguZUHmhiF", True, True),
                ("6tjbAfNHnUusWLZqFznMKyBrjs1ZX92eyKwiUi2Bsg3x", False, True),
                ("37xZ4jY3bSMBgxwekwdALRZK1kAUCh7YkkPabA4P2tq8", False, True),
                ("FAe4sisG95oZ42w7buUn5qEE4TAnfTTFPiguZUHmhiF", True, False),
                ("nosRB8DUV67oLNrL45bo2pFLrmsWPiewe2Lk2DRNYCp", False, False),
                ("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA", False, False),
                ("11111111111111111111111111111111", False, False),
            ],
        )

    def test_authorization_matches_official_tweetnacl_vector(self):
        self.assertEqual(
            build_authorization(
                CONFIDENTIAL_STUB_CID,
                bytes(self.payer),
                now_ms=1785144000123,
            ),
            "QmYBbVdWFgfoTEdPT7mnaXJz6zQzfKb1Pts4A5B9kDMBph:"
            "cWRPrV6oeYwMNkkXX4AafPQ3z5B1neGPnaKqVaTDH8o6KoaCQVAHSG7zWHfbZz5ueS2YC16dMtr2V7feWYoBCNr:"
            "1785144000123",
        )

    def test_matches_live_official_sdk_instruction_only_capture(self):
        """Captured from @nosana/sdk Jobs.list(..., instructionOnly=true)."""
        instruction = build_list_instruction(
            payer=self.payer.pubkey(),
            job=Pubkey.from_string("DjEAwhtbJ3xNmahLtyNGnuX5ZcL9jpkGEnU1JTTCvzYV"),
            run=Pubkey.from_string("739ng1zBYzr8ZxopuvtGMU3QFzoYZbDgkruphhXgm4D5"),
            market=Pubkey.from_string(MARKET),
            timeout_sec=600,
        )
        self.assertEqual(
            instruction.data.hex(),
            "36aec14311298426924301b36fefe50cd83c93a0686d2e25ce05da34b50cd79"
            "d04328ef3d0ec8cf65802000000000000",
        )
        self.assertEqual(
            [str(meta.pubkey) for meta in instruction.accounts],
            [
                "DjEAwhtbJ3xNmahLtyNGnuX5ZcL9jpkGEnU1JTTCvzYV",
                MARKET,
                "739ng1zBYzr8ZxopuvtGMU3QFzoYZbDgkruphhXgm4D5",
                "CiuGyhh6szsputL7MahWqvfRteFdL8WFhv64dgYmCrBu",
                "EYZESGGY1rn2mEqMkzokKP4fxHcFePqhgwxp3ruacU5V",
                "FAe4sisG95oZ42w7buUn5qEE4TAnfTTFPiguZUHmhiF",
                "6tjbAfNHnUusWLZqFznMKyBrjs1ZX92eyKwiUi2Bsg3x",
                "37xZ4jY3bSMBgxwekwdALRZK1kAUCh7YkkPabA4P2tq8",
                "FAe4sisG95oZ42w7buUn5qEE4TAnfTTFPiguZUHmhiF",
                "nosRB8DUV67oLNrL45bo2pFLrmsWPiewe2Lk2DRNYCp",
                "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",
                "11111111111111111111111111111111",
            ],
        )

    def test_invalid_cid_and_timeout_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "CID"):
            decode_confidential_stub_cid("not-a-cid")
        with self.assertRaisesRegex(ValueError, "timeout"):
            build_list_instruction(
                payer=self.payer.pubkey(),
                job=self.job.pubkey(),
                run=self.run.pubkey(),
                market=Pubkey.from_string(MARKET),
                timeout_sec=0,
                cid=CONFIDENTIAL_STUB_CID,
            )


class BootstrapBehaviorTests(unittest.TestCase):
    @staticmethod
    def _stub():
        return {
            "version": "0.1",
            "type": "container",
            "meta": {"trigger": "cli"},
            "logistics": {
                "send": {"type": "api-listen", "args": {}},
                "receive": {"type": "api-listen", "args": {}},
            },
            "ops": [],
        }

    @staticmethod
    def _bundle():
        payer = Keypair.from_seed(bytes(range(32)))
        return {
            "solanaSecret": str(payer),
            "market": MARKET,
            "timeoutSec": 600,
            "definition": {
                "version": "0.1",
                "type": "container",
                "ops": [{"type": "container/run", "id": "run", "args": {"image": "image"}}],
            },
        }

    def test_active_job_recovery_is_deterministic_and_requires_same_payer_market(self):
        jobs = [
            {"address": "old", "payer": "payer", "market": MARKET, "state": 1, "timeStart": 10},
            {"address": "other-payer", "payer": "other", "market": MARKET, "state": 1, "timeStart": 99},
            {"address": "done", "payer": "payer", "market": MARKET, "state": 2, "timeStart": 100},
            {"address": "new", "payer": "payer", "market": MARKET, "state": 0, "timeStart": 20},
        ]
        self.assertEqual(select_active_job(jobs, payer="payer", market=MARKET)["address"], "new")
        self.assertIsNone(select_active_job(jobs, payer="payer", market="another-market"))

    def test_fixed_market_escrow_and_move_out_floor_gate(self):
        allowed = evaluate_post_gate(
            job_price_microunits_per_sec=45,
            market_job_timeout_sec=7200,
            nos_balance=0.70,
            sol_balance=0.006,
        )
        self.assertTrue(allowed["allowed"])
        self.assertAlmostEqual(allowed["escrowNos"], 0.324)
        refused = evaluate_post_gate(
            job_price_microunits_per_sec=45,
            market_job_timeout_sec=7200,
            nos_balance=0.50,
            sol_balance=0.006,
        )
        self.assertFalse(refused["allowed"])
        self.assertIn("move-out reserve", refused["reason"])

    def test_gate_fails_closed_without_balance_or_fee_floor(self):
        self.assertFalse(
            evaluate_post_gate(
                job_price_microunits_per_sec=45,
                market_job_timeout_sec=7200,
                nos_balance=None,
                sol_balance=0.006,
            )["allowed"]
        )
        self.assertFalse(
            evaluate_post_gate(
                job_price_microunits_per_sec=45,
                market_job_timeout_sec=7200,
                nos_balance=1,
                sol_balance=0.0049,
            )["allowed"]
        )

    def test_ephemeral_key_stays_in_sandbox_and_decrypts_only_ciphertext(self):
        with tempfile.TemporaryDirectory() as tmp:
            key_path = Path(tmp) / "bootstrap.key"
            public_b64 = prepare_ephemeral_key(key_path)
            self.assertEqual(key_path.stat().st_mode & 0o777, 0o600)
            plaintext = json.dumps(
                {"solanaSecret": "secret-sol", "baseKey": "secret-base"}
            ).encode()
            ciphertext = SealedBox(PublicKey(__import__("base64").b64decode(public_b64))).encrypt(
                plaintext
            )
            self.assertEqual(decrypt_bootstrap_bundle(ciphertext, key_path), json.loads(plaintext))
            self.assertNotIn(b"secret-sol", ciphertext)

    def test_delivery_retries_finitely_and_returns_only_safe_receipt(self):
        calls = []
        responses = iter(
            [
                {"status": 503, "ok": False},
                {"status": 200, "ok": True},
            ]
        )

        def request(**kwargs):
            calls.append(kwargs)
            return next(responses)

        receipt = deliver_definition_until_running(
            job={"address": "job", "node": "node"},
            definition={"ops": [{"args": {"env": {"SECRET": "never-return"}}}]},
            cid=CONFIDENTIAL_STUB_CID,
            secret_bytes=bytes(Keypair.from_seed(bytes(range(32)))),
            request_impl=request,
            sleep=lambda _: None,
            attempts=3,
            now_ms=lambda: 1785144000123,
        )
        self.assertEqual(receipt, {"delivered": True, "attempts": 2, "httpStatus": 200})
        self.assertEqual(len(calls), 2)
        self.assertIn("Authorization", calls[0]["headers"])
        self.assertNotIn("never-return", json.dumps(receipt))

    def test_delivery_failure_is_bounded(self):
        with self.assertRaisesRegex(RuntimeError, "after 2 attempts"):
            deliver_definition_until_running(
                job={"address": "job", "node": "node"},
                definition={"ops": []},
                cid=CONFIDENTIAL_STUB_CID,
                secret_bytes=bytes(Keypair.from_seed(bytes(range(32)))),
                request_impl=lambda **_: {"status": 503, "ok": False},
                sleep=lambda _: None,
                attempts=2,
                now_ms=lambda: 1785144000123,
            )

    def test_submit_list_sends_once_and_requires_finalized_confirmation(self):
        calls = []
        blockhash = "EkSnNWid2cvwEVnVx9aBqawnmiCNiDgp3gUdkDPTKN1N"

        def rpc(method, params):
            calls.append((method, params))
            if method == "getLatestBlockhash":
                return {"value": {"blockhash": blockhash}}
            if method == "sendTransaction":
                return "tx-signature"
            if method == "getSignatureStatuses":
                return {"value": [{"confirmationStatus": "finalized", "err": None}]}
            raise AssertionError(method)

        payer = Keypair.from_seed(bytes(range(32)))
        receipt = submit_list_job(
            payer=payer,
            market=Pubkey.from_string(MARKET),
            timeout_sec=600,
            rpc_impl=rpc,
            job=Keypair.from_seed(bytes(range(32, 64))),
            run=Keypair.from_seed(bytes(range(64, 96))),
        )
        self.assertEqual(receipt["signature"], "tx-signature")
        self.assertEqual(receipt["status"], "finalized")
        self.assertEqual([method for method, _ in calls].count("sendTransaction"), 1)

    def test_submit_unknown_confirmation_never_resubmits(self):
        calls = []

        def rpc(method, params):
            calls.append(method)
            if method == "getLatestBlockhash":
                return {"value": {"blockhash": "EkSnNWid2cvwEVnVx9aBqawnmiCNiDgp3gUdkDPTKN1N"}}
            if method == "sendTransaction":
                return "tx-signature"
            if method == "getSignatureStatuses":
                return {"value": [None]}
            raise AssertionError(method)

        with self.assertRaisesRegex(RuntimeError, "unknown"):
            submit_list_job(
                payer=Keypair.from_seed(bytes(range(32))),
                market=Pubkey.from_string(MARKET),
                timeout_sec=600,
                rpc_impl=rpc,
                confirmation_attempts=2,
                sleep=lambda _: None,
            )
        self.assertEqual(calls.count("sendTransaction"), 1)

    def test_market_account_prefix_matches_live_official_sdk_values(self):
        raw = bytearray(64)
        raw[:8] = bytes.fromhex("c94ebbe1f0c6c9fb")
        struct.pack_into("<q", raw, 40, 86400)
        struct.pack_into("<Q", raw, 48, 48)
        struct.pack_into("<q", raw, 56, 7200)
        self.assertEqual(
            parse_market_account(bytes(raw)),
            {
                "jobExpirationSec": 86400,
                "jobPriceMicrounitsPerSec": 48,
                "jobTimeoutSec": 7200,
            },
        )

    def test_bootstrap_recovers_running_job_without_send_transaction(self):
        payer = str(Keypair.from_seed(bytes(range(32))).pubkey())
        active = {
            "address": "job-active",
            "payer": payer,
            "market": MARKET,
            "state": 1,
            "timeStart": 100,
            "node": "node",
        }

        def get_json(url):
            if "/ipfs/" in url:
                return self._stub()
            if "?payer=" in url:
                return {"jobs": [active]}
            if url.endswith("/job-active"):
                return active
            raise AssertionError(url)

        receipt = bootstrap_once(
            bundle=self._bundle(),
            sandbox_id="sb-recovery",
            rpc_impl=lambda method, params: (_ for _ in ()).throw(AssertionError(method)),
            get_json=get_json,
            request_impl=lambda **_: (_ for _ in ()).throw(
                AssertionError("a RUNNING job already has its confidential definition")
            ),
            sleep=lambda _: None,
        )
        self.assertEqual(receipt["action"], "recovered")
        self.assertIsNone(receipt["listSignature"])
        self.assertEqual(receipt["jobAddress"], "job-active")
        self.assertEqual(
            receipt["delivery"],
            {
                "delivered": False,
                "attempts": 0,
                "httpStatus": None,
                "alreadyRunning": True,
            },
        )

    def test_bootstrap_empty_state_lists_exactly_once(self):
        payer = str(Keypair.from_seed(bytes(range(32))).pubkey())
        raw = bytearray(64)
        raw[:8] = bytes.fromhex("c94ebbe1f0c6c9fb")
        struct.pack_into("<q", raw, 40, 86400)
        struct.pack_into("<Q", raw, 48, 48)
        struct.pack_into("<q", raw, 56, 7200)
        calls = []

        def rpc(method, params):
            calls.append(method)
            if method == "getSignaturesForAddress":
                return []
            if method == "getAccountInfo":
                return {"value": {"data": [__import__("base64").b64encode(raw).decode(), "base64"]}}
            if method == "getBalance":
                return {"value": 6_000_000}
            if method == "getTokenAccountsByOwner":
                return {
                    "value": [
                        {
                            "account": {
                                "data": {
                                    "parsed": {
                                        "info": {"tokenAmount": {"uiAmount": 1.0}}
                                    }
                                }
                            }
                        }
                    ]
                }
            if method == "getLatestBlockhash":
                return {"value": {"blockhash": "EkSnNWid2cvwEVnVx9aBqawnmiCNiDgp3gUdkDPTKN1N"}}
            if method == "sendTransaction":
                return "one-list-signature"
            if method == "getSignatureStatuses":
                return {"value": [{"confirmationStatus": "finalized", "err": None}]}
            raise AssertionError(method)

        def get_json(url):
            if "/ipfs/" in url:
                return self._stub()
            if "?payer=" in url:
                return {"jobs": []}
            if "/api/jobs/" in url:
                address = url.rsplit("/", 1)[-1]
                return {
                    "address": address,
                    "payer": payer,
                    "market": MARKET,
                    "state": 1,
                    "node": "node",
                }
            raise AssertionError(url)

        receipt = bootstrap_once(
            bundle=self._bundle(),
            sandbox_id="sb-list",
            rpc_impl=rpc,
            get_json=get_json,
            request_impl=lambda **_: {"ok": True, "status": 200},
            sleep=lambda _: None,
        )
        self.assertEqual(receipt["action"], "listed")
        self.assertEqual(receipt["listSignature"], "one-list-signature")
        self.assertEqual(calls.count("sendTransaction"), 1)


if __name__ == "__main__":
    unittest.main()
