"""Fit math for tops (T-shirts, shirts, sweatshirts), jackets, coats and trousers. Everything is in centimetres.

Ease is the garment's measurement minus the body's. A jacket needs some ease to move in; how much depends on the
cut. Parts a tailor can change (sleeves, waist) cost little when they're off; parts they can't (shoulders, chest,
length) cost a lot.

Nothing here keeps the measurements it's given: they come in with a request and are gone after it.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field, replace

from .util import Span, flag, rnd, rint, text

CUTS = {
    "slim": {"label": "Slim", "chest": Span(6, 10), "waist": Span(6, 11)},
    "regular": {"label": "Regular", "chest": Span(9, 13), "waist": Span(10, 15)},
    "classic": {"label": "Classic", "chest": Span(12, 17), "waist": Span(14, 20)},
}

# What to ask for: the range of answers the API accepts, the range most adults fall in (outside it, the page asks
# whether it was measured right), and how to measure it. Hips and inseam are only needed for trousers.
MEASUREMENTS = [
    {"key": "chest", "label": "Chest", "help": "Around the fullest part, under the arms.", "range": Span(60, 200), "usual": Span(80, 135),
     "how": "around the fullest part of the chest, under the arms, with the tape level"},
    {"key": "waist", "label": "Waist", "help": "Around your middle, at the navel.", "range": Span(50, 200), "usual": Span(60, 130),
     "how": "around your middle at the navel, tape snug but not tight"},
    {"key": "shoulders", "label": "Shoulders", "help": "Across the back, shoulder bone to shoulder bone.", "range": Span(30, 70), "usual": Span(38, 54),
     "how": "straight across the back from one shoulder bone to the other, not around the arms"},
    {"key": "arm", "label": "Arm", "help": "Shoulder bone to wrist bone, arm relaxed.", "range": Span(40, 90), "usual": Span(52, 72),
     "how": "from the shoulder bone to the wrist bone with the arm hanging"},
    {"key": "height", "label": "Height", "help": "Standing, without shoes.", "range": Span(130, 230), "usual": Span(150, 205),
     "how": "standing straight against a wall, without shoes"},
    {"key": "hips", "label": "Hips", "help": "Around the fullest part of the seat. For trousers.", "range": Span(60, 200), "usual": Span(82, 135),
     "optional": True, "how": "around the fullest part of the seat, feet together"},
    {"key": "inseam", "label": "Inseam", "help": "Crotch to floor, inside the leg. For trousers.", "range": Span(50, 110), "usual": Span(66, 92),
     "optional": True, "how": "from the crotch down the inside of the leg to the floor, without shoes"},
]

# What a size chart gives for each size: finished garment measurements in centimetres.
SIZE_MEASUREMENTS = ["chest", "waist", "shoulders", "sleeve", "length"]
TROUSER_MEASUREMENTS = ["waist", "seat", "thigh", "inseam", "leg_opening"]

# Leggings stretch over the body: made a little smaller than it, at the waist and the seat.
LEGGINGS_WAIST_EASE = Span(-12, 1)
LEGGINGS_SEAT_EASE = {"slim": Span(-16, -4), "regular": Span(-14, -2), "classic": Span(-10, 1)}
# An elastic waist (joggers, sweatpants, pull-on pants) is made smaller than the body and stretches on, by about 8%
# of the body's waist (some 6 to 7 cm); past that it's tight, and a tailor can't let it out. It may be up to 6 cm
# bigger than the body, gathered in by its cord. Within that, the size that stretches a little under halfway (a
# size's relaxed waist is made for the smallest body it fits) wins a tie.
ELASTIC_STRETCH = 0.08
ELASTIC_ROOM = 6
ELASTIC_AIM = 0.4  # of the stretch
ELASTIC_TIE = 0.1  # penalty per cm from the aim
# The cloth under an elastic waist is gathered in, so pull-on pants are made this much fuller over the seat than
# tailored ones, as their cut.
GATHERED_SEAT = 8
# The knee is about this share of the way down from the crotch to the floor.
KNEE_SHARE = 0.47

# Trousers sit at the waist with a little room, need more over the seat (by cut), and break just above the shoe:
# about 3 cm shorter than the inseam measured to the floor.
TROUSER_WAIST_EASE = Span(0, 3)
SEAT_EASE = {"slim": Span(3, 7), "regular": Span(6, 10), "classic": Span(9, 14)}
# Pants made loose on purpose (baggy, wide-leg, pleated: the shop's words): 20 cm or more over the seat is how
# they're meant to be, so the waist picks the size.
LOOSE_SEAT_EASE = Span(8, 34)
HEM_ABOVE_FLOOR = 3
HEM_TOLERANCE = 1.5
LEG_OPENINGS = [(38, "a slim, tapered leg"), (44, "a straight leg"), (math.inf, "a wide leg")]

# Rules of thumb a tailor would use.
SHOULDER_EASE = Span(-0.75, 1.5)  # seam sits on the shoulder bone or just past it, give or take a tape measure's error
SLEEVE_ABOVE_WRIST = 1.5          # sleeve ends ~1.5 cm above the wrist bone, showing shirt cuff
SLEEVE_TOLERANCE = 1
LENGTH_PER_HEIGHT = 0.43          # jacket back length is about 43% of height
LENGTH_TOLERANCE = 2
ALTERATIONS = {
    "waist": {"loose": ("take_in_waist", "Take in the waist", 5), "tight": ("let_out_waist", "Let out the waist", 2.5)},
    "trouser_waist": {"loose": ("take_in_waist", "Take in the waist", 5), "tight": ("let_out_waist", "Let out the waist", 3)},
    # Through the centre back seam, which trousers are made with extra in for this.
    "seat": {"loose": ("take_in_seat", "Take in the seat", 6)},
    "inseam": {"long": ("shorten_hem", "Take up the hem", 15), "short": ("lengthen_hem", "Let down the hem", 4)},
    "sleeve": {"long": ("shorten_sleeves", "Shorten the sleeves", 5), "short": ("lengthen_sleeves", "Lengthen the sleeves", 3)},
}

# A coat goes over a jacket, so it needs this much more room in the chest and waist. Its length is a matter of
# style, so it says where it ends rather than calling it right or wrong.
COAT_EXTRA_EASE = 7
NECK_BASE_PER_HEIGHT = 0.835  # the collar seam sits at about 83.5% of height
HEMLINES = [
    (0.47, "at the hip"), (0.40, "at the seat"), (0.34, "mid-thigh"), (0.29, "just above the knee"),
    (0.25, "at the knee"), (0.19, "below the knee"), (0.12, "mid-calf"), (0.07, "low on the calf"),
    (0.0, "at the ankle"),
]

# Tops are worn closer or looser than tailoring, and how much is mostly style: these are the usual ranges. Their
# shoulder seam may drop past the shoulder bone; their length is checked against where a top usually ends (about
# 41% of height from the collar seam), with more leeway than a jacket's.
TOP_CUTS = {
    "slim": {"chest": Span(4, 9), "waist": Span(4, 10)},
    "regular": {"chest": Span(8, 15), "waist": Span(8, 18)},
    "classic": {"chest": Span(14, 26), "waist": Span(14, 30)},
}
# A dress sits closer than a T-shirt.
DRESS_CUTS = {
    "slim": {"chest": Span(2, 6), "waist": Span(2, 7)},
    "regular": {"chest": Span(4, 9), "waist": Span(4, 11)},
    "classic": {"chest": Span(7, 14), "waist": Span(8, 16)},
}
# A women's top sits closer than a men's.
WOMEN_TOP_CUTS = {
    "slim": {"chest": Span(0, 6), "waist": Span(0, 8)},
    "regular": {"chest": Span(3, 10), "waist": Span(4, 14)},
    "classic": {"chest": Span(8, 18), "waist": Span(10, 24)},
}
# A baby tee's stretchy knit is made about the size of the body, or a little smaller.
SNUG_TOP_CUTS = {
    "slim": {"chest": Span(-7, 1), "waist": Span(-6, 4)},
    "regular": {"chest": Span(-5, 4), "waist": Span(-4, 8)},
    "classic": {"chest": Span(-2, 8), "waist": Span(0, 12)},
}
SNUG_SHORT = 10                      # and may end this much higher than a women's top usually does
SNUG_SHOULDER_EASE = Span(-5, 3)     # its shoulder seams sit a little in from the shoulder
# A fitted knit (a "shrunken" sweater hoodie, a ribbed top): made a little smaller than the body, and stretches on.
# Its chest as a share of the body's, by how close it's worn (regular: about -8 to +2 cm on a 90 cm chest, aiming at
# about -4); the size nearest the aim wins a tie. Its shoulder seams sit on the bone or up to 2 cm inside it; it may
# end at the waist (see SNUG_SHORT).
FITTED_KNIT_SHARE = {"slim": Span(-0.12, -0.02), "regular": Span(-0.09, 0.02), "classic": Span(-0.05, 0.05)}
FITTED_KNIT_AIM = {"slim": -0.08, "regular": -0.05, "classic": -0.01}
FITTED_KNIT_SHOULDER_EASE = Span(-2, 2)
FITTED_KNIT_TIE = 0.2  # penalty per cm from the aim
TOP_SHOULDER_EASE = Span(-1, 5)
TOP_LENGTH_PER_HEIGHT = 0.41
TOP_LENGTH_TOLERANCE = 4
# A women's top usually ends higher, at the top of the hip.
WOMEN_TOP_LENGTH_PER_HEIGHT = 0.36
SHORT_SLEEVE = 40  # a sleeve shorter than this (cm, from the shoulder seam) is a short sleeve

# Penalty per centimetre outside the target, plus a flat cost when no tailor can fix it.
WEIGHT = {"shoulders": 4, "chest": 3, "length": 2, "waist": 1, "sleeve": 0.5, "trouser_waist": 2, "elastic_waist": 2, "seat": 2,
          "stretch_seat": 2, "inseam": 0.4, "hips": 2}
UNFIXABLE = 6

# A women's jacket usually ends higher, at the top of the hip.
WOMEN_JACKET_LENGTH_PER_HEIGHT = 0.37
# Where a jacket made to end at the waist (cropped, a bomber, a track jacket) ends, by its length as a share of the
# height: (share, words), the first it's under.
WAIST_HEMLINES = [(0.27, "Cropped. It ends above your waist."), (0.32, "Made short. It ends at your waist."),
                  (0.38, "Made short. It ends at the top of your hips."), (math.inf, "It ends at your hips.")]

# A stretch dress is made smaller than the body and stretches onto it: its chest, waist and hips as a share of the
# body's, by how close it's worn.
STRETCH_SHARE = {"slim": Span(-0.12, -0.03), "regular": Span(-0.09, 0.01), "classic": Span(-0.05, 0.05)}
DRESS_HIPS = {"slim": Span(2, 6), "regular": Span(3, 10), "classic": Span(6, 16)}
NO_SLEEVES = {"none": "Sleeveless", "straps": "Straps, no sleeves", "thin_straps": "Thin straps, no sleeves",
              "strapless": "Strapless", "one_shoulder": "One shoulder", "halter": "Halter, no sleeves"}
STRAPLESS_TOP = 18  # cm: a strapless dress's length is measured from its top edge, this far below the shoulder

# Some tops are made roomy on purpose (oversized, boxy), often with a dropped shoulder: the seam sits down the arm.
# Their chart is much bigger than the body each size is for, so they're judged against how they're meant to be
# worn. The usual body for each letter size: (chest, shoulders) in cm.
LETTER_BODY = {"XXS": (81, 40), "XS": (86, 41), "S": (91, 43), "M": (97, 45), "L": (104, 47), "XL": (112, 49),
               "XXL": (120, 51), "XXXL": (128, 53)}
# A women's (bust as dress_cut.LETTERS has it).
WOMEN_LETTER_BODY = {"XXS": (78, 36), "XS": (82, 37), "S": (87, 38), "M": (92, 39.5), "L": (98, 41),
                     "XL": (104, 42.5), "XXL": (110, 44), "XXXL": (116, 45.5)}
# Italian and French men's sizes (44 to 60) are half the chest they're made for, in cm; the shoulders grow about
# 1 cm a size from 45 cm at a 48.
NUMBERED = re.compile(r"\A(4[2-9]|5\d|6[0-2])\b")
# This much more chest than its size's usual body (cm): made roomy. About a classic cut's most room (a men's top's
# 26 cm, a women's 18); or any more than a regular cut's when the shop says it's oversized.
ROOMY = 25
ROOMY_WOMEN = 18
OVERSIZED = {"men": 15, "women": 10}
DROPPED = 8                      # this much wider shoulders than its size's usual body: a dropped shoulder
ROOMY_CUT = {"slim": -6, "regular": 0, "classic": 6}   # Snug sizes down, Loose sizes up
ROOMY_EASE = Span(-5, 7)         # around the room it's made with
BOXY_SHORT = 10                  # a roomy top may be cut this much shorter than usual (boxy)


@dataclass(frozen=True)
class Fix:
    action: str
    text: str
    amount: float


@dataclass(frozen=True)
class Check:
    """One part of a size against the body. status is "unknown" when the size chart doesn't give that measurement
    (ease is None then). note describes a measurement that has no right answer, such as where a coat's hem falls.
    good is the range of ease that fits for the cut chosen (cm), so a result can show where this size falls in it;
    None when a check has no such range (a hem that only says where it ends)."""

    part: str
    label: str
    ease: float | None
    status: str
    fix: Fix | None
    penalty: float
    note: str | None = None
    good: Span | None = None

    def fixable(self) -> bool:
        return self.status in ("good", "unknown") or self.fix is not None

    def with_(self, **changes) -> "Check":
        return replace(self, **changes)


@dataclass(frozen=True)
class Result:
    size: str
    checks: list = field(default_factory=list)
    penalty: float = 0

    def verdict(self) -> str:
        """ "fits" as it comes, "alter" with a tailor's help, or "compromise" when something can't be fixed."""
        if not all(check.fixable() for check in self.checks):
            return "compromise"
        return "alter" if any(check.fix for check in self.checks) else "fits"


def _result(size, checks) -> Result:
    return Result(size=size.get("name"), checks=checks, penalty=rnd(sum(check.penalty for check in checks)))


# ---- the checks


def skirt_length(length, inseam, height) -> Check:
    """Where a skirt ends, from the waist down: the knee is about this far below it, a little under a third of the
    height (or the inseam's share, when given)."""
    knee = inseam * (1 - KNEE_SHARE) + float(height) * 0.13 if inseam else float(height) * 0.32
    above = rint(knee - length)
    note = (f"Ends about {above} cm above the knee" if above >= 3 else
            f"Ends about {-above} cm below the knee" if above <= -3 else "Ends at the knee")
    if length > knee + 25:
        note = "Ends near the ankle"
    return Check(part="length", label="Length", ease=rnd(length - knee, 1), status="good", fix=None, penalty=0, note=note)


def shorts_length(inseam, leg) -> Check:
    """Where shorts end: above or at the knee, said in centimetres."""
    above = rint(leg * KNEE_SHARE - inseam)
    note = (f"Ends about {above} cm above the knee" if above >= 2 else
            f"Ends about {-above} cm below the knee" if above <= -2 else "Ends at the knee")
    return Check(part="inseam", label="Length", ease=rnd(inseam - leg * KNEE_SHARE, 1), status="good", fix=None, penalty=0, note=note)


def check_size(body, size, cut="regular", garment="jacket", design_=None, style=None, details=None) -> Result:
    """A jacket or a coat. design_: how its sizes are cut (see design). style: how it looks ("bomber"). details:
    {"women", "cropped", "ends": "waist" (made to end at the waist: a track jacket, a blouson)}."""
    details = dict(details or {})
    ranges = dict(CUTS[cut])
    coat = garment == "coat"
    if coat:
        ranges = {key: value.shifted(COAT_EXTRA_EASE) if isinstance(value, Span) else value for key, value in ranges.items()}
    design_ = design_ or {}
    roomy, dropped = (None, False) if coat else (design_.get("roomy"), design_.get("dropped"))
    women = flag(details.get("women"))
    short_by_design = not coat and (flag(details.get("cropped")) or text(details.get("ends")) == "waist" or style == "bomber")

    def shoulders(value):
        if dropped:
            return check("shoulders", "Shoulders", value - body["shoulders"], "good").with_(note="The shoulder seam is made to sit down the arm.")
        return range_check("shoulders", "Shoulders", value - body["shoulders"], SHOULDER_EASE)

    def chest(value):
        return roomy_chest(value - body["chest"], roomy, cut) if roomy else range_check("chest", "Chest", value - body["chest"], ranges["chest"])

    def waist(value):
        good = ranges["waist"].shifted(roomy) if roomy else ranges["waist"]
        return range_check("waist", "Waist", value - body["waist"], good)

    def length(value):
        if coat:
            return coat_length(value, body["height"])
        diff = value - body["height"] * (WOMEN_JACKET_LENGTH_PER_HEIGHT if women else LENGTH_PER_HEIGHT)
        if short_by_design and diff < 0:
            return waist_length(value, diff, body["height"])
        if (roomy or dropped) and diff < 0 and diff >= -BOXY_SHORT:
            return check("length", "Length", diff, "good").with_(note="Made short and boxy. It ends at your hips.")
        return length_check(diff)

    checks = [
        given(size, "shoulders", "Shoulders", shoulders),
        given(size, "chest", "Chest", chest),
        given(size, "waist", "Waist", waist),
        given(size, "sleeve", "Sleeves", lambda value: sleeve_check(value - (body["arm"] - SLEEVE_ABOVE_WRIST))),
        given(size, "length", "Length", length),
    ]
    return _result(size, checks)


def waist_length(length, diff, height) -> Check:
    """A jacket made to end at the waist: where it ends, not right or wrong."""
    note = next(words for share, words in WAIST_HEMLINES if length < height * share)
    return Check(part="length", label="Length", ease=rnd(diff), status="good", fix=None, penalty=0, note=note)


def roomy_chest(ease, roomy, cut) -> Check:
    """A chest made roomy on purpose (see design): judged against the room it's made with, the size nearest it
    first."""
    aim = roomy + ROOMY_CUT[cut]
    found = range_check("chest", "Chest", ease, Span(aim + ROOMY_EASE.min, aim + ROOMY_EASE.max))
    found = found.with_(penalty=rnd(found.penalty + abs(ease - aim) * 0.05))
    return found.with_(note="Made to be big and loose. On you, it's loose the way it should be.") if found.status == "good" else found


def check_trousers(body, size, cut="regular", style=None, details=None) -> Result:
    """style: "shorts" (their length is where they end, not right or wrong), "leggings" (stretch, made smaller than
    the body), "skirt", or another (trousers, jeans, joggers). details: {"elastic": pull-on (an elastic or drawcord
    waist), "fit": "loose" or "slim" (how the shop says the pants are cut), "hem": "unfinished" (sold long, to be
    hemmed)}."""
    details = dict(details or {})
    stretch = style == "leggings"
    # Joggers, and pull-on pants with an elastic or drawcord waist.
    elastic = style == "joggers" or flag(details.get("elastic"))
    made = None if style == "skirt" or stretch else text(details.get("fit"))

    def waist(value):
        if not elastic:
            return range_check("trouser_waist", "Waist", value - body["waist"], LEGGINGS_WAIST_EASE if stretch else TROUSER_WAIST_EASE, shown_as="waist")
        return elastic_waist(value - body["waist"], body["waist"])

    def seat(value):
        if not body.get("hips"):
            return needs("seat", "Seat", "hips")
        if stretch:
            return stretch_seat(value - body["hips"], cut)
        good = LOOSE_SEAT_EASE if made == "loose" else SEAT_EASE["slim" if made == "slim" else cut]
        if elastic and made != "loose":
            good = Span(good.min, good.max + GATHERED_SEAT)
        found = range_check("seat", "Seat", value - body["hips"], good)
        if found.status == "good" and made == "loose" and value - body["hips"] > SEAT_EASE["classic"].max:
            return found.with_(note="Cut loose over the seat, as it's meant to be")
        return found

    def inseam(value):
        if not body.get("inseam"):
            return needs("inseam", "Length", "inseam")
        if style == "shorts":
            return shorts_length(value, body["inseam"])
        if text(details.get("hem")) == "unfinished":
            return unhemmed(value, body["inseam"])
        return hem_check(value - (body["inseam"] - HEM_ABOVE_FLOOR))

    def leg(value):
        words = next(words for limit, words in LEG_OPENINGS if value < limit)
        return Check(part="leg_opening", label="Leg", ease=None, status="good", fix=None, penalty=0, note=f"Cut with {words}")

    checks = [given(size, "waist", "Waist", waist), given(size, "seat", "Seat", seat)]
    if style == "skirt":
        checks.append(given(size, "length", "Length", lambda value: skirt_length(value, body.get("inseam"), body["height"])))
    else:
        checks.append(given(size, "inseam", "Length", inseam))
        checks.append(given(size, "leg_opening", "Leg", leg))
    return _result(size, checks)


def elastic_waist(ease, waist) -> Check:
    """An elastic waist against the body's: within its stretch (see ELASTIC_STRETCH), the size nearest the aim
    first."""
    stretch = rnd(waist * ELASTIC_STRETCH, 1)
    found = range_check("elastic_waist", "Waist", ease, Span(-stretch, ELASTIC_ROOM), shown_as="waist")
    found = found.with_(penalty=rnd(found.penalty + abs(ease + stretch * ELASTIC_AIM) * ELASTIC_TIE))
    return found.with_(note="The elastic waist stretches to fit") if found.status == "good" and ease < 0 else found


def stretch_seat(ease, cut) -> Check:
    """Leggings' seat: made smaller than the body, it stretches on."""
    found = range_check("stretch_seat", "Seat", ease, LEGGINGS_SEAT_EASE[cut], shown_as="seat")
    return found.with_(note="Stretches to fit close to the body") if found.status == "good" else found


def unhemmed(inseam, leg) -> Check:
    """Pants sold long, to be hemmed to the wearer: their length is a note, not a fault."""
    hem = rint(leg - HEM_ABOVE_FLOOR)
    return Check(part="inseam", label="Length", ease=rnd(inseam - hem), status="good", fix=None, penalty=0,
                 note=f"Comes unhemmed. Have it hemmed to about {hem} cm.")


def check_dress(body, size, cut="regular", details=None) -> Result:
    """A dress: bust, waist and hips (it sits on all three), sleeves and shoulders only when it has sleeves, and its
    length as where it ends. A stretch dress may be smaller than the body; a flared one free at the hips."""
    details = dict(details or {})
    stretch = flag(details.get("stretch"))
    sleeves = text(details.get("sleeves"))
    flared = text(details.get("fit")) == "flared"
    ranges = DRESS_CUTS[cut]

    def around(rule, label, value, own, plain):
        if not own:
            return needs(rule, label, rule)
        if stretch:
            share = STRETCH_SHARE[cut]
            good = Span(own * share.min, own * share.max)
        else:
            good = plain
        found = range_check(rule, label, value - own, good)
        if stretch and found.status == "good" and value < own:
            return found.with_(note="Stretches to fit close to the body")
        return found

    checks = [
        given(size, "chest", "Bust", lambda value: around("chest", "Bust", value, body.get("chest"), ranges["chest"])),
        given(size, "waist", "Waist", lambda value: range_check("waist", "Waist", value - body["waist"], ranges["waist"]) if flared and not stretch
              else around("waist", "Waist", value, body.get("waist"), ranges["waist"])),
    ]
    if size.get("hips"):
        checks.append(given(size, "hips", "Hips", lambda value: around("hips", "Hips", value, body.get("hips"), Span(2, 80) if flared else DRESS_HIPS[cut])))
    if sleeves in NO_SLEEVES:
        checks.append(Check(part="sleeve", label="Sleeves", ease=None, status="good", fix=None, penalty=0, note=NO_SLEEVES[sleeves]))
    else:
        checks.append(given(size, "shoulders", "Shoulders", lambda value: range_check("shoulders", "Shoulders", value - body["shoulders"], TOP_SHOULDER_EASE)))

        def sleeve(value):
            if value < SHORT_SLEEVE:
                return Check(part="sleeve", label="Sleeves", ease=None, status="good", fix=None, penalty=0, note="Short sleeves")
            return sleeve_check(value - body["arm"])

        checks.append(given(size, "sleeve", "Sleeves", sleeve))
    checks.append(given(size, "length", "Length", lambda value: coat_length(value + (STRAPLESS_TOP if sleeves == "strapless" else 0), body["height"])))
    return _result(size, checks)


def design(sizes, details=None) -> dict:
    """How a top's or a jacket's sizes are cut: {"roomy": the extra chest it's made with (cm), or None; "dropped":
    True/False}, from each size's chart against the body that size is for (a men's or women's letter size, or an
    Italian number). details: "dropped" (its shop photo shows dropped shoulders, whatever its chart's numbers say),
    "women", "fit": "oversized" (the shop says it's oversized or boxy)."""
    details = dict(details or {})
    women = flag(details.get("women"))
    # (Numbers that stop below 50 are more likely a shirt's collar.)
    italian = any(re.match(r"\A(5\d|6[0-2])\b", text(size.get("name")).strip()) for size in sizes)
    known = []
    for size in sizes:
        body = size_body(size.get("name"), women, numbered=italian)
        if body:
            known.append((size, body))
    chest = sorted(size["chest"] - body[0] for size, body in known if size.get("chest"))
    shoulders = sorted(size["shoulders"] - body[1] for size, body in known if size.get("shoulders"))
    middle = chest[len(chest) // 2] if chest else None
    said = text(details.get("fit")) == "oversized"
    roomy = None
    if middle is not None and (middle >= (ROOMY_WOMEN if women else ROOMY) or (said and middle > OVERSIZED["women" if women else "men"])):
        roomy = middle
    dropped = flag(details.get("dropped")) or bool(shoulders and shoulders[len(shoulders) // 2] >= DROPPED)
    return {"roomy": roomy, "dropped": dropped}


def size_body(name, women=False, numbered=True):
    """The usual body (chest, shoulders) a size is made for, from its name; None when the name isn't a size this
    knows."""
    label = text(name).upper().strip()
    found = re.match(r"\A(XXXL|3XL|XXL|2XL|XL|XXS|2XS|XS|S|M|L)\b", label)
    if found:
        letter = found.group(1).replace("3XL", "XXXL").replace("2XL", "XXL").replace("2XS", "XXS")
        return (WOMEN_LETTER_BODY if women else LETTER_BODY).get(letter)
    if women or not numbered:
        return None
    found = NUMBERED.match(label)
    if not found:
        return None
    n = int(found.group(1))
    return (n * 2, 45 + (n - 48) / 2.0)


def check_top(body, size, cut="regular", design_=None, style=None, details=None) -> Result:
    """A T-shirt, shirt, sweatshirt or other top. Short sleeves end on the upper arm, so they aren't checked against
    the arm. design_: how its sizes are cut (see design). details: {"women": a women's top (it ends higher),
    "cropped": made to end above the waist, "snug": a baby tee (see SNUG_TOP_CUTS), "fit": "fitted" with "stretch":
    True: a fitted knit, made the size of the body or smaller (see FITTED_KNIT_SHARE)}."""
    details = dict(details or {})
    design_ = design_ or {}
    women = flag(details.get("women"))
    cropped = flag(details.get("cropped"))
    snug = flag(details.get("snug"))
    roomy, dropped = design_.get("roomy"), design_.get("dropped")
    # A chart made roomy says more than a listing's "fitted" (a zip hoodie with "fitted cuffs" and a slim rib).
    knit = not roomy and text(details.get("fit")) == "fitted" and flag(details.get("stretch"))
    snug = snug or knit
    ranges = (DRESS_CUTS if style == "dress" else SNUG_TOP_CUTS if snug else WOMEN_TOP_CUTS if women else TOP_CUTS)[cut]

    def shoulders(value):
        if dropped:
            return check("shoulders", "Shoulders", value - body["shoulders"], "good").with_(note="The shoulder seam is made to sit down the arm.")
        good = FITTED_KNIT_SHOULDER_EASE if knit else SNUG_SHOULDER_EASE if snug else TOP_SHOULDER_EASE
        return range_check("shoulders", "Shoulders", value - body["shoulders"], good)

    def chest(value):
        if knit:
            # A fitted knit stretches on: its chest a share of the body's, the size nearest the aim first.
            share = FITTED_KNIT_SHARE[cut]
            found = range_check("chest", "Chest", value - body["chest"], Span(body["chest"] * share.min, body["chest"] * share.max))
            found = found.with_(penalty=rnd(found.penalty + abs(value - body["chest"] * (1 + FITTED_KNIT_AIM[cut])) * FITTED_KNIT_TIE))
            if found.status == "good" and value < body["chest"]:
                return found.with_(note="A fitted knit: it stretches to fit close to the body.")
            return found
        if roomy:
            return roomy_chest(value - body["chest"], roomy, cut)
        return range_check("chest", "Chest", value - body["chest"], ranges["chest"])

    def waist(value):
        good = ranges["waist"].shifted(roomy) if roomy else ranges["waist"]
        return range_check("waist", "Waist", value - body["waist"], good)

    def sleeve(value):
        if value < SHORT_SLEEVE:
            return Check(part="sleeve", label="Sleeves", ease=None, status="good", fix=None, penalty=0, note="Short sleeves")
        # Long sleeves end at the wrist bone. A dropped shoulder's sleeve starts down the arm.
        start = (size["shoulders"] - body["shoulders"]) / 2.0 if dropped and size.get("shoulders") else 0
        return sleeve_check(value + start - body["arm"])

    def length(value):
        if style == "dress":
            return coat_length(value, body["height"])
        diff = value - body["height"] * (WOMEN_TOP_LENGTH_PER_HEIGHT if women else TOP_LENGTH_PER_HEIGHT)
        if cropped:
            return check("length", "Length", diff, "good").with_(note="Cropped. It's made to end above your waist.")
        if snug and -SNUG_SHORT <= diff <= TOP_LENGTH_TOLERANCE:
            return check("length", "Length", diff, "good").with_(
                note="Made short, to end near your waist." if knit else "A baby tee: made short, to end near your waist.")
        good = Span(-TOP_LENGTH_TOLERANCE, TOP_LENGTH_TOLERANCE)
        if abs(diff) <= TOP_LENGTH_TOLERANCE:
            return check("length", "Length", diff, "good", good=good)
        if (roomy or dropped) and diff < 0 and diff >= -BOXY_SHORT:
            return check("length", "Length", diff, "good").with_(note="Made short and boxy. It ends at your hips.")
        return check("length", "Length", diff, "long" if diff > 0 else "short", None, (abs(diff) - TOP_LENGTH_TOLERANCE) * WEIGHT["length"], good=good)

    checks = [
        given(size, "shoulders", "Shoulders", shoulders),
        given(size, "chest", "Chest", chest),
        given(size, "waist", "Waist", waist),
        given(size, "sleeve", "Sleeves", sleeve),
        given(size, "length", "Length", length),
    ]
    return _result(size, checks)


def rank(body, sizes, cut="regular", garment="jacket", style=None, details=None) -> list:
    """Every size, best first. style: how a top is cut, when it changes what fits ("dress": its length is where it
    ends, not right or wrong). details: a dress's cut ({"stretch", "sleeves", "fit"}, see dress_cut), or how a top,
    jacket or pants are made (see check_top, check_size, check_trousers)."""
    details = dict(details or {})
    cuts = None
    results = []
    for size in sizes:
        if garment == "trousers":
            results.append(check_trousers(body, size, cut, style=style, details=details))
        elif garment == "top":
            if style == "dress":
                results.append(check_dress(body, size, cut, details))
            else:
                cuts = cuts or design(sizes, details)
                results.append(check_top(body, size, cut, cuts, style=style, details=details))
        elif garment == "jacket":
            cuts = cuts or design(sizes, details)
            results.append(check_size(body, size, cut, garment, cuts, style=style, details=details))
        else:
            results.append(check_size(body, size, cut, garment, style=style, details=details))
    return sorted(results, key=lambda result: result.penalty)


def warnings(body) -> list:
    """Measurements outside the range most adults fall in, with how to measure them again."""
    out = []
    for m in MEASUREMENTS:
        value = body.get(m["key"])
        if value is None or m["usual"].covers(value):
            continue
        way = "larger" if value > m["usual"].max else "smaller"
        out.append({"part": m["key"], "message": f"{m['label']} looks {way} than most people's. Check it: measure {m['how']}."})
    return out


def needs(part, label, measurement) -> Check:
    return Check(part=str(part), label=label, ease=None, status="unknown", fix=None, penalty=0, note=f"Add your {measurement} to check this")


def hem_check(diff) -> Check:
    good = Span(-HEM_TOLERANCE, HEM_TOLERANCE)
    if abs(diff) <= HEM_TOLERANCE:
        return check("inseam", "Length", diff, "good", good=good)
    return altered("inseam", "Length", diff, "long" if diff > 0 else "short", abs(diff) - HEM_TOLERANCE, good=good)


def coat_length(length, height) -> Check:
    hem = (height * NECK_BASE_PER_HEIGHT - length) / height
    where = next((words for share, words in HEMLINES if hem >= share), HEMLINES[-1][1])
    return Check(part="length", label="Length", ease=rnd(length - height * LENGTH_PER_HEIGHT), status="good", fix=None, penalty=0,
                 note=f"Ends {where}")


def given(size, part, label, then) -> Check:
    value = size.get(part)
    if value is None:
        return Check(part=part, label=label, ease=None, status="unknown", fix=None, penalty=0)
    return then(value)


def range_check(rule, label, ease, good, shown_as=None) -> Check:
    """rule: which weight and alterations apply; shown_as: the part name the API reports, when it differs."""
    if good.covers(ease):
        return check(shown_as or rule, label, ease, "good", good=good)
    status = "tight" if ease < good.min else "loose"
    off = good.min - ease if ease < good.min else ease - good.max
    return altered(rule, label, ease, status, off, shown_as=shown_as, good=good)


def sleeve_check(diff) -> Check:
    good = Span(-SLEEVE_TOLERANCE, SLEEVE_TOLERANCE)
    if abs(diff) <= SLEEVE_TOLERANCE:
        return check("sleeve", "Sleeves", diff, "good", good=good)
    return altered("sleeve", "Sleeves", diff, "long" if diff > 0 else "short", abs(diff), good=good)


def length_check(diff) -> Check:
    good = Span(-LENGTH_TOLERANCE, LENGTH_TOLERANCE)
    if abs(diff) <= LENGTH_TOLERANCE:
        return check("length", "Length", diff, "good", good=good)
    return altered("length", "Length", diff, "long" if diff > 0 else "short", abs(diff) - LENGTH_TOLERANCE, good=good)


def altered(rule, label, ease, status, off, shown_as=None, good=None) -> Check:
    action, words, limit = ALTERATIONS.get(rule, {}).get(status, (None, None, None))
    if action and off <= limit:
        return check(shown_as or rule, label, ease, status, Fix(action=action, text=words, amount=rnd(off)), off * WEIGHT[rule], good=good)
    return check(shown_as or rule, label, ease, status, None, off * WEIGHT[rule] + UNFIXABLE, good=good)


def check(part, label, ease, status, fix=None, penalty=0, good=None) -> Check:
    return Check(part=str(part), label=label, ease=rnd(ease), status=status, fix=fix, penalty=rnd(penalty), good=good)
