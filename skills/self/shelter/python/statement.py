"""Public, allowlist-only financial statement for the managed Python second house."""

from __future__ import annotations

import argparse
import base58
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

from nacl.signing import VerifyKey

from heartbeat import build_heartbeat_message, emit_heartbeats


BASE_RPC_URL = "https://mainnet.base.org"
SOLANA_RPC_URL = "https://api.mainnet-beta.solana.com"
POLYMARKET_POSITIONS_URL = "https://data-api.polymarket.com/positions"
BASE_USDC_ADDRESS = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
NOS_MINT = "nosXBVoaCTtYdLvKY6Csb4AC8JCdQKKAaWYtx2ZMoo7"
RUNTIME_COST_USD = 0.015

PUBLIC_TOP = (
    "v",
    "generatedAt",
    "sandboxId",
    "wallets",
    "balances",
    "polymarket",
    "economy",
    "heartbeats",
)
PUBLIC_NESTED = {
    "wallets": ("base", "solana", "polymarket"),
    "balances": ("baseUsdc", "solanaSol", "solanaNos"),
    "polymarket": ("positionCount", "currentValueUsd", "cashPnlUsd", "redeemableCount"),
    "economy": ("externalRevenueUsd", "runtimeCostUsd", "verdict"),
    "heartbeats": ("claimed", "verified"),
}

_EVM_ADDRESS = re.compile(r"^0x[0-9a-fA-F]{40}$")
_SOLANA_ADDRESS = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")
_TUNNEL_URL = re.compile(r"https?://[a-z0-9-]+\.trycloudflare\.com")

DEFAULT_BASE_ADDRESS = "0x810f6d61f7606deee2657d3083e150a222bc29c5"
DEFAULT_SOLANA_ADDRESS = "71FfqFniYoMsWZb1qFeQDb1fk2xqvajzivpsnMb44gTf"
DEFAULT_POLYMARKET_ADDRESS = "0x904B50d2e214Da947d83D6a2D32c4E3Ffc17Eb74"


def request_json(url, payload=None):
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = Request(
        url,
        data=body,
        headers={"content-type": "application/json", "user-agent": "anicca-s20b-statement/1"},
        method="GET" if body is None else "POST",
    )
    with urlopen(request, timeout=15) as response:
        return json.load(response)


def _nonnegative_number(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a non-negative finite number")
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"{name} must be a non-negative finite number")
    return number


def _evm_address(value, name):
    if not isinstance(value, str) or not _EVM_ADDRESS.fullmatch(value):
        raise ValueError(f"{name} must be a 20-byte EVM address")
    return value


def _solana_address(value):
    if not isinstance(value, str) or not _SOLANA_ADDRESS.fullmatch(value):
        raise ValueError("solana_address must be a base58 public key")
    return value


def _rpc_payload(method, params):
    return {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}


def fetch_base_usdc(address, request_json=request_json):
    address = _evm_address(address, "base_address")
    calldata = "0x70a08231" + ("0" * 24) + address[2:].lower()
    response = request_json(
        BASE_RPC_URL,
        _rpc_payload(
            "eth_call",
            [{"to": BASE_USDC_ADDRESS, "data": calldata}, "latest"],
        ),
    )
    result = response.get("result") if isinstance(response, dict) else None
    if not isinstance(result, str) or not re.fullmatch(r"0x[0-9a-fA-F]+", result):
        raise ValueError("Base RPC returned no usable USDC balance")
    return int(result, 16) / 1_000_000


def fetch_solana_balances(address, request_json=request_json):
    address = _solana_address(address)
    sol_response = request_json(
        SOLANA_RPC_URL,
        _rpc_payload("getBalance", [address, {"commitment": "confirmed"}]),
    )
    try:
        lamports = sol_response["result"]["value"]
    except (KeyError, TypeError):
        raise ValueError("Solana RPC returned no usable SOL balance") from None
    solana_sol = _nonnegative_number(lamports, "solana lamports") / 1_000_000_000

    nos_response = request_json(
        SOLANA_RPC_URL,
        _rpc_payload(
            "getTokenAccountsByOwner",
            [
                address,
                {"mint": NOS_MINT},
                {"encoding": "jsonParsed", "commitment": "confirmed"},
            ],
        ),
    )
    try:
        accounts = nos_response["result"]["value"]
    except (KeyError, TypeError):
        raise ValueError("Solana RPC returned no usable NOS token accounts") from None
    if not isinstance(accounts, list):
        raise ValueError("Solana RPC returned malformed NOS token accounts")

    nos_total = 0.0
    for account in accounts:
        try:
            token_amount = account["account"]["data"]["parsed"]["info"]["tokenAmount"]
            raw_amount = token_amount["amount"]
            decimals = token_amount["decimals"]
        except (KeyError, TypeError):
            raise ValueError("Solana RPC returned a malformed NOS token account") from None
        if isinstance(raw_amount, bool) or not isinstance(raw_amount, str) or not raw_amount.isdigit():
            raise ValueError("NOS raw amount must be an unsigned integer string")
        if isinstance(decimals, bool) or not isinstance(decimals, int) or decimals < 0:
            raise ValueError("NOS decimals must be a non-negative integer")
        nos_total += int(raw_amount) / (10 ** decimals)

    return {"solanaSol": solana_sol, "solanaNos": nos_total}


