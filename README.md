# Renderer

A fitting room in a web page: a 3D mannequin shaped by your measurements, wearing clothes cut from their own sewing
patterns and draped by a cloth simulation, in whichever size you pick, with how each size fits (tight, loose, a
tailor's fix) worked out from the garment's size chart.

Paste a store's product link, paste its size chart, give the sizes yourself, or add photos of the garment: it goes
on the mannequin. The server is Python (standard library plus Beautiful Soup and lxml); the page is plain ES modules
with three.js, served as they are, with no build step.

It keeps nothing about the people who use it: no accounts, no cookies, no database, nothing written to disk.
Measurements travel with each request and are used for that one answer; the server's log has a request's method,
path and status, never its query string or body. The page keeps your outfit and numbers in the tab's own
`sessionStorage` only, gone when the tab closes.

## Run it

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -e ".[test]"
python -m renderer            # http://127.0.0.1:8000/  (--host, --port to change)
```

The four sample garments under "No link? Try one of ours" and pasted charts work with no network: the server reads
its own sample pages from disk. Reading a store's link needs the network, and only reaches public addresses.

The 3D view uses WebGL. A browser without a graphics card (software WebGL) works too, but sews and drapes a garment
in tens of seconds instead of a few.

`App` in `renderer/server.py` is a plain WSGI application, if you'd rather mount it under another server.

## Tests

```sh
pytest                                   # the server: fit math, chart reading, link import, the API
node --test tests/javascript/*.test.mjs  # the page's modules: patterns, cloth, drape, photos, lasts (npm test does the same)
```

## How it fits together

| Where | What |
|---|---|
| `renderer/fit.py` | Fit for tops, dresses, jackets, coats and trousers: each size's ease against the body, by cut, with a tailor's alterations |
| `renderer/shoes.py` | Fit for shoes: the last's length and width against the foot, by scale (US, UK, EU, cm) and brand |
| `renderer/size_charts.py`, `renderer/data/size_charts/` | The built-in sample charts (made up; not any real brand's) |
| `renderer/garment_import/` | A product page, a Shopify shop's product, or a pasted chart, read into a garment: what it is, its colour and cloth, its cut, and its finished measurements per size (`chart_reader.py`, `dress_cut.py`, `page.py`); `fetcher.py` fetches one page, public addresses only |
| `renderer/api.py` | The JSON API |
| `renderer/server.py` | The WSGI app: the page, its files, the API |
| `renderer/static/js/lib/stage.js` | The 3D view (three.js): the mannequin, poses, lighting |
| `renderer/static/js/lib/garments/` | Sewing patterns (`pattern.js`, `pants.js`, `dress.js`), the cloth simulation (`drape.js`, `gpu_drape.js`, in workers), shoes, bags, reading store photos for colour and print (`print.js`) |
| `renderer/static/js/controllers/fitting_room_controller.js` | The page (Stimulus) |
| `renderer/static/models`, `shoes`, `drapes`, `fonts` | The mannequin, shoe templates, a bank of drapes to start from, typefaces |

### The API

| | |
|---|---|
| `GET /api/v1/fit_guide` | What to measure, and the cuts |
| `GET /api/v1/size_charts`, `GET /api/v1/size_charts/:key` | The sample charts |
| `POST /api/v1/size_charts/:key/fits`, `POST /api/v1/fits` | Every size ranked against a body: `{ unit, cut, garment, style, details, measurements, sizes }` (`garment: "shoes"` for shoes) |
| `POST /api/v1/garment_imports` | A garment from `{ url }` (with `shop_data` or `page_html` when the browser read the store for it), `{ text }` (a pasted chart), or `{ photo_kind, photo_style }` |
| `GET /api/v1/garment_imports/image?url=` | A store's product photo passed through, so the page can read its pixels |

### Settings

| Variable | |
|---|---|
| `RENDERER_FOOTWEAR=1`, `RENDERER_BAGS=1` | Try on shoes and bags (off by default: they're less finished than clothes) |
| `RENDERER_ALLOW_PRIVATE_HOSTS=1` | Let a pasted link reach this machine or a private network (for a shop running locally) |
| `RENDERER_RELOAD=1` | Re-read the page's template on every request, while working on it |

## Where it came from

This is the fitting room of a larger app (Rails), taken out as a service of its own and moved from Ruby to Python.
The Python server gives the same answers as the Ruby it replaces: every Ruby test was ported, and the two were run
side by side on over 600 listings and 1,900 fits, agreeing on all but two ties between equally good sizes, which
Python breaks by the chart's order. Two of the ported expectations (two baby tees' lengths) didn't hold in the Ruby
either; they're kept, marked as expected to fail.

Left out:

- **Every AI model.** The app read photos with machine-learning models in the browser and on a server: a body's
  measurements from a photo (MediaPipe), garment cut-outs (SlimSAM), how alike two pictures look and what a photo
  shows (DINOv2), depth (Depth Anything), a vision server, an AI try-on and a "studio look". None of it is here. The
  modules that asked them now answer that there's no model (`photo_remote.js`, `vision.js`, `likeness.js`,
  `depth.js`, `segment.js`), which is what the page always did when a model couldn't load: store photos are read by
  their colours alone (`print.js`), and your measurements are typed or slid.
- Accounts, sign-in and saved fits; the stories and the rooms around the fitting room; the music and car bars.

## Credits and licences

The code is MIT (see `LICENSE`). What it ships with:

- three.js r170 (MIT), its addons, N8AO (CC0), three-gpu-pathtracer (MIT, with three-mesh-bvh), Stimulus (MIT):
  `renderer/static/js/vendor/`, each with its licence.
- The mannequin, the studio light and the cloth textures are CC0: MakeHuman's assets, Poly Haven, ambientCG
  (`renderer/static/models/CREDITS.md`).
- Some shoe templates are made from Google Scanned Objects, CC BY 4.0 (`renderer/static/shoes/CREDITS.md`).
- The typefaces are under the SIL Open Font License (`renderer/static/fonts/`).
- The tests' listings (`tests/fixtures/kith_listings.json`, `tests/test_dress_cut.py`) are real store listings'
  public words, kept as test data for how listings are written.
