"""Deterministic extraction of homework and exam questions from pages."""

# Portions adapted from ZeKaiNie/universal-examprep-skill (MIT), see vendor/exam-cram-coach/LICENSE

from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
from pathlib import Path
import re
from typing import Iterable, Sequence

from exam_prep_lib.ingest_issues import IngestIssue
from exam_prep_lib.defaults import (
    EXTRACTION_ACCEPTED_FRACTION_BLOCKING,
    EXTRACTION_HARD_QUESTION_CAP,
    EXTRACTION_LECTURE_QUESTIONS_PER_PAGE_BLOCKING,
    EXTRACTION_QUESTIONS_PER_PAGE_GAP,
    VERB_SLOT_TO_QTYPE,
)
from exam_prep_lib.lexicon import load
from exam_prep_lib.semantics import best_slot
from exam_prep_lib.text_normalize import canonical_key

from .chapters import number_from_name
from .extractor import ExtractedPage, ExtractedSource

QUESTION_RE = re.compile(r"^\s*(?:№\s*)?([0-9]+(?:[.\-][0-9A-Za-z]+)*)?\s*[.:)]?\s*(.*)$", re.IGNORECASE)
SOLUTION_RE = re.compile(r"^\s*(?:№\s*)?([0-9]+(?:[.\-][0-9A-Za-z]+)*)?\s*[.:)]?\s*(.*)$", re.IGNORECASE)
POINTS_RE = re.compile(r"\(\s*\d+\s*[^)]*\)", re.IGNORECASE)
OPTION_RE = re.compile(r"^\s*([A-DА-Г])\s*[).:-]\s*(.+)$", re.IGNORECASE)
EXTRACTABLE_KINDS = frozenset({"exam", "homework"})
OPT_IN_KINDS = frozenset({"other", "lecture", "notes"})


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


def _solution_file_key(path: str, language: str = "ru") -> str:
    stem = canonical_key(Path(path).stem)
    for entry in load(language).by_slot["kind.solution"]:
        for separator in ("_", "-", " "):
            suffix = f"{separator}{entry.canonical}"
            if stem.endswith(suffix):
                return stem[: -len(suffix)]
    return stem


def _marker(line: str, *, solution: bool, language: str) -> tuple[str | None, str] | None:
    stripped = line.strip()
    if not stripped:
        return None
    first = stripped.split(maxsplit=1)[0].strip("#.,:;()[]{}")
    if stripped.startswith("№"):
        if solution:
            return None
        rest = stripped[1:].lstrip()
    else:
        found = best_slot("kind.", first, load(language))
        if found is None:
            return None
        if solution and found.slot != "kind.solution":
            return None
        if not solution and found.slot not in {"kind.homework", "kind.exam"}:
            return None
        rest = stripped[len(stripped.split(maxsplit=1)[0]):].lstrip()
    parsed = QUESTION_RE.match(rest)
    if not parsed:
        return None
    label, payload = parsed.groups()
    return label, payload


def _blocks(text: str, *, solution: bool = False, language: str = "ru") -> list[tuple[str | None, str]]:
    blocks: list[tuple[str | None, list[str]]] = []
    current: tuple[str | None, list[str]] | None = None
    for raw_line in text.splitlines():
        match = _marker(raw_line, solution=solution, language=language)
        if match:
            if current is not None:
                blocks.append((current[0], "\n".join(current[1]).strip()))
            label, rest = match
            current = (label, [rest] if rest else [])
        elif current is not None:
            current[1].append(raw_line)
    if current is not None:
        blocks.append((current[0], "\n".join(current[1]).strip()))
    return blocks


def _blocks_with(text: str, marker: re.Pattern[str], language: str = "ru") -> list[tuple[str | None, str]]:
    return _blocks(text, solution=marker is SOLUTION_RE, language=language)


def heads(text: str, language: str = "ru") -> list[str]:
    return [line.strip() for line in text.splitlines() if _marker(line, solution=False, language=language)]


def _split_answer(text: str, language: str = "ru") -> tuple[str, str | None]:
    offset = 0
    for line in text.splitlines(keepends=True):
        if _marker(line, solution=True, language=language):
            payload = _marker(line, solution=True, language=language)[1]
            tail = text[offset + len(line):]
            answer = "\n".join(part for part in (payload, tail) if part).strip() or None
            return text[:offset].strip(), answer
        offset += len(line)
    return text.strip(), None


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


def _extract_points(prompt: str, language: str = "ru") -> tuple[str, int | None]:
    lexicon = load(language)
    for candidate in POINTS_RE.finditer(prompt):
        if best_slot("unit.points", candidate.group(0), lexicon) is None:
            continue
        value = re.search(r"\d+", candidate.group(0))
        if value is None:
            continue
        cleaned = f"{prompt[:candidate.start()]}{prompt[candidate.end():]}"
        return cleaned.strip(), int(value.group(0))
    return prompt, None


