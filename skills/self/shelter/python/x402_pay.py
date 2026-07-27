"""x402_pay.py — pay for HTTP resources from a container that has no Node.

Why this exists: our second landlord rents exactly one image, python:3.11. The agent's whole
payment stack was JavaScript, so a box we can rent is a box the agent cannot earn or eat in. This
is the minimum needed to survive there — an x402 "exact" payment built by hand.

It is deliberately dependency-thin: eth_account (for the EIP-712 signature) and requests. No web3,
no RPC, no gas. x402's exact scheme rides on EIP-3009, where a signature alone authorises the
transfer and the recipient submits it, so a wallet that holds only the token can still pay.

Every constant here was read out of @x402/core 2.19.0 and @x402/evm 2.19.0 rather than guessed:
the request header is PAYMENT-SIGNATURE for x402Version 2 (X-PAYMENT was v1), validAfter is the
literal string "0", and the amount is echoed from the 402 verbatim with no unit conversion.
"""

import base64
import json
import secrets
import time

import requests
from eth_account import Account
from eth_utils import to_checksum_address

PAYMENT_HEADER = "PAYMENT-SIGNATURE"  # v2. v1 used X-PAYMENT; sending the wrong one just 402s again.

TRANSFER_WITH_AUTHORIZATION_TYPES = {
    "TransferWithAuthorization": [
        {"name": "from", "type": "address"},
        {"name": "to", "type": "address"},
        {"name": "value", "type": "uint256"},
        {"name": "validAfter", "type": "uint256"},
        {"name": "validBefore", "type": "uint256"},
        {"name": "nonce", "type": "bytes32"},
    ]
}


def read_payment_required(response):
    """The 402's terms. Spec says a PAYMENT-REQUIRED header; some servers put it in the body.

    Accept both. A client that only reads the header silently fails against half the servers, and
    the failure looks like "the server won't tell me the price".
    """
    header = response.headers.get(PAYMENT_HEADER.replace("SIGNATURE", "REQUIRED"))
    if header:
        return json.loads(base64.b64decode(header))
    body = response.json()
    if isinstance(body, dict) and "x402Version" in body:
        return body
    raise ValueError("the server asked for payment but stated no terms")


def choose_requirement(payment_required, network_prefix="eip155:"):
    """Pick an offer we can actually pay. Returns None rather than raising, so a caller can say
    which offers it saw and why none fit."""
    for accepted in payment_required.get("accepts", []):
        if accepted.get("scheme") != "exact":
            continue
        if not str(accepted.get("network", "")).startswith(network_prefix):
            continue
        extra = accepted.get("extra") or {}
        # The signature's domain needs the token's own EIP-712 name and version. Without them the
        # signature is valid but for the wrong domain, and the facilitator rejects it as forged.
        if extra.get("name") and extra.get("version"):
            return accepted
    return None


def build_payment_header(accepted, private_key, resource=None, now=None):
    """Sign one EIP-3009 authorisation and encode it the way the server expects.

    Pure apart from the randomness and the clock, both injectable, so this is testable without
    money or a network.
    """
    chain_id = int(str(accepted["network"]).split(":")[1])
    account = Account.from_key(private_key)
    from_addr = to_checksum_address(account.address)
    pay_to = to_checksum_address(accepted["payTo"])
    asset = to_checksum_address(accepted["asset"])

    nonce_hex = "0x" + secrets.token_bytes(32).hex()
    valid_after = "0"
    valid_before = str(int(now or time.time()) + int(accepted["maxTimeoutSeconds"]))
    value = accepted["amount"]  # verbatim: already in the token's base units

    domain = {
        "name": accepted["extra"]["name"],
        "version": accepted["extra"]["version"],
        "chainId": chain_id,
        "verifyingContract": asset,
    }
    message = {
        "from": from_addr,
        "to": pay_to,
        "value": int(value),
        "validAfter": int(valid_after),
        "validBefore": int(valid_before),
        "nonce": nonce_hex,
    }
    signed = Account.sign_typed_data(account.key, domain, TRANSFER_WITH_AUTHORIZATION_TYPES, message)
    # HexBytes.hex() omits the 0x prefix on this version; a bare hex string is rejected downstream.
    signature = signed.signature.hex()
    if not signature.startswith("0x"):
        signature = "0x" + signature

    payload = {
        "x402Version": 2,
        "accepted": accepted,
        "payload": {
            "authorization": {
                "from": from_addr,
                "to": pay_to,
                "value": value,
                "validAfter": valid_after,
                "validBefore": valid_before,
                "nonce": nonce_hex,
            },
            "signature": signature,
        },
    }
    if resource:
        payload["resource"] = resource
    return base64.b64encode(json.dumps(payload).encode("utf-8")).decode("ascii")


def pay_and_post(url, body, private_key, session=None, max_price=None):
    """POST, and if the answer is 402, pay once and repeat.

    `max_price` is in the token's base units and is checked BEFORE signing — an agent looping on a
    paid endpoint should be stopped by arithmetic, not by an empty wallet.
    """
    http = session or requests
    first = http.post(url, json=body)
    if first.status_code != 402:
        return {"ok": first.status_code < 400, "status": first.status_code, "paid": False, "response": first}

    terms = read_payment_required(first)
    accepted = choose_requirement(terms)
    if accepted is None:
        return {"ok": False, "status": 402, "paid": False, "reason": "no offer this wallet can pay"}
    if max_price is not None and int(accepted["amount"]) > int(max_price):
        return {
            "ok": False,
            "status": 402,
            "paid": False,
            "reason": f"asks {accepted['amount']}, over the {max_price} allowed",
        }

    header = build_payment_header(accepted, private_key, resource=terms.get("resource"))
    second = http.post(url, json=body, headers={PAYMENT_HEADER: header})
    receipt = second.headers.get("PAYMENT-RESPONSE") or second.headers.get("payment-response") or ""
    tx = ""
    if receipt:
        try:
            tx = json.loads(base64.b64decode(receipt)).get("transaction", "")
        except Exception:
            tx = ""
    return {
        "ok": second.status_code < 400,
        "status": second.status_code,
        "paid": True,
        "tx": tx,
        "amount": accepted["amount"],
        "response": second,
    }


if __name__ == "__main__":
    import os
    import sys

    key = os.environ.get("BASE_KEY")
    if not key:
        sys.exit("BASE_KEY is not set")
    prompt = sys.argv[1] if len(sys.argv) > 1 else "Say in one sentence that you paid for this yourself."
    result = pay_and_post(
        "https://blockrun.ai/api/v1/chat/completions",
        {"model": "openai/gpt-5-mini", "messages": [{"role": "user", "content": prompt}], "max_tokens": 80},
        key,
        max_price=20000,  # 0.02 USDC — a hard ceiling on one call
    )
    print("HTTP", result["status"], "paid" if result.get("paid") else "unpaid")
    if result.get("tx"):
        print("TX", result["tx"])
    if result.get("reason"):
        print("REASON", result["reason"])
    if result.get("response") is not None:
        print(result["response"].text[:500])
    sys.exit(0 if result["ok"] else 1)
