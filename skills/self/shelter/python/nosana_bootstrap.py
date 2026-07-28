"""Minimal Python client for bootstrapping confidential Nosana jobs.

The instruction layout and account derivations mirror Nosana's public Rust
program and the official JavaScript SDK.  This module intentionally does not
use Nosana's embedded Pinata credential.
"""

from __future__ import annotations

import base64
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import struct
import time

import base58
from nacl.public import PrivateKey, SealedBox
from nacl.signing import SigningKey
import requests
from solders.hash import Hash
from solders.instruction import AccountMeta, Instruction
from solders.keypair import Keypair
from solders.message import Message
from solders.pubkey import Pubkey
from solders.transaction import Transaction


CONFIDENTIAL_STUB_CID = "QmYBbVdWFgfoTEdPT7mnaXJz6zQzfKb1Pts4A5B9kDMBph"
JOBS_PROGRAM = "nosJhNRqr2bc9g1nfGDcXXTXvYUmxD4cVwy2pMWhrYM"
NOS_MINT = "nosXBVoaCTtYdLvKY6Csb4AC8JCdQKKAaWYtx2ZMoo7"
REWARDS_PROGRAM = "nosRB8DUV67oLNrL45bo2pFLrmsWPiewe2Lk2DRNYCp"
TOKEN_PROGRAM = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
ASSOCIATED_TOKEN_PROGRAM = "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL"
SYSTEM_PROGRAM = "11111111111111111111111111111111"
DEFAULT_NOS_MOVE_OUT_RESERVE = 0.34
DEFAULT_SOL_FEE_FLOOR = 0.005
DEFAULT_NODE_DOMAIN = "node.k8s.prd.nos.ci"
DEFAULT_RPC_URL = "https://api.mainnet-beta.solana.com"
DEFAULT_JOBS_API = "https://dashboard.k8s.prd.nos.ci/api/jobs"
MARKET_DISCRIMINATOR = bytes.fromhex("c94ebbe1f0c6c9fb")


def decode_confidential_stub_cid(cid: str) -> bytes:
    """Return the 32-byte sha2-256 digest carried by a CIDv0."""

    try:
        decoded = base58.b58decode(cid)
    except Exception as exc:
        raise ValueError("CID must be valid base58") from exc
    if len(decoded) != 34 or decoded[:2] != b"\x12\x20":
        raise ValueError("CID must be a CIDv0 sha2-256 multihash")
    return decoded[2:]


def _pda(seeds: list[bytes], program: Pubkey) -> Pubkey:
    return Pubkey.find_program_address(seeds, program)[0]


def _associated_token_address(owner: Pubkey, mint: Pubkey) -> Pubkey:
    token_program = Pubkey.from_string(TOKEN_PROGRAM)
    ata_program = Pubkey.from_string(ASSOCIATED_TOKEN_PROGRAM)
    return _pda([bytes(owner), bytes(token_program), bytes(mint)], ata_program)


def build_list_instruction(
    *,
    payer: Pubkey,
    job: Pubkey,
    run: Pubkey,
    market: Pubkey,
    timeout_sec: int,
    cid: str = CONFIDENTIAL_STUB_CID,
) -> Instruction:
    """Build Nosana Jobs `list` exactly as the official SDK does."""

    if not isinstance(timeout_sec, int) or timeout_sec <= 0:
        raise ValueError("timeout must be a positive integer")

    jobs_program = Pubkey.from_string(JOBS_PROGRAM)
    mint = Pubkey.from_string(NOS_MINT)
    rewards_program = Pubkey.from_string(REWARDS_PROGRAM)
    user = _associated_token_address(payer, mint)
    vault = _pda([bytes(market), bytes(mint)], jobs_program)
    rewards_reflection = _pda([b"reflection"], rewards_program)
    rewards_vault = _pda([bytes(mint)], rewards_program)

    accounts = [
        AccountMeta(job, True, True),
        AccountMeta(market, False, True),
        AccountMeta(run, True, True),
        AccountMeta(user, False, True),
        AccountMeta(vault, False, True),
        AccountMeta(payer, True, True),
        AccountMeta(rewards_reflection, False, True),
        AccountMeta(rewards_vault, False, True),
        AccountMeta(payer, True, False),
        AccountMeta(rewards_program, False, False),
        AccountMeta(Pubkey.from_string(TOKEN_PROGRAM), False, False),
        AccountMeta(Pubkey.from_string(SYSTEM_PROGRAM), False, False),
    ]
    data = (
        hashlib.sha256(b"global:list").digest()[:8]
        + decode_confidential_stub_cid(cid)
        + struct.pack("<q", timeout_sec)
    )
    return Instruction(jobs_program, data, accounts)


