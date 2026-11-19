"""The JSON API: what the fitting room page asks the server. Every answer is worked out from the request alone; the
measurements in a request are used for that one answer and never kept, logged or cached.

Each handler takes the request's parameters (a dict, from its JSON body and its query string) and returns
(status, body, headers): body is a dict to send as JSON, or bytes with a Content-Type header.
"""

from __future__ import annotations

import hashlib
import re

from . import fit, shoes, size_charts
from . import garment_import as gi
from .cache import TTLCache
from .garment_import import chart_reader, fetcher
from .util import number, presence, rnd, text

UNITS = {"cm": 1, "in": 2.54}
MAX_SIZES = 60
DETAILS = ("stretch", "sleeves", "fit", "women", "cropped", "snug", "dropped", "elastic", "hem", "ends")
NO_STORE = {"Cache-Control": "no-store"}
# A photo this big is more than any shop's product shot.
PROXY_IMAGE_BYTES = 8_000_000
# Raster images only: an SVG served from here could carry a script on this origin.
PROXY_IMAGE_TYPES = re.compile(r"\Aimage/(?!svg)[a-z0-9.+-]+\Z")
PROXY_IMAGES = TTLCache(seconds=3600, size=128)
FALSE_WORDS = (False, 0, "0", "f", "F", "false", "FALSE", "off", "OFF")


def json_response(status, body, headers=None):
    return status, body, dict(headers or {})


def invalid(errors):
    return json_response(422, {"error": "invalid", "errors": errors})


def boolean(value):
    """A loosely given yes or no, as a form sends it: None and "" are neither."""
    if value is None or value == "":
        return None
    return not any(value == word and type(value) is type(word) for word in FALSE_WORDS)


def span_json(span):
    return {"min": span.min, "max": span.max}


# ---- GET /api/v1/fit_guide


def fit_guide(params):
    """What a client needs to build the measurements form: what to ask for, and the cuts to offer."""
    return json_response(200, {
        "units": "cm",
        "measurements": [{"key": m["key"], "label": m["label"], "help": m["help"], "optional": m.get("optional", False),
                          "min_cm": m["range"].min, "max_cm": m["range"].max, "usual_cm": span_json(m["usual"])} for m in fit.MEASUREMENTS],
        "cuts": [{"key": key, "label": cut["label"], "chest_ease_cm": span_json(cut["chest"]), "waist_ease_cm": span_json(cut["waist"])}
                 for key, cut in fit.CUTS.items()],
    })


# ---- GET /api/v1/size_charts, /api/v1/size_charts/:key


def size_chart_index(params):
    return json_response(200, {"size_charts": [chart.summary() for chart in size_charts.all_charts()]})


def size_chart_show(params, key):
    return json_response(200, size_charts.find(key).as_json())


# ---- POST /api/v1/fits, /api/v1/size_charts/:key/fits


def fits(params, chart_key=None):
    """Ranks a garment's sizes against a body: a stored chart's, or sizes sent in the request (an imported garment's).
    The response says not to cache it."""
    if text(params.get("garment")) == "shoes":
        return shoe_fits(params)
    chart = size_charts.find(chart_key) if chart_key is not None else None
    cut = text(params.get("cut", "regular"))
    garment = text(params.get("garment", "jacket"))
    unit = text(params.get("unit", "cm"))

    errors = {}
    if cut not in fit.CUTS:
        errors["cut"] = f"must be one of {', '.join(fit.CUTS)}"
    if unit not in UNITS:
        errors["unit"] = "must be cm or in"
    if garment not in gi.KINDS:
        errors["garment"] = f"must be one of {', '.join(gi.KINDS)}"
    body = read_body(params, fit.MEASUREMENTS, UNITS.get(unit, 1), errors)
    sizes = chart.sizes if chart else read_sizes(params, garment, errors)
    if errors:
        return invalid(errors)

    given = params.get("details")
    details = {key: given[key] for key in DETAILS if key in given} if isinstance(given, dict) else {}
    results = fit.rank(body, sizes, cut, garment, style=presence(text(params.get("style"))), details=details)
    return json_response(200, {
        "size_chart": chart.summary() if chart else None,
        "cut": cut,
        "garment": garment,
        "units": "cm",
        "best": results[0].size,
        "warnings": fit.warnings(body),
        "sizes": [result_json(result) for result in results],
    }, NO_STORE)


def shoe_fits(params):
    """Shoes: the foot's length (and width) against the sizes' scale. measurements: {foot, ball}; sizes: [{name}];
    scale, brand, style, fabric, width as the listing gives them."""
    unit = text(params.get("unit", "cm"))
    errors = {}
    if unit not in UNITS:
        errors["unit"] = "must be cm or in"
    foot = read_body(params, shoes.MEASUREMENTS, UNITS.get(unit, 1), errors)
    sizes = params.get("sizes")
    if not (isinstance(sizes, list) and 1 <= len(sizes) <= MAX_SIZES):
        errors["sizes"] = f"must be a list of 1 to {MAX_SIZES} sizes"
    if errors:
        return invalid(errors)

    names = [name for name in (text(size.get("name") if isinstance(size, dict) else size).strip()[:20] for size in sizes) if name]
    scale = text(params.get("scale")) if text(params.get("scale")) in shoes.SCALES else shoes.scale_for(names, women=bool(boolean(params.get("women"))))
    results = shoes.rank(foot, [{"name": name} for name in names], scale=scale, brand=presence(text(params.get("brand"))),
                         style=presence(text(params.get("style"))), fabric=presence(text(params.get("fabric"))), width=presence(text(params.get("width"))))
    if not results:
        # No size names that are sizes ("One size"): shown for the look.
        return json_response(200, {"garment": "shoes", "units": "cm", "scale": scale, "best": names[0] if names else None, "warnings": [],
                                   "sizes": [{"size": name, "verdict": "fits", "penalty": 0, "checks": []} for name in names]}, NO_STORE)
    return json_response(200, {"garment": "shoes", "units": "cm", "scale": scale, "best": results[0].size, "warnings": shoes.warnings(foot),
                               "sizes": [result_json(result) for result in results]}, NO_STORE)


