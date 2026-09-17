"""Run deterministic synthetic checks or export fresh-context pressure cases."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any
from evaluate_transcripts import release_case_ids


ROOT = Path(__file__).parents[2]
MANIFEST = Path(__file__).with_name("pressure-cases.json")
ACTIVATION_MANIFEST = Path(__file__).with_name("activation-cases.json")
SKILL_PATH = ROOT / "skill" / "exam-prep" / "SKILL.md"


def load_cases() -> list[dict[str, Any]]:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))["cases"]


def load_case(case_id: str) -> dict[str, Any]:
    for case in load_cases():
        if case.get("id") == case_id:
            return dict(case)
    raise ValueError(f"unknown case: {case_id}")


def load_activation_cases() -> list[dict[str, Any]]:
    return json.loads(ACTIVATION_MANIFEST.read_text(encoding="utf-8"))["cases"]


def emit_activation_set(path: Path) -> int:
    cases = load_activation_cases()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for case in cases:
            packet = {
                "case_id": case["id"],
                "system_context": (
                    "Run this prompt in a fresh host context using normal skill discovery. "
                    "Do not inject exam-prep instructions manually. Record whether the host "
                    "activated exam-prep before answering."
                ),
                "user_prompt": case["prompt"],
                "should_activate": case["should_activate"],
            }
            handle.write(json.dumps(packet, ensure_ascii=False, sort_keys=True) + "\n")
    return len(cases)


def build_prompt_packet(
    *,
    case: dict[str, Any],
    variant: str,
    repetition: int,
    skill_text: str = "",
) -> dict[str, Any]:
    if variant not in {"baseline", "skill"}:
        raise ValueError(f"unknown variant: {variant}")
    if repetition < 1:
        raise ValueError("repetition must be positive")
    case_id = case.get("id")
    if not isinstance(case_id, str) or not case_id:
        raise ValueError("case must have a non-empty id")

    system_context = (
        "You are in a fresh, isolated tutor context. Use only the learner facts "
        "and the user prompt supplied in this packet. Do not assume prior chat history."
    )
    if variant == "skill":
        system_context += "\n\nReference skill instructions:\n" + skill_text
    return {
        "case_id": case_id,
        "variant": variant,
        "repetition": repetition,
        "system_context": system_context,
        "user_prompt": case["prompt"],
        "learner_facts": list(case.get("learner_facts", [])),
        "rubric": {
            "forbidden_behavior": list(case.get("forbidden_behavior", [])),
            "pass_criteria": list(case.get("pass_criteria", [])),
        },
    }


def emit_evaluation_set(
    path: Path,
    *,
    case_ids: list[str],
    repeat: int,
    skill_text: str,
) -> int:
    if repeat < 1:
        raise ValueError("repeat must be positive")
    cases = [load_case(case_id) for case_id in case_ids]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for case in cases:
            for variant in ("baseline", "skill"):
                for repetition in range(1, repeat + 1):
                    packet = build_prompt_packet(
                        case=case,
                        variant=variant,
                        repetition=repetition,
                        skill_text=skill_text,
                    )
                    handle.write(json.dumps(packet, ensure_ascii=False, sort_keys=True) + "\n")
    return len(cases) * 2 * repeat


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--case")
    parser.add_argument("--deterministic", action="store_true")
    parser.add_argument("--emit-eval-set", type=Path)
    parser.add_argument("--emit-activation-set", type=Path)
    parser.add_argument("--repeat", type=int, default=5)
    parser.add_argument("--cases", help="comma-separated case IDs")
    parser.add_argument("--skill-file", type=Path, default=SKILL_PATH)
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
    if args.emit_eval_set:
        if args.cases:
            case_ids = [item.strip() for item in args.cases.split(",") if item.strip()]
        else:
            case_ids = list(release_case_ids())
        try:
            skill_text = args.skill_file.read_text(encoding="utf-8")
            count = emit_evaluation_set(
                args.emit_eval_set,
                case_ids=case_ids,
                repeat=args.repeat,
                skill_text=skill_text,
            )
        except (OSError, ValueError) as exc:
            parser.error(str(exc))
        print(json.dumps({"status": "evaluation_set_written", "records": count, "path": str(args.emit_eval_set)}))
        return 0
    if args.emit_activation_set:
        try:
            count = emit_activation_set(args.emit_activation_set)
        except (OSError, ValueError) as exc:
            parser.error(str(exc))
        print(json.dumps({
            "status": "activation_set_written",
            "records": count,
            "path": str(args.emit_activation_set),
        }))
        return 0
    if args.list:
        print(json.dumps([case["id"] for case in cases], ensure_ascii=False, indent=2))
        return 0
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
