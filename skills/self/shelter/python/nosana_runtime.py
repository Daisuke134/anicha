"""Long-lived Python heartbeat and financial-statement service for a Nosana container."""

import base58
import json
import os
from pathlib import Path
import threading
import time

from nacl.signing import SigningKey

from heartbeat import emit_heartbeats
from statement import (
    DEFAULT_POLYMARKET_ADDRESS,
    _verify_heartbeat_row,
    build_public_statement,
    serve_statement,
)


def main():
    job_address = os.environ["NOSANA_JOB_ADDRESS"]
    base_address = os.environ["BASE_PUBLIC_ADDRESS"]
    secret = base58.b58decode(os.environ["SOLANA_SESSION"])
    signing_key = SigningKey(secret[:32])
    payer = base58.b58encode(signing_key.verify_key.encode()).decode("ascii")
    heartbeat_file = Path("/tmp/heartbeats.jsonl")
    statement_file = Path("/tmp/statement.json")

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
    )
    statement_file.write_text(
        json.dumps(statement, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    serve_statement(
        statement_file=statement_file,
        heartbeats_file=heartbeat_file,
        port=8080,
    )


if __name__ == "__main__":
    main()
