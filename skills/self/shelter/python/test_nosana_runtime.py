"""Contract tests for the long-lived Nosana Python runtime."""

import unittest

from nosana_runtime import fetch_nosana_runtime_cost_usd


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
