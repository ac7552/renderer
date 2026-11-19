"""The sample shop (sample_shop.py): a made-up Shopify shop this server answers for itself, so a store link can be
tried with no network. The tests run with no network too (conftest's no_network)."""

import base64
import re

import pytest

from renderer import sample_shop
from renderer.server import STATIC

from .test_api import call

HANDLES = sample_shop.handles()
# What each sample should import as, and its middle size's chart (cm), as Kiwi Sizing's chart gives it.
EXPECTED = {
    "loopwheel-pocket-tee-sage": ({"garment": "top", "style": "tee"}, "M", {"chest": 106.68, "length": 71.12, "sleeve": 20.96}),
    "heavyweight-hoodie-forest": ({"garment": "top", "style": "hoodie"}, "M", {"chest": 116.84, "length": 69.85, "sleeve": 62.23}),
    "nylon-coach-jacket-rust": ({"garment": "jacket"}, "M", {"chest": 116.84, "shoulders": 48.9}),
    "relaxed-selvedge-jean-indigo": ({"garment": "trousers", "style": "jeans"}, "31", {"waist": 82.55, "seat": 109.22, "inseam": 81.28}),
    "rib-knit-midi-slip-dress-black": ({"garment": "top", "style": "dress", "women": True}, "M", {"chest": 86.36, "waist": 71.12, "length": 114.3}),
    "pleated-mini-skirt-plum": ({"garment": "trousers", "style": "skirt", "women": True}, "M", {"waist": 71.12, "length": 40.64}),
}


def test_every_sample_is_expected_and_has_its_photos():
    assert sorted(HANDLES) == sorted(EXPECTED)
    for handle in HANDLES:
        for picture in sample_shop.find(handle)["images"]:
            data = (STATIC / sample_shop.PHOTOS / picture["file"]).read_bytes()
            assert data[:3] == b"\xff\xd8\xff" and len(data) < 2_500_000


def test_answers_as_a_shopify_shop_does():
    meta = call("GET", "/meta.json").json()
    assert re.fullmatch(r"[a-z0-9-]+\.myshopify\.com", meta["myshopify_domain"])

    product = call("GET", "/products/heavyweight-hoodie-forest.json", host="127.0.0.1:8000").json()["product"]
    assert product["handle"] == "heavyweight-hoodie-forest"
    assert product["options"] == [{"id": product["options"][0]["id"], "product_id": product["id"], "name": "Size", "position": 1,
                                   "values": ["S", "M", "L", "XL", "XXL"]}]
    assert [v["title"] for v in product["variants"]] == ["S", "M", "L", "XL", "XXL"]
    # Its photos at this server's own address, as the page's browser reached it.
    assert [image["src"] for image in product["images"]] == [
        "http://127.0.0.1:8000/sample_shop/heavyweight-hoodie-forest-front.jpg",
        "http://127.0.0.1:8000/sample_shop/heavyweight-hoodie-forest-back.jpg",
    ]
    photo = call("GET", "/sample_shop/heavyweight-hoodie-forest-front.jpg")
    assert photo.status == 200 and photo.headers["Content-Type"] == "image/jpeg"

    page = call("GET", "/products/heavyweight-hoodie-forest")
    assert page.status == 200 and "Heavyweight Hoodie - Forest" in page.body.decode()
    assert "Not a real shop" in page.body.decode()


def test_unknown_products_are_not_found():
    assert call("GET", "/products/no-such-thing").status == 404
    assert call("GET", "/products/no-such-thing.json").status == 404


@pytest.mark.parametrize("handle", HANDLES)
def test_imports_each_sample_with_no_network(handle):
    said, size, measured = EXPECTED[handle]
    response = call("POST", "/api/v1/garment_imports", {"url": f"http://127.0.0.1:8000/products/{handle}"})

    assert response.status == 200, response.json()
    garment = response.json()["garment"]
    for key, value in said.items():
        assert garment[key] == value, key
    # The chart Kiwi Sizing would give, not the kind's usual sizes.
    sizes = {s["name"]: s for s in garment["chart"]["sizes"]}
    assert list(sizes) == sample_shop.find(handle)["sizes"]
    for key, value in measured.items():
        assert sizes[size][key] == pytest.approx(value, abs=0.01), key
    # And the shop's photo, read from disk.
    assert garment["photo"].startswith("data:image/jpeg;base64,")
    assert garment["source_url"] == f"http://127.0.0.1:8000/products/{handle}"


def test_the_hoodie_comes_with_its_back():
    garment = call("POST", "/api/v1/garment_imports", {"url": "http://127.0.0.1:8000/products/heavyweight-hoodie-forest"}).json()["garment"]
    assert garment["back_photo"].startswith("data:image/jpeg;base64,")
    assert garment["back_photo"] != garment["photo"]


def test_the_page_s_own_reading_gets_the_shop_s_chart():
    # The page reads the shop itself (its product, its photos and their shapes) and can't reach Kiwi Sizing offline:
    # the server adds the chart, and keeps what the page read.
    handle = "loopwheel-pocket-tee-sage"
    product = call("GET", f"/products/{handle}.json").json()["product"]
    photo = "data:image/jpeg;base64," + base64.b64encode((STATIC / sample_shop.PHOTOS / f"{handle}-front.jpg").read_bytes()).decode()
    shop_data = {"product": product, "shop": sample_shop.shop()["myshopify_domain"], "sizing": None, "photo": photo,
                 "shape": {"length": 1.34, "waist": 0.98, "hem": 0.99, "sleeve": 0.42, "sleeveDown": 0.12, "armpit": 0.3}}
    garment = call("POST", "/api/v1/garment_imports", {"url": f"http://127.0.0.1:8000/products/{handle}", "shop_data": shop_data}).json()["garment"]

    assert garment["photo"] == photo
    assert {s["name"]: s["chest"] for s in garment["chart"]["sizes"]}["M"] == pytest.approx(106.68)


def test_another_site_s_products_are_that_site_s():
    # The same path on another address is that shop's, asked as any other link (and private ones aren't asked).
    response = call("POST", "/api/v1/garment_imports", {"url": "http://10.0.0.1/products/heavyweight-hoodie-forest"})
    assert response.json()["error"] == "fetch_failed"


def test_the_page_offers_the_sample_shop():
    page = call("GET", "/").body.decode()
    for handle in HANDLES:
        assert f'data-path="/products/{handle}"' in page
