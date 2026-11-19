"""The page's sample shop: a made-up Shopify shop this server answers for itself, so a store link can be tried with no
network, through the same reading as a real Shopify shop's (garment_import's from_shopify) and the page's own
(fitting_room_controller.js's readShop).

It answers what a Shopify shop does, at the same addresses: a product as JSON at /products/<handle>.json, the shop's
Shopify name at /meta.json, and the product's page at /products/<handle>. Its size charts are what Kiwi Sizing (the
chart app many Shopify shops use) would answer for each product; the server hands them to the import itself, as
Kiwi's own server can't be reached offline. The products, charts and photos are invented
(data/sample_shop/products.json; the photos are drawn by script/sample_shop/photos.py).
"""

from __future__ import annotations

import base64
import html
import json
import re
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).parent / "data" / "sample_shop" / "products.json"
# Where the photos are served from, under the page's own files.
PHOTOS = "sample_shop"
PRODUCT = re.compile(r"\A/products/([a-z0-9][a-z0-9-]*)\Z")
PRODUCT_JSON = re.compile(r"\A/products/([a-z0-9][a-z0-9-]*)\.json\Z")


@lru_cache(maxsize=1)
def data() -> dict:
    return json.loads(DATA.read_text(encoding="utf-8"))


def shop() -> dict:
    return data()["shop"]


def handles() -> list:
    return [item["handle"] for item in data()["products"]]


def find(handle):
    """The product's entry in the data file, or None."""
    return next((item for item in data()["products"] if item["handle"] == handle), None)


def meta() -> dict:
    """What a Shopify shop answers at /meta.json (the parts the import reads)."""
    found = shop()
    return {"name": found["name"], "myshopify_domain": found["myshopify_domain"], "currency": found["currency"], "published_products_count": len(handles())}


def product(item, origin) -> dict:
    """A product as Shopify answers it at /products/<handle>.json. origin: this server's own ("http://127.0.0.1:8000"),
    for the photos' addresses."""
    sizes = item["sizes"]
    stamp = "2026-11-01T09:00:00-05:00"
    return {
        "id": item["id"], "title": item["title"], "handle": item["handle"], "body_html": item["body_html"],
        "vendor": item["vendor"], "product_type": item["product_type"], "tags": item["tags"],
        "created_at": stamp, "updated_at": stamp, "published_at": stamp,
        "options": [{"id": item["id"] * 10 + 1, "product_id": item["id"], "name": "Size", "position": 1, "values": sizes}],
        "variants": [{"id": item["id"] * 100 + i, "product_id": item["id"], "title": size, "option1": size, "option2": None, "option3": None,
                      "price": item["price"], "sku": f"{item['handle']}-{size}".upper(), "position": i + 1, "available": True}
                     for i, size in enumerate(sizes)],
        "images": [image(item, i, picture, origin) for i, picture in enumerate(item["images"])],
        "image": image(item, 0, item["images"][0], origin) if item["images"] else None,
    }


def image(item, index, picture, origin) -> dict:
    return {"id": item["id"] * 1000 + index, "product_id": item["id"], "position": index + 1, "alt": picture["alt"],
            "width": 1200, "height": 1500, "src": f"{origin}/{PHOTOS}/{picture['file']}"}


def sizing(item) -> dict:
    """The product's size chart as Kiwi Sizing answers it (getSizingChart): one table of cells."""
    rows = [[{"type": "single", "value": cell} for cell in row] for row in item["chart"]]
    return {"sizings": [{"tables": {"t0": {"data": rows}}}]}


def photo(item, static, index=0):
    """One of the product's photos as a data: URL (what the page sends when it has read a shop's photos), or None."""
    if index >= len(item["images"]):
        return None
    path = Path(static) / PHOTOS / item["images"][index]["file"]
    if not path.is_file():
        return None
    return "data:image/jpeg;base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def shop_data(item, origin, static, given=None) -> dict:
    """What the import reads a Shopify product from ({"product", "shop", "sizing", ...}): the page's own reading of
    the sample shop when it sent one (given: its product, photos and their shapes), with the chart Kiwi would have
    answered; else the server's, with the product's photos from disk."""
    if isinstance(given, dict):
        return {**given, "sizing": given.get("sizing") or sizing(item)}
    back = next((i for i, picture in enumerate(item["images"]) if picture["alt"].endswith(" back")), None)
    return {"product": product(item, origin), "shop": shop()["myshopify_domain"], "sizing": sizing(item),
            "photo": photo(item, static), "back_photo": photo(item, static, back) if back is not None else None}


def page(item, origin) -> str:
    """The product's page, for a person who opens the link."""
    found = product(item, origin)
    e = html.escape
    photos = "".join(f'<img src="{e(p["src"])}" alt="{e(p["alt"])}" width="360" height="450">' for p in found["images"])
    header, *rows = item["chart"]
    table = "<tr>" + "".join(f"<th>{e(cell)}</th>" for cell in header) + "</tr>" + "".join(
        "<tr>" + "".join(f"<td>{e(cell)}</td>" for cell in row) + "</tr>" for row in rows)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{e(item["title"])} · {e(shop()["name"])}</title>
  <!-- A made-up Shopify-style product page for trying Fitroom's link import with no network. Not a real shop or product. -->
  <style>
    body {{ font: 16px/1.5 Georgia, serif; max-width: 760px; margin: 40px auto; padding: 0 16px; color: #222; }}
    img {{ width: 360px; height: auto; margin: 0 8px 8px 0; background: #f2f0ec; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border-bottom: 1px solid #ddd; padding: 8px; text-align: left; }}
  </style>
</head>
<body>
  <p><em>{e(shop()["name"])}: a made-up shop for trying Fitroom offline. Not a real shop.</em></p>
  <h1>{e(item["title"])}</h1>
  <p>{e(item["vendor"])} · ${e(item["price"])}</p>
  <div>{photos}</div>
  {item["body_html"]}
  <p>Sizes: {e(", ".join(item["sizes"]))}</p>
  <h2>Size chart (inches)</h2>
  <table>{table}</table>
</body>
</html>
"""
