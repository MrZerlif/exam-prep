"""Deterministic extraction of homework and exam questions from pages."""

# Portions adapted from ZeKaiNie/universal-examprep-skill (MIT), see vendor/exam-cram-coach/LICENSE

from __future__ import annotations

from dataclasses import dataclass, field, replace
import hashlib
from pathlib import Path
import re
from typing import Iterable, Mapping, Sequence

from exam_prep_lib.ingest_issues import IngestIssue
from exam_prep_lib.defaults import (
    EXTRACTION_ACCEPTED_FRACTION_BLOCKING,
    EXTRACTION_HARD_QUESTION_CAP,
    EXTRACTION_LECTURE_QUESTIONS_PER_PAGE_BLOCKING,
    EXTRACTION_QUESTIONS_PER_PAGE_GAP,
    VERB_SLOT_TO_QTYPE,
)
from exam_prep_lib.lexicon import Lexicon, load
from exam_prep_lib.semantics import best_slot
from exam_prep_lib.text_normalize import canonical_key

from .chapters import number_from_name
from .candidates import score
from .extractor import ExtractedPage, ExtractedSource
from .labels import option_run, segment
from .points import extract as extract_points, infer_token, verify_total

QUESTION_RE = re.compile(r"^\s*(?:№\s*)?([0-9]+(?:[.\-][0-9A-Za-z]+)*)?\s*[.:)]?\s*(.*)$", re.IGNORECASE)
SOLUTION_RE = re.compile(r"^\s*(?:№\s*)?([0-9]+(?:[.\-][0-9A-Za-z]+)*)?\s*[.:)]?\s*(.*)$", re.IGNORECASE)
POINTS_RE = re.compile(r"\(\s*\d+\s*[^)]*\)", re.IGNORECASE)
OPTION_LINE_RE = re.compile(r"^\s*(?P<label>[^\W\d_]{1,3}|\d{1,2})\s*[).:：-]\s*(?P<body>.+)$", re.UNICODE)
EXTRACTABLE_KINDS = frozenset({"exam", "homework"})
OPT_IN_KINDS = frozenset({"other", "lecture", "notes"})
# A file with no prose is a parser failure only where prose was expected. In a
# problem set one line per task is the normal layout, not a symptom.
PROSE_EXPECTED_KINDS = frozenset({"lecture", "notes", "other"})


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
    signals: dict[str, float] = field(default_factory=dict)

    @property
    def expected_evidence(self) -> list[str]:
        return [self.reference_answer] if self.reference_answer else []


def pair_key(label: str | None) -> str | None:
    return label.casefold() if label else None


def _solution_file_key(path: str, language: str = "ru", *, lexicon: Lexicon | None = None) -> str:
    stem = canonical_key(Path(path).stem)
    for entry in (lexicon or load(language)).by_slot["kind.solution"]:
        for separator in ("_", "-", " "):
            suffix = f"{separator}{entry.canonical}"
            if stem.endswith(suffix):
                return stem[: -len(suffix)]
    return stem


def _marker(line: str, *, solution: bool, language: str, lexicon: Lexicon | None = None) -> tuple[str | None, str] | None:
    stripped = line.strip()
    if not stripped:
        return None
    raw_first = stripped.split(maxsplit=1)[0]
    first = raw_first.strip("#.,:;()[]{}")
    if stripped.startswith("№"):
        if solution:
            return None
        rest = stripped[1:].lstrip()
    else:
        found = best_slot("kind.", first, lexicon or load(language))
        if found is None:
            return None
        if solution and found.slot != "kind.solution":
            return None
        if not solution and found.slot not in {"kind.homework", "kind.exam"}:
            return None
        prefix_length = len(raw_first)
        if raw_first.casefold().startswith(found.token.casefold()) and raw_first[len(found.token):].isdigit():
            prefix_length = len(found.token)
        rest = stripped[prefix_length:].lstrip()
    parsed = QUESTION_RE.match(rest)
    if not parsed:
        return None
    label, payload = parsed.groups()
    return label, payload


def _blocks(
    text: str,
    *,
    solution: bool = False,
    language: str = "ru",
    lexicon: Lexicon | None = None,
) -> list[tuple[str | None, str]]:
    blocks: list[tuple[str | None, list[str]]] = []
    current: tuple[str | None, list[str]] | None = None
    for raw_line in text.splitlines():
        match = _marker(raw_line, solution=solution, language=language, lexicon=lexicon)
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