def build_authorization(
    message: str,
    secret_bytes: bytes,
    *,
    now_ms: int,
) -> str:
    """Match @nosana/sdk AuthorizationManager.generate(includeTime=true)."""

    if not isinstance(message, str) or not message:
        raise ValueError("authorization message is required")
    if not isinstance(now_ms, int) or now_ms <= 0:
        raise ValueError("authorization timestamp must be positive")
    try:
        signing_key = SigningKey(bytes(secret_bytes)[:32])
    except Exception as exc:
        raise ValueError("secret must contain a valid Ed25519 seed") from exc
    signature = signing_key.sign(message.encode("utf-8")).signature
    return f"{message}:{base58.b58encode(signature).decode('ascii')}:{now_ms}"


def select_active_job(jobs: list[dict], *, payer: str, market: str) -> dict | None:
    """Use Nosana's public job state as the durable restart ledger."""

    eligible = [
        job
        for job in jobs
        if isinstance(job, dict)
        and job.get("payer") == payer
        and job.get("market") == market
        and int(job.get("state", -1)) in (0, 1)
        and isinstance(job.get("address"), str)
        and job["address"]
    ]
    if not eligible:
        return None
    return max(eligible, key=lambda job: (int(job.get("timeStart") or 0), job["address"]))


def evaluate_post_gate(
    *,
    job_price_microunits_per_sec: int,
    market_job_timeout_sec: int,
    nos_balance: float | None,
    sol_balance: float | None,
    nos_reserve: float = DEFAULT_NOS_MOVE_OUT_RESERVE,
    sol_fee_floor: float = DEFAULT_SOL_FEE_FLOOR,
) -> dict:
    numbers = (
        job_price_microunits_per_sec,
        market_job_timeout_sec,
        nos_balance,
        sol_balance,
        nos_reserve,
        sol_fee_floor,
    )
    if any(
        not isinstance(value, (int, float)) or not math.isfinite(value)
        for value in numbers
    ):
        return {"allowed": False, "reason": "refusing to post without finite price and balances"}
    if job_price_microunits_per_sec <= 0 or market_job_timeout_sec <= 0:
        return {"allowed": False, "reason": "market escrow bounds are invalid"}
    escrow = job_price_microunits_per_sec / 1_000_000 * market_job_timeout_sec
    if sol_balance < sol_fee_floor:
        return {
            "allowed": False,
            "reason": f"{sol_balance} SOL is under the {sol_fee_floor} fee floor",
            "escrowNos": escrow,
        }
    if nos_balance - escrow < nos_reserve:
        return {
            "allowed": False,
            "reason": (
                f"posting {escrow} NOS would cross the {nos_reserve} NOS move-out reserve"
            ),
            "escrowNos": escrow,
        }
    return {
        "allowed": True,
        "reason": "fixed market escrow and move-out reserve are funded",
        "escrowNos": escrow,
    }


def prepare_ephemeral_key(path: str | Path) -> str:
    """Create the sandbox-only sealed-box private key and return its public half."""

    key_path = Path(path)
    key_path.parent.mkdir(parents=True, exist_ok=True)
    private = PrivateKey.generate()
    descriptor = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(descriptor, bytes(private))
    finally:
        os.close(descriptor)
    os.chmod(key_path, 0o600)
    return base64.b64encode(bytes(private.public_key)).decode("ascii")


def decrypt_bootstrap_bundle(ciphertext: bytes, key_path: str | Path) -> dict:
    try:
        private = PrivateKey(Path(key_path).read_bytes())
        plaintext = SealedBox(private).decrypt(ciphertext)
        bundle = json.loads(plaintext)
    except Exception as exc:
        raise ValueError("encrypted bootstrap bundle is invalid") from exc
    if not isinstance(bundle, dict):
        raise ValueError("encrypted bootstrap bundle must contain an object")
    return bundle


