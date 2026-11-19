"""How a dress is cut, read from its listing's name, category and description (shops describe dresses in a few set
phrases: "strapless", "thin straps", "form-fitting", "mini length", "75% nylon / 25% elastane"), and the usual
measurements of each women's size when the listing gives no chart.

A cut: {sleeves, neckline, length, fit, stretch, fabric, printed, details, ...}
  sleeves     "strapless", "one_shoulder", "halter", "thin_straps", "straps", "none" (sleeveless), "short" or "long"
  neckline    "straight", "scoop", "plunge", "round", "high" or "cowl" (a front that falls in soft folds)
  length      "mini", "knee", "midi" or "maxi"
  fit         "fitted", "slim", "relaxed" or "flared"
  hem_flare   True when only the hem flares out ("flared hem", mermaid, trumpet): the body keeps its fit
  waist_flare True when the skirt widens all the way from the waist (an A-line or fit and flare, as its photo
              shows): it's cut flaring from the waist, not the hips
  shape       the shape its photo showed (widths over the chest's, heights over the length): what the 3D view cuts
              it to
  collar      True for a shirt dress's collar ("classic collar", "point collar"): drawn with it and buttons
  stretch     True when the cloth stretches (elastane, spandex, jersey), so it's made smaller than the body
  fabric      the cloth as the 3D view draws it: "stretch", "jersey", "leather", "silk", "structured" (suiting,
              scuba, ponte, a boned bodice: stiff, so it skims the body and holds a flare out) or "cotton". Read by
              what most of it is: 8% silk doesn't make a silk dress, nor 5% polyurethane (an elastane) a leather one
  printed     True when the listing says the cloth is printed or patterned (only then is a print read off the photo)
  flounce     True for a gathered strip at the hem ("ruffled hem", "tiered", "flounce"): drawn on the hem
  pleats      True for a pleated or gathered skirt: cut fuller at its waist than its waistband and gathered into it
  tiers       for a tiered dress, how many tiers its skirt has (2 to 4; "tiered" alone is 3)
  slit        "side" (one, up the wearer's left) or "sides" (both) for a slit up the side seam
  belt        "buckle" for a belt at the waist, "tie" for a tie belt or a sash: drawn round the waist
  details     what the 3D view doesn't draw ("tie", "cut-outs", "draping" ...), to say so
"""

from __future__ import annotations

import re

from ..util import first_match, joined, presence, rnd, text
from .chart_reader import Chart

I = re.I

