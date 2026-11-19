"""The JSON API, through the WSGI application as a browser would reach it."""

import io
import json
from wsgiref.util import setup_testing_defaults

import pytest

from renderer import api
from renderer.garment_import import fetcher
from renderer.server import App

MEASUREMENTS = {"chest": 40, "waist": 34, "shoulders": 18, "arm": 25.75, "height": 70}


class Response:
    def __init__(self, status, headers, body):
        self.status = int(status.split(" ", 1)[0])
        self.headers = dict(headers)
        self.body = body

    def json(self):
        return json.loads(self.body)


def call(method, path, body=None, query="", host="127.0.0.1:8000"):
    data = json.dumps(body).encode() if body is not None else b""
    environ = {"REQUEST_METHOD": method, "PATH_INFO": path, "QUERY_STRING": query, "HTTP_HOST": host,
               "CONTENT_LENGTH": str(len(data)), "CONTENT_TYPE": "application/json", "wsgi.input": io.BytesIO(data)}
    setup_testing_defaults(environ)
    found = {}

    def start_response(status, headers):
        found["status"], found["headers"] = status, headers

    chunks = App()(environ, start_response)
    return Response(found["status"], found["headers"], b"".join(chunks))


def post_fit(params, chart="sample_suit_jacket"):
    return call("POST", f"/api/v1/size_charts/{chart}/fits", params)


@pytest.fixture(autouse=True)
def fresh_images():
    api.PROXY_IMAGES.clear()


def test_ranks_sizes_for_a_body_in_inches():
    response = post_fit({"unit": "in", "cut": "regular", "measurements": MEASUREMENTS})

    assert response.status == 200
    assert response.headers["Cache-Control"] == "no-store"
    found = response.json()
    assert found["best"] == "40R"
    assert found["units"] == "cm"
    assert len(found["sizes"]) == 18
    assert [check["part"] for check in found["sizes"][0]["checks"]] == ["shoulders", "chest", "waist", "sleeve", "length"]
    # Each check says the range of ease that fits for the cut, so the page can show where a size falls in it.
    best = {check["part"]: check for check in next(size for size in found["sizes"] if size["size"] == "40R")["checks"]}
    chest = best["chest"]
    assert len(chest["good_cm"]) == 2
    assert chest["good_cm"][0] < chest["good_cm"][1]
    assert best["sleeve"]["good_cm"] == [-1.0, 1.0]


def test_explains_whats_missing_or_out_of_range():
    response = post_fit({"unit": "cm", "measurements": {"chest": 101, "waist": 86, "shoulders": 3, "arm": 65}})

    assert response.status == 422
    errors = response.json()["errors"]
    assert errors["height"] == "is required"
    assert "between" in errors["shoulders"]


def test_rejects_unknown_cuts_and_units():
    response = post_fit({"unit": "ft", "cut": "baggy", "measurements": MEASUREMENTS})

    assert response.status == 422
    errors = response.json()["errors"]
    assert "cut" in errors
    assert "unit" in errors


def test_an_unknown_chart_is_a_404():
    assert post_fit({"measurements": MEASUREMENTS}, chart="nope").status == 404


def test_the_api_sets_no_cookies():
    assert "Set-Cookie" not in post_fit({"unit": "in", "measurements": MEASUREMENTS}).headers


def test_fits_sizes_sent_in_the_request_such_as_an_imported_garments():
    sizes = [
        {"name": "40R", "chest": 113, "waist": 100.3, "shoulders": 45.7, "sleeve": 63.5, "length": None},
        {"name": "42R", "chest": 118.1, "waist": 105.4, "shoulders": 47, "sleeve": 64.1, "length": None},
    ]
    response = call("POST", "/api/v1/fits", {"unit": "in", "measurements": MEASUREMENTS, "sizes": sizes})

    assert response.status == 200
    found = response.json()
    assert found["best"] == "40R"
    assert found["size_chart"] is None
    assert next(check for check in found["sizes"][0]["checks"] if check["part"] == "length")["status"] == "unknown"


def test_checks_the_sizes_sent_in_the_request():
    response = call("POST", "/api/v1/fits", {"measurements": MEASUREMENTS, "sizes": [{"name": "", "chest": "big"}]})

    assert response.status == 422
    errors = response.json()["errors"]
    assert errors["sizes.0.name"] == "is required"
    assert errors["sizes.0.chest"] == "must be a number"


