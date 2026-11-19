"""Turns a size chart table (rows of cell text, from a web page or pasted) into finished garment measurements per
size, in centimetres, for a jacket or coat (chest, waist, shoulders, sleeve, length) or trousers (waist, seat, thigh,
inseam, leg opening).

Shops write charts many ways: sizes as rows or as columns, inches or cm, "pit to pit" half widths, ranges like
"38-40", and either the garment's own measurements or the body it's meant to fit. This works out which, and converts
body charts to estimated garment measurements.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace

from ..util import blank, num_text, presence, rnd, squish, text, truncate

I = re.I

# For each kind of garment: its columns (checked in order, so "Sleeve length" is a sleeve and "Inside leg" an
# inseam), the one a chart must have, the believable range for it in cm, and the ease a regular cut adds to a body
# chart's numbers.
SCHEMES = {
    "jacket": {
        "columns": {
            "chest": re.compile(r"chest|bust|pit|p2p", I),
            "waist": re.compile(r"waist", I),
            "shoulders": re.compile(r"shoulder", I),
            "sleeve": re.compile(r"sleeve|\barm\b", I),
            "length": re.compile(r"length|back|nape", I),
        },
        "key": "chest", "plausible": (70, 180), "inches_below": 70,
        "body_to_garment": {"chest": 11, "waist": 12.5, "shoulders": 0.75, "sleeve": -1.5},
    },
    "trousers": {
        "columns": {
            "waist": re.compile(r"waist", I),
            "seat": re.compile(r"seat|hip", I),
            "thigh": re.compile(r"thigh", I),
            "inseam": re.compile(r"inseam|inside leg|inner leg|leg length", I),
            "leg_opening": re.compile(r"opening|hem|bottom|ankle|cuff", I),
            "rise": re.compile(r"\brise\b", I),
            # A skirt's (or shorts') length from the waist.
            "length": re.compile(r"length|\blong\b", I),
        },
        "key": "waist", "plausible": (55, 160), "inches_below": 52,
        "body_to_garment": {"waist": 2.5, "seat": 6},
    },
}
HALF = re.compile(r"pit|p2p|half|flat|across", I)
BODY_WORDS = re.compile(r"body measure|to fit|fits chest|fits waist|your (?:chest|waist|measure)|body size", I)
GARMENT_WORDS = re.compile(r"garment|finished|laid flat|product measure|item measure|flat measure", I)
WIDTHS = ("chest", "waist", "seat", "thigh", "leg_opening")

# A chart that says its sleeves run from the centre of the back of the neck ("sleeve from CB", "centre back
# sleeve", "sleeve length (from center back)"), in the sleeve column's label or the text round it.
CENTRE_BACK = r"\b(?:cb|c\.b\.|cbn|centre[- ]?back|center[- ]?back|back of (?:the )?neck|nape)(?![a-z])"
CENTRE_BACK_RE = re.compile(CENTRE_BACK, I)
LETTER_SIZE = re.compile(r"\A(X{0,3}S|M|X{0,3}L|[2-6]XL)\Z", I)


@dataclass(frozen=True)
class Chart:
    """sleeve_from: where the chart's sleeve is measured from, when it isn't the shoulder seam: "centre_back" (the
    chart says so), or "centre_back_guessed" (its sleeves are too long to be from the shoulder). The sizes then hold
    the sleeve from the shoulder seam, converted once. unused: the header's labels that weren't read as any
    measurement ("Hem", "Rise" on a jacket's chart), so a pasted chart can say what it left out."""

    sizes: list
    unit: str
    kind: str
    missing: list
    sleeve_from: str | None = None
    unused: list | None = field(default=None)

    def with_(self, **changes) -> "Chart":
        return replace(self, **changes)

    def as_json(self) -> dict:
        out = {"sizes": self.sizes, "unit": self.unit, "kind": self.kind, "missing": self.missing}
        if self.sleeve_from:
            out["sleeve_from"] = self.sleeve_from
        if self.unused:
            out["unused"] = self.unused
        return out


def scheme_for(garment) -> str:
    return "trousers" if text(garment) == "trousers" else "jacket"


def measures(garment) -> list:
    return list(SCHEMES[scheme_for(garment)]["columns"].keys())


def read(rows, context="", single=False, garment="jacket"):
    return ChartReader(rows, context, single=single, garment=garment).read()


def number(value):
    """"38", "38.5", "38,5", "38 ½", "38 1/2", "38-40" (the middle), "97cm"."""
    words = text(value).replace(",", ".")
    words = words.replace("½", ".5").replace("¼", ".25").replace("¾", ".75")

    def fraction(m):
        whole, top, bottom = int(m.group(1)), float(m.group(2)), int(m.group(3))
        part = top / bottom if bottom else float("inf")
        return num_text(whole + part)

    words = re.sub(r"(\d+)\s+(\d)/(\d)", fraction, words)
    words = re.sub(r"(\d)\s+\.(\d)", r"\1.\2", words)
    found = re.search(r"(\d+(?:\.\d+)?)\s*(?:-|–|—|to)\s*(\d+(?:\.\d+)?)", words)
    if found:
        return (float(found.group(1)) + float(found.group(2))) / 2
    found = re.search(r"\d+(?:\.\d+)?", words)
    return float(found.group(0)) if found else None


class ChartReader:
    # A size conversion chart (S, M, L against US, UK, EU or IT sizes) has no measurements, but a men's US or UK
    # jacket size is the chest it fits in inches, and an Italian or French one is half of it in cm. Read as a body
    # chart of chests: kind "sizes".
    SIZE_SYSTEMS = [(re.compile(r"\A(US|UK)\b", I), 2.54), (re.compile(r"\A(IT|FR)\b", I), 2.0)]

    def __init__(self, rows, context, single=False, garment="jacket"):
        """single: the table is one item's own measurements (a resale listing), so one size is enough and the
        numbers are the garment's. garment: "jacket", "coat" or "trousers"."""
        self.single = single
        self.scheme = SCHEMES[scheme_for(garment)]
        self.columns = self.scheme["columns"]
        self.key = self.scheme["key"]
        self.rows = [row for row in ([squish(cell) for cell in row] for row in rows) if not all(blank(cell) for cell in row)]
        self.context = text(context)

    def read(self):
        """A Chart, or None if the table isn't a size chart for this kind of garment."""
        table = self.oriented()
        if table is None:
            return self.conversion()
        header, body = table[0], table[1:]
        columns = self.map_columns(header)
        if self.key not in columns or len(body) < (1 if self.single else 2):
            return None
        unit = self.detect_unit(header, columns, body)
        raw = [size for size in (self.raw_size(row, columns, header) for row in body) if size]
        if len(raw) < (1 if self.single else 2):
            return None
        raw = self.flat_widths(raw, unit)
        kind = "garment" if self.single else self.detect_kind(raw, unit)
        sizes = [self.to_garment_cm(size, unit, kind) for size in raw]
        low, high = self.scheme["plausible"]
        if not all(size.get(self.key) is not None and low <= size[self.key] <= high for size in sizes):
            return None
        used = [col["index"] for col in columns.values()]
        unused = [label for i, label in enumerate(header) if i > 0 and i not in used and not LETTER_SIZE.search(label) and presence(label)]
        return Chart(sizes=sizes, unit=unit, kind=kind, missing=[key for key in self.columns if key not in columns],
                     sleeve_from=self.sleeve_from(columns), unused=unused[:8])

    def oriented(self):
        """Sizes as rows, with measurements across the top. Transposes charts written the other way round."""
        if len(self.rows) < 2:
            return None
        width = max(len(row) for row in self.rows)
        rows = [row + [""] * (width - len(row)) for row in self.rows]
        flipped = [list(column) for column in zip(*rows)]
        if self.measurement_labels(rows[0]) >= 2:
            return rows
        if self.measurement_labels([row[0] for row in rows]) >= 2:
            return flipped
        # A table of sizes with just the one measurement that matters (a chest, or a waist), as conversion tables in
        # size guides often have.
        if self.key_label(rows[0]):
            return rows
        if self.key_label([row[0] for row in rows]):
            return flipped
        return None

    def sleeve_from(self, columns):
        """"centre_back" when the chart says its sleeve runs from the back of the neck: in the sleeve column's own
        label ("Sleeve from CB"), or in the words round the table. (A "centre back length" is a length.)"""
        if "sleeve" not in columns:
            return None
        if CENTRE_BACK_RE.search(columns["sleeve"]["label"]):
            return "centre_back"
        if re.search(r"sleeve[^.;\n]{0,40}" + CENTRE_BACK, self.context, I) or re.search(CENTRE_BACK + r"[^.;\n]{0,24}sleeve", self.context, I):
            return "centre_back"
        return None

    def measurement_labels(self, cells) -> int:
        return sum(1 for cell in cells if any(pattern.search(cell) for pattern in self.columns.values()))

    def key_label(self, cells) -> bool:
        return any(self.columns[self.key].search(cell) for cell in cells[1:]) and len(self.rows) >= 3

    def map_columns(self, header) -> dict:
        columns = {}
        order = sorted(self.columns.keys(), key=lambda key: 0 if key in ("sleeve", "inseam") else 1)
        for index, label in enumerate(header):
            if index == 0:
                continue
            key = next((key for key in order if self.columns[key].search(label)), None)
            if key is None or key in columns:
                continue
            columns[key] = {"index": index, "half": key in WIDTHS and bool(HALF.search(label)), "label": label}
        return columns

    def flat_widths(self, raw, unit):
        """Charts often give chests and waists measured flat, straight across, without saying so. When the main
        measurement is too small for a whole way round but right for half of it, double the widths."""
        found = sorted(size[self.key] for size in raw if size.get(self.key) is not None)
        middle = len(raw) // 2
        key = found[middle] if middle < len(found) else None
        low, high = self.scheme["plausible"]
        if key is None or not (self.to_cm(key, unit) < low and low <= self.to_cm(key, unit) * 2 <= high):
            return raw
        return [{k: (v * 2 if k in WIDTHS and v else v) for k, v in size.items()} for size in raw]

    def raw_size(self, row, columns, header=()):
        name = truncate(row[0] if row else "", 20, omission="")
        if blank(name) or any(pattern.search(name) for pattern in self.columns.values()):
            return None
        # Size guides list several systems side by side; lead with the letter size shops sell by.
        taken = [col["index"] for col in columns.values()]
        letter = next((cell for i, cell in enumerate(row) if i > 0 and i not in taken and LETTER_SIZE.search(cell)), None)
        if letter and not LETTER_SIZE.search(name):
            system = re.search(r"\b(FR|IT|EU|UK|US)\b", text(header[0] if header else ""))
            name = truncate(f"{letter} / " + " ".join(part for part in (system.group(0) if system else None, name) if part is not None), 20, omission="")
        values = {}
        for key, col in columns.items():
            n = number(row[col["index"]] if col["index"] < len(row) else None)
            values[key] = n * 2 if n is not None and col["half"] else n
        if values.get(self.key) is None:
            return None
        return {"name": name, **values}

    def detect_unit(self, header, columns, body) -> str:
        labels = " ".join(header)
        values = " ".join(cell for row in body for cell in row)
        if re.search(r"\d\s*cm\b", values, I):
            return "cm"
        if re.search(r"\d\s*(?:\"|”|in\b|inch)", values, I):
            return "in"
        if re.search(r"\bcm\b|centim", labels, I):
            return "cm"
        if re.search(r"\binch|\(in\)|\bin\.|\"", labels, I):
            return "in"
        if re.search(r"\bcm\b|centim", self.context, I) and not re.search(r"\binch", self.context, I):
            return "cm"
        if re.search(r"\binch", self.context, I) and not re.search(r"\bcm\b", self.context, I):
            return "in"
        index = columns[self.key]["index"]
        found = sorted(n for n in (number(row[index] if index < len(row) else None) for row in body) if n is not None)
        middle = len(body) // 2
        typical = found[middle] if middle < len(found) else 0.0
        limit = self.scheme["inches_below"] / (2.0 if columns[self.key]["half"] else 1)
        return "cm" if typical > limit else "in"

    def detect_kind(self, sizes, unit) -> str:
        """Body charts usually give the chest (or waist) a garment is meant for, which matches its size number: a
        US 40 jacket fits a 40 in chest, an EU 50 a 100 cm chest, a 32 trouser a 32 in waist."""
        if BODY_WORDS.search(self.context):
            return "body"
        if GARMENT_WORDS.search(self.context):
            return "garment"
        # And it grows as its size numbers do: 2.54 cm a size for inches, 2 cm for an EU or Italian size. (EU garment
        # chests can land near a size number in inches by chance: an Armani 54 jacket is 139 cm round.)
        numbered = []
        for size in sizes:
            digits = re.search(r"\d+", size["name"])
            if digits and size.get(self.key) is not None:
                numbered.append((int(digits.group(0)), self.to_cm(size[self.key], unit)))
        numbered.sort()
        slope = None
        if len(numbered) >= 3 and numbered[-1][0] > numbered[0][0]:
            slope = (numbered[-1][1] - numbered[0][1]) / float(numbered[-1][0] - numbered[0][0])
        matches = 0
        for size in sizes:
            digits = re.search(r"\d+", size["name"])
            if not digits:
                continue
            label = int(digits.group(0))
            cm = self.to_cm(size[self.key], unit)
            inches = abs(cm - label * 2.54) <= 2.6 and (slope is None or abs(slope - 2.54) < 0.2)
            eu = self.key == "chest" and abs(cm - label * 2) <= 4 and (slope is None or abs(slope - 2) < 0.2)
            if inches or eu:
                matches += 1
        return "body" if matches >= len(sizes) / 2.0 else "garment"

    def to_garment_cm(self, size, unit, kind) -> dict:
        out = {"name": size["name"]}
        for key in self.columns:
            cm = self.to_cm(size[key], unit) if size.get(key) is not None else None
            if cm is not None and kind == "body":
                cm += self.scheme["body_to_garment"].get(key, 0)
            out[key] = rnd(cm) if cm is not None else None
        return out

    @staticmethod
    def to_cm(value, unit):
        return value * 2.54 if unit == "in" else value

    def conversion(self):
        if self.single or self.key != "chest" or len(self.rows) < 3:
            return None
        header, body = self.rows[0], self.rows[1:]
        for system, cm_per_size in self.SIZE_SYSTEMS:
            column = next((i for i, cell in enumerate(header) if system.search(cell)), None)
            if not column:
                continue
            sizes = []
            for row in body:
                n = number(row[column] if column < len(row) else None)
                if n is None:
                    continue
                chest = n * cm_per_size
                if not 76 <= chest <= 142:
                    continue
                names = []
                for part in (row[0] if row else None, f"{header[column]} {row[column] if column < len(row) else ''}"):
                    if part not in names:
                        names.append(part)
                name = truncate(" / ".join(text(part) for part in names), 20, omission="")
                sizes.append(self.to_garment_cm({"name": name, "chest": chest}, "cm", "body"))
            if len(sizes) >= 3:
                return Chart(sizes=sizes, unit="in", kind="sizes", missing=[key for key in self.columns if key != "chest"])
        return None
