#!/usr/bin/env python3

from __future__ import annotations

import argparse
from pathlib import Path
import sys
import uuid

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

load_dotenv()

from dungeon.game import run_game
from tracing.logger import TraceLogger


def main() -> None:
    parser = argparse.ArgumentParser(description="Run dungeon agent simulations.")
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--turn-limit", type=int, default=60)
    args = parser.parse_args()

    results: list[dict[str, object]] = []
    for index in range(args.runs):
        run_id = f"run_{uuid.uuid4().hex[:8]}"
        logger = TraceLogger(run_id)
        run_seed = None if args.seed is None else args.seed + index
        result = run_game(
            run_id=run_id,
            seed=run_seed,
            turn_limit=args.turn_limit,
            logger=logger,
        )
        results.append(result)

    print("\nSummary")
    print("run_id         seed        turns  result")
    for result in results:
        status = "WIN" if result["termination_reason"] == "win" else "TURN_LIMIT"
        print(
            f"{result['run_id']:<14} {result['seed']:<11} {result['turns']:<6} {status}"
        )


if __name__ == "__main__":
    main()
