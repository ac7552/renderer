"""Fit for footwear. Everything in centimetres.

A shoe fits by its last: the length inside it, and its width at the ball. Shops give sizes on a scale (US, UK, EU, or
centimetres on some Japanese and running-shoe charts), and sometimes a width (D, 2E, N, W). The scales are fixed
lengths (a US men's size is a third of an inch, a UK size the same with a different start, an EU size two thirds of
a centimetre); what varies by brand is how much shorter the inside of the shoe is than the scale says, which the
brands' own charts show (Nike runs about half a size shorter than New Balance at the same number). BRAND_OFFSETS has
what's published; others take the scale as it is.

The verdict for a size: toe room (the last's length less the foot's, which should be about a thumb's width,
TOE_ROOM), and width at the ball against the last's width for the width code. Styles differ: a boot or a running
shoe is cut with a little more room, a loafer or a pump must hold the heel, so less.

Nothing here keeps the measurements it's given.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .util import Span, rnd, text

MEASUREMENTS = [
    {"key": "foot", "label": "Foot length", "help": "Heel to the longest toe, standing on the foot.", "range": Span(15, 35), "usual": Span(21, 31),
     "how": "standing on a sheet of paper, heel against a wall, mark the longest toe and measure to the wall"},
    {"key": "ball", "label": "Foot width", "help": "Across the widest part of the foot, at the ball.", "range": Span(6, 14), "usual": Span(8, 11.5),
     "optional": True, "how": "standing, across the widest part of the foot where the toes join it"},
]

# Scales: internal length of the shoe in cm for a size number. US and UK sizes are a third of an inch apart
# (0.8467 cm); EU sizes two thirds of a centimetre. The starts are the usual last tables: a US men's 9 is a 27 cm
# foot, a US women's 9 is a 25.5 cm (women's numbering runs about 1.5 ahead of men's), a UK 8 is a 27 cm, an EU 42
# a 27 cm.
THIRD_INCH = 2.54 / 3
SCALES = {
    "us_m": lambda n: 27.0 + (n - 9) * THIRD_INCH,
    "us_w": lambda n: 25.5 + (n - 9) * THIRD_INCH,
    "uk": lambda n: 27.0 + (n - 8) * THIRD_INCH,
    "eu": lambda n: 27.0 + (n - 42) * (2.0 / 3),
    "cm": lambda n: float(n),
    "mm": lambda n: n / 10.0,
}

# How much shorter than the scale a brand's lasts run (cm), from the brands' published size-to-foot tables.
# Positive: the brand says a given size is for a shorter foot than the plain scale (it runs small). Their lasts
# differ more than their charts admit, which fit guides say in words ("runs half a size small"): these offsets are
# those words.
BRAND_OFFSETS = [
    (re.compile(r"nike|jordan", re.I), 0.4),
    (re.compile(r"converse", re.I), -0.5),
    (re.compile(r"vans", re.I), 0.0),
    (re.compile(r"adidas|yeezy", re.I), 0.2),
    (re.compile(r"new balance", re.I), 0.0),
    (re.compile(r"asics", re.I), 0.3),
    (re.compile(r"salomon", re.I), 0.3),
    (re.compile(r"hoka", re.I), 0.0),
    (re.compile(r"on running|\bon\b cloud", re.I), 0.2),
    (re.compile(r"dr\.? ?martens", re.I), -0.6),
    (re.compile(r"birkenstock", re.I), 0.0),
    (re.compile(r"clarks", re.I), 0.0),
    (re.compile(r"timberland", re.I), -0.3),
    (re.compile(r"ugg", re.I), -0.4),
]

# Width at the ball of the last (cm) for a US men's 9 (27 cm) by width code, from the Brannock scale: a D is 9.6 cm,
# each step a quarter inch narrower or wider. Scaled with the length (a bigger shoe is wider in proportion, about
# 0.35 cm a size). Women's codes: B is medium.
WIDTHS = {"4A": 8.3, "3A": 8.6, "2A": 8.9, "A": 9.2, "B": 9.4, "C": 9.5, "D": 9.6, "E": 9.9, "2E": 10.3, "3E": 10.6, "4E": 10.9, "6E": 11.5}
WIDTH_WORDS = [
    (re.compile(r"extra[- ]wide|\b4E\b|\bEEEE\b|\bXW\b", re.I), "4E"),
    (re.compile(r"\bwide\b|\bW\b|\b2E\b|\bEE\b", re.I), "2E"),
    (re.compile(r"\bnarrow\b|\bN\b", re.I), "B"),
    (re.compile(r"\bmedium\b|\bregular\b|\bstandard\b|\bD\b|\bM\b", re.I), "D"),
]
WIDTH_PER_CM = 0.35 / THIRD_INCH  # cm of width per cm of length, along a size run

# Toe room (cm, the last's length less the foot's) that fits, by style: a running shoe needs a thumb's width, a boot
# a little more (thick socks, the foot sliding on a slope), a dress shoe, a loafer or a pump less (they're meant to
# hold the foot, and a long loafer slips at the heel).
TOE_ROOM = {
    "sneaker": Span(1.0, 1.8), "hightop": Span(1.0, 1.8), "runner": Span(1.2, 2.0),
    "boot": Span(1.2, 2.2), "loafer": Span(0.6, 1.3), "heel": Span(0.4, 1.1), "sandal": Span(0.3, 1.2), "flat": Span(0.5, 1.2),
}
DEFAULT_TOE_ROOM = Span(0.8, 1.6)
# Width: the last may be this much narrower than the foot (the upper gives, more in knit and canvas than in
# leather) or this much wider, and fit.
WIDTH_EASE = {"leather": Span(-0.3, 0.8), "suede": Span(-0.4, 0.8), "canvas": Span(-0.6, 0.9), "knit": Span(-0.9, 1.0), "mesh": Span(-0.8, 1.0)}
DEFAULT_WIDTH_EASE = Span(-0.5, 0.9)

# Penalty per cm off.
WEIGHT = {"toe": 3.0, "width": 2.0}


@dataclass(frozen=True)
class Check:
    """As fit.Check: a shoe can't be altered, so a check is fixable only when it's good."""

    part: str
    label: str
    ease: float
    status: str
    penalty: float
    note: str | None = None
    fix = None
    good = None

    def fixable(self) -> bool:
        return self.status == "good"


@dataclass(frozen=True)
class Result:
    size: str
    checks: list = field(default_factory=list)
    penalty: float = 0

    def verdict(self) -> str:
        return "fits" if all(check.status == "good" for check in self.checks) else "compromise"


SIZE_NAME = re.compile(r"\b(US|UK|EU|EUR|JP|CM|MM)\b\s*[:\-]?\s*(\d+(?:[.,]\d+)?)|(\d+(?:[.,]\d+)?)\s*(?:\b(US|UK|EU|EUR|JP|CM|MM)\b)?", re.I)
OWN_SCALE = {"UK": "uk", "EU": "eu", "EUR": "eu", "JP": "cm", "CM": "cm", "MM": "mm"}


def parse_size(name, scale="us_m"):
    """A size name ("9", "9.5", "US 9", "EU 42.5", "UK 8", "27 cm", "9 Wide", "9.5 (2E)") on a chart whose scale is
    `scale` ("us_m", "us_w", "uk", "eu", "cm"), as {"number", "scale", "width"} or None when it isn't a size. A name
    that says its own scale ("EU 42") overrides the chart's."""
    words = text(name).strip()
    found = SIZE_NAME.search(words)
    if not found:
        return None
    number = float((found.group(2) or found.group(3)).replace(",", "."))
    said = (found.group(1) or found.group(4) or "").upper()
    own = OWN_SCALE.get(said)
    # (The width from the rest of the name: "9 Wide", "9.5 (2E)", "10 W".)
    rest = words.replace(found.group(0), " ", 1)
    # (A leading W or M is the chart's gender, see scale_for, not a width.)
    rest = re.sub(r"\A\s*[WM]\b", " ", rest, count=1, flags=re.I)
    width = next((code for pattern, code in WIDTH_WORDS if pattern.search(rest)), None)
    return {"number": number, "scale": own or scale, "width": width}


