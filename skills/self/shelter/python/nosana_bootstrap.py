"""Python bootstrap/poster primitives for confidential Nosana jobs.

This module copies the public Nosana Jobs `list` account contract and the
official CLI authorization format. It deliberately contains no wallet value.
"""

from __future__ import annotations

import hashlib
import struct

import base58
from solders.instruction import AccountMeta, Instruction
from solders.keypair import Keypair
from solders.pubkey import Pubkey


CONFIDENTIAL_STUB_CID = "QmYBbVdWFgfoTEdPT7mnaXJz6zQzfKb1Pts4A5B9kDMBph"
JOBS_PROGRAM = "nosJhNRqr2bc9g1nfGDcXXTXvYUmxD4cVwy2pMWhrYM"
NOS_MINT = "nosXBVoaCTtYdLvKY6Csb4AC8JCdQKKAaWYtx2ZMoo7"
REWARDS_PROGRAM = "nosRB8DUV67oLNrL45bo2pFLrmsWPiewe2Lk2DRNYCp"
TOKEN_PROGRAM = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
ASSOCIATED_TOKEN_PROGRAM = "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL"
SYSTEM_PROGRAM = "11111111111111111111111111111111"


def decode_confidential_stub_cid(cid: str) -> bytes:
    """Return the 32-byte sha2-256 multihash payload expected by `list`."""
    try:
        decoded = base58.b58decode(cid)
    except Exception as exc:
        raise ValueError("CID must be a base58 sha2-256 multihash") from exc
    if len(decoded) != 34 or decoded[:2] != b"\x12\x20":
        raise ValueError("CID must be a base58 sha2-256 multihash")
    return decoded[2:]


def _pda(seeds: list[bytes], program: str) -> Pubkey:
    return Pubkey.find_program_address(seeds, Pubkey.from_string(program))[0]


def _associated_token_address(owner: Pubkey, mint: Pubkey) -> Pubkey:
    return _pda(
        [bytes(owner), bytes(Pubkey.from_string(TOKEN_PROGRAM)), bytes(mint)],
        ASSOCIATED_TOKEN_PROGRAM,
    )


def build_list_instruction(
    *,
    payer: Pubkey,
    job: Pubkey,
    run: Pubkey,
    market: Pubkey,
    timeout_sec: int,
    cid: str = CONFIDENTIAL_STUB_CID,
) -> Instruction:
    if not isinstance(timeout_sec, int) or timeout_sec <= 0:
        raise ValueError("timeout must be a positive integer")
    mint = Pubkey.from_string(NOS_MINT)
    rewards = Pubkey.from_string(REWARDS_PROGRAM)
    accounts = [
        AccountMeta(job, True, True),
        AccountMeta(market, False, True),
        AccountMeta(run, True, True),
        AccountMeta(_associated_token_address(payer, mint), False, True),
        AccountMeta(_pda([bytes(market), bytes(mint)], JOBS_PROGRAM), False, True),
        AccountMeta(payer, True, True),
        AccountMeta(_pda([b"reflection"], REWARDS_PROGRAM), False, True),
        AccountMeta(_pda([bytes(mint)], REWARDS_PROGRAM), False, True),
        AccountMeta(payer, True, False),
        AccountMeta(rewards, False, False),
        AccountMeta(Pubkey.from_string(TOKEN_PROGRAM), False, False),
        AccountMeta(Pubkey.from_string(SYSTEM_PROGRAM), False, False),
    ]
    data = (
        hashlib.sha256(b"global:list").digest()[:8]
        + decode_confidential_stub_cid(cid)
        + struct.pack("<q", timeout_sec)
    )
    return Instruction(Pubkey.from_string(JOBS_PROGRAM), data, accounts)


def build_authorization(message: str, secret_bytes: bytes, *, now_ms: int) -> str:
    if not isinstance(message, str) or not message:
        raise ValueError("authorization message is required")
    if not isinstance(now_ms, int) or now_ms <= 0:
        raise ValueError("authorization timestamp must be positive")
    try:
        keypair = Keypair.from_bytes(secret_bytes)
    except Exception as exc:
        raise ValueError("authorization secret must be one 64-byte Solana keypair") from exc
    signature = keypair.sign_message(message.encode("utf-8"))
    return f"{message}:{signature}:{now_ms}"

