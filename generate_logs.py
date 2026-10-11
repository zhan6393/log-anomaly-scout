#!/usr/bin/env python3
"""
generate_logs.py — synthesize a realistic application log file with injected
failure windows for the log-anomaly-scout demo.

All content is fictional: invented services, endpoints, hostnames, and IDs.
No real personal data or company system details are used.

Output:
    logs/app.log          — ~2000 lines of logs, fixed random seed (reproducible)
    logs/ground_truth.json — injected incident windows (start/end/label/service)

Usage:
    python generate_logs.py
"""

from __future__ import annotations

import json
import random
from datetime import datetime, timedelta
from pathlib import Path

SEED = 20261010
START = datetime(2026, 10, 1, 0, 0, 0)
TOTAL_MINUTES = 360  # 6 hours of logs
TARGET_LINES = 2000
OUT_DIR = Path(__file__).resolve().parent / "logs"

# --- Fictional services and message templates -------------------------------
SERVICES = ["api-gateway", "auth-svc", "order-svc", "payment-svc"]

INFO_TEMPLATES = [
    "Request processed req_id=REQ-{n:06d} latency={lat}ms",
    "Health check ok instance=inst-{h} region=ca-central-1",
    "Cache refresh completed keys={k} duration={d}ms",
    "Worker heartbeat worker_id=wrk-{h}",
    "Scheduled job finished job=nightly-report rc=0",
]

WARN_TEMPLATES = [
    "Retry attempt {r}/3 for req_id=REQ-{n:06d} backoff={b}ms",
    "Slow query detected table=orders p95={lat}ms",
    "Connection pool usage high pool=db-read usage={p}%",
]

ERROR_TEMPLATES = [
    "NullPointerError handling req_id=REQ-{n:06d} endpoint=/api/v1/checkout",
    "Downstream timeout after 3000ms req_id=REQ-{n:06d}",
    "Malformed payload rejected req_id=REQ-{n:06d} reason=schema-mismatch",
]

# --- Injected failure windows (fictional incidents) --------------------------
# Each entry: service, start minute offset, end minute offset, label, spike template
INJECTIONS = [
    {
        "service": "payment-svc",
        "start_min": 70,
        "end_min": 85,
        "label": "db-connection-storm",
        "error_rate": 0.55,
        "error_templates": [
            "Connection refused: db-primary:5432 pool exhausted req_id=REQ-{n:06d}",
            "Transaction rollback failed req_id=REQ-{n:06d} reason=db-unavailable",
        ],
    },
    {
        "service": "api-gateway",
        "start_min": 220,
        "end_min": 238,
        "label": "upstream-timeout-wave",
        "error_rate": 0.45,
        "error_templates": [
            "Upstream timeout after 5000ms req_id=REQ-{n:06d} upstream=orders",
            "502 Bad Gateway req_id=REQ-{n:06d} upstream=orders",
        ],
    },
    {
        "service": "order-svc",
        "start_min": 300,
        "end_min": 312,
        "label": "circuit-breaker-open",
        "error_rate": 0.35,
        "error_templates": [
            "Circuit breaker OPEN for inventory-client req_id=REQ-{n:06d}",
            "Fallback response served req_id=REQ-{n:06d} reason=inventory-degraded",
        ],
    },
]


def in_window(minute: int, service: str):
    """Return the injection dict if (minute, service) falls inside a window."""
    for inj in INJECTIONS:
        if inj["service"] == service and inj["start_min"] <= minute < inj["end_min"]:
            return inj
    return None


def main() -> None:
    rng = random.Random(SEED)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    lines = []
    ts = START
    for i in range(TARGET_LINES):
        # advance time by a small random delta so ~2000 lines span 360 minutes
        ts += timedelta(seconds=rng.uniform(8, 14))
        service = rng.choice(SERVICES)
        minute = int((ts - START).total_seconds() // 60)

        inj = in_window(minute, service)
        roll = rng.random()
        if inj and roll < inj["error_rate"]:
            level, msg = "ERROR", rng.choice(inj["error_templates"])
        elif roll < 0.015:  # background noise
            level, msg = "ERROR", rng.choice(ERROR_TEMPLATES)
        elif roll < 0.06:
            level, msg = "WARN", rng.choice(WARN_TEMPLATES)
        else:
            level, msg = "INFO", rng.choice(INFO_TEMPLATES)

        msg = msg.format(
            n=rng.randint(1, 999999),
            lat=rng.randint(5, 400),
            k=rng.randint(10, 500),
            d=rng.randint(20, 800),
            h=rng.randint(1, 12),
            r=rng.randint(1, 3),
            b=rng.randint(100, 2000),
            p=rng.randint(70, 99),
        )
        lines.append(f"{ts.strftime('%Y-%m-%dT%H:%M:%S')} {level} {service} {msg}\n")

    (OUT_DIR / "app.log").write_text("".join(lines), encoding="utf-8")

    ground_truth = [
        {
            "service": inj["service"],
            "start": (START + timedelta(minutes=inj["start_min"])).strftime(
                "%Y-%m-%dT%H:%M:%S"
            ),
            "end": (START + timedelta(minutes=inj["end_min"])).strftime(
                "%Y-%m-%dT%H:%M:%S"
            ),
            "label": inj["label"],
        }
        for inj in INJECTIONS
    ]
    (OUT_DIR / "ground_truth.json").write_text(
        json.dumps(ground_truth, indent=2) + "\n", encoding="utf-8"
    )

    print(f"Wrote {len(lines)} lines -> {OUT_DIR / 'app.log'}")
    print(f"Wrote {len(ground_truth)} injected windows -> {OUT_DIR / 'ground_truth.json'}")


if __name__ == "__main__":
    main()
