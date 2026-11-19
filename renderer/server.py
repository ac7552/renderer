"""The renderer's web server: the fitting room page, its files, and the JSON API (api.py), as one WSGI application.

It keeps nothing about the people who use it: no accounts, no cookies, no database, nothing written to disk. What a
request carries (measurements, a link) is used for its answer and dropped; the log has each request's method, path
and status, never its query string or body.

    from renderer.server import App
    app = App()            # a WSGI application: mount it under any WSGI server
    python -m renderer     # or run this one (see __main__.py)
"""

from __future__ import annotations

import html
import json
import mimetypes
import os
import re
import traceback
from http import HTTPStatus
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from . import api, sample_shop, size_charts

STATIC = Path(__file__).parent / "static"
MAX_BODY = 16 * 1024 * 1024
# Folders of the page's files, by the path they're served at. Models, shoes and drapes are big and don't change
# between versions of the page often: the browser may keep them a day.
LONG_LIVED = ("models/", "shoes/", "drapes/", "fonts/")
TYPES = {".js": "text/javascript", ".mjs": "text/javascript", ".css": "text/css", ".json": "application/json", ".glb": "model/gltf-binary",
         ".bin": "application/octet-stream", ".hdr": "application/octet-stream", ".wasm": "application/wasm", ".woff2": "font/woff2",
         ".webp": "image/webp", ".jpg": "image/jpeg", ".png": "image/png", ".ico": "image/x-icon", ".svg": "image/svg+xml",
         ".html": "text/html; charset=utf-8", ".txt": "text/plain; charset=utf-8", ".md": "text/plain; charset=utf-8"}
SECURITY = [("X-Content-Type-Options", "nosniff"), ("X-Frame-Options", "SAMEORIGIN"), ("Referrer-Policy", "strict-origin-when-cross-origin")]
# The page's own sample product pages, read from disk when the page asks for one, not fetched over the network
# (so they work with no network, and on a server that won't fetch its own private address).
SAMPLES = re.compile(r"\A/samples/([a-z0-9-]+)\.html\Z")


class Request:
    def __init__(self, environ):
        self.environ = environ
        self.method = environ.get("REQUEST_METHOD", "GET").upper()
        self.path = environ.get("PATH_INFO", "/") or "/"
        self.query = {key: values[-1] for key, values in parse_qs(environ.get("QUERY_STRING", ""), keep_blank_values=True).items()}
        self.host = environ.get("HTTP_HOST") or environ.get("SERVER_NAME", "")
        self.origin = f"{environ.get('wsgi.url_scheme') or 'http'}://{self.host}"
        self._body = None

    def body(self) -> dict:
        """The JSON body, or {} for none. Raises ValueError for one that isn't a JSON object or is too big."""
        if self._body is None:
            try:
                length = int(self.environ.get("CONTENT_LENGTH") or 0)
            except ValueError:
                length = 0
            if length > MAX_BODY:
                raise ValueError("too_big")
            raw = self.environ["wsgi.input"].read(length) if length > 0 else b""
            if not raw.strip():
                self._body = {}
            else:
                found = json.loads(raw.decode("utf-8"))
                if not isinstance(found, dict):
                    raise ValueError("not an object")
                self._body = found
        return self._body

    def params(self) -> dict:
        """The query string's parameters, and the JSON body's over them."""
        return {**self.query, **self.body()}


