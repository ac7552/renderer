"""A maker's size chart: the finished measurements of each size, in centimetres. Charts describe garments, never the
person using the page, so they're the only data the renderer keeps (as files that ship with it)."""

from __future__ import annotations

import json
import re
from pathlib import Path

from . import fit

DIR = Path(__file__).parent / "data" / "size_charts"
MEASUREMENTS = fit.SIZE_MEASUREMENTS
NAVY = "#1f2a4a"


class NotFound(Exception):
    pass


class SizeChart:
    def __init__(self, key, data):
        self.key = key
        self.name = data["name"]
        self.garment = data["garment"]
        self.source = data["source"]
        self.sizes = [{k: size[k] for k in ("name", *MEASUREMENTS) if k in size} for size in data["sizes"]]
        # How the 3D view draws it, when the chart says (see garment_import): its style, cloth and colour.
        self.style = data.get("style")
        self.fabric = data.get("fabric")
        self.color = data.get("color")
        self.color_name = data.get("color_name")
        self.cut = data.get("cut")

    def summary(self) -> dict:
        return {"key": self.key, "name": self.name, "garment": self.garment, "source": self.source}

    def as_garment(self) -> dict:
        """The same shape an imported garment has, so clients treat built-in and imported clothes alike."""
        out = {"name": self.name, "brand": None, "color_name": self.color_name or "Navy", "color": self.color or NAVY, "source_url": None,
               "garment": self.garment}
        out.update({key: value for key, value in (("style", self.style), ("fabric", self.fabric), ("cut", self.cut)) if value is not None})
        out["chart"] = {"sizes": self.sizes, "unit": "cm", "kind": "garment",
                        "missing": [m for m in MEASUREMENTS if not any(size.get(m) for size in self.sizes)]}
        return out

    def as_json(self) -> dict:
        return {**self.summary(), "sizes": self.sizes}


def find(key) -> SizeChart:
    path = DIR / f"{key}.json"
    if not (isinstance(key, str) and re.fullmatch(r"[a-z0-9_]+", key) and path.exists()):
        raise NotFound(f"no size chart named {key}")
    return SizeChart(key, json.loads(path.read_text()))


def all_charts() -> list:
    return [find(path.stem) for path in sorted(DIR.glob("*.json"))]