SLEEVES = [
    ("strapless", re.compile(r"strapless|bandeau|\btube (?:dress|top)|off[- ]the[- ]shoulders?|off[- ]shoulder|corset bodice", I)),
    ("one_shoulder", re.compile(r"one[- ]shoulder|single[- ]shoulder|asymmetric(?:al)? (?:neck|shoulder)", I)),
    ("halter", re.compile(r"halter", I)),
    ("long", re.compile(r"long[- ]sleeves?|\bl/s\b|full[- ]length sleeves?|bishop sleeves?|raglan sleeves?|batwing|dolman|kimono sleeves?|\b[ck]aftan\b", I)),
    ("short", re.compile(r"short[- ]sleeves?|cap sleeves?|puff sleeves?|t-?shirt dress|tee dress|flutter sleeves?|polo dress", I)),
    # Sleeves the listing only mentions in passing ("raw sleeve cuffs", "cold shoulder") are long ones.
    ("long", re.compile(r"sleeve cuffs?|cold[- ]shoulder|cut[- ]?outs? (?:on|at) the shoulders?", I)),
    ("thin_straps", re.compile(r"spaghetti|thin straps?|skinny straps?|narrow straps?|slip dress|\bslip\b|cami\b|camisole|adjustable straps?", I)),
    ("straps", re.compile(r"wide straps?|\bstraps?\b|racer ?back|tank dress|\btank\b|square neck", I)),
    ("none", re.compile(r"sleeveless", I)),
]
# An "asymmetrical off-shoulder neckline" is off one shoulder: the other is covered.
OFF_ONE_SHOULDER = re.compile(r"asymmetric(?:al)?\s+off[- ](?:the[- ])?shoulders?", I)
OFF_SHOULDER = re.compile(r"off[- ](?:the[- ])?shoulders?", I)
SLEEVED = re.compile(r"sleeve cuffs?|long[- ]sleeves?|full[- ]length sleeves?|\bsleeves\b", I)
NECKLINES = [
    ("plunge", re.compile(r"plung|deep[- ]v|v[- ]neck|\bv\b neck|wrap front", I)),
    ("high", re.compile(r"high[- ]neck|mock[- ]neck|turtle ?neck|funnel neck|halter neck", I)),
    ("cowl", re.compile(r"cowl", I)),
    ("scoop", re.compile(r"scoop|sweetheart|u[- ]neck", I)),
    ("straight", re.compile(r"straight neck|square neck|boat ?neck|bateau|straight[- ]across", I)),
    ("round", re.compile(r"crew ?neck|round neck|jewel neck", I)),
]
LENGTHS = [
    ("maxi", re.compile(r"maxi|floor[- ]length|full[- ]length|\bgown|ankle[- ]length", I)),
    ("midi", re.compile(r"midi|tea[- ]length|calf[- ]length|below the knee", I)),
    ("mini", re.compile(r"\bmini\b|short dress|above the knee|micro", I)),
    ("knee", re.compile(r"knee[- ]length", I)),
]
FITS = [
    ("fitted", re.compile(r"form[- ]fitting|bodycon|body[- ]con|figure[- ]hugging|second[- ]skin|fitted|sculpted|corset|boning", I)),
    ("flared", re.compile(r"a[- ]line|flare|skater|full skirt|tiered|swing|circle skirt|fit[- ]and[- ]flare", I)),
    ("relaxed", re.compile(r"relaxed|loose|shift dress|oversized|boxy|easy fit", I)),
    ("slim", re.compile(r"slim", I)),
]
# A flare only at the hem (the body keeps its fit down to it), or on the sleeves: neither makes the dress an A-line.
HEM_FLARE = re.compile(r"flared? hem|flare (?:at|from) the (?:hem|knee)|mermaid|trumpet|fishtail", I)
SLEEVE_FLARE = re.compile(r"(?:flared?|bell|trumpet|wide) (?:sleeves?|cuffs?)", I)
SHIRT_COLLAR = re.compile(r"(?:classic|shirt|point|spread|button[- ]down|camp|pointed|polo) collar|\bcollared\b|\bpolo dress|(?<![\w-])shirt ?dress", I)
STRETCH = re.compile(r"elastane|spandex|lycra|stretch|jersey|ribbed|rib[- ]knit|\bknit(?:ted)?\b", I)
# Cloths that hold their shape: stiff to bend, whether they stretch or not.
STRUCTURED = re.compile(r"suiting|scuba|ponte|neoprene|bonded|\bbon(?:ing|ed)\b|corset|structured|tweed|boucl[eé]|\bcrepe\b(?! de chine)", I)
# A hem with a strip gathered onto it: drawn as the body's shape, with the strip on (not as a flare).
FLOUNCE = re.compile(r"ruffled? hem|ruffle (?:at|on) the hem|flounce|tiered|tiers\b|peplum hem", I)
PLEATED = re.compile(r"pleat|accordion|plissé|plisse|gathered (?:skirt|waist)|\bgathered\b", I)
# A wrap dress or skirt ties at the waist: its belt is a tie, when the listing names no other.
WRAP = re.compile(r"\bwrap\b|faux[- ]wrap|wrap[- ](?:front|style|dress|skirt)", I)
TIERED = re.compile(r"\b(two|three|four|[234])[- ]tier(?:ed|s)?\b|\btiered\b|\btiers\b", I)
TIER_COUNTS = {"two": 2, "three": 3, "four": 4}
# Slits up the side seams (both, or one), and a belt at the waist ("belt loops" aren't one).
SIDE_SLITS = re.compile(r"side slits|slits (?:at|on|up) (?:the|both) sides|split sides|side splits", I)
SIDE_SLIT = re.compile(r"side slit|side split|slit (?:at|on|up) the side|thigh[- ]high slit|leg slit|high slit", I)
BELT = re.compile(r"\bbelt(?:ed)?\b(?! loops?)", I)
# (A "self-tie closure on the back" isn't a belt, nor a sash draped to the hip.)
TIE_BELT = re.compile(r"tie belt|self[- ]tie belt|belt that ties|waist tie|ties? at the waist|sash (?:belt|at the waist|round the waist|around the waist)", I)
PRINTED = re.compile(r"print|pattern|floral|graphic|logo|stripe|check|plaid|gingham|polka|leopard|zebra|paisley|motif|parquet|camo|tie[- ]dye", I)
DETAILS = [
    ("belt", re.compile(r"\bbelt(?:ed)?\b(?! loops?)", I)), ("tie", re.compile(r"self[- ]tie|\btie\b|sash|bow\b", I)), ("scarf", re.compile(r"scarf", I)),
    ("cut-outs", re.compile(r"cut[- ]?outs?|open back|keyhole", I)), ("ruffles", re.compile(r"ruffle|frill", I)), ("sheer panels", re.compile(r"sheer", I)),
    ("slit", re.compile(r"\bslit\b", I)), ("draping", re.compile(r"drap(?:ed|ing)", I)), ("uneven hem", re.compile(r"asymmetric(?:al)? hem|high[- ]low", I)),
    ("faux fur", re.compile(r"faux fur|shearling", I)),
]

