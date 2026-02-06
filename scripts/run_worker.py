#!/usr/bin/env python
"""
AKASHI MAM - Celery Worker Runner

Usage:
    python scripts/run_worker.py [queue]

Examples:
    python scripts/run_worker.py          # Run all queues
    python scripts/run_worker.py proxy    # Run only proxy queue
    python scripts/run_worker.py metadata # Run only metadata queue
"""

import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.workers.celery_app import celery_app


if __name__ == "__main__":
    # Get queue from command line or run all
    queue = sys.argv[1] if len(sys.argv) > 1 else None

    worker_args = [
        "worker",
        "--loglevel=INFO",
        "--concurrency=2",
    ]

    if queue:
        worker_args.append(f"--queues={queue}")
    else:
        # All queues
        worker_args.append("--queues=default,metadata,proxy,thumbnail")

    celery_app.worker_main(worker_args)