def fetch_polymarket(address, request_json=request_json):
    address = _evm_address(address, "polymarket_address")
    response = request_json(
        f"{POLYMARKET_POSITIONS_URL}?{urlencode({'user': address})}",
        None,
    )
    if not isinstance(response, list):
        raise ValueError("Polymarket returned no usable positions list")

    current_micro = 0
    pnl_micro = 0
    redeemable_count = 0
    for position in response:
        if not isinstance(position, dict):
            raise ValueError("Polymarket returned a malformed position")
        current = _nonnegative_number(position.get("currentValue"), "position currentValue")
        cash_pnl = position.get("cashPnl")
        if isinstance(cash_pnl, bool) or not isinstance(cash_pnl, (int, float)):
            raise ValueError("position cashPnl must be finite")
        cash_pnl = float(cash_pnl)
        if not math.isfinite(cash_pnl):
            raise ValueError("position cashPnl must be finite")
        redeemable = position.get("redeemable")
        if not isinstance(redeemable, bool):
            raise ValueError("position redeemable must be boolean")
        current_micro += round(current * 1_000_000)
        pnl_micro += round(cash_pnl * 1_000_000)
        redeemable_count += int(redeemable)

    return {
        "positionCount": len(response),
        "currentValueUsd": current_micro / 1_000_000,
        "cashPnlUsd": pnl_micro / 1_000_000,
        "redeemableCount": redeemable_count,
    }


def allowlist_public_statement(candidate):
    if not isinstance(candidate, dict):
        raise ValueError("statement must be an object")
    public = {}
    for field in PUBLIC_TOP:
        if field not in candidate:
            continue
        value = candidate[field]
        nested_fields = PUBLIC_NESTED.get(field)
        if nested_fields is None:
            public[field] = value
        else:
            if not isinstance(value, dict):
                raise ValueError(f"{field} must be an object")
            public[field] = {name: value[name] for name in nested_fields if name in value}
    return public


def build_public_statement(
    *,
    sandbox_id,
    base_address,
    solana_address,
    polymarket_address,
    request_json=request_json,
    heartbeats=(),
    now_ms=lambda: int(time.time() * 1000),
):
    if not isinstance(sandbox_id, str) or not sandbox_id.startswith("sb-"):
        raise ValueError("sandbox_id must name a managed sandbox")
    base_address = _evm_address(base_address, "base_address")
    solana_address = _solana_address(solana_address)
    polymarket_address = _evm_address(polymarket_address, "polymarket_address")
    heartbeat_rows = list(heartbeats)
    base_usdc = fetch_base_usdc(base_address, request_json=request_json)
    solana = fetch_solana_balances(solana_address, request_json=request_json)
    polymarket = fetch_polymarket(polymarket_address, request_json=request_json)

    candidate = {
        "v": 1,
        "generatedAt": int(now_ms()),
        "sandboxId": sandbox_id,
        "wallets": {
            "base": base_address,
            "solana": solana_address,
            "polymarket": polymarket_address,
        },
        "balances": {
            "baseUsdc": base_usdc,
            **solana,
        },
        "polymarket": polymarket,
        "economy": {
            "externalRevenueUsd": 0.0,
            "runtimeCostUsd": RUNTIME_COST_USD,
            "verdict": "funded",
        },
        "heartbeats": {
            "claimed": len(heartbeat_rows),
            "verified": sum(1 for row in heartbeat_rows if row.get("verified") is True),
        },
    }
    return allowlist_public_statement(candidate)


def _usd(value, digits=4):
    number = float(value)
    if number == 0:
        return "$0.00"
    return f"${number:.{digits}f}"


