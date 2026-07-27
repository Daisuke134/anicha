"""Canonical Ed25519 heartbeat for the managed Python second house.

This module deliberately emits the same bytes as `nosana/heartbeat.mjs`. The two runtimes can
therefore share one independent verifier instead of letting Python grade evidence it produced.
"""

import json
import math

import base58
from nacl.signing import SigningKey


MESSAGE_KEYS = ("blockhash", "cycle", "jobAddress", "payer", "slot", "ts")


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