def _blocks_with(text: str, marker: re.Pattern[str], language: str = "ru", *, lexicon: Lexicon | None = None) -> list[tuple[str | None, str]]:
    return _blocks(text, solution=marker is SOLUTION_RE, language=language, lexicon=lexicon)


def heads(text: str, language: str = "ru", *, lexicon: Lexicon | None = None) -> list[str]:
    return [line.strip() for line in text.splitlines() if _marker(line, solution=False, language=language, lexicon=lexicon)]


def _split_answer(text: str, language: str = "ru", *, lexicon: Lexicon | None = None) -> tuple[str, str | None]:
    offset = 0
    for line in text.splitlines(keepends=True):
        if _marker(line, solution=True, language=language, lexicon=lexicon):
            payload = _marker(line, solution=True, language=language, lexicon=lexicon)[1]
            tail = text[offset + len(line):]
            answer = "\n".join(part for part in (payload, tail) if part).strip() or None
            return text[:offset].strip(), answer
        offset += len(line)
    return text.strip(), None


def _strip_shared_lines(value: str) -> str:
    return "\n".join(line.rstrip() for line in value.splitlines()).strip()


def _options(prompt: str) -> tuple[tuple[str, ...], str]:
    labels = option_run(prompt)
    if not labels:
        return (), prompt
    label_keys = {label.casefold() for label in labels}
    options: list[str] = []
    kept: list[str] = []
    for line in prompt.splitlines():
        found = OPTION_LINE_RE.match(line)
        if found and found.group("label").casefold() in label_keys:
            options.append(found.group("body").strip())
        else:
            kept.append(line)
    return tuple(options), "\n".join(kept).strip()


def _extract_points(prompt: str, language: str = "ru", token: str | None = None, *, lexicon: Lexicon | None = None) -> tuple[str, int | None]:
    lexicon = lexicon or load(language)
    for candidate in POINTS_RE.finditer(prompt):
        if extract_points(candidate.group(0), token=token, lexicon=lexicon) is None:
            continue
        value = re.search(r"\d+", candidate.group(0))
        if value is None:
            continue
        cleaned = f"{prompt[:candidate.start()]}{prompt[candidate.end():]}"
        return cleaned.strip(), int(value.group(0))
    return prompt, None


def _qtype(prompt: str, language: str = "ru", *, lexicon: Lexicon | None = None) -> str:
    found = best_slot("verb.", prompt, lexicon or load(language))
    return VERB_SLOT_TO_QTYPE.get(found.slot, "problem") if found else "problem"


def _chapter_hint(label: str | None, source_path: str, prompt: str, language: str = "ru", *, lexicon: Lexicon | None = None) -> int | None:
    if label and label.split(".")[0].isdigit():
        return int(label.split(".")[0])
    return number_from_name(source_path, language, lexicon=lexicon) or number_from_name(prompt, language, lexicon=lexicon)


def _match_solution(label: str | None, solutions: dict[str | None, str]) -> str | None:
    return solutions.get(pair_key(label))