def test_fits_trousers_using_hips_and_inseam_when_given():
    sizes = [{"name": "34", "waist": 88.9, "seat": 107, "thigh": 62, "inseam": 81.3, "leg_opening": 40}]
    response = call("POST", "/api/v1/fits", {"unit": "in", "garment": "trousers", "measurements": {**MEASUREMENTS, "hips": 39.5, "inseam": 32.25}, "sizes": sizes})

    assert response.status == 200
    checks = response.json()["sizes"][0]["checks"]
    assert [check["part"] for check in checks] == ["waist", "seat", "inseam", "leg_opening"]
    assert checks[-1]["note"] == "Cut with a straight leg"


def test_micro_shorts_with_an_inch_long_inseam_are_fitted_other_measurements_still_need_5_cm():
    sizes = [{"name": "S", "waist": 81.3, "seat": 90.2, "inseam": 2.54, "leg_opening": 63.5}]
    response = call("POST", "/api/v1/fits", {"unit": "in", "garment": "trousers", "style": "shorts", "measurements": {**MEASUREMENTS, "hips": 39.5, "inseam": 32.25}, "sizes": sizes})
    assert response.status == 200
    assert response.json()["best"] == "S"

    response = call("POST", "/api/v1/fits", {"unit": "in", "garment": "trousers", "measurements": MEASUREMENTS, "sizes": [{"name": "S", "waist": 3, "seat": 90}]})
    assert response.status == 422


def test_trousers_without_hips_or_inseam_say_whats_missing():
    response = call("POST", "/api/v1/fits", {"garment": "trousers", "unit": "in", "measurements": MEASUREMENTS, "sizes": [{"name": "34", "waist": 88.9, "seat": 107}]})

    seat = next(check for check in response.json()["sizes"][0]["checks"] if check["part"] == "seat")
    assert [seat["status"], seat["note"]] == ["unknown", "Add your hips to check this"]


def test_warns_about_measurements_most_people_dont_have():
    warnings = post_fit({"unit": "in", "measurements": {**MEASUREMENTS, "shoulders": 25}}).json()["warnings"]

    assert len(warnings) == 1
    assert warnings[0]["part"] == "shoulders"
    assert "not around the arms" in warnings[0]["message"]


def test_shoes_are_fitted_by_the_foot():
    response = call("POST", "/api/v1/fits", {"unit": "cm", "garment": "shoes", "brand": "New Balance", "style": "sneaker", "fabric": "mesh",
                                             "sizes": [{"name": n} for n in ["8", "8.5", "9", "9.5", "10", "10.5", "11"]], "measurements": {"foot": 26.5, "ball": 9.8}})
    assert response.status == 200
    found = response.json()
    assert [found["garment"], found["scale"], found["best"]] == ["shoes", "us_m", "10"]
    ten = next(size for size in found["sizes"] if size["size"] == "10")
    assert ten["verdict"] == "fits"
    assert [check["part"] for check in ten["checks"]] == ["toe", "width"]
    nine = next(size for size in found["sizes"] if size["size"] == "9")
    assert nine["verdict"] == "compromise"
    assert nine["checks"][0]["status"] == "tight"


def test_shoes_in_inches_on_an_eu_chart_with_a_womens_foot():
    response = call("POST", "/api/v1/fits", {"unit": "in", "garment": "shoes", "women": True, "sizes": [{"name": n} for n in ["37", "38", "39", "40"]],
                                             "measurements": {"foot": 9.45}})
    assert response.status == 200
    found = response.json()
    assert found["scale"] == "eu"
    # 9.45 in = 24 cm; an EU 38 is a 24.3 cm last, too tight for a sneaker; 39 (25 cm) fits.
    assert found["best"] == "39"


def test_shoes_with_no_foot_length_are_refused_plainly_sizes_that_arent_sizes_are_shown_for_the_look():
    response = call("POST", "/api/v1/fits", {"unit": "cm", "garment": "shoes", "sizes": [{"name": "10"}], "measurements": {}})
    assert response.status == 422
    assert response.json()["errors"]["foot"] == "is required"
    response = call("POST", "/api/v1/fits", {"unit": "cm", "garment": "shoes", "sizes": [{"name": "One size"}], "measurements": {"foot": 26}})
    assert response.status == 200
    assert response.json()["best"] == "One size"
    assert response.json()["sizes"][0]["checks"] == []


def test_reads_a_pasted_size_chart():
    response = call("POST", "/api/v1/garment_imports", {"text": "Size\tChest\tWaist\n40R\t44.5\t39.5\n42R\t46.5\t41.5\n"})

    assert response.status == 200
    garment = response.json()["garment"]
    assert garment["garment"] == "jacket"
    assert [size["name"] for size in garment["chart"]["sizes"]] == ["40R", "42R"]


def test_explains_a_link_it_cant_use():
    response = call("POST", "/api/v1/garment_imports", {"url": "http://127.0.0.1/admin"})

    assert response.status == 422
    assert response.json()["error"] == "fetch_failed"