def deliver_definition_until_running(
    *,
    job: dict,
    definition: dict,
    cid: str,
    secret_bytes: bytes,
    request_impl=None,
    sleep=time.sleep,
    attempts: int = 36,
    interval_seconds: float = 5,
    now_ms=lambda: int(time.time() * 1000),
    node_domain: str = DEFAULT_NODE_DOMAIN,
) -> dict:
    address = job.get("address") if isinstance(job, dict) else None
    node = job.get("node") if isinstance(job, dict) else None
    if not address or not node:
        raise ValueError("job address and claimed node are required for delivery")
    if not isinstance(attempts, int) or attempts < 1:
        raise ValueError("delivery attempts must be positive")
    requester = request_impl or _requests_post
    url = f"https://{node}.{node_domain}/job/{address}/job-definition"
    body = json.dumps(definition, separators=(",", ":"), ensure_ascii=False)
    last_status = None
    for attempt in range(1, attempts + 1):
        authorization = build_authorization(cid, secret_bytes, now_ms=now_ms())
        response = requester(
            url=url,
            headers={"Authorization": authorization, "Content-Type": "application/json"},
            body=body,
            timeout=15,
        )
        last_status = int(response.get("status", 0))
        if response.get("ok"):
            return {"delivered": True, "attempts": attempt, "httpStatus": last_status}
        if attempt < attempts:
            sleep(interval_seconds)
    raise RuntimeError(
        f"confidential definition delivery failed after {attempts} attempts "
        f"(last HTTP {last_status})"
    )


def _requests_post(*, url: str, headers: dict, body: str, timeout: float) -> dict:
    response = requests.post(url, headers=headers, data=body, timeout=timeout)
    return {"ok": response.ok, "status": response.status_code}


def submit_list_job(
    *,
    payer: Keypair,
    market: Pubkey,
    timeout_sec: int,
    rpc_impl,
    cid: str = CONFIDENTIAL_STUB_CID,
    job: Keypair | None = None,
    run: Keypair | None = None,
    confirmation_attempts: int = 20,
    sleep=time.sleep,
    confirmation_interval_seconds: float = 1,
) -> dict:
    """Sign and submit exactly once; a lost confirmation never causes a blind retry."""

    job = job or Keypair()
    run = run or Keypair()
    instruction = build_list_instruction(
        payer=payer.pubkey(),
        job=job.pubkey(),
        run=run.pubkey(),
        market=market,
        timeout_sec=timeout_sec,
        cid=cid,
    )
    latest = rpc_impl("getLatestBlockhash", [{"commitment": "finalized"}])
    try:
        blockhash = Hash.from_string(latest["value"]["blockhash"])
    except Exception as exc:
        raise RuntimeError("latest blockhash response is invalid") from exc
    message = Message.new_with_blockhash([instruction], payer.pubkey(), blockhash)
    transaction = Transaction([payer, job, run], message, blockhash)
    encoded = base64.b64encode(bytes(transaction)).decode("ascii")
    signature = rpc_impl(
        "sendTransaction",
        [encoded, {"encoding": "base64", "preflightCommitment": "confirmed"}],
    )
    if not isinstance(signature, str) or not signature:
        raise RuntimeError("list transaction submission returned no signature")
    for attempt in range(confirmation_attempts):
        status_result = rpc_impl(
            "getSignatureStatuses",
            [[signature], {"searchTransactionHistory": True}],
        )
        values = status_result.get("value") if isinstance(status_result, dict) else None
        status = values[0] if isinstance(values, list) and values else None
        if status and status.get("err") is not None:
            raise RuntimeError("list transaction failed on-chain")
        if status and status.get("confirmationStatus") == "finalized":
            return {
                "signature": signature,
                "status": "finalized",
                "jobAddress": str(job.pubkey()),
                "runAddress": str(run.pubkey()),
            }
        if attempt + 1 < confirmation_attempts:
            sleep(confirmation_interval_seconds)
    raise RuntimeError(
        f"list transaction confirmation unknown for {signature}; refusing to resubmit"
    )


def parse_market_account(data: bytes) -> dict:
    """Decode the fixed prefix of Nosana's public MarketAccount."""

    if not isinstance(data, bytes) or len(data) < 64:
        raise ValueError("market account data is too short")
    if data[:8] != MARKET_DISCRIMINATOR:
        raise ValueError("market account discriminator differs")
    return {
        "jobExpirationSec": struct.unpack_from("<q", data, 40)[0],
        "jobPriceMicrounitsPerSec": struct.unpack_from("<Q", data, 48)[0],
        "jobTimeoutSec": struct.unpack_from("<q", data, 56)[0],
    }


