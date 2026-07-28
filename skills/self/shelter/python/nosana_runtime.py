"""Long-lived Python heartbeat and financial-statement service for a Nosana container."""

import base58
import base64
import gzip
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
    CONFIDENTIAL_STUB_CID,
    DEFAULT_JOBS_API,
    DEFAULT_NOS_MOVE_OUT_RESERVE,
    DEFAULT_SOL_FEE_FLOOR,
    bind_job_address,
    deliver_definition_until_running,
    evaluate_post_gate,
    fetch_market_terms,
    fetch_payer_balances,
    make_rpc,
    select_successor_job,
    submit_list_job,
    submit_extend_job,
    verify_successor_service,
    wait_for_claimed_job,
)
from statement import (
    DEFAULT_POLYMARKET_ADDRESS,
    _verify_heartbeat_row,
    build_public_statement,
    serve_statement,
)

RUNTIME_SOURCE_FILES = (
    "heartbeat.py",
    "statement.py",
    "nosana_bootstrap.py",
    "nosana_runtime.py",
)
JOB_ADDRESS_PLACEHOLDER = "__NOSANA_JOB_ADDRESS__"
DEFAULT_LEASE_CEILING_SEC = 21_600
DEFAULT_REPLACEMENT_MARGIN_SEC = 1_500
DEFAULT_SUCCESSOR_TIMEOUT_SEC = 600


def should_attempt_replacement(
    job,
    *,
    now_sec,
    ceiling_sec=DEFAULT_LEASE_CEILING_SEC,
    margin_sec=DEFAULT_REPLACEMENT_MARGIN_SEC,
):
    """Replace only a running job that reached its hard lease ceiling."""

    try:
        timeout_sec = int(job["timeout"])
        lease_end = int(job["timeStart"]) + timeout_sec
        state = int(job["state"])
        remaining = lease_end - int(now_sec)
    except (KeyError, TypeError, ValueError):
        return False
    return (
        state == 1
        and timeout_sec >= int(ceiling_sec)
        and 0 < remaining <= int(margin_sec)
    )


def build_successor_definition(
    *,
    solana_session_b58,
    base_public_address,
    market,
    source_root=None,
    ceiling_sec=DEFAULT_LEASE_CEILING_SEC,
    replacement_margin_sec=DEFAULT_REPLACEMENT_MARGIN_SEC,
    successor_timeout_sec=DEFAULT_SUCCESSOR_TIMEOUT_SEC,
):
    """Rebuild the confidential Python service without recursively embedding a definition."""

    if not isinstance(solana_session_b58, str) or len(solana_session_b58) < 32:
        raise ValueError("Solana session is required")
    if (
        not isinstance(base_public_address, str)
        or not base_public_address.startswith("0x")
        or len(base_public_address) != 42
    ):
        raise ValueError("Base public address is required")
    root = Path(source_root or Path(__file__).parent)
    sources = {
        name: (root / name).read_text(encoding="utf-8")
        for name in RUNTIME_SOURCE_FILES
    }
    encoded = base64.b64encode(
        gzip.compress(
            json.dumps(sources, separators=(",", ":")).encode("utf-8"),
            compresslevel=9,
        )
    ).decode("ascii")
    reconstruct = (
        "import base64,gzip,json,pathlib;"
        'r=pathlib.Path("/tmp/f");'
        "r.mkdir(parents=True,exist_ok=True);"
        f'd=json.loads(gzip.decompress(base64.b64decode("{encoded}")));'
        '[(r/n).write_text(s,encoding="utf-8") for n,s in d.items()]'
    )
    command = "; ".join(
        (
            "set -e",
            f"python -c '{reconstruct}'",
            "python -m pip install -q "
            "PyNaCl==1.6.2 base58==2.1.1 solders==0.27.1 requests==2.34.2",
            "exec python /tmp/f/nosana_runtime.py",
        )
    )
    return {
        "version": "0.1",
        "type": "container",
        "ops": [
            {
                "type": "container/run",
                "id": "franklin-python",
                "args": {
                    "image": "docker.io/library/python:3.11",
                    "expose": 8080,
                    "gpu": True,
                    "cmd": command,
                    "env": {
                        "SOLANA_SESSION": solana_session_b58,
                        "NOSANA_JOB_ADDRESS": JOB_ADDRESS_PLACEHOLDER,
                        "NOSANA_MARKET": str(market),
                        "RENEW_MARGIN_SEC": "1700",
                        "SHELTER_LEASE_CEILING_SEC": str(int(ceiling_sec)),
                        "REPLACEMENT_MARGIN_SEC": str(int(replacement_margin_sec)),
                        "SUCCESSOR_TIMEOUT_SEC": str(int(successor_timeout_sec)),
                        "BASE_PUBLIC_ADDRESS": base_public_address,
                    },
                },
            }
        ],
    }


