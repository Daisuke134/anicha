"""Canonical Ed25519 heartbeat for the managed Python second house.

This module deliberately emits the same bytes as `nosana/heartbeat.mjs`. The two runtimes can
therefore share one independent verifier instead of letting Python grade evidence it produced.
"""

import argparse
import json
import math
import os
import sys
import time
from urllib.request import Request, urlopen

import base58
from nacl.signing import SigningKey


MESSAGE_KEYS = ("blockhash", "cycle", "jobAddress", "payer", "slot", "ts")
DEFAULT_RPC_URL = "https://api.mainnet-beta.solana.com"


def _non_empty_string(value):
    return isinstance(value, str) and len(value) > 0


def _integer(value):
    return isinstance(value, int) and not isinstance(value, bool)


def build_heartbeat_message(fields):
    """Return compact canonical JSON in the exact key order used by the JS verifier."""
    if not isinstance(fields, dict):
        raise TypeError("build_heartbeat_message: fields must be a dict")
    if not _non_empty_string(fields.get("jobAddress")):
        raise ValueError("build_heartbeat_message: jobAddress is required")
    if not _non_empty_string(fields.get("payer")):
        raise ValueError("build_heartbeat_message: payer is required")
    if not _non_empty_string(fields.get("blockhash")):
        raise ValueError("build_heartbeat_message: blockhash is required")
    if not _integer(fields.get("slot")) or fields["slot"] < 0:
        raise ValueError("build_heartbeat_message: slot must be a non-negative integer")
    ts = fields.get("ts")
    if isinstance(ts, bool) or not isinstance(ts, (int, float)) or not math.isfinite(ts) or ts <= 0:
        raise ValueError("build_heartbeat_message: ts must be a positive number")
    if not _integer(fields.get("cycle")) or fields["cycle"] < 0:
        raise ValueError("build_heartbeat_message: cycle must be a non-negative integer")

    ordered = {key: fields[key] for key in MESSAGE_KEYS}
    return json.dumps(ordered, separators=(",", ":"), ensure_ascii=False)


def make_heartbeat_entry(*, job_address, blockhash, slot, ts, cycle, signing_key):
    """Build and sign one entry; payer is always derived from the supplied Ed25519 key."""
    if not isinstance(signing_key, SigningKey):
        raise TypeError("make_heartbeat_entry: signing_key must be a SigningKey")
    payer = base58.b58encode(signing_key.verify_key.encode()).decode("ascii")
    public_fields = {
        "jobAddress": job_address,
        "payer": payer,
        "blockhash": blockhash,
        "slot": slot,
        "ts": ts,
        "cycle": cycle,
    }
    message = build_heartbeat_message(public_fields)
    signature = signing_key.sign(message.encode("utf-8")).signature
    sig = base58.b58encode(signature).decode("ascii")
    return {
        "v": 1,
        "kind": "shelter-heartbeat",
        "ts": ts,
        "cycle": cycle,
        "jobAddress": job_address,
        "payer": payer,
        "slot": slot,
        "blockhash": blockhash,
        "sig": sig,
    }


def fetch_latest_blockhash(rpc_url=DEFAULT_RPC_URL, opener=urlopen):
    """Read the fresh blockhash and response-context slot from Solana JSON-RPC."""
    body = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getLatestBlockhash",
            "params": [{"commitment": "confirmed"}],
        }
    ).encode("utf-8")
    request = Request(rpc_url, data=body, headers={"content-type": "application/json"}, method="POST")
    with opener(request, timeout=15) as response:
        payload = json.load(response)
    result = payload.get("result") or {}
    context = result.get("context") or {}
    value = result.get("value") or {}
    blockhash = value.get("blockhash")
    slot = context.get("slot")
    if not _non_empty_string(blockhash) or not _integer(slot) or slot < 0:
        raise ValueError("fetch_latest_blockhash: RPC returned no usable blockhash and slot")
    return blockhash, slot


def emit_heartbeats(
    *,
    job_address,
    cycles,
    interval_seconds,
    signing_key=None,
    fetcher=fetch_latest_blockhash,
    now_ms=lambda: int(time.time() * 1000),
    sleep=time.sleep,
    output=sys.stdout,
):
    """Emit a naturally timed JSONL sequence under one in-process Ed25519 identity."""
    if not _non_empty_string(job_address):
        raise ValueError("emit_heartbeats: job_address is required")
    if not _integer(cycles) or cycles < 1:
        raise ValueError("emit_heartbeats: cycles must be a positive integer")
    if isinstance(interval_seconds, bool) or not isinstance(interval_seconds, (int, float)):
        raise TypeError("emit_heartbeats: interval_seconds must be a non-negative number")
    if not math.isfinite(interval_seconds) or interval_seconds < 0:
        raise ValueError("emit_heartbeats: interval_seconds must be a non-negative number")

    key = signing_key or SigningKey.generate()
    entries = []
    for cycle in range(1, cycles + 1):
        blockhash, slot = fetcher()
        entry = make_heartbeat_entry(
            job_address=job_address,
            blockhash=blockhash,
            slot=slot,
            ts=now_ms(),
            cycle=cycle,
            signing_key=key,
        )
        output.write(json.dumps(entry, separators=(",", ":")) + "\n")
        output.flush()
        entries.append(entry)
        if cycle < cycles:
            sleep(interval_seconds)
    return entries


def main(argv=None):
    parser = argparse.ArgumentParser(description="Emit canonical shelter heartbeat JSONL")
    parser.add_argument("--cycles", type=int, default=2)
    parser.add_argument("--interval", type=float, default=45)
    parser.add_argument("--rpc", default=os.environ.get("SOLANA_RPC_URL", DEFAULT_RPC_URL))
    args = parser.parse_args(argv)

    sandbox_id = os.environ.get("MODAL_SANDBOX_ID")
    if not sandbox_id:
        parser.error("MODAL_SANDBOX_ID is required")
    emit_heartbeats(
        job_address=sandbox_id,
        cycles=args.cycles,
        interval_seconds=args.interval,
        fetcher=lambda: fetch_latest_blockhash(args.rpc),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