def make_rpc(rpc_url: str = DEFAULT_RPC_URL, *, post=requests.post):
    def call(method: str, params: list):
        response = post(
            rpc_url,
            headers={"Content-Type": "application/json"},
            data=json.dumps(
                {"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
                separators=(",", ":"),
            ),
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("error") is not None:
            raise RuntimeError(f"Solana RPC {method} failed")
        if "result" not in payload:
            raise RuntimeError(f"Solana RPC {method} returned no result")
        return payload["result"]

    return call


def fetch_market_terms(rpc_impl, market: Pubkey) -> dict:
    result = rpc_impl("getAccountInfo", [str(market), {"encoding": "base64"}])
    try:
        encoded = result["value"]["data"][0]
        return parse_market_account(base64.b64decode(encoded))
    except Exception as exc:
        raise RuntimeError("market account readback is invalid") from exc


def fetch_payer_balances(rpc_impl, payer: Pubkey) -> dict:
    balance = rpc_impl("getBalance", [str(payer), {"commitment": "confirmed"}])
    token = rpc_impl(
        "getTokenAccountsByOwner",
        [
            str(payer),
            {"mint": NOS_MINT},
            {"encoding": "jsonParsed", "commitment": "confirmed"},
        ],
    )
    try:
        sol = int(balance["value"]) / 1_000_000_000
        nos = sum(
            float(row["account"]["data"]["parsed"]["info"]["tokenAmount"]["uiAmount"] or 0)
            for row in token["value"]
        )
    except Exception as exc:
        raise RuntimeError("payer balance readback is invalid") from exc
    return {"sol": sol, "nos": nos}


def _default_get_json(url: str) -> dict:
    response = requests.get(url, timeout=20)
    response.raise_for_status()
    return response.json()


def discover_active_job(
    *,
    payer: str,
    market: str,
    rpc_impl,
    get_json=_default_get_json,
    jobs_api: str = DEFAULT_JOBS_API,
) -> dict | None:
    """Recover via indexer first, then recent payer transactions for queued-job gaps."""

    indexer_read_succeeded = False
    try:
        payload = get_json(f"{jobs_api}?payer={payer}")
        if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
            raise RuntimeError("payer jobs response has an invalid shape")
        indexer_read_succeeded = True
        direct = select_active_job(payload.get("jobs", []), payer=payer, market=market)
        if direct:
            return direct
    except Exception:
        pass

    try:
        signatures = rpc_impl("getSignaturesForAddress", [payer, {"limit": 10}])
    except Exception:
        signatures = []
    candidates = []
    for row in signatures or []:
        signature = row.get("signature") if isinstance(row, dict) else None
        if not signature:
            continue
        try:
            transaction = rpc_impl(
                "getTransaction",
                [signature, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}],
            )
            keys = transaction["transaction"]["message"]["accountKeys"]
        except Exception:
            continue
        for key in keys:
            address = key.get("pubkey") if isinstance(key, dict) else key
            if not isinstance(address, str) or address == payer:
                continue
            try:
                job = get_json(f"{jobs_api}/{address}")
            except Exception:
                continue
            if (
                job.get("payer") == payer
                and job.get("market") == market
                and int(job.get("state", -1)) in (0, 1)
            ):
                candidates.append(job)
    recovered = select_active_job(candidates, payer=payer, market=market)
    if recovered:
        return recovered
    if not indexer_read_succeeded:
        raise RuntimeError(
            "cannot prove that no active Nosana job exists while the payer index is unavailable; "
            "refusing to list"
        )
    return None


def wait_for_claimed_job(
    *,
    job_address: str,
    get_json=_default_get_json,
    jobs_api: str = DEFAULT_JOBS_API,
    attempts: int = 36,
    sleep=time.sleep,
    interval_seconds: float = 5,
) -> dict:
    last = None
    for attempt in range(attempts):
        try:
            last = get_json(f"{jobs_api}/{job_address}")
        except Exception:
            last = None
        if (
            isinstance(last, dict)
            and last.get("address") == job_address
            and int(last.get("state", -1)) == 1
            and last.get("node")
        ):
            return last
        if isinstance(last, dict) and int(last.get("state", -1)) == 2:
            raise RuntimeError("Nosana job became terminal before confidential delivery")
        if attempt + 1 < attempts:
            sleep(interval_seconds)
    raise RuntimeError(f"Nosana job {job_address} was not claimed within the delivery window")


def verify_confidential_stub(
    *,
    get_json=_default_get_json,
    cid: str = CONFIDENTIAL_STUB_CID,
) -> bool:
    expected = {
        "version": "0.1",
        "type": "container",
        "meta": {"trigger": "cli"},
        "logistics": {
            "send": {"type": "api-listen", "args": {}},
            "receive": {"type": "api-listen", "args": {}},
        },
        "ops": [],
    }
    actual = get_json(f"https://nosana.mypinata.cloud/ipfs/{cid}")
    if actual != expected:
        raise RuntimeError("public confidential stub differs from the pinned allowlist")
    decode_confidential_stub_cid(cid)
    return True


def bootstrap_once(
    *,
    bundle: dict,
    sandbox_id: str,
    rpc_impl,
    get_json=_default_get_json,
    request_impl=None,
    sleep=time.sleep,
) -> dict:
    """Recover or list once, deliver once, and return an allowlisted receipt."""

    if not sandbox_id:
        raise ValueError("sandbox id is required")
    try:
        payer = Keypair.from_base58_string(bundle["solanaSecret"])
        market = Pubkey.from_string(bundle["market"])
        timeout_sec = int(bundle["timeoutSec"])
        definition = bundle["definition"]
    except Exception as exc:
        raise ValueError("bootstrap bundle is incomplete") from exc
    if not isinstance(definition, dict) or not definition.get("ops"):
        raise ValueError("bootstrap definition is invalid")
    verify_confidential_stub(get_json=get_json)
    existing = discover_active_job(
        payer=str(payer.pubkey()),
        market=str(market),
        rpc_impl=rpc_impl,
        get_json=get_json,
    )
    list_receipt = None
    if existing:
        job_address = existing["address"]
        action = "recovered"
    else:
        terms = fetch_market_terms(rpc_impl, market)
        balances = fetch_payer_balances(rpc_impl, payer.pubkey())
        gate = evaluate_post_gate(
            job_price_microunits_per_sec=terms["jobPriceMicrounitsPerSec"],
            market_job_timeout_sec=terms["jobTimeoutSec"],
            nos_balance=balances["nos"],
            sol_balance=balances["sol"],
        )
        if not gate["allowed"]:
            raise RuntimeError(f"post gate refused: {gate['reason']}")
        list_receipt = submit_list_job(
            payer=payer,
            market=market,
            timeout_sec=timeout_sec,
            rpc_impl=rpc_impl,
            sleep=sleep,
        )
        job_address = list_receipt["jobAddress"]
        action = "listed"
    claimed = wait_for_claimed_job(
        job_address=job_address,
        get_json=get_json,
        sleep=sleep,
    )
    if claimed.get("payer") != str(payer.pubkey()) or claimed.get("market") != str(market):
        raise RuntimeError("claimed job readback does not bind the expected payer and market")
    delivery = deliver_definition_until_running(
        job=claimed,
        definition=definition,
        cid=CONFIDENTIAL_STUB_CID,
        secret_bytes=bytes(payer),
        request_impl=request_impl,
        sleep=sleep,
    )
    return {
        "ok": True,
        "sandboxId": sandbox_id,
        "action": action,
        "recovered": action == "recovered",
        "listed": action == "listed",
        "payer": str(payer.pubkey()),
        "market": str(market),
        "jobAddress": job_address,
        "listSignature": list_receipt["signature"] if list_receipt else None,
        "listStatus": list_receipt["status"] if list_receipt else None,
        "delivery": delivery,
    }


def _cli() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="mode", required=True)
    prepare = subparsers.add_parser("prepare-key")
    prepare.add_argument("--key-path", required=True)
    bootstrap = subparsers.add_parser("bootstrap")
    bootstrap.add_argument("--key-path", required=True)
    bootstrap.add_argument("ciphertext_chunks", nargs="+")
    args = parser.parse_args()
    sandbox_id = os.environ.get("MODAL_SANDBOX_ID", "")
    if not sandbox_id:
        raise RuntimeError("MODAL_SANDBOX_ID is required")
    if args.mode == "prepare-key":
        result = {
            "ok": True,
            "sandboxId": sandbox_id,
            "publicKey": prepare_ephemeral_key(args.key_path),
        }
    else:
        ciphertext = base64.b64decode("".join(args.ciphertext_chunks), validate=True)
        bundle = decrypt_bootstrap_bundle(ciphertext, args.key_path)
        result = bootstrap_once(
            bundle=bundle,
            sandbox_id=sandbox_id,
            rpc_impl=make_rpc(bundle.get("rpcUrl", DEFAULT_RPC_URL)),
        )
    print(json.dumps(result, separators=(",", ":"), ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(_cli())
    except Exception as error:
        print(
            json.dumps(
                {"ok": False, "error": str(error)[:200]},
                separators=(",", ":"),
            ),
            flush=True,
        )
        raise SystemExit(1)
