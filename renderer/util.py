"""Small helpers the rest of the package shares: rounding as the numbers have always been rounded (halves away
from zero, never to the even neighbour), inclusive ranges, and reading loosely typed values from JSON."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass


def _round_away(value: float) -> float:
    """A whole number, halves away from zero (C's round)."""
    whole = math.floor(abs(value))
    if abs(value) - whole >= 0.5:
        whole += 1
    return math.copysign(whole, value)


def rnd(value: float, digits: int = 2) -> float:
    """Rounds to `digits` places, halves away from zero, exactly as the numbers have always been rounded (Ruby's
    Float#round): scaled, rounded, then nudged when the scaling lost or gained a half (2.675 is 2.68)."""
    if value is None or isinstance(value, bool):
        return value
    value = float(value)
    if math.isinf(value) or math.isnan(value) or value == 0:
        return value
    scale = 10.0 ** digits
    whole = _round_away(value * scale)
    if value > 0:
        if (whole + 0.5) / scale <= value:
            whole += 1
    elif (whole - 0.5) / scale >= value:
        whole -= 1
    return whole / scale


def rint(value: float) -> int:
    """Rounds to a whole number, halves away from zero."""
    return int(_round_away(float(value)))


@dataclass(frozen=True)
class Span:
    """An inclusive range of numbers, min and max both in it."""

    min: float
    max: float

    def covers(self, value: float) -> bool:
        return self.min <= value <= self.max

    def shifted(self, by: float) -> "Span":
        return Span(self.min + by, self.max + by)

    def as_json(self) -> dict:
        return {"min": self.min, "max": self.max}


def text(value) -> str:
    """A value as words, the way a template would show it: nothing for None, "true" and "false" for booleans."""
    if value is None:
        return ""
    if value is True:
        return "true"
    if value is False:
        return "false"
    return str(value)


def flag(value) -> bool:
    """Whether a loosely typed flag is on: True or "true"."""
    return value is True or text(value) == "true"


def squish(value) -> str:
    """Whitespace runs as one space, trimmed."""
    return re.sub(r"\s+", " ", text(value)).strip()


def number(value):
    """A number from a loosely typed value ("12.5", 12, None), or None."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value) if math.isfinite(value) else None
    try:
        found = float(str(value).strip())
    except ValueError:
        return None
    return found if math.isfinite(found) else None


def blank(value) -> bool:
    """Nothing there: None, False, an empty or all-whitespace string, an empty list or dict."""
    if value is None or value is False:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, tuple, dict, set)):
        return len(value) == 0
    return False


def presence(value):
    """The value, or None when it's blank."""
    return None if blank(value) else value


def truncate(value, limit: int, omission: str = "...") -> str:
    """At most `limit` characters, ending in the omission when cut."""
    words = text(value)
    if len(words) <= limit:
        return words
    return words[: max(limit - len(omission), 0)] + omission


def titleize(value) -> str:
    """Words as a title: "sample label cashmere cardigan" is "Sample Label Cashmere Cardigan"."""
    words = text(value)
    words = re.sub(r"([A-Z\d]+)([A-Z][a-z])", r"\1_\2", words)
    words = re.sub(r"([a-z\d])([A-Z])", r"\1_\2", words)
    words = words.replace("-", "_").lower()
    words = re.sub(r"\A_+", "", words)
    words = re.sub(r"_id\Z", "", words)
    words = words.replace("_", " ")
    return re.sub(r"\b(?<!\w['’`()])[a-z]", lambda m: m.group(0).upper(), words)


def joined(product: dict, *keys) -> str:
    """Some of a listing's fields as one run of words, the missing ones as nothing."""
    return " ".join(text(product.get(key)) for key in keys)


def first_match(rules, words):
    """The name of the first (name, pattern) rule whose pattern is found in the words, or None."""
    words = text(words)
    for name, pattern in rules:
        if pattern.search(words):
            return name
    return None


def clamp(value, low, high):
    return max(low, min(high, value))


def num_text(value) -> str:
    """A number as Ruby writes it: 38.5, 40.0, 7."""
    if isinstance(value, float):
        if math.isinf(value):
            return "Infinity" if value > 0 else "-Infinity"
        return repr(value)
    return str(value)


def ruby_array(value) -> list:
    """A value as a list, the way Ruby's Array() makes one: nothing is [], a list stays, a dict is its pairs, and
    anything else is a list of itself."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, dict):
        return [[key, item] for key, item in value.items()]
    return [value]
