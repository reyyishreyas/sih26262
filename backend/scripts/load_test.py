"""Small read-only load probe for the API.

This is a repeatable smoke load test, not a capacity certification. It signs in
once, drives a fixed set of read endpoints from N concurrent workers for a bounded
duration, and reports latency percentiles and error counts.

Example against the demo stack:

    ../.venv/bin/python -m scripts.load_test --duration 10 --concurrency 10

Use a dedicated load-test account and a staging deployment for anything beyond a
local smoke run.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import sys
import time
from dataclasses import dataclass, field

import httpx

DEFAULT_PATHS = (
    "/health",
    "/api/v1/applications?limit=20",
    "/api/v1/officer/dashboard",
)


@dataclass
class Result:
    latencies_ms: list[float] = field(default_factory=list)
    statuses: dict[str, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


async def worker(
    client: httpx.AsyncClient,
    *,
    token: str,
    paths: tuple[str, ...],
    deadline: float,
    result: Result,
    index: int,
) -> None:
    headers = {"Authorization": f"Bearer {token}"}
    cursor = index
    while time.perf_counter() < deadline:
        path = paths[cursor % len(paths)]
        cursor += 1
        started = time.perf_counter()
        try:
            response = await client.get(path, headers=headers)
            result.statuses[str(response.status_code)] = (
                result.statuses.get(str(response.status_code), 0) + 1
            )
            if response.status_code >= 500:
                result.errors.append(f"{path}: {response.status_code}")
        except Exception as exc:  # noqa: BLE001 - reported in the summary
            result.errors.append(f"{path}: {type(exc).__name__}: {exc}")
        finally:
            result.latencies_ms.append((time.perf_counter() - started) * 1000)


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = min(len(ordered) - 1, int(round((len(ordered) - 1) * fraction)))
    return round(ordered[position], 2)


async def run(args: argparse.Namespace) -> dict:
    timeout = httpx.Timeout(args.timeout)
    limits = httpx.Limits(
        max_connections=args.concurrency * 2,
        max_keepalive_connections=args.concurrency,
    )
    async with httpx.AsyncClient(
        base_url=args.base_url.rstrip("/"), timeout=timeout, limits=limits
    ) as client:
        # Sign-in only accepts the sign-in screen's origin (app/api/auth.py), so
        # the probe names one rather than being refused like a plain client.
        login = await client.post(
            "/api/v1/auth/login",
            json={"email": args.email, "password": args.password},
            headers={"Origin": args.ui_origin},
        )
        if login.status_code != 200:
            raise SystemExit(
                f"login failed: {login.status_code} {login.text[:300]}"
            )
        token = login.json()["access_token"]

        result = Result()
        deadline = time.perf_counter() + args.duration
        started = time.perf_counter()
        await asyncio.gather(
            *[
                worker(
                    client,
                    token=token,
                    paths=tuple(args.path),
                    deadline=deadline,
                    result=result,
                    index=index,
                )
                for index in range(args.concurrency)
            ]
        )
        elapsed = time.perf_counter() - started

    requests = len(result.latencies_ms)
    return {
        "base_url": args.base_url,
        "duration_seconds": round(elapsed, 2),
        "concurrency": args.concurrency,
        "requests": requests,
        "requests_per_second": round(requests / elapsed, 2) if elapsed else 0,
        "status_counts": dict(sorted(result.statuses.items())),
        "errors": result.errors[:20],
        "error_count": len(result.errors),
        "latency_ms": {
            "mean": round(statistics.fmean(result.latencies_ms), 2)
            if result.latencies_ms
            else 0,
            "p50": percentile(result.latencies_ms, 0.50),
            "p95": percentile(result.latencies_ms, 0.95),
            "p99": percentile(result.latencies_ms, 0.99),
            "max": round(max(result.latencies_ms), 2)
            if result.latencies_ms
            else 0,
        },
        "note": (
            "Read-only smoke probe. This does not certify capacity, soak "
            "behaviour, multi-worker behaviour or failover."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--email", default="admin@demo.local")
    parser.add_argument(
        "--password",
        default=os.environ.get("SIH_LOADTEST_PASSWORD", "DemoPassw0rd!"),
    )
    parser.add_argument(
        "--ui-origin",
        default=os.environ.get("SIH_UI_ORIGIN", "http://localhost:5173"),
        help="origin sign-in accepts; this stands in for the browser",
    )
    parser.add_argument("--duration", type=float, default=10.0)
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument(
        "--path",
        action="append",
        default=list(DEFAULT_PATHS),
        help="read endpoint to request; may be repeated",
    )
    args = parser.parse_args()
    if args.duration <= 0 or args.concurrency <= 0:
        parser.error("duration and concurrency must be positive")
    print(json.dumps(asyncio.run(run(args)), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