def render_statement_html(statement):
    statement = allowlist_public_statement(statement)
    wallets = statement["wallets"]
    balances = statement["balances"]
    polymarket = statement["polymarket"]
    economy = statement["economy"]
    heartbeats = statement["heartbeats"]
    e = lambda value: escape(str(value), quote=True)

    return f"""<!doctype html>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Python second-house statement</title>
<style>
body{{font:14px/1.6 ui-monospace,Menlo,monospace;max-width:52rem;margin:3rem auto;padding:0 1rem}}
h1{{font-size:1.15rem}}h2{{font-size:1rem;margin-top:2rem;border-bottom:1px solid;padding-bottom:.2rem}}
table{{border-collapse:collapse;width:100%}}td,th{{padding:.3rem .5rem .3rem 0;text-align:left}}
.n{{text-align:right}}.zero{{font-weight:700}}code{{overflow-wrap:anywhere}}
</style>
<h1>What this Python agent can publicly account for</h1>
<p>Generated inside sandbox <code>{e(statement["sandboxId"])}</code>. The addresses and balances
below are public claims. If they disagree with their public APIs or chains, those sources win.</p>

<h2>Public wallets</h2>
<table>
<tr><th>rail</th><th>address</th></tr>
<tr><td>Base</td><td><code>{e(wallets["base"])}</code></td></tr>
<tr><td>Solana</td><td><code>{e(wallets["solana"])}</code></td></tr>
<tr><td>Polymarket proxy</td><td><code>{e(wallets["polymarket"])}</code></td></tr>
</table>

<h2>Balances</h2>
<table>
<tr><td>Base USDC</td><td class="n">{_usd(balances["baseUsdc"], 6)}</td></tr>
<tr><td>Solana SOL</td><td class="n">{e(balances["solanaSol"])}</td></tr>
<tr><td>Solana NOS</td><td class="n">{e(balances["solanaNos"])}</td></tr>
</table>

<h2>Polymarket — marked, not closed accounting</h2>
<table>
<tr><td>open positions</td><td class="n">{e(polymarket["positionCount"])}</td></tr>
<tr><td>marked position value</td><td class="n">{_usd(polymarket["currentValueUsd"], 4)}</td></tr>
<tr><td>positions API cash PnL</td><td class="n">{_usd(polymarket["cashPnlUsd"], 4)}</td></tr>
<tr><td>redeemable positions</td><td class="n">{e(polymarket["redeemableCount"])}</td></tr>
</table>
<p>This marked value is <strong>not closed net profit</strong>. It does not separate deployed
capital, recovered capital, fees, gas, or model costs. That separation belongs to the earnings
ledger.</p>

<h2>Economic truth</h2>
<p class="zero">{_usd(economy["externalRevenueUsd"], 2)} from outside</p>
<p>This proof runtime cost {_usd(economy["runtimeCostUsd"], 4)} at the provider's published
create-plus-exec price. The verdict remains <strong>{e(economy["verdict"])}</strong>, not
self-funded.</p>

<h2>Liveness</h2>
<p>{e(heartbeats["verified"])} of {e(heartbeats["claimed"])} heartbeat rows passed signature
verification before publication. Raw rows are available at <code>/heartbeats</code>; the exact
public snapshot is at <code>/statement.json</code>.</p>
"""


def make_statement_handler(statement, heartbeat_jsonl):
    statement = allowlist_public_statement(statement)
    html_body = render_statement_html(statement).encode("utf-8")
    json_body = (json.dumps(statement, separators=(",", ":")) + "\n").encode("utf-8")
    heartbeat_body = heartbeat_jsonl.encode("utf-8")
    routes = {
        "/": ("text/html; charset=utf-8", html_body),
        "/statement.json": ("application/json; charset=utf-8", json_body),
        "/heartbeats": ("application/x-ndjson; charset=utf-8", heartbeat_body),
    }

    class StatementHandler(BaseHTTPRequestHandler):
        def _respond(self, include_body):
            route = routes.get(self.path)
            if route is None:
                self.send_error(404, "not found")
                return
            content_type, body = route
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            if include_body:
                self.wfile.write(body)

        def do_GET(self):
            self._respond(include_body=True)

        def do_HEAD(self):
            self._respond(include_body=False)

        def log_message(self, *_args):
            return

    return StatementHandler


def serve_statement(*, statement_file, heartbeats_file, port):
    statement = json.loads(Path(statement_file).read_text(encoding="utf-8"))
    heartbeat_jsonl = Path(heartbeats_file).read_text(encoding="utf-8")
    handler = make_statement_handler(statement, heartbeat_jsonl)
    server = ThreadingHTTPServer(("127.0.0.1", int(port)), handler)
    server.serve_forever()


