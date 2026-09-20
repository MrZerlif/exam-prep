"""Language-independent structural labels used by candidate scoring."""

from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class Label:
    raw: str
    kind: str
    parts: tuple[int, ...]


@dataclass(frozen=True)
class Segment:
    label: Label | None
    body: str
    line_no: int
    indent: int


SEQUENCES = {
    "latin": "ABCDEFGH",
    "cyrillic": "АБВГДЕЖЗ",
    "greek": "ΑΒΓΔΕΖΗΘ",
    "roman": ("I", "II", "III", "IV", "V", "VI", "VII", "VIII"),
    "arabic": "12345678",
    "katakana": "アイウエオカキク",
}


_ARABIC_RE = re.compile(
    r"^(?P<indent>\s*)(?:[^\W\d_]+|№)?\s*"
    r"[\[(]?(?P<label>\d+(?:[.-]\d+)*)(?:\s*[\]).:])?\s*(?P<body>.*)$",
    re.UNICODE,
)
_ROMAN_RE = re.compile(
    r"^(?P<indent>\s*)(?:[^\W\d_]+\s+)?[\[(]?(?P<label>I{1,3}|IV|V?I{0,3}|IX|X{1,3}|XL|L?X{0,3}|XC|C{1,3}|CD|D?C{0,3}|CM|M{1,3})[\]).:]+\s*(?P<body>.*)$",
    re.IGNORECASE | re.UNICODE,
)
_LETTER_RE = re.compile(
    r"^(?P<indent>\s*)(?P<label>[A-ZА-Я])\s*[).:-]\s*(?P<body>.*)$",
    re.IGNORECASE | re.UNICODE,
)
_CJK_RE = re.compile(
    r"^(?P<indent>\s*)(?P<label>[一二三四五六七八九十百千]+)\s*[、.)：:]\s*(?P<body>.*)$",
    re.UNICODE,
)
_ROMAN_VALUES = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
_CJK_DIGITS = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
_OPTION_RE = re.compile(r"^(?P<indent>\s*)(?P<label>[^\W\d_]{1,3}|\d{1,2})\s*(?P<separator>[).:：-])\s*.+$", re.UNICODE)


def _roman(value: str) -> int:
    total = 0
    previous = 0
    for char in reversed(value.upper()):
        current = _ROMAN_VALUES[char]
        if current < previous:
            total -= current
        else:
            total += current
            previous = current
    return total


def _cjk(value: str) -> int:
    if value == "十":
        return 10
    if "十" in value:
        left, _, right = value.partition("十")
        return (_CJK_DIGITS.get(left, 1) * 10) + _CJK_DIGITS.get(right, 0)
    return _CJK_DIGITS[value]


def _label_match(line: str) -> tuple[Label, str, int] | None:
    for pattern, kind in ((_ARABIC_RE, "arabic"), (_ROMAN_RE, "roman"), (_LETTER_RE, "letter"), (_CJK_RE, "cjk")):
        found = pattern.match(line)
        if not found:
            continue
        raw = found.group("label")
        if kind == "arabic":
            parts = tuple(int(part) for part in re.split(r"[.-]", raw))
        elif kind == "roman":
            parts = (_roman(raw),)
        elif kind == "letter":
            parts = (ord(raw.upper()) - ord("A") + 1,)
        else:
            parts = (_cjk(raw),)
        indent = len(found.group("indent").expandtabs(4))
        return Label(raw, kind, parts), found.group("body"), indent
    return None


def segment(text: str) -> tuple[Segment, ...]:
    """Split text at structural labels without consulting a language lexicon."""

    result: list[Segment] = []
    current_label: Label | None = None
    current_body: list[str] = []
    current_line = 1
    current_indent = 0
    for line_no, raw_line in enumerate(text.splitlines(), 1):
        parsed = _label_match(raw_line)
        if parsed is not None and parsed[0].kind == "letter" and current_label is not None and current_label.kind != "letter":
            current_body.append(raw_line)
            continue
        if parsed is not None:
            if current_label is not None or current_body:
                result.append(Segment(current_label, "\n".join(current_body).strip(), current_line, current_indent))
            current_label, first_body, current_indent = parsed
            current_body = [first_body] if first_body else []
            current_line = line_no
        else:
            current_body.append(raw_line)
    if current_label is not None or current_body:
        result.append(Segment(current_label, "\n".join(current_body).strip(), current_line, current_indent))
    return tuple(result)


def _sequence_kind(labels: tuple[str, ...]) -> str | None:
    normalized = tuple(label.upper() for label in labels)
    for kind, sequence in SEQUENCES.items():
        values = tuple(sequence)
        for start in range(max(1, len(values) - len(normalized) + 1)):
            if values[start:start + len(normalized)] == normalized:
                return kind
    return None


def _option_run_detail(segment_body: str) -> tuple[tuple[str, ...], bool]:
    lines = segment_body.splitlines()
    best: tuple[tuple[str, ...], bool] = (), False
    current: list[tuple[str, str, str, int]] = []

    def consider() -> None:
        nonlocal best
        if not 2 <= len(current) <= 8:
            return
        labels = tuple(item[0] for item in current)
        separators = {item[1] for item in current}
        indents = {len(item[2].expandtabs(4)) for item in current}
        unique = len(set(label.upper() for label in labels)) == len(labels)
        short = all(item[3] <= 3 for item in current)
        known = _sequence_kind(labels) is not None
        if len(separators) == 1 and len(indents) == 1 and unique and short and len(labels) > len(best[0]):
            best = (labels, known)

    for raw_line in (*lines, ""):
        if not raw_line.strip():
            continue
        found = _OPTION_RE.match(raw_line)
        if found is None:
            consider()
            current = []
            continue
        current.append(
            (
                found.group("label"),
                found.group("separator"),
                found.group("indent"),
                len(found.group("label")),
            )
        )
    consider()
    return best


def option_run(segment_body: str) -> tuple[str, ...]:
    """Return one structural option-label run, or an empty tuple."""

    return _option_run_detail(segment_body)[0]


def option_run_quality(segment_body: str) -> float:
    """Return 1.0 for a declared sequence and 0.5 for a valid unknown script."""

    labels, known = _option_run_detail(segment_body)
    if not labels:
        return 0.0
    return 1.0 if known else 0.5