# Where a dress is cut out ("cut-outs on the shoulder", "open back", "keyhole"), where it's see-through ("sheer
# sleeves"; "semi sheer" alone means all of it), and where a scarf is attached ("on the side").
CUTOUT_PLACES = [("shoulders", re.compile(r"shoulders?", I)), ("back", re.compile(r"back", I)), ("front", re.compile(r"front|chest|bust|neck", I)),
                 ("sides", re.compile(r"sides?", I)), ("waist", re.compile(r"waist|hips?|midriff", I))]
SHEER_PLACES = [("sleeves", re.compile(r"sleeves?", I)), ("back", re.compile(r"back", I)), ("sides", re.compile(r"sides?|panels?", I)),
                ("skirt", re.compile(r"skirt|hem|overlay", I))]


def tiers(words):
    """How many tiers a tiered dress's skirt has: "three-tiered", "2-tier", "tiered" (three), or None."""
    found = TIERED.search(words)
    if not found:
        return None
    said = found.group(1)
    count = (TIER_COUNTS.get(said.lower()) or int(said)) if said else 3
    return max(2, min(4, count))


# A keyhole is small, and at the neck in front unless the listing puts it on the back. "Cutouts on the front and
# back" are in both places; one "cutout on the front and side" wraps round from the front, so it's in front.
KEYHOLE_BACK = re.compile(r"keyhole(?:\s+cut[- ]?outs?)?\s+(?:on|at)\s+(?:the\s+)?back", I)


def cutouts(words):
    keyhole_back = bool(KEYHOLE_BACK.search(words))
    words = KEYHOLE_BACK.sub(" ", words)
    named = []
    for plural, first, second in re.findall(r"cut[- ]?out(s?)\s+(?:on|at|along|to|across)\s+(?:the\s+)?(\w+)(?:\s+(?:and|&)\s+(?:the\s+)?(\w+))?", words, I):
        named.extend([first] if plural == "" else [part for part in (first, second) if part])
    places = [place for place in (first_match(CUTOUT_PLACES, w) for w in named) if place]
    # An asymmetrical one in front is off to one side, by the neck, not a keyhole down the middle.
    if re.search(r"asymmetric(?:al)?\s+cut[- ]?outs?\s+(?:on|at)\s+(?:the\s+)?front", words, I):
        places = ["front_side" if place == "front" else place for place in places]
    if re.search(r"open[- ]back|backless|low[- ]back|cut[- ]?out back", words, I):
        places.append("back")
    if re.search(r"keyhole", words, I):
        places.append("front")
    if keyhole_back:
        places.append("back_keyhole")
    if not places and re.search(r"cut[- ]?outs?", words, I):
        places.append("waist")
    return list(dict.fromkeys(places))


# (Mesh inside it, a lining or a shelf bra's, doesn't make a dress see-through.)
MESH_INSIDE = re.compile(r"(?:lined|lining)\s+(?:\w+\s+){0,3}(?:power\s+)?mesh|(?:power\s+)?mesh\s+(?:lining|lined|panels?|inserts?|bra)|power mesh", I)


def sheer(words):
    words = MESH_INSIDE.sub(" ", words)
    if not re.search(r"sheer|\bmesh\b|tulle", words, I):
        return None
    place = re.search(r"sheer\s+(\w+)", words, I)
    return [first_match(SHEER_PLACES, place.group(1) if place else "") or "all", "semi" if re.search(r"semi[- ]?sheer", words, I) else "sheer"]