def _qtype(prompt: str, language: str = "ru") -> str:
    found = best_slot("verb.", prompt, load(language))
    return VERB_SLOT_TO_QTYPE.get(found.slot, "problem") if found else "problem"


def _chapter_hint(label: str | None, source_path: str, prompt: str, language: str = "ru") -> int | None:
    if label and label.split(".")[0].isdigit():
        return int(label.split(".")[0])
    return number_from_name(source_path, language) or number_from_name(prompt, language)


def _match_solution(label: str | None, solutions: dict[str | None, str]) -> str | None:
    return solutions.get(pair_key(label))


def source_question_issues(source: ExtractedSource, language: str = "ru") -> tuple[IngestIssue, ...]:
    blocks = [block for page in source.pages for block in _blocks(page.text, language=language)]
    question_count = len(blocks)
    nonempty_lines = sum(1 for page in source.pages for line in page.text.splitlines() if line.strip())
    page_count = max(1, len(source.pages))
    questions_per_page = question_count / page_count
    accepted_fraction = question_count / max(1, nonempty_lines)
    blocking = (
        accepted_fraction > EXTRACTION_ACCEPTED_FRACTION_BLOCKING
        or (source.kind in {"lecture", "notes"} and questions_per_page > EXTRACTION_LECTURE_QUESTIONS_PER_PAGE_BLOCKING)
        or question_count > EXTRACTION_HARD_QUESTION_CAP
    )
    anomaly = questions_per_page > EXTRACTION_QUESTIONS_PER_PAGE_GAP
    issues: list[IngestIssue] = []
    if blocking or anomaly:
        severity = "blocking" if blocking else "gap"
        issues.append(
            IngestIssue(
                "extraction_anomaly",
                source.relative_path,
                f"{question_count} question blocks across {page_count} page(s); accepted_fraction={accepted_fraction:.3f}",
                severity,
            )
        )
    if source.kind in EXTRACTABLE_KINDS and question_count == 0:
        issues.append(
            IngestIssue(
                "no_questions_extracted",
                source.relative_path,
                f"no question blocks extracted from {source.kind} source",
                "gap",
            )
        )
    if source.kind == "other":
        issues.append(
            IngestIssue(
                "unclassified_source",
                source.relative_path,
                "source kind is other; use --include-unclassified to opt in",
                "gap",
            )
        )
    return tuple(issues)


def extract_questions(
    sources: Iterable[ExtractedSource],
    *,
    include_unclassified: bool = False,
    language: str = "ru",
) -> tuple[ExtractedQuestion, ...]:
    materialized = tuple(sources)
    solutions_by_file: dict[str, dict[str | None, str]] = {}
    for source in materialized:
        if source.kind != "solution":
            continue
        solutions = solutions_by_file.setdefault(_solution_file_key(source.relative_path), {})
        for page in source.pages:
            for label, answer in _blocks(page.text, solution=True, language=language):
                solutions[pair_key(label)] = _strip_shared_lines(answer)

    result: list[ExtractedQuestion] = []
    for source in materialized:
        if source.kind == "solution":
            continue
        if source.kind not in EXTRACTABLE_KINDS and not (include_unclassified and source.kind == "other"):
            continue
        kind = "exam" if source.kind == "exam" else "homework"
        solutions = solutions_by_file.get(_solution_file_key(source.relative_path, language), {})
        source_issues = tuple(source.issues) + source_question_issues(source, language)
        for page in source.pages:
            for label, raw_prompt in _blocks(page.text, language=language):
                prompt = _strip_shared_lines(raw_prompt)
                prompt, points = _extract_points(prompt, language)
                options, prompt = _options(prompt)
                prompt, embedded_answer = _split_answer(prompt, language)
                answer = _match_solution(label, solutions) or embedded_answer
                normalized = " ".join(prompt.split())
                question_id = hashlib.sha256((source.relative_path + (label or "") + normalized).encode("utf-8")).hexdigest()[:16]
                source_id = f"{source.relative_path}#p{page.number}"
                issues = list(source_issues)
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
                        chapter_hint=_chapter_hint(label, source.relative_path, prompt, language),
                        source_ref={"source_id": source_id, "locator": f"{source.relative_path} p.{page.number}"},
                        issues=tuple(issues),
                    )
                )
    return tuple(result)


def assign_chapters(questions: Sequence[ExtractedQuestion], sources: Iterable[ExtractedSource] = (), language: str = "ru") -> tuple[ExtractedQuestion, ...]:
    by_source = {
        source.relative_path: number_from_name(source.relative_path, language)
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
