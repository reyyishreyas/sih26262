"""Scheduler entry point.

    python -m app.workers.scheduler --interval 60

Every tick is a full re-query: the database is the queue.
"""

from __future__ import annotations

import argparse
import time

from .deadline_jobs import retry_pending, run_once


def main() -> None:
    parser = argparse.ArgumentParser(description="SIH26262 deadline & alert worker")
    parser.add_argument("--interval", type=int, default=60, help="seconds between ticks")
    parser.add_argument("--once", action="store_true", help="run a single tick and exit")
    args = parser.parse_args()

    while True:
        sweep = run_once()
        retry = retry_pending()
        print({"sweep": sweep, "retry": retry}, flush=True)
        if args.once:
            return
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