def read(product: dict) -> dict:
    """product: {name, category, description, fabric}."""
    name = joined(product, "name", "category")
    words = " ".join([name, text(product.get("description")), text(product.get("fabric"))])
    named_sleeves = first_match(SLEEVES, name) or first_match(SLEEVES, words)
    # "Off Shoulder" in its name and "asymmetrical off-shoulder neckline" in its description: off one shoulder.
    if named_sleeves == "strapless" and OFF_ONE_SHOULDER.search(words):
        named_sleeves = "one_shoulder"
    # An off-shoulder neckline over sleeves: long sleeves under a wide, straight neckline, not a strapless dress.
    off_shoulder_sleeved = named_sleeves == "strapless" and bool(OFF_SHOULDER.search(words)) and bool(SLEEVED.search(words))
    if off_shoulder_sleeved:
        named_sleeves = "long"
    sleeves = named_sleeves or "none"
    shares = fibre_shares(presence(product.get("fabric")) or product.get("description"))
    stretch = bool(STRETCH.search(words)) or sum(shares.get(fibre, 0.0) for fibre in STRETCHY) >= 3
    said_length = re.search(r"\b(mini|midi|maxi|knee)[- ]length\b", text(product.get("description")), I)
    sheer_read = sheer(words)
    cut = {
        "sleeves": sleeves,
        "neckline": first_match(NECKLINES, words) or ("straight" if off_shoulder_sleeved else None)
        or {"strapless": "straight", "thin_straps": "scoop", "straps": "scoop", "one_shoulder": "straight"}.get(sleeves, "round"),
        # Its own name first, then its description: a "Midi Skirt" filed under Maxi Skirts is a midi.
        "length": first_match(LENGTHS, product.get("name")) or (said_length.group(1).lower() if said_length else None)
        or first_match(LENGTHS, name) or first_match(LENGTHS, words) or "knee",
        "fit": first_match(FITS, SLEEVE_FLARE.sub(" ", HEM_FLARE.sub(" ", words))) or ("fitted" if stretch else "slim"),
        "hem_flare": bool(HEM_FLARE.search(words)),
        "collar": bool(SHIRT_COLLAR.search(words)),
        "stretch": stretch,
        "fabric": fabric(words, stretch, shares),
        "printed": bool(PRINTED.search(words)),
        "cutouts": cutouts(words),
        "sheer": sheer_read[0] if sheer_read else None,
        "sheer_kind": sheer_read[1] if sheer_read else None,
        "scarf": ("side" if re.search(r"scarf\s+(?:on|at)\s+the\s+side|side scarf", words, I) else "neck") if re.search(r"scarf", words, I) else None,
        "flounce": bool(FLOUNCE.search(words)),
        "tiers": tiers(words),
        "pleats": bool(PLEATED.search(words)),
        "slit": "sides" if SIDE_SLITS.search(words) else "side" if SIDE_SLIT.search(words) else None,
        "belt": "tie" if TIE_BELT.search(words) else "buckle" if BELT.search(words) else "tie" if WRAP.search(words) else None,
    }
    # What the 3D view doesn't draw (cut-outs, sheer parts and scarves it does; a flounce, a side slit and a belt
    # too: ruffles elsewhere, a front slit and a tie that isn't a belt it doesn't).
    drawn = ["cut-outs", "sheer panels", "scarf"]
    if cut["flounce"] and not re.search(r"ruffle|frill", FLOUNCE.sub(" ", words), I):
        drawn.append("ruffles")
    if cut["slit"]:
        drawn.append("slit")
    if cut["belt"]:
        drawn.append("belt")
    if cut["belt"] == "tie" and not dict(DETAILS)["tie"].search(TIE_BELT.sub(" ", words)):
        drawn.append("tie")
    cut["details"] = [detail for detail, pattern in DETAILS if pattern.search(words) and detail not in drawn]
    shape = product.get("dress_shape")
    told_length = bool(first_match(LENGTHS, product.get("name")) or said_length)
    return with_photo(cut, shape, words, named_sleeves, told_length=told_length) if shape else cut


