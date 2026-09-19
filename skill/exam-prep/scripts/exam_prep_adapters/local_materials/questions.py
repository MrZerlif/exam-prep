"""Deterministic extraction of homework and exam questions from pages."""

# Portions adapted from ZeKaiNie/universal-examprep-skill (MIT), see vendor/exam-cram-coach/LICENSE

from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
from pathlib import Path
import re
from typing import Iterable, Sequence

from exam_prep_lib.ingest_issues import IngestIssue

from .chapters import number_from_name
from .extractor import ExtractedPage, ExtractedSource

QUESTION_RE = re.compile(r"^\s*(?:задача|упражнение|пример|вопрос|билет|вариант|question|exercise|problem|№)\s*([0-9]+(?:[.\-][0-9A-Za-z]+)*)?\s*[.:)]?\s*(.*)$", re.IGNORECASE)
SOLUTION_RE = re.compile(r"^\s*(?:решение|ответ|отв\.?|указание|доказательство|solution|answer|key)\s*([0-9]+(?:[.\-][0-9A-Za-z]+)*)?\s*[.:)]?\s*(.*)$", re.IGNORECASE)
POINTS_RE = re.compile(r"\(\s*(\d+)\s*балл\w*\s*\)|\(\s*(\d+)\s*points?\s*\)", re.IGNORECASE)
OPTION_RE = re.compile(r"^\s*([A-DА-Г])\s*[).:-]\s*(.+)$", re.IGNORECASE)


@dataclass(frozen=True)
class ExtractedQuestion:
    question_id: str
    label: str | None
    prompt: str
    reference_answer: str | None
    kind: str
    options: tuple[str, ...]
    points: int | None
    chapter_hint: int | None
    source_ref: dict
    prompt_assets: tuple[str, ...] = ()
    answer_assets: tuple[str, ...] = ()
    issues: tuple[IngestIssue, ...] = ()

    @property
    def expected_evidence(self) -> list[str]:
        return [self.reference_answer] if self.reference_answer else []


def pair_key(label: str | None) -> str | None:
    return label.casefold() if label else None


def _solution_file_key(path: str) -> str:
    stem = Path(path).stem.casefold()
    return re.sub(
        r"(?:_|-| )(?:resheniya|reshenie|solutions?|answers?|otvety|ответы|решения|решение|key)$",
        "",
        stem,
    )


def _blocks(text: str, *, solution: bool = False) -> list[tuple[str | None, str]]:
    pattern = SOLUTION_RE if solution else QUESTION_RE
    blocks: list[tuple[str | None, list[str]]] = []
    current: tuple[str | None, list[str]] | None = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        match = pattern.match(line)
        if match:
            if current is not None:
                blocks.append((current[0], "\n".join(current[1]).strip()))
            label, rest = match.groups()
            current = (label, [rest] if rest else [])
        elif current is not None:
            current[1].append(raw_line)
    if current is not None:
        blocks.append((current[0], "\n".join(current[1]).strip()))
    return blocks


def _blocks_with(text: str, marker: re.Pattern[str]) -> list[tuple[str | None, str]]:
    return _blocks(text, solution=marker is SOLUTION_RE)


def heads(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if QUESTION_RE.match(line.strip())]


def _split_answer(text: str) -> tuple[str, str | None]:
    match = re.search(r"(?:^|\n)\s*(?:решение|ответ|solution|answer)\s*:?\s*", text, re.IGNORECASE)
    if not match:
        return text.strip(), None
    return text[: match.start()].strip(), text[match.end() :].strip() or None


def _strip_shared_lines(value: str) -> str:
    return "\n".join(line.rstrip() for line in value.splitlines()).strip()


def _options(prompt: str) -> tuple[tuple[str, ...], str]:
    options: list[str] = []
    kept: list[str] = []
    for line in prompt.splitlines():
        match = OPTION_RE.match(line)
        if match:
            options.append(match.group(2).strip())
        else:
            kept.append(line)
    return tuple(options), "\n".join(kept).strip()


def _qtype(prompt: str) -> str:
    if "определ" in prompt.casefold() or "define" in prompt.casefold():
        return "definition"
    if "докаж" in prompt.casefold() or "prove" in prompt.casefold():
        return "proof"
    if "вычисл" in prompt.casefold() or "compute" in prompt.casefold() or "calculate" in prompt.casefold():
        return "calculation"
    return "problem"


def _chapter_hint(label: str | None, source_path: str, prompt: str) -> int | None:
    if label and label.split(".")[0].isdigit():
        return int(label.split(".")[0])
    return number_from_name(source_path) or number_from_name(prompt)


def _match_solution(label: str | None, solutions: dict[str | None, str]) -> str | None:
    return solutions.get(pair_key(label))


def extract_questions(sources: Iterable[ExtractedSource]) -> tuple[ExtractedQuestion, ...]:
    materialized = tuple(sources)
    solutions_by_file: dict[str, dict[str | None, str]] = {}
    for source in materialized:
        if source.kind != "solution":
            continue
        solutions = solutions_by_file.setdefault(_solution_file_key(source.relative_path), {})
        for page in source.pages:
            for label, answer in _blocks(page.text, solution=True):
                solutions[pair_key(label)] = _strip_shared_lines(answer)

    result: list[ExtractedQuestion] = []
    for source in materialized:
        if source.kind == "solution":
            continue
        kind = "exam" if source.kind == "exam" else "homework"
        solutions = solutions_by_file.get(_solution_file_key(source.relative_path), {})
        for page in source.pages:
            for label, raw_prompt in _blocks(page.text):
                prompt = _strip_shared_lines(raw_prompt)
                points_match = POINTS_RE.search(prompt)
                points = int(next(group for group in points_match.groups() if group)) if points_match else None
                if points_match:
                    prompt = POINTS_RE.sub("", prompt).strip()
                options, prompt = _options(prompt)
                prompt, embedded_answer = _split_answer(prompt)
                answer = _match_solution(label, solutions) or embedded_answer
                normalized = " ".join(prompt.split())
                question_id = hashlib.sha256((source.relative_path + (label or "") + normalized).encode("utf-8")).hexdigest()[:16]
                source_id = f"{source.relative_path}#p{page.number}"
                issues = list(source.issues)
                if not answer:
                    issues.append(IngestIssue("missing_answer", source_id, "no matching reference answer", "gap"))
                result.append(
                    ExtractedQuestion(
                        question_id=question_id,
                        label=label,
                        prompt=prompt,
                        reference_answer=answer,
                        kind=kind,
                        options=options,
                        points=points,
                        chapter_hint=_chapter_hint(label, source.relative_path, prompt),
                        source_ref={"source_id": source_id, "locator": f"{source.relative_path} p.{page.number}"},
                        issues=tuple(issues),
                    )
                )
    return tuple(result)


def assign_chapters(questions: Sequence[ExtractedQuestion], sources: Iterable[ExtractedSource] = ()) -> tuple[ExtractedQuestion, ...]:
    by_source = {
        source.relative_path: number_from_name(source.relative_path)
        for source in sources
    }
    result: list[ExtractedQuestion] = []
    for question in questions:
        if question.chapter_hint is not None:
            result.append(question)
            continue
        source_id = str(question.source_ref.get("source_id", ""))
        source_path = source_id.split("#", 1)[0]
        chapter = by_source.get(source_path)
        result.append(replace(question, chapter_hint=chapter))
    return tuple(result)