def last_length(size, brand=None) -> float:
    """The length inside the shoe for a parsed size (cm), for a brand."""
    scale = SCALES.get(size["scale"], SCALES["us_m"])
    offset = next((value for pattern, value in BRAND_OFFSETS if pattern.search(text(brand))), 0.0)
    return scale(size["number"]) - offset


def last_width(size, length, width_code=None) -> float:
    """The width at the ball of the last (cm): by the width code (D when none), scaled with the length."""
    code = width_code or size.get("width") or ("B" if size["scale"] == "us_w" else "D")
    base = WIDTHS.get(code, WIDTHS["D"])
    return base + (length - 27.0) * WIDTH_PER_CM


def rank(foot, sizes, scale="us_m", brand=None, style=None, fabric=None, width=None) -> list:
    """Every size, best first. foot: {"foot": cm, "ball": cm or None}; sizes: [{"name"}]; scale (the chart's),
    brand, style, fabric, width (a width code the listing gives)."""
    results = []
    for size in sizes:
        parsed = parse_size(size.get("name"), scale)
        if parsed:
            results.append(check(foot, size.get("name"), parsed, brand=brand, style=style, fabric=fabric, width=width))
    return sorted(results, key=lambda result: result.penalty)


def check(foot, name, parsed, brand=None, style=None, fabric=None, width=None) -> Result:
    length = last_length(parsed, brand)
    room = length - float(foot["foot"])
    want = TOE_ROOM.get(text(style), DEFAULT_TOE_ROOM)
    toe = range_check("toe", "Length", room, want, WEIGHT["toe"],
                      tight="Toes touch the end", loose="Heel will slip", fits=f"About {rnd(room, 1)} cm in front of the toes")
    checks = [toe]
    if foot.get("ball"):
        ease = last_width(parsed, length, width) - float(foot["ball"])
        checks.append(range_check("width", "Width", ease, WIDTH_EASE.get(text(fabric), DEFAULT_WIDTH_EASE), WEIGHT["width"],
                                  tight="Narrow across the ball", loose="Roomy across the ball", fits="Right across the ball"))
    # (Of two sizes that fit, the snugger: a tenth of a point per cm of room, which never outweighs a fault.)
    penalty = sum(c.penalty for c in checks) + (room * 0.1 if toe.status == "good" else 0)
    return Result(size=name, checks=checks, penalty=rnd(penalty))