def with_photo(cut, shape, words, named_sleeves, told_length=True):
    """The cut, its shape from its photo where the photo is clear (the words still give its cloth, its back and
    what's on it)."""
    cut = dict(cut)
    # (Not over sleeves the words name: a "short sleeve" polo dress's collar is narrow at the top too.)
    if shape.get("halter") and named_sleeves not in ("strapless", "one_shoulder", "long", "short"):
        cut["sleeves"] = "halter"
    elif shape.get("strapless") and named_sleeves is None:
        cut["sleeves"] = "strapless"
    elif shape.get("sleeves") and (named_sleeves is None or cut["sleeves"] == "none"):
        cut["sleeves"] = shape["sleeves"]
    # A dress only the shop's category calls a maxi, and its photo shows short: the photo's length.
    if not told_length and cut["length"] == "maxi" and shape.get("length"):
        cut["length"] = "mini" if shape["length"] < 3 else "midi" if shape["length"] < 3.4 else "maxi"
    if not (shape.get("hem") and shape.get("waist")):
        return cut
    flounce = bool(FLOUNCE.search(words))
    hem = min(shape.get("hips") or shape["hem"], shape["hem"]) if flounce else shape["hem"]
    flare_from = None if flounce else shape.get("flare_from")
    if flare_from == "waist":
        if hem >= 1.2:
            cut["fit"] = "flared"
            cut["waist_flare"] = True
    elif flare_from == "hips":
        if hem >= 1.3:
            cut["fit"] = "flared"
    elif flare_from == "knee":
        cut["hem_flare"] = True
    else:
        # Straight in its photo, whatever the words say about a flare.
        if cut["fit"] == "flared" and hem < 1.15:
            cut["fit"] = "fitted" if cut["stretch"] else "slim"
    parts = {"waist": shape.get("waist"), "waist_at": shape.get("waist_at"), "hips": shape.get("hips"), "hem": rnd(hem, 3),
             "neck_depth": shape.get("neck_depth"), "neck_width": shape.get("neck_width")}
    cut["shape"] = {key: value for key, value in parts.items() if value is not None}
    return cut


# A material line's fibres and their shares ("77% Viscose / 15% Nylon / 8% Silk" is {"viscose": 77, "nylon": 15,
# "silk": 8}), from its first part only: a contrast cloth, a lining or a trim after it isn't what most of it is.
FIBRES = [("elastane", re.compile(r"elastane|spandex|lycra", I)), ("polyurethane", re.compile(r"polyurethane|\bpu\b", I)), ("silk", re.compile(r"silk", I)),
          ("viscose", re.compile(r"viscose|rayon|modal|lyocell|tencel|cupro", I)), ("nylon", re.compile(r"nylon|polyamide", I)),
          ("polyester", re.compile(r"polyester", I)), ("cotton", re.compile(r"cotton", I)), ("wool", re.compile(r"wool|cashmere|merino|alpaca|mohair", I)),
          ("linen", re.compile(r"linen", I)), ("acrylic", re.compile(r"acrylic", I))]
STRETCHY = ("elastane", "polyurethane")


def fibre_shares(material) -> dict:
    main = re.split(r"\b(?:contrast|lining|trim|body 2|rib(?:bing)?|panel|embroidery|pocketing)\b", text(material), maxsplit=1, flags=I)[0]
    out = {}
    for share, fibre in re.findall(r"(\d{1,3}(?:\.\d+)?)\s*%\s*([a-z][a-z ]*)", main, I):
        key = first_match(FIBRES, fibre)
        if key:
            out[key] = out.get(key, 0.0) + float(share)
    return out


def fabric(words, stretch, shares=None) -> str:
    shares = shares or {}
    leather = bool(re.search(r"leather|vinyl|latex|pleather", words, I)) or shares.get("polyurethane", 0.0) >= 50 or \
        (not shares and bool(re.search(r"\bpu\b|polyurethane", words, I)))
    if leather:
        return "leather"
    if STRUCTURED.search(words):
        return "structured"
    if re.search(r"satin|chiffon|charmeuse|organza|georgette|crepe de chine", words, I):
        return "silk"
    if (shares.get("silk", 0.0) >= 30) if shares else re.search(r"silk", words, I):
        return "silk"
    # Smooth, slippery cloths that hang like silk: a nylon slip, a sequinned or viscose dress.
    if not stretch and re.search(r"\bnylon\b|viscose|rayon|cupro|lyocell|tencel|modal|sequin|slip dress", words, I):
        return "silk"
    if stretch and not re.search(r"\bknit(?:ted)?\b|jersey|ribbed|rib[- ]knit", words, I):
        return "stretch"
    if stretch:
        return "jersey"
    return "cotton"


# The body (cm) each women's size is for: [bust, waist, hips].
LETTERS = {
    "XXS": [78, 60, 86], "XS": [82, 64, 90], "S": [87, 69, 95], "M": [92, 74, 100], "L": [98, 80, 106],
    "XL": [104, 86, 112], "XXL": [110, 92, 118], "XXXL": [116, 98, 124], "4XL": [122, 104, 130],
}
LETTER_NAMES = {"2XS": "XXS", "2XL": "XXL", "3XL": "XXXL", "XXXXL": "4XL"}
# Some brands number their sizes 0 to 3 (or 4): XS to L (or XL).
BRAND_NUMBERS = ["XS", "S", "M", "L", "XL"]