def test_needs_a_link_or_a_chart():
    assert call("POST", "/api/v1/garment_imports", {}).status == 422


def test_reads_its_own_sample_pages_from_disk_with_no_network():
    response = call("POST", "/api/v1/garment_imports", {"url": "http://127.0.0.1:8000/samples/grey-t-shirt.html"})

    assert response.status == 200
    garment = response.json()["garment"]
    assert [garment["garment"], garment["style"]] == ["top", "tee"]
    # Another site's /samples/ page is that site's, asked as any other link.
    assert call("POST", "/api/v1/garment_imports", {"url": "http://10.0.0.1/samples/grey-t-shirt.html"}).json()["error"] == "fetch_failed"


PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 64


def test_passes_a_shops_photo_through_as_an_image_the_browser_may_cache_for_an_hour(monkeypatch):
    asked = []

    def get_image(url, max_bytes, types):
        asked.append((url, max_bytes, types))
        return PNG, "image/png"

    monkeypatch.setattr(fetcher, "get_image", get_image)
    response = call("GET", "/api/v1/garment_imports/image", query="url=https%3A%2F%2Fcdn.example.com%2Fboot.png%3Fwidth%3D1000")

    assert response.status == 200
    assert response.headers["Content-Type"] == "image/png"
    assert response.body == PNG
    assert sorted(response.headers["Cache-Control"].split(", ")) == ["max-age=3600", "public"]
    url, most, types = asked[0]
    assert url == "https://cdn.example.com/boot.png?width=1000"
    assert most == 8_000_000
    assert types.search("image/webp")
    assert not types.search("image/svg+xml")
    assert not types.search("text/html")


def test_turns_away_a_private_address_without_asking_it():
    response = call("GET", "/api/v1/garment_imports/image", query="url=http%3A%2F%2F127.0.0.1%2Fsecret.png")

    assert response.status == 422
    assert response.json()["error"] == "fetch_failed"


def test_turns_away_what_isnt_a_link_and_what_isnt_a_photo(monkeypatch):
    assert call("GET", "/api/v1/garment_imports/image", query="url=not+a+link").status == 422

    def not_a_photo(*args, **kwargs):
        raise fetcher.Error("That isn't a photo.")

    monkeypatch.setattr(fetcher, "get_image", not_a_photo)
    response = call("GET", "/api/v1/garment_imports/image", query="url=https%3A%2F%2Fshop.example.com%2Fproducts%2Fboot")
    assert response.status == 422
    assert response.json()["message"] == "That isn't a photo."


def test_lists_charts_without_their_sizes():
    response = call("GET", "/api/v1/size_charts")
    assert response.status == 200
    chart = next(c for c in response.json()["size_charts"] if c["key"] == "sample_suit_jacket")
    assert chart["garment"] == "jacket"
    assert "sizes" not in chart


def test_shows_one_chart_with_its_sizes():
    response = call("GET", "/api/v1/size_charts/sample_suit_jacket")
    assert response.status == 200
    assert len(response.json()["sizes"]) == 18


def test_the_fit_guide_lists_measurements_and_cuts():
    response = call("GET", "/api/v1/fit_guide")
    assert response.status == 200
    found = response.json()
    assert [m["key"] for m in found["measurements"]] == ["chest", "waist", "shoulders", "arm", "height", "hips", "inseam"]
    assert [found["measurements"][0]["optional"], found["measurements"][5]["optional"]] == [False, True]
    assert [c["key"] for c in found["cuts"]] == ["slim", "regular", "classic"]


def test_the_page_carries_its_samples_and_an_import_map():
    response = call("GET", "/")
    page = response.body.decode()
    assert response.status == 200
    assert '"lib/garments/print": "/js/lib/garments/print.js"' in page
    assert "data-fitting-room-garment-value=" in page
    assert 'data-slider-for="chest"' in page
    assert "{{" not in page


def test_files_are_served_from_the_page_folder_only():
    assert call("GET", "/js/lib/format.js").status == 200
    assert call("GET", "/js/lib/format.js").headers["Content-Type"] == "text/javascript"
    assert call("GET", "/../server.py").status == 404
    assert call("GET", "/templates/index.html").status == 404
    assert call("GET", "/js/../../server.py").status == 404


def test_a_body_that_isnt_json_is_a_bad_request():
    environ = {"REQUEST_METHOD": "POST", "PATH_INFO": "/api/v1/fits", "CONTENT_LENGTH": "5", "wsgi.input": io.BytesIO(b"nope!")}
    setup_testing_defaults(environ)
    found = {}
    App()(environ, lambda status, headers: found.update(status=status))
    assert found["status"].startswith("400")
