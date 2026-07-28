"""Minimal Python client for bootstrapping confidential Nosana jobs.

The instruction layout and account derivations mirror Nosana's public Rust
program and the official JavaScript SDK.  This module intentionally does not
use Nosana's embedded Pinata credential.
"""

from __future__ import annotations

import base64
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
