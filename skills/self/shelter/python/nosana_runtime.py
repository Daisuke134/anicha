"""Long-lived Python heartbeat and financial-statement service for a Nosana container."""

import base58
import json
import os
from pathlib import Path
import threading
import time

from nacl.signing import SigningKey
import requests
from solders.keypair import Keypair
from solders.pubkey import Pubkey

from heartbeat import emit_heartbeats
from nosana_bootstrap import (
    DEFAULT_NOS_MOVE_OUT_RESERVE,
    DEFAULT_SOL_FEE_FLOOR,
    fetch_market_terms,
    fetch_payer_balances,
    make_rpc,
    submit_extend_job,
)
from statement import (
    DEFAULT_POLYMARKET_ADDRESS,
    _verify_heartbeat_row,
    build_public_statement,
    serve_statement,
)


def fetch_nosana_runtime_cost_usd(job_address, requests_get=requests.get):
    response = requests_get(
        f"https://dashboard.k8s.prd.nos.ci/api/jobs/{job_address}",
        timeout=15,
    )
    response.raise_for_status()
    job = response.json()
    timeout = job.get("timeout")
    hourly_rate = job.get("usdRewardPerHour")
    for name, value in (("timeout", timeout), ("usdRewardPerHour", hourly_rate)):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
            raise ValueError(f"{name} must be a non-negative number")
    return float(hourly_rate) * float(timeout) / 3600


def main():
    job_address = os.environ["NOSANA_JOB_ADDRESS"]
    base_address = os.environ["BASE_PUBLIC_ADDRESS"]
    secret = base58.b58decode(os.environ["SOLANA_SESSION"])
    signing_key = SigningKey(secret[:32])
    payer = base58.b58encode(signing_key.verify_key.encode()).decode("ascii")
    heartbeat_file = Path("/tmp/heartbeats.jsonl")
    statement_file = Path("/tmp/statement.json")
    renewals_file = Path("/tmp/renewals.jsonl")

    def renewal_loop():
        payer_keypair = Keypair.from_base58_string(os.environ["SOLANA_SESSION"])
        market = Pubkey.from_string(os.environ["NOSANA_MARKET"])
        rpc = make_rpc()
        margin = int(os.environ.get("RENEW_MARGIN_SEC", "180"))
        add_seconds = 600
        ceiling = 21_600
        while True:
            try:
                job = requests.get(
                    f"https://dashboard.k8s.prd.nos.ci/api/jobs/{job_address}",
                    timeout=15,
                ).json()
                current_timeout = int(job["timeout"])
                left = int(job["timeStart"]) + current_timeout - int(time.time())
                if current_timeout < ceiling and left < margin:
                    balances = fetch_payer_balances(rpc, payer_keypair.pubkey())
                    terms = fetch_market_terms(rpc, market)
                    extension_cost = (
                        terms["jobPriceMicrounitsPerSec"] * add_seconds / 1_000_000
                    )
                    if (
                        balances["sol"] >= DEFAULT_SOL_FEE_FLOOR
                        and balances["nos"] - extension_cost
                        >= DEFAULT_NOS_MOVE_OUT_RESERVE
                    ):
                        receipt = submit_extend_job(
                            payer=payer_keypair,
                            job=Pubkey.from_string(job_address),
                            market=market,
                            new_timeout_sec=current_timeout + add_seconds,
                            rpc_impl=rpc,
                        )
                        with renewals_file.open("a", encoding="utf-8") as output:
                            output.write(
                                json.dumps(
                                    {
                                        "jobAddress": job_address,
                                        "from": current_timeout,
                                        "to": current_timeout + add_seconds,
                                        "signature": receipt["signature"],
                                    },
                                    separators=(",", ":"),
                                )
                                + "\n"
                            )
            except Exception:
                pass
            time.sleep(45)

    def heartbeat_loop():
        with heartbeat_file.open("a", encoding="utf-8", buffering=1) as output:
            emit_heartbeats(
                job_address=job_address,
                cycles=10_000,
                interval_seconds=45,
                signing_key=signing_key,
                output=output,
            )

    threading.Thread(target=heartbeat_loop, daemon=True).start()
    threading.Thread(target=renewal_loop, daemon=True).start()
    rows = []
    for _ in range(120):
        if heartbeat_file.exists():
            rows = [
                json.loads(line)
                for line in heartbeat_file.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        if len(rows) >= 2:
            break
        time.sleep(1)
    if len(rows) < 2:
        raise RuntimeError("two naturally timed heartbeats were not produced")

    verified = [{**row, "verified": _verify_heartbeat_row(row)} for row in rows]
    statement = build_public_statement(
        sandbox_id="sb-nosana-python",
        base_address=base_address,
        solana_address=payer,
        polymarket_address=DEFAULT_POLYMARKET_ADDRESS,
        heartbeats=verified,
        runtime_cost_usd=fetch_nosana_runtime_cost_usd(job_address),
    )
    statement_file.write_text(
        json.dumps(statement, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    serve_statement(
        statement_file=statement_file,
        heartbeats_file=heartbeat_file,
        port=8080,
        runtime_cost_usd_provider=lambda: fetch_nosana_runtime_cost_usd(job_address),
    )


if __name__ == "__main__":
    main()