def _get_json(url):
    response = requests.get(url, timeout=20)
    response.raise_for_status()
    return response.json()


def replace_shelter_once(
    *,
    current_job_address,
    payer_keypair,
    market,
    definition,
    timeout_sec,
    rpc_impl,
    get_json=_get_json,
    market_terms_impl=fetch_market_terms,
    balances_impl=fetch_payer_balances,
    list_impl=submit_list_job,
    wait_impl=wait_for_claimed_job,
    delivery_impl=deliver_definition_until_running,
    verify_impl=verify_successor_service,
    request_impl=None,
    service_get_impl=None,
    sleep=time.sleep,
    verify_attempts=20,
    verify_interval_seconds=15,
):
    """List or recover one successor, then prove it before declaring handover."""

    payer = str(payer_keypair.pubkey())
    payload = get_json(f"{DEFAULT_JOBS_API}?payer={payer}")
    if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
        raise RuntimeError("payer jobs response is unavailable; refusing replacement")
    successor = select_successor_job(
        payload["jobs"],
        current_address=current_job_address,
        payer=payer,
        market=str(market),
    )
    list_receipt = None
    action = "recovered"
    if successor is None:
        terms = market_terms_impl(rpc_impl, market)
        balances = balances_impl(rpc_impl, payer_keypair.pubkey())
        gate = evaluate_post_gate(
            job_price_microunits_per_sec=terms["jobPriceMicrounitsPerSec"],
            # The on-chain list instruction escrows price * the requested timeout. This is the
            # move for which DEFAULT_NOS_MOVE_OUT_RESERVE was saved, so replacement may spend
            # that reserve instead of requiring a second reserve behind it.
            market_job_timeout_sec=int(timeout_sec),
            nos_balance=balances["nos"],
            sol_balance=balances["sol"],
            nos_reserve=0,
        )
        if not gate["allowed"]:
            raise RuntimeError(f"replacement gate refused: {gate['reason']}")
        list_receipt = list_impl(
            payer=payer_keypair,
            market=market,
            timeout_sec=int(timeout_sec),
            rpc_impl=rpc_impl,
            sleep=sleep,
        )
        successor = {"address": list_receipt["jobAddress"]}
        action = "listed"
    claimed = wait_impl(
        job_address=successor["address"],
        get_json=get_json,
        sleep=sleep,
    )
    if claimed.get("payer") != payer or claimed.get("market") != str(market):
        raise RuntimeError("successor claim is not bound to the expected payer and market")

    def verify():
        kwargs = {
            "job": claimed,
            "payer": payer,
            "cid": CONFIDENTIAL_STUB_CID,
            "secret_bytes": bytes(payer_keypair),
        }
        if service_get_impl is not None:
            kwargs["request_get"] = service_get_impl
        return verify_impl(**kwargs)

    verification = None
    if action == "recovered":
        try:
            verification = verify()
        except Exception:
            verification = None
    delivery = None
    if verification is None:
        delivery_kwargs = {
            "job": claimed,
            "definition": bind_job_address(definition, successor["address"]),
            "cid": CONFIDENTIAL_STUB_CID,
            "secret_bytes": bytes(payer_keypair),
            "sleep": sleep,
        }
        if request_impl is not None:
            delivery_kwargs["request_impl"] = request_impl
        delivery = delivery_impl(**delivery_kwargs)
        last_error = None
        for attempt in range(int(verify_attempts)):
            try:
                verification = verify()
                break
            except Exception as exc:
                last_error = exc
                if attempt + 1 < int(verify_attempts):
                    sleep(verify_interval_seconds)
        if verification is None:
            raise RuntimeError("successor never passed public service verification") from last_error
    return {
        "ok": True,
        "action": action,
        "oldJobAddress": current_job_address,
        "jobAddress": successor["address"],
        "listSignature": list_receipt["signature"] if list_receipt else None,
        "listStatus": list_receipt["status"] if list_receipt else None,
        "delivery": delivery,
        "verification": verification,
    }