def range_check(part, label, ease, want, weight, tight, loose, fits) -> Check:
    if ease < want.min:
        status, off = "tight", want.min - ease
    elif ease > want.max:
        status, off = "loose", ease - want.max
    else:
        status, off = "good", 0.0
    note = fits if status == "good" else tight if status == "tight" else loose
    return Check(part=part, label=label, ease=rnd(ease), status=status, penalty=rnd(off * weight), note=note)


def scale_for(names, women=False) -> str:
    """The scale a chart's size names are on, from the names and the listing: "EU 42" says EU; plain numbers 33 and
    up are EU, 20 to 32 are cm, 3 to 16 are US (women's when the listing is women's)."""
    sample = [text(n) for n in names]
    # Every size led by W (or M) is a women's (men's) chart, not a width.
    if len(sample) > 1 and all(re.match(r"\A\s*W\b", n, re.I) for n in sample):
        women = True
    if any(re.search(r"\bEU\b|\bEUR\b", n, re.I) for n in sample):
        return "eu"
    if any(re.search(r"\bUK\b", n, re.I) for n in sample):
        return "uk"
    if any(re.search(r"\bcm\b|\bJP\b", n, re.I) for n in sample):
        return "cm"
    numbers = []
    for n in sample:
        found = re.search(r"\d+(?:[.,]\d+)?", n)
        if found:
            numbers.append(float(found.group(0).replace(",", ".")))
    if not numbers:
        return "us_w" if women else "us_m"
    median = sorted(numbers)[len(numbers) // 2]
    if median >= 33:
        return "eu"
    if median >= 20:
        return "cm"
    return "us_w" if women else "us_m"


def warnings(foot) -> list:
    """Measurements outside the usual range, with how to measure again (as fit.warnings)."""
    out = []
    for m in MEASUREMENTS:
        value = foot.get(m["key"])
        if value is None or m["usual"].covers(value):
            continue
        way = "larger" if value > m["usual"].max else "smaller"
        out.append({"measurement": m["key"], "message": f"{m['label']} of {value} cm is {way} than most. Check it: measure {m['how']}."})
    return out
