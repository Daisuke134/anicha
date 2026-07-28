"""Contract tests for the long-lived Nosana Python runtime."""

from pathlib import Path
import unittest

from solders.keypair import Keypair
from solders.pubkey import Pubkey

from nosana_runtime import (
    build_successor_definition,
    fetch_nosana_runtime_cost_usd,
    replace_shelter_once,
    run_replacement_if_due,
    should_attempt_replacement,
)


MARKET = "7AtiXMSH6R1jjBxrcYjehCkkSF7zvYWte63gwEDBcGHq"


class NosanaRuntimeCost(unittest.TestCase):
    def test_uses_live_job_rate_and_current_timeout(self):
        class Response:
            def raise_for_status(self):
                return None

            def json(self):
                return {"timeout": 2400, "usdRewardPerHour": 0.04335}

        cost = fetch_nosana_runtime_cost_usd(
            "BsjuTkzKbryb5r95kpeVUpbaXMXLs4AKzPCMPNNyybpX",
            requests_get=lambda *_args, **_kwargs: Response(),
        )

        self.assertAlmostEqual(cost, 0.0289)

    def test_rejects_negative_or_boolean_job_values(self):
        for payload in (
            {"timeout": -1, "usdRewardPerHour": 0.04335},
            {"timeout": 2400, "usdRewardPerHour": -1},
            {"timeout": True, "usdRewardPerHour": 0.04335},
        ):
            class Response:
                def raise_for_status(self):
                    return None

                def json(self):
                    return payload

            with self.subTest(payload=payload), self.assertRaises(ValueError):
                fetch_nosana_runtime_cost_usd(
                    "BsjuTkzKbryb5r95kpeVUpbaXMXLs4AKzPCMPNNyybpX",
                    requests_get=lambda *_args, **_kwargs: Response(),
                )