def extract_tunnel_url(log_text):
    if not isinstance(log_text, str):
        raise ValueError("tunnel log must be text")
    matches = _TUNNEL_URL.findall(log_text)
    if len(matches) != 1:
        raise ValueError("tunnel log must contain exactly one Quick Tunnel URL")
    parsed = urlsplit(matches[0])
    if (
        parsed.scheme != "https"
        or parsed.hostname is None
        or not parsed.hostname.endswith(".trycloudflare.com")
        or parsed.port is not None
        or parsed.path
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("tunnel URL must be a bare HTTPS trycloudflare.com origin")
    return matches[0]


def _verify_heartbeat_row(row):
    try:
        verify_key = VerifyKey(base58.b58decode(row["payer"]))
        signature = base58.b58decode(row["sig"])
        verify_key.verify(build_heartbeat_message(row).encode("utf-8"), signature)
        return True
    except Exception:
        return False


def launch_public_statement(
    *,
    cloudflared_path,
    port,
    sandbox_id,
    base_address,
    solana_address,
    polymarket_address,
    request_json=request_json,
    heartbeat_emitter=emit_heartbeats,
    heartbeat_verifier=_verify_heartbeat_row,
    popen=subprocess.Popen,
    sleep=time.sleep,
    read_text=lambda path: Path(path).read_text(encoding="utf-8"),
    temporary_root=Path("/tmp/s20b-statement"),
    now_ms=lambda: int(time.time() * 1000),
):
    temporary_root = Path(temporary_root)
    temporary_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    heartbeat_file = temporary_root / "heartbeats.jsonl"
    statement_file = temporary_root / "statement.json"
    tunnel_log = temporary_root / "cloudflared.log"

    heartbeat_output = io.StringIO()
    heartbeat_rows = heartbeat_emitter(
        job_address=sandbox_id,
        cycles=2,
        interval_seconds=5,
        output=heartbeat_output,
    )
    heartbeat_jsonl = heartbeat_output.getvalue()
    heartbeat_file.write_text(heartbeat_jsonl, encoding="utf-8")
    statement_heartbeats = [
        {**row, "verified": heartbeat_verifier(row)}
        for row in heartbeat_rows
    ]
    statement = build_public_statement(
        sandbox_id=sandbox_id,
        base_address=base_address,
        solana_address=solana_address,
        polymarket_address=polymarket_address,
        request_json=request_json,
        heartbeats=statement_heartbeats,
        now_ms=now_ms,
    )
    statement_file.write_text(
        json.dumps(statement, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )

    server_process = popen(
        [
            sys.executable,
            str(Path(__file__)),
            "serve",
            "--statement-file",
            str(statement_file),
            "--heartbeats-file",
            str(heartbeat_file),
            "--port",
            str(port),
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        close_fds=True,
    )
    tunnel_process = popen(
        [
            str(cloudflared_path),
            "tunnel",
            "--no-autoupdate",
            "--url",
            f"http://127.0.0.1:{port}",
            "--logfile",
            str(tunnel_log),
            "--loglevel",
            "info",
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        close_fds=True,
    )

    last_log = ""
    for _ in range(50):
        if server_process.poll() is not None:
            raise RuntimeError("statement server exited before the tunnel became ready")
        if tunnel_process.poll() is not None:
            raise RuntimeError("cloudflared exited before publishing a URL")
        try:
            last_log = read_text(tunnel_log)
        except (FileNotFoundError, OSError):
            last_log = ""
        try:
            url = extract_tunnel_url(last_log)
            return {
                "ok": True,
                "sandboxId": sandbox_id,
                "url": url,
                "statement": statement,
            }
        except ValueError:
            sleep(0.5)
    raise TimeoutError("Quick Tunnel did not publish one valid URL within 25 seconds")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Serve a public Python second-house statement")
    subparsers = parser.add_subparsers(dest="command", required=True)

    serve_parser = subparsers.add_parser("serve")
    serve_parser.add_argument("--statement-file", required=True)
    serve_parser.add_argument("--heartbeats-file", required=True)
    serve_parser.add_argument("--port", type=int, default=8080)

    launch_parser = subparsers.add_parser("launch")
    launch_parser.add_argument("--cloudflared", required=True)
    launch_parser.add_argument("--port", type=int, default=8080)
    launch_parser.add_argument("--base-address", default=DEFAULT_BASE_ADDRESS)
    launch_parser.add_argument("--solana-address", default=DEFAULT_SOLANA_ADDRESS)
    launch_parser.add_argument("--polymarket-address", default=DEFAULT_POLYMARKET_ADDRESS)

    args = parser.parse_args(argv)
    if args.command == "serve":
        serve_statement(
            statement_file=args.statement_file,
            heartbeats_file=args.heartbeats_file,
            port=args.port,
        )
        return 0

    sandbox_id = os.environ.get("MODAL_SANDBOX_ID")
    if not sandbox_id:
        parser.error("MODAL_SANDBOX_ID is required")
    result = launch_public_statement(
        cloudflared_path=args.cloudflared,
        port=args.port,
        sandbox_id=sandbox_id,
        base_address=args.base_address,
        solana_address=args.solana_address,
        polymarket_address=args.polymarket_address,
    )
    sys.stdout.write(json.dumps(result, separators=(",", ":")) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