def body_for(name, all_names=()):
    """A size's body, from its name: a letter size, a US dress size (00 to 24), or a brand's 0-3 number when the
    sizes run 0 to 3 or 4. None when the name isn't any of these."""
    found = re.match(r"(\d?X*[SML]|XX?S|00|\d{1,2})\b", text(name).upper().strip())
    if not found:
        return None
    label = LETTER_NAMES.get(found.group(1), found.group(1))
    if label in LETTERS:
        return LETTERS[label]
    numbers = [int(n) for n in (text(other).strip() for other in all_names) if re.fullmatch(r"\d{1,2}", n)]
    # (As Ruby's to_i: the digits it starts with, else 0.)
    n = -2 if label == "00" else int(re.match(r"\d*", label).group(0) or 0)
    if numbers and max(numbers) <= 4 and label != "00" and n < len(BRAND_NUMBERS):
        return LETTERS[BRAND_NUMBERS[n]]
    # US dress sizes: a 0 is for about an 81 cm bust; each size up adds about 1.3 cm, then 1.9 cm from a 10.
    bust_in = 32 + n * 0.5 if n <= 10 else 37 + (n - 10) * 0.75
    bust = rnd(bust_in * 2.54, 1)
    return [bust, rnd(bust - 18, 1), rnd(bust + 8, 1)]


# How much bigger (cm) than the body each fit is made, or for a stretch cloth how much of the body it is.
EASE = {"fitted": [3, 3, 4], "slim": [6, 6, 6], "relaxed": [14, 16, 14], "flared": [6, 6, 14]}
STRETCH_SHARE = 0.95
# Length from the shoulder's high point (or, strapless, from the top edge) at size M, cm.
LENGTHS_CM = {"mini": 80, "knee": 95, "midi": 112, "maxi": 140}
STRAPLESS_TOP = 18  # a strapless dress starts this far below where a strap would
STRAPLESS_BUST_EASE = 2


def usual_sizes(cut, names=()) -> Chart:
    """Every size's usual garment measurements, named as the shop names them (or XS to XL when it doesn't)."""
    names = list(dict.fromkeys(text(name) for name in names))
    names = [name for name in names if body_for(name, names)]
    if not names:
        names = ["XS", "S", "M", "L", "XL"]
    ordered = sorted(names, key=lambda name: body_for(name, names)[0])
    middle = next((i for i, name in enumerate(ordered) if body_for(name, names)[0] >= LETTERS["M"][0]), None)
    sizes = []
    for i, name in enumerate(ordered):
        bust, waist, hips = body_for(name, names)
        if cut.get("stretch") and cut.get("fit") in ("fitted", "slim"):
            chest, waist_g, hips_g = (rnd(part * STRETCH_SHARE, 1) for part in (bust, waist, hips))
        else:
            ease = EASE.get(cut.get("fit"), EASE["slim"])
            chest, waist_g, hips_g = (rnd(part + more, 1) for part, more in zip((bust, waist, hips), ease))
        # A strapless dress is held up by its bust: cut close there whatever its fit below.
        if cut.get("sleeves") == "strapless":
            chest = min(chest, bust + STRAPLESS_BUST_EASE)
        step = i - (middle or 0)
        length = LENGTHS_CM.get(cut.get("length"), 95) + step - (STRAPLESS_TOP if cut.get("sleeves") == "strapless" else 0)
        sleeve = {"long": 59 + step * 0.5, "short": 14 + step * 0.3}.get(cut.get("sleeves"))
        shoulders = rnd(37 + (bust - 92) * 0.2, 1) if cut.get("sleeves") in ("long", "short") else None
        sizes.append({"name": name, "chest": chest, "waist": waist_g, "hips": hips_g, "shoulders": shoulders,
                      "sleeve": rnd(sleeve, 1) if sleeve is not None else None, "length": rnd(length, 1)})
    missing = [part for part in ("shoulders", "sleeve") if all(size[part] is None for size in sizes)]
    return Chart(sizes=sizes, unit="cm", kind="sizes", missing=[part for part in missing if part not in not_needed(cut)])


def not_needed(cut) -> list:
    """What a dress's chart needn't give: sleeves and shoulders when it has none."""
    return [] if cut.get("sleeves") in ("short", "long") else ["sleeve", "shoulders"]