class App:
    """The WSGI application. static: the folder of the page's files."""

    def __init__(self, static=STATIC):
        self.static = Path(static).resolve()
        self.page = None

    # ---- WSGI

    def __call__(self, environ, start_response):
        request = Request(environ)
        try:
            status, headers, body = self.route(request)
        except size_charts.NotFound as error:
            status, headers, body = self.json(404, {"error": "not_found", "message": str(error)})
        except ValueError as error:
            if str(error) == "too_big":
                status, headers, body = self.json(413, {"error": "too_big", "message": "That request is too big."})
            else:
                status, headers, body = self.json(400, {"error": "bad_request", "message": "Send JSON: an object."})
        except Exception:  # noqa: BLE001 - one bad request mustn't take the server down
            traceback.print_exc()
            status, headers, body = self.json(500, {"error": "server_error", "message": "Something went wrong on the server."})
        phrase = HTTPStatus(status).phrase
        start_response(f"{status} {phrase}", headers + SECURITY)
        return [b"" if request.method == "HEAD" else body]

    def route(self, request):
        path, method = request.path, request.method
        if path.startswith("/api/v1/"):
            return self.api(request, path[len("/api/v1/"):].rstrip("/"), method)
        if method not in ("GET", "HEAD"):
            return self.text(405, "Method not allowed")
        if path in ("/", "/fit", "/index.html"):
            return self.html(self.render_page())
        if path == "/up":
            return self.text(200, "ok")
        shop = self.sample_shop(request)
        if shop:
            return shop
        return self.file(path)

    def sample_shop(self, request):
        """The sample shop's answers (sample_shop.py), at the addresses a Shopify shop answers at, or None."""
        path = request.path
        if path == "/meta.json":
            return self.json(200, sample_shop.meta())
        found = sample_shop.PRODUCT_JSON.match(path)
        item = sample_shop.find(found.group(1)) if found else None
        if item:
            return self.json(200, {"product": sample_shop.product(item, request.origin)})
        found = sample_shop.PRODUCT.match(path)
        item = sample_shop.find(found.group(1)) if found else None
        if item:
            return self.html(sample_shop.page(item, request.origin))
        if found or sample_shop.PRODUCT_JSON.match(path):
            return self.text(404, "Not found")
        return None

    def api(self, request, route, method):
        parts = route.split("/")
        if route == "fit_guide" and method in ("GET", "HEAD"):
            return self.answer(api.fit_guide(request.query))
        if route == "size_charts" and method in ("GET", "HEAD"):
            return self.answer(api.size_chart_index(request.query))
        if len(parts) == 2 and parts[0] == "size_charts" and method in ("GET", "HEAD"):
            return self.answer(api.size_chart_show(request.query, parts[1]))
        if len(parts) == 3 and parts[0] == "size_charts" and parts[2] == "fits" and method == "POST":
            return self.answer(api.fits(request.params(), chart_key=parts[1]))
        if route == "fits" and method == "POST":
            return self.answer(api.fits(request.params()))
        if route == "garment_imports" and method == "POST":
            return self.answer(api.garment_imports(*self.with_sample(request)))
        if route == "garment_imports/image" and method in ("GET", "HEAD"):
            return self.answer(api.garment_image(request.query))
        return self.json(404, {"error": "not_found", "message": "No such address."})

    def with_sample(self, request):
        """The request's parameters, with this server's own sample page read from disk when that's the link, or its
        sample shop's product as a Shopify shop answers it (with the size chart Kiwi Sizing would give)."""
        params, body = request.params(), request.body()
        try:
            link = urlsplit(str(params.get("url") or ""))
        except ValueError:
            return params, body
        product = sample_shop.PRODUCT.match(link.path or "")
        item = sample_shop.find(product.group(1)) if product else None
        if item and link.netloc == request.host and not body.get("page_html"):
            return params, {**body, "shop_data": sample_shop.shop_data(item, request.origin, self.static, given=body.get("shop_data"))}
        sample = SAMPLES.match(link.path or "")
        if sample and link.netloc == request.host and not body.get("page_html"):
            page = self.static / "samples" / f"{sample.group(1)}.html"
            if page.is_file():
                body = {**body, "page_html": page.read_text(encoding="utf-8")}
        return params, body

    # ---- answers

    def answer(self, result):
        status, body, headers = result
        if isinstance(body, (bytes, bytearray)):
            return status, [(key, value) for key, value in headers.items()], bytes(body)
        return self.json(status, body, headers)

    @staticmethod
    def json(status, body, headers=None):
        data = json.dumps(body, ensure_ascii=False, allow_nan=False).encode("utf-8")
        out = [("Content-Type", "application/json; charset=utf-8"), ("Content-Length", str(len(data)))]
        out += [(key, value) for key, value in (headers or {}).items()]
        if not any(key == "Cache-Control" for key, _ in out):
            out.append(("Cache-Control", "no-store"))
        return status, out, data

    @staticmethod
    def text(status, words):
        data = words.encode("utf-8")
        return status, [("Content-Type", "text/plain; charset=utf-8"), ("Content-Length", str(len(data)))], data

    @staticmethod
    def html(page):
        data = page.encode("utf-8")
        return 200, [("Content-Type", "text/html; charset=utf-8"), ("Content-Length", str(len(data))), ("Cache-Control", "no-cache")], data

    def file(self, path):
        relative = path.lstrip("/")
        target = (self.static / relative).resolve()
        if (self.static not in target.parents) or not target.is_file() or relative.startswith(("templates/", ".")) or "/." in relative:
            return self.text(404, "Not found")
        data = target.read_bytes()
        kind = TYPES.get(target.suffix.lower()) or mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        cache = "public, max-age=86400" if relative.startswith(LONG_LIVED) else "no-cache"
        return 200, [("Content-Type", kind), ("Content-Length", str(len(data))), ("Cache-Control", cache)], data

    # ---- the page

    def render_page(self):
        if self.page is None or os.environ.get("RENDERER_RELOAD") == "1":
            template = (self.static / "templates" / "index.html").read_text(encoding="utf-8")
            values = {
                "importmap": json.dumps({"imports": self.import_map()}, indent=2),
                "garment": html.escape(json.dumps(size_charts.find("sample_t_shirt").as_garment()), quote=True),
                "dress": html.escape(json.dumps(size_charts.find("sample_dress").as_garment()), quote=True),
                "body_parts": self.body_parts(),
            }
            self.page = re.sub(r"\{\{(\w+)\}\}", lambda m: values[m.group(1)], template)
        return self.page

    def import_map(self):
        """The page's modules by the names its code imports them by: "lib/garments/print" is /js/lib/garments/print.js,
        and the vendored libraries by their packages' names."""
        out = {"application": "/js/application.js", "@hotwired/stimulus": "/js/vendor/stimulus.js",
               "three": "/js/vendor/three.js", "n8ao": "/js/vendor/n8ao.js", "postprocessing": "/js/vendor/postprocessing-shim.js",
               "three-gpu-pathtracer": "/js/vendor/three-gpu-pathtracer.js",
               "three/examples/jsm/postprocessing/Pass.js": "/js/vendor/three-addons/Pass.js"}
        addons = {
            "environments": ["RoomEnvironment"], "controls": ["OrbitControls"], "loaders": ["GLTFLoader", "RGBELoader"],
            "utils": ["BufferGeometryUtils"], "libs": ["meshopt_decoder.module"],
            "postprocessing": ["EffectComposer", "OutputPass", "SMAAPass", "ShaderPass", "MaskPass", "Pass"],
            "shaders": ["CopyShader", "OutputShader", "SMAAShader"],
        }
        for folder, names in addons.items():
            for name in names:
                out[f"three/addons/{folder}/{name}.js"] = f"/js/vendor/three-addons/{name}.js"
        js = self.static / "js"
        for folder in ("controllers", "lib"):
            for file in sorted((js / folder).rglob("*.js")):
                name = file.relative_to(js).with_suffix("").as_posix()
                out[name] = f"/js/{file.relative_to(js).as_posix()}"
        return out

    @staticmethod
    def body_parts():
        """The measurements form's rows (what the Rails page's PagesHelper#body_parts made)."""
        from .page import body_parts_html

        return body_parts_html()


def make_app():
    return App()