def read_body(params, measurements, scale, errors):
    given = params.get("measurements")
    given = given if isinstance(given, dict) else {}
    body = {}
    for m in measurements:
        value = number(given.get(m["key"]))
        cm = value * scale if value is not None else None
        if cm is None:
            if not m.get("optional"):
                errors[m["key"]] = "is required"
        elif not m["range"].covers(cm):
            errors[m["key"]] = f"must be between {m['range'].min} and {m['range'].max} cm"
        body[m["key"]] = cm
    return body


def read_sizes(params, garment, errors):
    """Sizes sent with the request, in centimetres. The garment's main measurement (chest, or waist for trousers) is
    required; the rest can be missing."""
    keys = chart_reader.measures(garment)
    if garment == "top":
        keys = keys + ["hips"]  # a dress's
    required = keys[0]
    given = params.get("sizes")
    if not (isinstance(given, list) and 1 <= len(given) <= MAX_SIZES):
        errors["sizes"] = f"must be a list of 1 to {MAX_SIZES} sizes"
        return []
    out = []
    for index, size in enumerate(given):
        size = size if isinstance(size, dict) else {}
        name = text(size.get("name")).strip()[:20]
        if not name:
            errors[f"sizes.{index}.name"] = "is required"
        read = {}
        for key in keys:
            raw = size.get(key)
            value = number(raw) if raw is not None else None
            if value is None and raw is not None:
                errors[f"sizes.{index}.{key}"] = "must be a number"
            # (A micro short's inseam is an inch or two: only an inseam may be under 5 cm.)
            least = 0 if key == "inseam" else 5
            if value is not None and not least <= value <= 250:
                errors[f"sizes.{index}.{key}"] = f"must be between {least} and 250 cm"
            read[key] = value
        read["name"] = name
        if read[required] is None:
            errors.setdefault(f"sizes.{index}.{required}", "is required")
        out.append(read)
    return out


def result_json(result):
    return {
        "size": result.size,
        "verdict": result.verdict(),
        "penalty": result.penalty,
        "checks": [{
            "part": check.part,
            "label": check.label,
            "ease_cm": check.ease,
            "good_cm": [round_cm(check.good.min), round_cm(check.good.max)] if check.good else None,
            "status": check.status,
            "fixable": check.fixable(),
            "note": check.note,
            "fix": {"action": check.fix.action, "text": check.fix.text, "amount_cm": check.fix.amount} if check.fix else None,
        } for check in result.checks],
    }


def round_cm(value):
    return rnd(float(value))


# ---- POST /api/v1/garment_imports, GET /api/v1/garment_imports/image


def garment_imports(params, body):
    """Reads a garment from a pasted product link ({"url"}, with "shop_data" when the person's browser read a Shopify
    shop's product for it, or "page_html" when it read the page), a pasted size chart ({"text"}), or what the page
    worked out about clothes in a person's own photo ({"photo_kind", "photo_style"}; the photo stays on their
    device). Nothing about the person asking is kept."""
    try:
        if presence(params.get("url")):
            garment = gi.from_url(params["url"], shop_data=body.get("shop_data"), page_html=body.get("page_html"))
        elif presence(params.get("text")):
            garment = gi.from_text(text(params["text"])[:20_000], garment=params.get("garment"))
        elif presence(params.get("photo_kind")):
            garment = gi.from_photo(kind=params["photo_kind"], style=params.get("photo_style"))
        else:
            return json_response(422, {"error": "invalid", "message": "Send a url or the text of a size chart."})
        if garment.get("garment") == "shoes" and not gi.footwear_on():
            raise gi.not_supported("shoes")
        if garment.get("garment") == "bag" and not gi.bags_on():
            raise gi.not_supported("bags")
        return json_response(200, {"garment": garment})
    except gi.Error as error:
        return json_response(422, {"error": error.code, "message": error.message})


def garment_image(params):
    """A shop's product photo passed through this server, so the page can read its pixels when the shop's image server
    won't let a browser (no CORS header). The same checks as reading a page: public web addresses only, an image, not
    too big, not too slow. Held in memory for an hour by its address, and cacheable by the browser for as long."""
    url = text(params.get("url"))
    try:
        data, kind = PROXY_IMAGES.fetch(("image", hashlib.sha256(url.encode("utf-8")).hexdigest()),
                                        lambda: fetcher.get_image(url, max_bytes=PROXY_IMAGE_BYTES, types=PROXY_IMAGE_TYPES))
    except fetcher.Error as error:
        return json_response(422, {"error": "fetch_failed", "message": str(error)})
    return 200, data, {"Content-Type": kind, "Content-Disposition": "inline", "Cache-Control": "public, max-age=3600"}