def source_question_issues(source: ExtractedSource, language: str = "ru", *, lexicon: Lexicon | None = None) -> tuple[IngestIssue, ...]:
    semantic_lexicon = lexicon or load(language)
    blocks = [candidate for page in source.pages for candidate in score(segment(page.text), source=source, lexicon=semantic_lexicon)]
    question_count = len(blocks)
    segments_total = sum(len(segment(page.text)) for page in source.pages)
    page_count = max(1, len(source.pages))
    questions_per_page = question_count / page_count
    accepted_fraction = question_count / max(1, segments_total)
    blocking = (
        (
            source.kind in PROSE_EXPECTED_KINDS
            and accepted_fraction > EXTRACTION_ACCEPTED_FRACTION_BLOCKING
        )
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
    extraction_mode: str = "scored",
    expected_total_points: float | int | None = 100,
    lexicon: Lexicon | None = None,
    lexicon_by_source: Mapping[str, Lexicon] | None = None,
) -> tuple[ExtractedQuestion, ...]:
    if extraction_mode not in {"legacy", "scored"}:
        raise ValueError("extraction_mode must be legacy or scored")
    materialized = tuple(sources)
    semantic_lexicon = lexicon or load(language)
    solutions_by_file: dict[tuple[str, str], dict[str | None, str]] = {}

    def source_lexicon(source: ExtractedSource) -> Lexicon:
        return (lexicon_by_source or {}).get(source.relative_path, semantic_lexicon)

    def solution_key(source: ExtractedSource, source_semantics: Lexicon) -> tuple[str, str]:
        return (
            source_semantics.language,
            _solution_file_key(
                source.relative_path,
                source_semantics.language,
                lexicon=source_semantics,
            ),
        )

    for source in materialized:
        if source.kind != "solution":
            continue
        source_semantics = source_lexicon(source)
        solutions = solutions_by_file.setdefault(solution_key(source, source_semantics), {})
        for page in source.pages:
            for label, answer in _blocks(
                page.text,
                solution=True,
                language=source_semantics.language,
                lexicon=source_semantics,
            ):
                solutions[pair_key(label)] = _strip_shared_lines(answer)

    result: list[ExtractedQuestion] = []
    for source in materialized:
        if source.kind == "solution":
            continue
        if source.kind not in EXTRACTABLE_KINDS and not (include_unclassified and source.kind == "other"):
            continue
        source_semantics = source_lexicon(source)
        kind = "exam" if source.kind == "exam" else "homework"
        solutions = solutions_by_file.get(solution_key(source, source_semantics), {})
        point_token = infer_token(source.pages, lexicon=source_semantics)
        candidate_pages = {
            page.number: score(
                segment(page.text),
                source=source,
                lexicon=source_semantics,
                solutions_by_file=solutions,
                points_token=point_token,
            )
            for page in source.pages
        }
        point_values = [
            extract_points(candidate.segment.body, token=point_token, lexicon=source_semantics)
            for candidates in candidate_pages.values()
            for candidate in candidates
            if candidate.bucket in {"accept", "review"}
        ]
        points_verified = verify_total(point_values, expected_total_points) if point_values else None
        points_weight = 0.5 if points_verified is False else 1.0
        if points_weight != 1.0:
            candidate_pages = {
                    page.number: score(
                        segment(page.text),
                        source=source,
                        lexicon=source_semantics,
                    solutions_by_file=solutions,
                    points_token=point_token,
                    points_weight=points_weight,
                )
                for page in source.pages
            }
        source_issues = list(
            tuple(source.issues)
            + source_question_issues(source, source_semantics.language, lexicon=source_semantics)
        )
        if points_verified is False:
            source_issues.append(IngestIssue("low_confidence_question", source.relative_path, "inferred point total does not match expected_total_points", "info"))
        for page in source.pages:
            if extraction_mode == "legacy":
                candidate_blocks = tuple(
                    (label, raw_prompt, None)
                    for label, raw_prompt in _blocks(
                        page.text,
                        language=source_semantics.language,
                        lexicon=source_semantics,
                    )
                )
            else:
                candidate_blocks = tuple(
                    (candidate.segment.label.raw, candidate.segment.body, candidate)
                    for candidate in candidate_pages.get(page.number, ())
                    if candidate.bucket in {"accept", "review"}
                )
            for label, raw_prompt, candidate in candidate_blocks:
                prompt = _strip_shared_lines(raw_prompt)
                prompt, points = _extract_points(
                    prompt,
                    source_semantics.language,
                    point_token,
                    lexicon=source_semantics,
                )
                options, prompt = _options(prompt)
                prompt, embedded_answer = _split_answer(
                    prompt,
                    source_semantics.language,
                    lexicon=source_semantics,
                )
                answer = _match_solution(label, solutions) or embedded_answer
                normalized = " ".join(prompt.split())
                question_id = hashlib.sha256((source.relative_path + (label or "") + normalized).encode("utf-8")).hexdigest()[:16]
                source_id = f"{source.relative_path}#p{page.number}"
                issues = list(source_issues)
                if candidate is not None and candidate.bucket == "review":
                    issues.append(IngestIssue("low_confidence_question", source_id, f"candidate score={candidate.score:.4f}", "info"))
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
                        chapter_hint=_chapter_hint(
                            label,
                            source.relative_path,
                            prompt,
                            source_semantics.language,
                            lexicon=source_semantics,
                        ),
                        source_ref={"source_id": source_id, "locator": f"{source.relative_path} p.{page.number}"},
                        issues=tuple(issues),
                        signals=dict(candidate.signals) if candidate is not None else {},
                    )
                )
    return tuple(result)


def assign_chapters(questions: Sequence[ExtractedQuestion], sources: Iterable[ExtractedSource] = (), language: str = "ru", *, lexicon: Lexicon | None = None) -> tuple[ExtractedQuestion, ...]:
    by_source = {
        source.relative_path: number_from_name(source.relative_path, language, lexicon=lexicon)
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
