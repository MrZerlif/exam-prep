"""Run deterministic synthetic checks or print fresh-context pressure cases."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).parents[2]
MANIFEST = Path(__file__).with_name("pressure-cases.json")


def load_cases() -> list[dict]:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))["cases"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--case")
    parser.add_argument("--deterministic", action="store_true")
    args = parser.parse_args(argv)
    if args.deterministic:
        completed = subprocess.run(
            [sys.executable, "-m", "unittest", "tests.test_synthetic_scenarios", "-v"],
            cwd=ROOT,
            check=False,
        )
        return completed.returncode
    cases = load_cases()
    if args.case:
        selected = next((case for case in cases if case["id"] == args.case), None)
        if selected is None:
            parser.error(f"unknown case: {args.case}")
        print(json.dumps(selected, ensure_ascii=False, indent=2))
        return 0
    if args.list:
        print(json.dumps([case["id"] for case in cases], ensure_ascii=False, indent=2))
        return 0
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