class NosanaReplacementPolicy(unittest.TestCase):
    def test_only_attempts_near_the_hard_ceiling_while_current_job_is_running(self):
        job = {"state": 1, "timeStart": 1_000, "timeout": 21_600}
        self.assertFalse(
            should_attempt_replacement(job, now_sec=20_000, ceiling_sec=21_600, margin_sec=1_500)
        )
        self.assertTrue(
            should_attempt_replacement(job, now_sec=21_200, ceiling_sec=21_600, margin_sec=1_500)
        )
        self.assertFalse(
            should_attempt_replacement(
                {**job, "state": 2},
                now_sec=21_200,
                ceiling_sec=21_600,
                margin_sec=1_500,
            )
        )

    def test_definition_rebuilds_a_successor_without_putting_secret_in_command(self):
        secret = str(Keypair.from_seed(bytes(range(32))))
        definition = build_successor_definition(
            solana_session_b58=secret,
            base_public_address="0xd072CDDda8371D97834859E9c840F9B0F1e51a1d",
            market=MARKET,
            source_root=Path(__file__).parent,
        )
        args = definition["ops"][0]["args"]
        self.assertEqual(args["env"]["SOLANA_SESSION"], secret)
        self.assertEqual(args["env"]["NOSANA_JOB_ADDRESS"], "__NOSANA_JOB_ADDRESS__")
        self.assertEqual(args["env"]["SHELTER_LEASE_CEILING_SEC"], "21600")
        self.assertEqual(args["env"]["REPLACEMENT_MARGIN_SEC"], "1500")
        self.assertNotIn(secret, args["cmd"])
        self.assertIn("nosana_runtime.py", args["cmd"])
        # The official schema accepts an unbounded string; keep a local regression ceiling so
        # recursive source packaging cannot grow unnoticed.
        self.assertLess(len(args["cmd"].encode("utf-8")), 30_000)

    def test_reuses_an_existing_successor_without_listing_or_redelivering(self):
        payer_keypair = Keypair.from_seed(bytes(range(32)))
        payer = str(payer_keypair.pubkey())
        jobs = [
            {"address": "current", "payer": payer, "market": MARKET, "state": 1, "timeStart": 10},
            {
                "address": "successor",
                "payer": payer,
                "market": MARKET,
                "state": 1,
                "timeStart": 20,
                "node": "node",
            },
        ]
        receipt = replace_shelter_once(
            current_job_address="current",
            payer_keypair=payer_keypair,
            market=Pubkey.from_string(MARKET),
            definition={"ops": [{"args": {"env": {}}}]},
            timeout_sec=600,
            rpc_impl=lambda *_: (_ for _ in ()).throw(AssertionError("no rpc write")),
            get_json=lambda _url: {"jobs": jobs},
            wait_impl=lambda **_: jobs[1],
            list_impl=lambda **_: (_ for _ in ()).throw(AssertionError("no list")),
            delivery_impl=lambda **_: (_ for _ in ()).throw(AssertionError("no delivery")),
            verify_impl=lambda **_: {
                "serviceUrl": "https://service.example",
                "httpStatus": {"/": 200, "/statement.json": 200, "/heartbeats": 200},
                "heartbeatVerified": True,
                "heartbeatCycle": 2,
            },
        )
        self.assertEqual(receipt["action"], "recovered")
        self.assertEqual(receipt["jobAddress"], "successor")
        self.assertIsNone(receipt["listSignature"])

    def test_lists_once_after_floor_gate_then_delivers_and_verifies(self):
        payer_keypair = Keypair.from_seed(bytes(range(32)))
        payer = str(payer_keypair.pubkey())
        calls = []

        def get_json(_url):
            return {
                "jobs": [
                    {
                        "address": "current",
                        "payer": payer,
                        "market": MARKET,
                        "state": 1,
                        "timeStart": 10,
                    }
                ]
            }

        receipt = replace_shelter_once(
            current_job_address="current",
            payer_keypair=payer_keypair,
            market=Pubkey.from_string(MARKET),
            definition={"ops": [{"args": {"env": {"NOSANA_JOB_ADDRESS": "__NOSANA_JOB_ADDRESS__"}}}]},
            timeout_sec=600,
            rpc_impl=lambda *_: None,
            get_json=get_json,
            market_terms_impl=lambda *_: {
                "jobPriceMicrounitsPerSec": 48,
                "jobTimeoutSec": 7_200,
            },
            balances_impl=lambda *_: {"nos": 0.75, "sol": 0.025},
            list_impl=lambda **_: {
                "jobAddress": "successor",
                "signature": "list-tx",
                "status": "finalized",
            },
            wait_impl=lambda **_: {
                "address": "successor",
                "payer": payer,
                "market": MARKET,
                "state": 1,
                "node": "node",
            },
            delivery_impl=lambda **kwargs: calls.append(kwargs["definition"]) or {
                "delivered": True,
                "attempts": 1,
                "httpStatus": 200,
            },
            verify_impl=lambda **_: {
                "serviceUrl": "https://service.example",
                "httpStatus": {"/": 200, "/statement.json": 200, "/heartbeats": 200},
                "heartbeatVerified": True,
                "heartbeatCycle": 2,
            },
        )
        self.assertEqual(receipt["action"], "listed")
        self.assertEqual(receipt["listSignature"], "list-tx")
        self.assertEqual(len(calls), 1)
        self.assertEqual(
            calls[0]["ops"][0]["args"]["env"]["NOSANA_JOB_ADDRESS"],
            "successor",
        )

    def test_replacement_can_spend_the_move_out_reserve_on_the_requested_lease(self):
        payer_keypair = Keypair.from_seed(bytes(range(32)))
        payer = str(payer_keypair.pubkey())
        receipt = replace_shelter_once(
            current_job_address="current",
            payer_keypair=payer_keypair,
            market=Pubkey.from_string(MARKET),
            definition={"ops": [{"args": {"env": {}}}]},
            timeout_sec=600,
            rpc_impl=lambda *_: None,
            get_json=lambda _url: {
                "jobs": [
                    {
                        "address": "current",
                        "payer": payer,
                        "market": MARKET,
                        "state": 1,
                        "timeStart": 10,
                    }
                ]
            },
            market_terms_impl=lambda *_: {
                "jobPriceMicrounitsPerSec": 48,
                "jobTimeoutSec": 7_200,
            },
            balances_impl=lambda *_: {"nos": 0.34, "sol": 0.01},
            list_impl=lambda **_: {
                "jobAddress": "successor",
                "signature": "list-from-reserve",
                "status": "finalized",
            },
            wait_impl=lambda **_: {
                "address": "successor",
                "payer": payer,
                "market": MARKET,
                "state": 1,
                "node": "node",
            },
            delivery_impl=lambda **_: {
                "delivered": True,
                "attempts": 1,
                "httpStatus": 200,
            },
            verify_impl=lambda **_: {
                "serviceUrl": "https://service.example",
                "httpStatus": {"/": 200, "/statement.json": 200, "/heartbeats": 200},
                "heartbeatVerified": True,
                "heartbeatCycle": 2,
            },
        )
        self.assertEqual(receipt["listSignature"], "list-from-reserve")

    def test_due_cycle_builds_definition_and_calls_the_real_replacement_boundary_once(self):
        payer_keypair = Keypair.from_seed(bytes(range(32)))
        calls = []
        receipt = run_replacement_if_due(
            job={"state": 1, "timeStart": 1_000, "timeout": 21_600},
            now_sec=21_200,
            current_job_address="current",
            payer_keypair=payer_keypair,
            market=Pubkey.from_string(MARKET),
            base_public_address="0xd072CDDda8371D97834859E9c840F9B0F1e51a1d",
            rpc_impl=lambda *_: None,
            source_root=Path(__file__).parent,
            replace_impl=lambda **kwargs: calls.append(kwargs) or {"ok": True},
        )
        self.assertEqual(receipt, {"ok": True})
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["current_job_address"], "current")
        self.assertEqual(
            calls[0]["definition"]["ops"][0]["args"]["env"]["NOSANA_JOB_ADDRESS"],
            "__NOSANA_JOB_ADDRESS__",
        )

    def test_not_due_cycle_does_not_construct_or_submit_a_successor(self):
        self.assertIsNone(
            run_replacement_if_due(
                job={"state": 1, "timeStart": 1_000, "timeout": 21_600},
                now_sec=10_000,
                current_job_address="current",
                payer_keypair=Keypair.from_seed(bytes(range(32))),
                market=Pubkey.from_string(MARKET),
                base_public_address="0xd072CDDda8371D97834859E9c840F9B0F1e51a1d",
                rpc_impl=lambda *_: None,
                replace_impl=lambda **_: (_ for _ in ()).throw(AssertionError("not due")),
            )
        )