def run_replacement_if_due(
    *,
    job,
    now_sec,
    current_job_address,
    payer_keypair,
    market,
    base_public_address,
    rpc_impl,
    source_root=None,
    ceiling_sec=DEFAULT_LEASE_CEILING_SEC,
    replacement_margin_sec=DEFAULT_REPLACEMENT_MARGIN_SEC,
    successor_timeout_sec=DEFAULT_SUCCESSOR_TIMEOUT_SEC,
    replace_impl=replace_shelter_once,
):
    """Cross the pure due-policy boundary before constructing or buying anything."""

    if not should_attempt_replacement(
        job,
        now_sec=now_sec,
        ceiling_sec=ceiling_sec,
        margin_sec=replacement_margin_sec,
    ):
        return None
    definition = build_successor_definition(
        solana_session_b58=str(payer_keypair),
        base_public_address=base_public_address,
        market=market,
        source_root=source_root,
        ceiling_sec=ceiling_sec,
        replacement_margin_sec=replacement_margin_sec,
        successor_timeout_sec=successor_timeout_sec,
    )
    return replace_impl(
        current_job_address=current_job_address,
        payer_keypair=payer_keypair,
        market=market,
        definition=definition,
        timeout_sec=successor_timeout_sec,
        rpc_impl=rpc_impl,
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
    replacements_file = Path("/tmp/replacements.jsonl")
    replacement_errors_file = Path("/tmp/replacement-errors.jsonl")

    def renewal_loop():
        payer_keypair = Keypair.from_base58_string(os.environ["SOLANA_SESSION"])
        market = Pubkey.from_string(os.environ["NOSANA_MARKET"])
        rpc = make_rpc()
        margin = int(os.environ.get("RENEW_MARGIN_SEC", "180"))
        ceiling = int(
            os.environ.get("SHELTER_LEASE_CEILING_SEC", str(DEFAULT_LEASE_CEILING_SEC))
        )
        replacement_margin = int(
            os.environ.get("REPLACEMENT_MARGIN_SEC", str(DEFAULT_REPLACEMENT_MARGIN_SEC))
        )
        successor_timeout = int(
            os.environ.get("SUCCESSOR_TIMEOUT_SEC", str(DEFAULT_SUCCESSOR_TIMEOUT_SEC))
        )
        add_seconds = 600
        replacement_completed = False
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
                if not replacement_completed:
                    try:
                        replacement = run_replacement_if_due(
                            job=job,
                            now_sec=int(time.time()),
                            current_job_address=job_address,
                            payer_keypair=payer_keypair,
                            market=market,
                            base_public_address=base_address,
                            rpc_impl=rpc,
                            ceiling_sec=ceiling,
                            replacement_margin_sec=replacement_margin,
                            successor_timeout_sec=successor_timeout,
                        )
                        if replacement is not None:
                            with replacements_file.open("a", encoding="utf-8") as output:
                                output.write(
                                    json.dumps(replacement, separators=(",", ":")) + "\n"
                                )
                            replacement_completed = True
                    except Exception as error:
                        with replacement_errors_file.open("a", encoding="utf-8") as output:
                            output.write(
                                json.dumps(
                                    {
                                        "jobAddress": job_address,
                                        "error": str(error)[:240],
                                        "ts": int(time.time()),
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
