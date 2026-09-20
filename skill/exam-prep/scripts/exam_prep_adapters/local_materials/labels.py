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
