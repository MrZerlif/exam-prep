"""Evaluate externally produced pressure-case transcripts and explicit scores.

This module deliberately does not infer semantic success from response text. A
human or host-level evaluator supplies independent boolean scores for every
rubric item; this script only validates and aggregates those scores.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).parents[2]
MANIFEST = Path(__file__).with_name("pressure-cases.json")


class EvaluationError(ValueError):
    """The score file is incomplete or structurally invalid."""


def _cases_by_id() -> dict[str, dict[str, Any]]:
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    cases = data.get("cases", [])
    return {case["id"]: case for case in cases if isinstance(case, dict) and case.get("id")}


def _release_case_ids(cases: dict[str, dict[str, Any]]) -> tuple[str, ...]:
    case_ids = tuple(sorted(case_id for case_id, case in cases.items() if case.get("release_gate") is True))
    if not case_ids:
        raise EvaluationError("manifest must identify at least one release case")
    return case_ids


def release_case_ids() -> tuple[str, ...]:
    return _release_case_ids(_cases_by_id())

def _score_bool(value: Any, *, case_id: str, variant: str, field: str, criterion: str) -> bool:
    if not isinstance(value, bool):
        raise EvaluationError(
            f"{case_id}/{variant}: {field}[{criterion!r}] must be an explicit boolean"
        )
    return value


def _validate_records(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    cases = _cases_by_id()
    required_case_ids = set(_release_case_ids(cases))
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise EvaluationError(f"record {index} must be an object")
        case_id = record.get("case_id")
        variant = record.get("variant")
        if case_id not in cases:
            raise EvaluationError(f"record {index}: unknown case_id {case_id!r}")
        if variant not in {"baseline", "skill"}:
            raise EvaluationError(f"record {index}: variant must be baseline or skill")
        repetition = record.get("repetition")
        if not isinstance(repetition, int) or isinstance(repetition, bool) or repetition < 1:
            raise EvaluationError(f"{case_id}/{variant}: repetition must be a positive integer")
        if not isinstance(record.get("response"), str):
            raise EvaluationError(f"{case_id}/{variant}/{repetition}: response is required")
        pass_scores = record.get("pass_scores")
        forbidden_scores = record.get("forbidden_scores")
        if not isinstance(pass_scores, dict) or not isinstance(forbidden_scores, dict):
            raise EvaluationError(f"{case_id}/{variant}/{repetition}: score is missing")
        case = cases[case_id]
        for criterion in case.get("pass_criteria", []):
            if criterion not in pass_scores:
                raise EvaluationError(
                    f"{case_id}/{variant}/{repetition}: score is missing for pass criterion {criterion!r}"
                )
            _score_bool(
                pass_scores[criterion], case_id=case_id, variant=variant,
                field="pass_scores", criterion=criterion,
            )
        for criterion in case.get("forbidden_behavior", []):
            if criterion not in forbidden_scores:
                raise EvaluationError(
                    f"{case_id}/{variant}/{repetition}: score is missing for forbidden criterion {criterion!r}"
                )
            _score_bool(
                forbidden_scores[criterion], case_id=case_id, variant=variant,
                field="forbidden_scores", criterion=criterion,
            )
        grouped.setdefault((case_id, variant), []).append(record)

    if not grouped:
        raise EvaluationError("score file contains no records")
    selected_case_ids = {case_id for case_id, _variant in grouped}
    missing_required = sorted(required_case_ids - selected_case_ids)
    if missing_required:
        raise EvaluationError("missing required release cases: " + ", ".join(missing_required))
    expected_keys = {
        (case_id, variant)
        for case_id in selected_case_ids
        for variant in ("baseline", "skill")
    }
    missing_keys = sorted(expected_keys - set(grouped))
    if missing_keys:
        raise EvaluationError("missing score runs for " + ", ".join(f"{case}/{variant}" for case, variant in missing_keys))
    for case_id, variant in sorted(expected_keys):
        items = grouped[(case_id, variant)]
        repetitions = [item["repetition"] for item in items]
        if len(items) < 5 or len(set(repetitions)) != len(repetitions):
            raise EvaluationError(
                f"{case_id}/{variant}: at least five distinct runs are required"
            )
    return [item for items in grouped.values() for item in items]


def summarize_scores(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Return a compact case/variant summary and release-gate decision."""
    records = _validate_records(records)
    cases = _cases_by_id()
    release_case_id_set = set(_release_case_ids(cases))
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for record in records:
        grouped.setdefault((record["case_id"], record["variant"]), []).append(record)

    selected_case_ids = sorted({record["case_id"] for record in records})
    summary: dict[str, Any] = {
        "status": "pass",
        "release_ready": True,
        "cases": {},
        "failures": [],
    }
    for case_id in selected_case_ids:
        case_summary: dict[str, Any] = {}
        for variant in ("baseline", "skill"):
            items = sorted(grouped[(case_id, variant)], key=lambda item: item["repetition"])
            criteria = list(cases[case_id].get("pass_criteria", []))
            total = len(items) * len(criteria)
            passed = sum(
                bool(item["pass_scores"][criterion])
                for item in items
                for criterion in criteria
            )
            forbidden_violations = sum(
                sum(bool(item["forbidden_scores"][criterion]) for criterion in cases[case_id].get("forbidden_behavior", []))
                for item in items
            )
            pass_rate = (passed / total) if total else 1.0
            failures: list[str] = []
            if forbidden_violations:
                failures.append("forbidden behavior was independently scored")
            if pass_rate < 0.9:
                failures.append("required criteria pass rate is below 90%")
            case_summary[variant] = {
                "runs": len(items),
                "required_criteria": len(criteria),
                "passed_criteria": passed,
                "pass_rate": round(pass_rate, 4),
                "forbidden_violations": forbidden_violations,
                "status": "pass" if not failures else "fail",
                "failures": failures,
            }

        baseline = case_summary["baseline"]["pass_rate"]
        skill = case_summary["skill"]["pass_rate"]
        if skill < baseline:
            case_summary["skill"]["status"] = "fail"
            case_summary["skill"]["failures"].append("skill pass rate is worse than baseline")
        case_summary["release_ready"] = case_summary["skill"]["status"] == "pass"
        if case_id in release_case_id_set and not case_summary["release_ready"]:
            summary["release_ready"] = False
            for reason in case_summary["skill"]["failures"]:
                summary["failures"].append(f"{case_id}/skill: {reason}")
        summary["cases"][case_id] = case_summary

    if not summary["release_ready"]:
        summary["status"] = "fail"
    return summary


def load_records(path: Path) -> list[dict[str, Any]]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise EvaluationError(f"cannot read score file: {exc}") from exc
    try:
        decoded = json.loads(text) if text.lstrip().startswith("[") else [json.loads(line) for line in text.splitlines() if line.strip()]
    except json.JSONDecodeError as exc:
        raise EvaluationError(f"score file is not valid JSONL/JSON: {exc}") from exc
    if not isinstance(decoded, list):
        raise EvaluationError("score file must contain a JSON array or JSONL records")
    return decoded


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("score_file", nargs="?", type=Path)
    parser.add_argument("--input", dest="input_file", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    path = args.input_file or args.score_file
    if path is None:
        parser.error("a score JSONL file is required")
    try:
        summary = summarize_scores(load_records(path))
    except EvaluationError as exc:
        print(json.dumps({"status": "evaluation_error", "release_ready": False, "error": str(exc)}))
        return 1
    output = json.dumps(summary, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output + "\n", encoding="utf-8")
    print(output)
    return 0 if summary["release_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
