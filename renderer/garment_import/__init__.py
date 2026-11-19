"""Turns a pasted product link, or a pasted size chart, into a garment the fitting room can fit (a top, jacket, coat or
trousers): what it is, its colour, and its finished measurements per size. It reads the shop's page once when asked
and keeps nothing about who asked; the parsed garment is held in this process's memory for an hour by its link, so a
second look doesn't refetch the page, and is never written anywhere.
"""

from __future__ import annotations

import base64
import hashlib
import os
import re
from urllib.parse import quote_plus, unquote_plus, urlsplit

from bs4 import BeautifulSoup

from .. import fit
from .. import shoes as fit_shoes
from ..cache import TTLCache
from ..util import (blank, clamp, first_match, joined, presence, rnd, ruby_array, squish, text, titleize,
                    truncate)
from . import chart_reader, dress_cut, fetcher
from .chart_reader import Chart
from .page import Page, node_text

I = re.I


class Error(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


def union(*patterns):
    return re.compile("|".join(f"(?:{p.pattern})" for p in patterns), I)


UNSUPPORTED = re.compile(r"shoe|sneaker|boot|sock|\btie\b|belt|\bhat\b|\bcap\b|scarf|bag\b", I)
# Things worn but not fitted here, each with what to call it ("can't try on shoes yet"). Read from the name, the
# shop's category and its tags; checked first, so "Low Top Sneakers" is never a top.
NOT_FITTED = [
    ("shoes", re.compile(r"sneakers?|\bshoes?\b|\bboots?\b|footwear|loafers?|sandals?|slides?\b|mules?\b|clogs?|trainers?|\bheels?\b", I)),
    ("belts", re.compile(r"\bbelts?\b|belt bag", I)),
    ("bags", re.compile(r"\bbags?\b|backpack|tote|wallet|pouch|card holder|small leather goods", I)),
    ("hats", re.compile(r"\bhats?\b|\bcaps?\b|beanie|headwear|bucket hat|balaclava", I)),
    ("sunglasses", re.compile(r"sunglasses|eyewear|glasses|frames\b", I)),
    ("jewelry", re.compile(r"jewel|necklace|bracelet|\brings?\b|earrings?|watch(?:es)?\b", I)),
    ("socks", re.compile(r"\bsocks?\b|underwear|boxers?|briefs\b", I)),
    ("scarves and ties", re.compile(r"scarf|scarves|\bties?\b|gloves?", I)),
    ("swimwear", re.compile(r"swim|bikini", I)),
    # (A bodysuit is a top that fastens below: it's worn tucked into the pants or skirt, see garment.)
    ("unitards", re.compile(r"unitard|catsuit", I)),
    ("accessories", re.compile(r"accessor", I)),
]
# Dresses (a "dress shirt" or "dress pants" isn't one), drawn as a top cut long. A shirt dress, sweater dress or slip
# dress named in one word ("Shirtdress") is one too.
DRESSES = re.compile(r"\b(?:dress(?:es)?(?!\s*(?:shirts?|pants|trousers|shoes?|socks|coats?|jackets?|boots?)\b)|(?:shirt|sweater|slip|tee|knit|tank|polo|wrap)dress(?:es)?|gowns?|maxi|midi|sundress|frock|kaftan|caftan)\b", I)
NOT_A_SUIT = r"(?<!body)(?<!cat)(?<!track)(?<!jump)(?<!swim)(?<!play)(?<!boiler)(?<!flight)(?<!sweat)suit"
# (Not a "bodysuit", a "catsuit", or a tracksuit's or jumpsuit's top.)
JACKETS = re.compile(rf"jacket|blazer|{NOT_A_SUIT}|coat|sport ?coat|tuxedo|dinner|overshirt|shacket|puffer|windbreaker|anorak|gilet|blouson|shrug|bolero", I)
# T-shirts, shirts, polos, sweatshirts, hoodies and knitwear: worn on the body, under a jacket.
TOPS = re.compile(r"t-?shirt|\btees?\b|shirt|polo|henley|tank\b|sweatshirt|crewneck|hoodie|hooded|sweater|jumper|cardigan|pullover|knit\b|\bjerseys?\b|\btop\b|bodysuit|quarter[- ]?zip|half[- ]?zip|1/4[- ]?zip|turtle ?necks?|mock ?necks?|roll ?necks?", I)
# How a top looks, for drawing it: the first match in its name wins, then in its category, else a tee. "T-shirt" is
# checked before "shirt", so a T-shirt is never drawn as a button-up.
TOP_STYLES = [
    ("dress", DRESSES),
    ("hoodie", re.compile(r"hoodie|hooded", I)),
    ("tank", re.compile(r"\btanks?\b|tank top|camisole|\bcami\b|singlet|sleeveless", I)),
    # A rugby shirt (a long-sleeve polo): a collar on a buttoned placket, long sleeves.
    ("rugby", re.compile(r"\brugby\b|long[- ]?sleeve polo|\bpolo\b.*long[- ]?sleeve|\bl/s polo", I)),
    ("polo", re.compile(r"\bpolos?\b", I)),
    ("cardigan", re.compile(r"cardigan", I)),
    ("longsleeve", re.compile(r"long[- ]?sleeve.*\b(t[- ]?shirt|tee)|\b(t[- ]?shirt|tee)s?\b.*long[- ]?sleeve", I)),
    ("tee", re.compile(r"\bt[- ]?shirts?\b|\btees?\b|\bundershirts?\b", I)),
    ("sweater", re.compile(r"sweater|jumper|knit\b|knitted|cashmere crew|merino|turtle ?neck|roll ?neck", I)),
    ("sweatshirt", re.compile(r"sweatshirt|pullover|crew ?neck|fleece", I)),
    ("shortshirt", re.compile(r"short[- ]?sleeve.*shirt|\bs/s\b.*shirt|camp[- ]?(collar|shirt)|bowling shirt|aloha|hawaiian|resort shirt", I)),
    # (A "Long Sleeve Shirt" is a button-up; a long-sleeve T-shirt was caught above.)
    ("shirt", re.compile(r"oxford|flannel|button[- ]?(down|up|front)|poplin|dress shirt|chambray|long[- ]?sleeve\b(?:\s+\w+){0,3}\s+shirt\b|long[- ]?sleeve shirt", I)),
    ("longsleeve", re.compile(r"long[- ]?sleeve|\bl/s\b|henley", I)),
    ("shirt", re.compile(r"shirts?\b", I)),
    # A quarter zip that's none of these (not a "Quarter-Zip Shirt" or a knit one) is a sweatshirt with a zip.
    ("sweatshirt", re.compile(r"quarter[- ]?zip|half[- ]?zip|1/4[- ]?zip", I)),
]
TROUSERS = re.compile(r"trouser|pants?\b|jeans?\b|chinos?\b|slacks|leggings?\b|\btights\b|joggers?\b|sweatpants?|track ?pants?|\bshorts?\b(?![- ]?sleeve)|skirts?\b|skort", I)
# Worn over tailoring and cut long; fitted with more room and no "right" length.
COATS = re.compile(r"overcoat|topcoat|top coat|car coat|trench|peacoat|pea coat|parka|duffle|\bduster\b|\bcoat\b", I)
NOT_COATS = re.compile(rf"sport ?coat|{NOT_A_SUIT}|blazer|tuxedo", I)
# Words that say what a garment is, whichever kind (see kind_of: the words after a name's dash).
NAMES_A_GARMENT = union(DRESSES, TOPS, JACKETS, COATS, TROUSERS)
FITTED_KINDS = union(DRESSES, TOPS, JACKETS, TROUSERS)
# A "hoodie" that's insulated is outerwear, and so is one that zips up with a hood, unless it's knitwear. Down as a
# filling, not as a word ("dress it up or down", "button-down", "down the front").
INSULATED = re.compile(r"\bdown[- ](?:filled|fill|insulated|jacket|parka|coat|vest|puffer)\b|(?:goose|duck) down\b|\bdown (?:and|&) feathers?\b|downproof|puffer|quilted|insulated|padded(?![- ](?:elbows?|shoulders?|knees?|patch(?:es)?))|parka|windbreaker|shell", I)
HOODED_OUTERWEAR = union(INSULATED, re.compile(r"zip(?:per)? closure|two-way zip", I))
# A sweatshirt's make: a zip-up hoodie with these is a sweatshirt that zips, not a shell jacket with a hood.
SWEATSHIRT_MAKE = re.compile(r"kangaroo|ribbed (?:cuffs?|hems?|trims?|waistband)|rib(?:bed)?[- ]knit (?:cuffs?|hems?)|french terry|loopback|\bterry\b|\bfleece\b|brushed (?:back|inside|interior)|sweatshirt", I)
# A puffer (a down or padded jacket, coat or vest, quilted into baffles): drawn lofted, its baffles puffed.
PUFFER = re.compile(r"puffer|nuptse|\bdown[- ](?:filled|fill|jacket|parka|coat|vest|insulat\w*)|(?:goose|duck) down|down (?:and|&) feather|fill[- ]power|quilted|baffle|\binsulated\b|\bpadded (?:jacket|coat|vest|parka)", I)
# Knitwear: a sweater, a cardigan, anything knitted. Drawn as a knit (ribbed, matte) whatever its fibre.
KNITWEAR = re.compile(r"sweater|jumper|cardigan|\bknit(?:ted|wear)?\b|crochet|cable[- ]knit|rib[- ]?knit", I)
# Fibres spun for knitwear: a top of them is a knit (see knitwear).
KNIT_FIBRES = re.compile(r"merino|cashmere", I)
# A top made to sit close: a shrunken or baby fit, a fitted or slim cut. (Not "fitted cuffs" or a "fitted hem".)
FITTED_TOP = re.compile(r"shrunken|\bbaby (?:tee|t-?shirt|rib|fit)|\bslim\b|\bfitted\b(?!\s*(?:cuffs?|hems?|waist(?:band)?|sleeves?|neck))|body[- ]?con|second[- ]skin|form[- ]fitting|skin[- ]?tight", I)
# Kiwi Sizing's chart API, which many Shopify shops load their size charts from (see Page.kiwi_sizing).
KIWI_SIZING = "https://app.kiwisizing.com/api/getSizingChart"

# How a jacket looks, so the 3D view draws the right one: tailored (blazers, suit and sport jackets), shirt
# (button-front denim, trucker and work jackets), bomber, or zip (most other outerwear). First match wins.
ZIP_FRONT = re.compile(r"two-way zip|zip(?:per)? closure|full[- ]zip|zip[- ]up|front zip", I)
STYLES = [
    # (A shrug or a bolero is worn open over the shoulders, as a cardigan is.)
    ("cardigan", re.compile(r"cardigan|\bshrug\b|\bbolero\b", I)),
    ("tailored", re.compile(rf"blazer|{NOT_A_SUIT}|sport ?coat|tuxedo|dinner jacket|smoking jacket|lapel", I)),
    ("bomber", re.compile(r"bomber|varsity|letterman|flight jacket|ma-1|baseball jacket|harrington|aviator|blouson", I)),
    ("zip", ZIP_FRONT),
    ("shirt", re.compile(r"denim(?: \w+)? jacket|jean jacket|trucker|chore|overshirt|shirt[- ]jacket|shacket|work jacket|field jacket|barn jacket|hunting jacket|ranch jacket|coach(?:es)? jacket|utility|safari|chambray|button[- ](front|closure|up)|point collar", I)),
    ("zip", re.compile(r"zip|moto\b|biker|leather jacket|shearling|puffer|down jacket|windbreaker|anorak|track jacket|blouson|fleece", I)),
]
# A front that buttons or snaps shut (not a collar's or a pocket's snap).
FRONT_BUTTONS = re.compile(r"(?:button|snap)s?(?: closure)? (?:on|down|at) the front|(?:button|snap)[- ](?:front|up|down|placket)|front (?:button|snap)s?|\bbutton(?:s|ed)? closure\b(?! (?:on|at) the (?:collar|cuffs?|pockets?|sleeves?))", I)
# What only a shirt jacket is called (a "utility" jacket can zip).
SHIRT_NAMED = re.compile(r"denim(?: \w+)? jacket|jean jacket|trucker|overshirt|shirt[- ]jacket|shacket|chambray|button", I)
# Shops' outerwear sections, where a jacket that says nothing else is more likely casual than tailored.
OUTERWEAR = re.compile(r"outerwear|coats?[-_ ](and|&)[-_ ]jackets|jackets?[-_ ](and|&)[-_ ]coats", I)

# What the cloth looks like, from the product's name and description, so the 3D view can draw its surface.
FABRICS = [
    # Linen first: a silk-linen blend hangs and looks like linen, not satin.
    ("linen", re.compile(r"linen|ramie|hemp", I)),
    ("silk", re.compile(r"silk|satin|taffeta|chiffon|charmeuse", I)),
    ("denim", re.compile(r"denim|jean|trucker|chambray", I)),
    ("leather", re.compile(r"leather|suede|biker|moto\b", I)),
    ("nylon", re.compile(r"nylon|puffer|down\b|quilted|shell|windbreaker|anorak|parka", I)),
    ("wool", re.compile(r"wool|cashmere|tweed|flannel|camel hair|alpaca|mohair", I)),
    ("cotton", re.compile(r"cotton|canvas|chore|field|overshirt|work jacket|twill|corduroy", I)),
]

# Fabric colours a garment is likely to be, as the 3D view should draw them.
COLORS = {
    "navy": "#1f2a4a", "midnight": "#1a2038", "charcoal": "#35383e", "black": "#151619",
    "grey": "#73777f", "gray": "#73777f", "blue": "#2c4a8f", "brown": "#5a3d2b",
    "tan": "#a9845b", "camel": "#b38a5c", "caramel": "#a8743f", "beige": "#c2ad8c", "khaki": "#a99a72",
    "olive": "#545b39", "green": "#3e5240", "burgundy": "#5c1e2a", "wine": "#5c1e2a",
    "white": "#e9e6df", "ivory": "#e9e4d6", "cream": "#e6dcc6",
    "indigo": "#2b3f66", "neutrals": "#b9ad98", "stone": "#b8b0a0", "red": "#7a2a2a",
    # The rest of what shops call their colours (the photo's own colour replaces these once it's read; until then a
    # "Yellow Moss" cardigan shouldn't show navy).
    "yellow": "#d8bf3a", "mustard": "#c49a2c", "gold": "#c8a14a", "lemon": "#e6d86a", "orange": "#d8722e",
    "rust": "#9a4a2a", "terracotta": "#b0603e", "peach": "#e8b296", "coral": "#e07a64", "pink": "#e3a3b4",
    "rose": "#c98b93", "blush": "#e2b8b0", "fuchsia": "#c2307a", "magenta": "#b0306e", "purple": "#5c3a7a",
    "plum": "#5a2e48", "lilac": "#b9a2cf", "lavender": "#b7a8d6", "violet": "#6a4c9c", "mauve": "#a5838f",
    "maroon": "#5a1c24", "sage": "#a5ab8e", "moss": "#7a7a3e", "mint": "#b8dcc4", "lime": "#a8c64a",
    "forest": "#2f4a35", "emerald": "#2a6a4c", "teal": "#2b6b6e", "turquoise": "#3aa8a8", "aqua": "#7ccdd0",
    "sky": "#9cc3e4", "cobalt": "#2a4aa8", "royal": "#2a44a0", "taupe": "#8a7e72", "sand": "#cdb894",
    "oatmeal": "#d8ccb4", "oat": "#d8ccb4", "bone": "#e3dccb", "ecru": "#e2d9c2", "silver": "#b8bcc2",
    "chocolate": "#4a2f22", "espresso": "#3a2a22", "mocha": "#6a4c3a", "cognac": "#8a4a26", "slate": "#5a6270",
    "graphite": "#45484e", "pewter": "#7c7f84", "onyx": "#1c1d20", "heather": "#9a9ca1", "seal": "#6e6a60",
}
COLOR_WORDS = {name: re.compile(rf"\b{name}\b", I) for name in COLORS}
DEFAULT_COLOR = "#2a3552"

# Parts of a link's path that say nothing about the garment.
LINK_NOISE = re.compile(r"""\A(?:products?|p|dp|pd|item|items|shop|store|collections?|catalog|category|categories|clothing|apparel|
                [a-z]{2}(?:[-_][a-z]{2})?|new|new[-_]arrivals|sale|all|view|detail|details|index|default|wom[ae]n|m[ae]n|
                mens|womens|wmns|ladies|unisex|kids)\Z""", I | re.X)
# The noun the note gives each style ("so this is a men's cardigan").
LINK_NOUNS = {
    "dress": "a dress", "skirt": "a skirt", "cardigan": "a cardigan", "sweater": "a sweater", "shortknit": "a sweater",
    "hoodie": "a hoodie", "shirt": "a shirt", "shortshirt": "a shirt", "tee": "a T-shirt", "longsleeve": "a long-sleeve T-shirt",
    "polo": "a polo", "rugby": "a rugby shirt", "tank": "a tank top", "sweatshirt": "a sweatshirt", "tailored": "a blazer", "bomber": "a bomber jacket",
    "jeans": "jeans", "shorts": "shorts", "joggers": "joggers", "leggings": "leggings", "romper": "a romper", "jumpsuit": "a jumpsuit",
}
KIND_NOUNS = {"top": "a top", "jacket": "a jacket", "coat": "a coat", "trousers": "pants", "shoes": "shoes", "socks": "socks",
              "belt": "a belt", "bag": "a bag", "onepiece": "a jumpsuit"}
# A garment the link says nothing about the colour of shows grey until a photo gives it one.
LINK_GREY = "#8c8f95"

KINDS = ("top", "jacket", "coat", "trousers")
# One-piece outfits: drawn and fitted as a top tucked into shorts (a romper) or pants (a jumpsuit), one cloth.
ONE_PIECES = re.compile(r"romper|jumpsuit|playsuit|boiler ?suit|coveralls?|overalls?\b|dungarees|flight suit", I)
# Worn but not fitted: drawn on the mannequin from the listing's colour and photo, in the size picked.
ACCESSORIES = ("shoes", "socks", "belt", "bag")
ACCESSORY_GROUPS = {"shoes": "shoes", "socks": "socks", "belt": "belts"}
# A bag that's carried or worn, and what isn't one though a shop files it with them (a wallet, a suitcase, a case).
BAGS = re.compile(r"backpacks?|rucksacks?|knapsack|daypack|totes?\b|duffles?|duffels?|weekender|holdall|cross[- ]?body|messenger|sling|belt bag|waist (?:bag|pack)|fanny|bum bag|hip pack|satchel|briefcase|clutch|shopper|handbag|\bbags?\b", I)
NOT_BAGS = re.compile(r"wallet|card ?(?:holder|case)|carry[- ]on|luggage|suitcase|trolley|\btrunk\b|\bcases?\b|key ?(?:chain|ring|pouch|clip)|coin|charm|dust bag|laundry bag|garment bag|sleeping bag|small leather goods", I)
# How a bag is worn: on the back, across the body with the bag at the hip, across the chest, or carried in the hand.
BAG_STYLES = [
    ("backpack", re.compile(r"backpacks?|rucksacks?|knapsack|daypack", I)),
    ("sling", re.compile(r"belt bag|waist (?:bag|pack)|fanny|bum bag|hip pack|sling|chest (?:bag|pack|rig)", I)),
    ("duffle", re.compile(r"duffles?|duffels?|weekender|holdall|gym bag|travel bag|boston", I)),
    ("crossbody", re.compile(r"cross[- ]?body|messenger|camera bag|satchel|saddle|sacoche|musette|mini bags?|phone (?:bag|pouch)|side bag", I)),
    ("clutch", re.compile(r"clutch|pouch", I)),
]
# What a listing calls its own shape ("Silhouette: Tote").
BAG_SILHOUETTE = re.compile(r"silhouette:?\s*([^\W\d_](?:[^\W\d_]|[ -]){2,24})", I)
BAG_CARRIED = re.compile(r"tote|hobo|shopper|bucket|shoulder|handbag|top[- ]handle", I)
WORN_ON = [
    ("shoes", re.compile(r"sneakers?|\bshoes?\b|\bboots?\b|footwear|loafers?|sandals?|slides?\b|mules?\b|clogs?|trainers?|derby|oxfords?\b|brogues?|moccasins?|\b\d{3}v?\d?\b|runners?|low top|high top", I)),
    ("socks", re.compile(r"\bsocks?\b", I)),
    ("belt", re.compile(r"\bbelts?\b", I)),
]
# How a shoe is drawn: a boot, a loafer, a sandal, or a sneaker. First match wins (see shoe_style).
SHOE_STYLES = [
    ("hightop", re.compile(r"high[- ]?tops?|\bhi\b", I)),
    ("sneaker", re.compile(r"sneakers?|trainers?|runners?|running shoes?", I)),
    ("boot", re.compile(r"\bboots?\b|chelsea|chukka|combat|hiking", I)),
    ("sandal", re.compile(r"sandals?|slides?\b|mules?\b|clogs?|flip[- ]?flops?|slippers?", I)),
    ("loafer", re.compile(r"loafers?|moccasins?|penny|derb(?:y|ies)|oxfords?\b|brogues?|monk strap|dress shoes?|ballet|flats?\b|pumps?\b|heels?\b", I)),
]
SOCK_STYLES = [("knee", re.compile(r"knee|over[- ]the[- ]calf|\bhigh\b", I)), ("ankle", re.compile(r"ankle|no[- ]show|low[- ]cut|quarter|trainer socks?", I))]
ELASTIC_WAIST = re.compile(r"elastic(?:ated|ised|ized)?\s+(?:waist|waistband)|drawcord|drawstring|pull[- ]on", I)
BROWSER_PHOTO = re.compile(r"\Adata:image/(?:jpeg|png|webp);base64,")
BASE64_CHARS = re.compile(r"[^A-Za-z0-9+/=]")
# Bump when what an import returns changes, so imports held from before aren't served.
FORMAT = 42
PAGE_HTML_BYTES = 4_000_000

# Shoes are off until they're steadier, and bags the same way: their links answer as a hat's does, unless the
# server is started with RENDERER_FOOTWEAR=1 or RENDERER_BAGS=1. Tests set these directly.
footwear = None
bags = None


def footwear_on() -> bool:
    return os.environ.get("RENDERER_FOOTWEAR") == "1" if footwear is None else footwear


def bags_on() -> bool:
    return os.environ.get("RENDERER_BAGS") == "1" if bags is None else bags


def not_supported(what) -> Error:
    return Error("not_supported", f"Can't try on {what} yet. It works with tops, dresses, jackets, coats and pants.")


# Imports by link, and photos the page asked for through this server: in memory, for an hour, never written down.
IMPORTS = TTLCache(seconds=3600, size=256)

# How a photo is fetched (tests replace it).
fetch_image = fetcher.get_image
fetch_page = fetcher.get


def dig(value, *keys):
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def number_or_none(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def ruby_split(pattern, words, flags=0):
    """Split as Ruby does: no empty strings at the end, nothing at all from nothing."""
    parts = re.split(pattern, words, flags=flags)
    while parts and parts[-1] == "":
        parts.pop()
    return parts


def fragment_text(html) -> str:
    return node_text(BeautifulSoup(text(html), "html.parser"))


def to_query(params: dict) -> str:
    pairs = [f"{quote_plus(text(key), safe='')}={quote_plus(text(value), safe='')}" for key, value in params.items() if value is not None]
    return "&".join(sorted(pairs))


# ---- the ways in


def from_url(url, shop_data=None, page_html=None):
    """shop_data: a Shopify product's details as the person's own browser read them ({"product", "shop", "sizing"}),
    for shops that answer browsers quickly but stall or turn away apps (see from_shopify). page_html: the product
    page as the person's own browser shows it, for shops that turn apps away or fill their pages in by script. Read
    as a fetched page would be."""
    url = text(url).strip()
    try:
        if isinstance(page_html, str) and presence(page_html):
            if len(page_html.encode("utf-8")) > PAGE_HTML_BYTES:
                raise Error("page_too_big", "That page is too big to read.")
            return with_photo(GarmentImport().from_page(page_html, source_url=url))
        if isinstance(shop_data, dict):
            garment = GarmentImport().from_shopify(url, given=shop_data)
            if garment:
                photo = text(shop_data.get("photo"))
                if browser_photo(photo):
                    garment.pop("image_url", None)
                    garment["photo"] = photo
                else:
                    garment = with_photo(garment)
                # The shop's photo of the back, which the browser found and read.
                back = text(shop_data.get("back_photo"))
                if garment.get("photo") and browser_photo(back):
                    garment["back_photo"] = back
                # And its close-up of the cloth, laid on as the fabric itself.
                closeup = text(shop_data.get("closeup"))
                if garment.get("photo") and browser_photo(closeup):
                    garment["closeup"] = closeup
                return garment

        def read():
            importer = GarmentImport()
            return with_photo(importer.from_shopify(url) or importer.from_page(fetch_page(url), source_url=url))

        return IMPORTS.fetch(("garment_import", FORMAT, hashlib.sha256(url.encode("utf-8")).hexdigest()), read)
    except fetcher.GaveUp as error:
        return from_link(url, because=error.reason)
    except fetcher.Error as error:
        raise Error("fetch_failed", str(error)) from None


def from_link(url, because, name=None, category=None):
    """A link whose store wouldn't give its page: what the link's own words say the garment is, in that kind's usual
    sizes, with a note saying so. because: what the store did ("therealreal.com doesn't let apps read its pages")."""
    return GarmentImport().from_link(url, because=because, name=name, category=category)


def from_text(chart_text, garment="jacket"):
    """garment: what a pasted chart is for ("top", "jacket", "coat" or "trousers")."""
    return GarmentImport().from_text(chart_text, garment=garment)


def from_photo(kind, style=None):
    return GarmentImport().from_photo(kind=kind, style=style)


def browser_photo(photo) -> bool:
    """A photo the browser read and sent as a data URL, small enough to keep."""
    if not isinstance(photo, str) or len(photo.encode("utf-8")) >= 3_500_000:
        return False
    head = BROWSER_PHOTO.match(photo[:40])
    if not head:
        return False
    data = photo[head.end():]
    return bool(data) and not BASE64_CHARS.search(data)


def with_photo(garment):
    """The shop's main product photo, fetched here and sent to the page inline, so the person's browser never
    contacts the shop's image server and the page can read the photo's colours. Optional."""
    url = garment.pop("image_url", None)
    if not url:
        return garment
    try:
        data, kind = fetch_image(url)
    except fetcher.Error:
        return garment
    return {**garment, "photo": f"data:{kind};base64,{base64.b64encode(data).decode('ascii')}"}


def shoe_style(name, category=None, tags=None) -> str:
    """How a shoe is drawn (SHOE_STYLES; a sneaker when nothing says): by what the listing's own name calls it, then
    its category, then the shop's tags. The name less its colourway after a dash: a sneaker in "Chelsea Blue" isn't
    a boot."""
    head = ruby_split(r"\s[-–|]\s", text(name))
    for said in (head[0] if head else None, category, tags):
        style = first_match(SHOE_STYLES, " ".join(text(part) for part in ruby_array(said)))
        if style:
            return style
    return "sneaker"


def bag_style(named, description=None) -> str:
    """A bag's kind (BAG_STYLES; a tote when nothing says). What the listing calls its own shape comes first."""
    said = BAG_SILHOUETTE.search(text(description))
    if said:
        style = first_match(BAG_STYLES, said.group(1))
        if style:
            return style
        if BAG_CARRIED.search(said.group(1)):
            return "tote"
    return first_match(BAG_STYLES, named) or "tote"


# A bag's own measurements from its listing's words, in cm: {width, height, depth} (what's given of them), sure:
# False when which way up it stands is a guess, and drop (a handle's or a strap's, when given). None when the
# listing gives none. H is always the height and D the depth; of a length and a width, the greater is across the
# bag's face and the lesser its depth, unless a depth is given too (then both are its face).
BAG_LABELS = {"h": "h", "height": "h", "w": "w", "width": "w", "d": "d", "depth": "d", "l": "l", "length": "l"}
BAG_UNIT = r"(?:\"|”|″|''|in(?:ch(?:es)?)?\b\.?|cm\b|mm\b)"


def bag_size(words, style=None):
    words = squish(re.sub(r"&quot;|&#34;|&rdquo;|&Prime;", '"', re.sub(r"<[^>]+>", " ", text(words)), flags=I))

    def cm(number, unit, bare):
        value = float(number)
        unit = text(unit).lower()
        if unit.startswith("cm"):
            value *= 1
        elif unit.startswith("mm"):
            value *= 0.1
        elif unit == "":
            value *= bare
        else:
            value *= 2.54
        return rnd(value, 1) if 2 <= value <= 120 else None

    # A label then its number ("H 9.84\"", "Height: 40 cm"), or the number, its unit, then its label ("12\"W", "40cm
    # H"; not "31 L", a capacity in litres).
    labelled = [(label, number, unit) for label, number, unit in
                re.findall(rf"\b(height|width|depth|length|[hwdl])\b\s*[:=]?\s*(\d+(?:\.\d+)?)\s*({BAG_UNIT})?", words, I)]
    labelled += [(label, number, unit) for number, unit, label in
                 re.findall(rf"(\d+(?:\.\d+)?)\s*({BAG_UNIT})\s*(height|width|depth|length|[hwdl])\b(?!\s*[:=]?\s*\d)", words, I)]
    units = [unit for _, _, unit in labelled if presence(unit)]
    # (A number with no unit beside others in inches is in inches too; alone, small numbers are inches.)
    bare = 1 if any(re.search("cm", u, I) for u in units) else 0.1 if any(re.search("mm", u, I) for u in units) else 2.54
    found = {}
    for label, number, unit in labelled:
        key = BAG_LABELS.get(label.lower())
        if key and found.get(key) is None:
            found[key] = cm(number, unit, bare)
    found = {key: value for key, value in found.items() if value is not None}
    # No labels: "Dimensions: 30 x 40 x 12 cm", the least of three the depth.
    if not found:
        m = re.search(rf"(\d+(?:\.\d+)?)\s*({BAG_UNIT})?\s*[x×]\s*(\d+(?:\.\d+)?)\s*({BAG_UNIT})?(?:\s*[x×]\s*(\d+(?:\.\d+)?)\s*({BAG_UNIT})?)?", words, I)
        if m:
            units_given = [u for u in (m.group(2), m.group(4), m.group(6)) if u is not None]
            unit = units_given[-1] if units_given else ""
            given = [n for n in (m.group(1), m.group(3), m.group(5)) if n is not None]
            bare = 2.54 if unit == "" and max(float(n) for n in given) <= 30 else 1
            numbers = [value for value in (cm(n, unit, bare) for n in given) if value is not None]
            if len(numbers) >= 2:
                depth = min(numbers) if len(numbers) == 3 else None
                face = sorted(numbers)[-2:] if depth is not None else numbers
                out = {"width": max(face), "height": min(face), "depth": depth, "sure": False}
                return {key: value for key, value in out.items() if value is not None}
    dropped = re.search(rf"(?:handle|strap)s?\s*drop\s*[:=-]?\s*(\d+(?:\.\d+)?)\s*({BAG_UNIT})?", words, I)
    drop = cm(dropped.group(1), dropped.group(2), 2.54) if dropped else None
    # (One number alone is as likely something else's: a laptop sleeve's, a strap's.)
    if len(found) < 2:
        return {"drop": drop} if drop else None
    size = {"height": found.get("h"), "depth": found.get("d")}
    face = [value for value in (found.get("l"), found.get("w")) if value is not None]
    sure = True
    if size["height"] is not None and size["depth"] is not None:
        size["width"] = max(face) if face else None
    elif size["height"] is not None:
        size["width"] = max(face) if face else None
        if len(face) == 2:
            size["depth"] = min(face)
    else:
        # No height given: the two are its face, the taller a backpack's height, the longer another bag's width.
        a, b = (max(face) if face else None), (min(face) if len(face) == 2 else None)
        if style == "backpack":
            size["height"], size["width"] = a, b
        else:
            size["width"], size["height"] = a, b
        sure = False
    size = {key: value for key, value in size.items() if value is not None}
    if not size:
        return None
    if not sure:
        size["sure"] = False
    if drop:
        size["drop"] = drop
    return size


# Usual finished measurements (cm) of tops and jackets by letter size, for listings that say only their size ("Size:
# M") with no chart: [chest, shoulders, sleeve, length] at XS, then the step to each next size.
USUAL_SIZES = ["XS", "S", "M", "L", "XL", "XXL", "XXXL"]
USUAL = {
    "tee": [[94, 42, 19.5, 68], [6, 2, 0.5, 2]],
    "tee_women": [[84, 37, 15, 59], [5, 1.5, 0.5, 1.5]],
    "top_women": [[86, 37, 58, 60], [5, 1.5, 1, 1.5]],
    "top": [[96, 42, 61, 66], [6, 2, 1, 2]],
    "jacket": [[100, 43, 62, 66], [6, 2, 1, 1.5]],
    "jacket_women": [[91, 37.5, 56, 57], [5, 1.5, 0.5, 1.5]],
    "coat": [[104, 44, 62, 92], [6, 2, 1, 2]],
    "coat_women": [[100, 37.5, 56, 96], [5, 1.5, 0.5, 1.5]],
    "dress": [[84, 36, 14, 95], [5, 1.5, 0.5, 1.5]],
    "dress_long": [[84, 36, 58, 100], [5, 1.5, 1, 1.5]],
}
LETTER = re.compile(r"\A(XXXL|3XL|XXL|2XL|XL|L|M|S|XS)\b", I)
ALL_LETTERS = ["XXS", "XS", "S", "M", "L", "XL", "XXL", "XXXL", "4XL"]
# Japanese and some European brands number their sizes 0 (or 1) upward: 0 is an XS, 1 an S, 2 an M.
BRAND_SIZE_LETTERS = ["XS", "S", "M", "L", "XL", "XXL", "XXXL"]
# The waist (cm) men's pants in each letter size are made for.
MEN_WAIST = {"XXS": 66, "XS": 71, "S": 76, "M": 81, "L": 86, "XL": 94, "XXL": 102, "XXXL": 109, "4XL": 117}
# [leg opening around (cm), extra room at the seat and thigh (cm)] by how the listing says the leg is cut.
TROUSER_LEGS = [
    # Leggings and tights stretch over the body, made smaller than it.
    (re.compile(r"leggings?|\btights\b", I), (21, -12)),
    (re.compile(r"joggers?|sweatpants?|track ?pants?", I), (26, 6)),
    (re.compile(r"wide[- ]leg|palazzo|flared?|barrel|balloon", I), (58, 10)),
    (re.compile(r"boot ?cut", I), (46, 2)),
    (re.compile(r"skinny", I), (28, -6)),
    (re.compile(r"slim|tapered", I), (34, -2)),
    (re.compile(r"straight", I), (42, 2)),
]
# A skirt's usual length (cm) by how long it's called, and how far below the waist its rise sits it.
SKIRT_LENGTHS = {"mini": 40, "knee": 56, "midi": 74, "maxi": 96}
SKIRT_RISES = [(9, re.compile(r"low[- ]rise|low[- ]waist|hip[- ]hugg|sits? (?:low )?on the hips", I)), (4, re.compile(r"mid[- ]rise", I)),
               (0, re.compile(r"high[- ]rise|high[- ]waist", I))]
# A skirt as short as its photo shows it, when that's more than 12% shorter than its words say; never longer.
PHOTO_SKIRT_LENGTH = 0.8
SKIRT_SHORTEST = 38
# Shorts as long as their photo shows them, when their listing names no inseam.
PHOTO_SHORTS_LENGTH = 0.78
# A coat cut short: one its photo shows with its sleeves reaching down to its hem or past it, or one its name calls
# short, a peacoat, an aviator, a biker, a bomber or a jacket.
SHORT_COAT_NAME = re.compile(r"\bshort\b|pea ?coat|\bcaban\b|aviator|\bbiker\b|bomber|\bmods\b|\bjacket\b", I)
SHORT_COAT_LENGTH = 1.05  # a little longer than a jacket's usual length: a parka covers the seat
# A top's length as its photo shows it (see photographed_length).
TYPICAL_PHOTO_LENGTH = {"tee": 1.65, "sweat": 1.07, "shirt": 1.35, "jacket": 1.05}
UNCROP = {"tee": 0.9, "shirt": 0.9, "sweat": 1.2}
PHOTO_TEE_LENGTH = 0.75

# How a listing says a top is cut, on its usual sizes: roomier, cropped, close or with short cap sleeves.
FIT_WORDS = [
    (re.compile(r"oversized|boxy|loose fit|baggy", I), {"chest": 10, "length": 2, "shoulders": 4}),
    (re.compile(r"relaxed", I), {"chest": 4, "shoulders": 1}),
    (re.compile(r"dropped shoulders?", I), {"shoulders": 3}),
    (re.compile(r"slim fit|fitted|baby tee|mini tee|shrunken|body[- ]?con|second[- ]skin", I), {"chest": -6, "length": -3, "shoulders": -2}),
    (re.compile(r"crop(?:ped)?\b", I), {"length_share": 0.75}),
    (re.compile(r"cap sleeves?", I), {"sleeve_share": 0.55}),
]
# What the shop photo shows overrules the listing's words, which are often the same for every top a brand sells.
BABY_TEE = {"chest": -4, "length": -8, "shoulders": -3}
ROOMY_TOP = {"chest": 4, "shoulders": 3}
SHORT_SLEEVES = {"sleeve_share": 0.75}
ROOMY_WORDS = [change for _, change in FIT_WORDS[:3]]
DRESS_FLARES = ("waist", "hips", "knee")

GENDER = re.compile(r"\b(wom[ae]n'?s?|femme|ladies|men'?s|man|homme)\b", I)
WOMEN = re.compile(r"\b(wom[ae]n'?s?|femme|ladies)\b", I)
MEN_ONLY = re.compile(r"\b(men'?s|man|homme)\b", I)
GARMENT_WORDS = {
    "top": re.compile(r"top|shirt|sweater|knit|jacket", I), "jacket": re.compile(r"jacket|coat|blazer|suit", I),
    "coat": re.compile(r"coat|jacket", I), "trousers": re.compile(r"trouser|pant|jean", I),
}
# A puffer: quilted or down-filled outside. A quilted lining (a varsity jacket's, a field jacket's) isn't one.
QUILTED_INSIDE = re.compile(r"quilted (?:lining|liner|interior)|quilt[- ]lined|lined with (?:a )?quilt\w*", I)
HALF_ZIP = re.compile(r"half[- ]?zip|quarter[- ]?zip|1/4[- ]?zip|\bhalf[- ]zipper\b", I)
# Shirt-like outerwear that's quilted or padded is lightly so: not lofted into baffles unless it's filled with down.
LIGHT_QUILT = re.compile(r"overshirt|shacket|shirt[- ]jacket|flannel|chore|work(?:wear)?[- ]jacket|trucker|liner", I)
FILLED = re.compile(r"puffer|nuptse|\bdown\b|fill[- ]power|baffle", I)
# How pants are made, for drawing them: jeans, joggers, leggings, shorts, or trousers (anything else).
BOTTOM_STYLES = [
    ("skirt", re.compile(r"skirts?\b|skort", I)),
    ("leggings", re.compile(r"leggings?|\btights\b", I)),
    ("shorts", re.compile(r"\bshorts?\b(?![- ]?sleeve)", I)),
    ("joggers", re.compile(r"joggers?|sweatpants?|track ?pants?|\bsweats\b", I)),
    ("jeans", re.compile(r"jeans?\b|denim", I)),
]
SHOPIFY_PRODUCT = re.compile(r"/products/([a-z0-9][a-z0-9_-]*)", I)
OVERSIZED = re.compile(r"oversized|\bboxy\b|loose[- ]fit|relaxed[- ]fit|drop(?:ped)?[- ]shoulders?", I)
WAIST_LENGTH = re.compile(r"\btrack\b|blouson|bomber|varsity|letterman|harrington|aviator|\bma-1\b|crop(?:ped)?\b", I)
HOODED = re.compile(r"\bhood(?:ed|s|ie|y)?\b|\bparka\b|\banorak\b", I)
NO_HOOD = re.compile(r"hoodless|no hood|without (?:a )?hood|(?:stowable|stowaway|stow[- ]away|packable|concealed|hidden|tuck(?:ed|able)?[- ]away|roll[- ]away) hood|hoo[dk][- ]and[- ]eye|hood (?:stows|packs|tucks|rolls) (?:away|in|into)", I)
LOOSE_BOTTOMS = re.compile(r"\b(?:baggy|wide(?:[- ]leg)?(?![- ]?(?:waist)?band)|relaxed|loose|oversized|pleat(?:s|ed)?|balloon|barrel)\b", I)
SLIM_BOTTOMS = re.compile(r"\b(?:slim|skinny|tapered)\b", I)
OPEN_HEM = re.compile(r"\b(?:straight|wide|open)[- ](?:leg|hem)|\bopen hem|\bflared?\b", I)
UNHEMMED = re.compile(r"unhemmed|un-hemmed|unfinished (?:hem|length|leg)|hem (?:is )?left unfinished|to be hemmed|hemmed to (?:order|length|your)", I)
UNHEMMED_PAST = 12
# What a chart can't mean, left out (and then estimated, as when a chart doesn't give it): a shop's typo would
# otherwise be drawn as a leg three centimetres round.
PLAUSIBLE = {"leg_opening": (12, 120), "thigh": (30, 150), "seat": (50, 200), "waist": (40, 200), "inseam": (5, 120),
             "rise": (12, 60), "chest": (50, 220), "shoulders": (25, 80), "sleeve": (5, 100), "length": (25, 160)}
# Charts measure a sleeve from the shoulder seam, or from the centre of the back of the neck, and say which only
# sometimes. Kept from the shoulder seam: converted once (see shoulder_sleeves).
USUAL_ARM = {"women": 58, "men": 65}
SHOULDER_SLEEVE_PAST_ARM = 10
WOMEN_SHOULDERS = 42  # a chart whose middle size's shoulders are under this is cut for women
SHIRT_COLLAR = re.compile(r"(?:classic|point|spread|camp|cuban|button[- ]down|pointed|notched) collar", I)
NAMED_COLLAR = union(SHIRT_COLLAR, re.compile(r"\b(?:notch(?:ed)?|peak(?:ed)?|wide|broad)?\s*lapels?\b|shawl collar|shirt collar|spread collar|convertible collar|polo collar|johnny collar|knit collar|(?:fold|turn)[- ]down collar|\bcollared\b|corduroy collar|contrast collar", I))
NOT_TURNED_DOWN = re.compile(r"stand(?:[- ]up)? collar|mandarin|band collar|funnel|mock[- ]?neck|turtle ?neck|collarless|crew ?neck|hood|shearling collar|fur collar", I)
# Clothes from a person's own photo: every usual size of that kind of thing, marked as guessed.
PHOTO_NAMES = {
    "top": {"tee": "T-shirt", "longsleeve": "Long-sleeve T-shirt", "sweatshirt": "Sweatshirt", "hoodie": "Hoodie", "shirt": "Shirt", "shortshirt": "Short-sleeve shirt",
            "polo": "Polo", "rugby": "Rugby shirt", "tank": "Tank top", "sweater": "Sweater", "cardigan": "Cardigan", "shortknit": "Short-sleeve sweater",
            "dress": "Dress", "dress_long": "Long-sleeve dress"},
    "jacket": {"zip": "Zip-up jacket", "bomber": "Bomber jacket", "shirt": "Shirt jacket", "tailored": "Blazer", "cardigan": "Cardigan"},
    "coat": {}, "trousers": {"jeans": "Jeans", "shorts": "Shorts", "skirt": "Skirt"},
}


class GarmentImport:
    def __init__(self, fetch_json=None, fetch_page=None):
        """fetch_json, fetch_page: read a size chart service's answer, or a shop's size guide page (stubbed in tests)."""
        self.fetch_json = fetch_json or fetcher.get_json
        self.fetch_page = fetch_page or globals()["fetch_page"]

    # ---- links, pages, pasted charts

    def from_link(self, url, because, name=None, category=None):
        given = {"name": presence(squish(name)), "category": presence(squish(category))}
        try:
            path = urlsplit(text(url).strip()).path
        except ValueError:
            path = ""
        segments = [s for s in (re.sub(r"\.(?:html?|php|aspx?)\Z", "", unquote_plus(part), flags=I) for part in ruby_split("/", path)) if not blank(s)]

        def words_of(segment):
            return [word for word in ruby_split(r"[-_+\s]+", segment) if not (re.search(r"\d", word) or len(word) < 2)]

        # The name: the last part of the path that reads as words (less any item code), the category the parts before
        # it that aren't the store's own sections.
        at = next((i for i in range(len(segments) - 1, -1, -1) if len(words_of(segments[i])) >= 2), None)
        if at is None:
            at = next((i for i in range(len(segments) - 1, -1, -1) if words_of(segments[i]) and not LINK_NOISE.search(segments[i])), None)
        product_name = titleize(" ".join(words_of(segments[at]))) if at is not None else ""
        before = [s for s in (segments[:at] if at is not None else []) if not (LINK_NOISE.search(s) or not words_of(s))]
        product_category = presence(titleize((before[-1] if before else "").replace("-", " ").replace("_", " ")))

        # (A shop's name for it in capitals, "CAMO SHARK FULL ZIP HOODIE", in capitals only at each word's start.)
        def upper(words):
            return words if re.search(r"[a-z]", words) else "".join(part.capitalize() for part in re.split(r"(\s+)", words))

        if given["name"]:
            product_name = upper(given["name"])
        if given["category"]:
            product_category = upper(given["category"])
        colour = next((key for key in COLORS if COLOR_WORDS[key].search(product_name)), None)
        product = {"name": presence(product_name) or "Top", "brand": None, "color": colour.capitalize() if colour else None, "category": product_category,
                   "description": None, "fabric": None, "sizes": [], "tags": [], "sorted": False}
        product["women"] = self.women(product, url)
        kind = self.kind_of(product) if (presence(product_name) or product_category) else "top"
        if kind in ACCESSORIES:
            found = self.accessory(product, kind, url)
        elif kind == "onepiece":
            found = self.one_piece(product, url, lambda part, part_kind: self.usual_for(part_kind, self.top_style_of(part), part))
        else:
            if kind == "trousers":
                chart = self.usual_skirts(product) if self.bottom_style_of(product) == "skirt" else self.usual_trousers(product)
            elif self.dress(kind, product):
                chart = dress_cut.usual_sizes(dress_cut.read(product))
            else:
                chart = self.usual_sizes(kind, self.top_style_of(product), product)
            found = self.garment(product, chart, kind=kind, source_url=url)
        if not colour:
            found["color"] = LINK_GREY
            for part in (found.get("parts") or {}).values():
                part["color"] = LINK_GREY
        noun = LINK_NOUNS.get(found.get("style")) or KIND_NOUNS.get(found.get("garment"), "a top")
        if any(re.fullmatch(r"(?:wom[ae]n|m[ae]n|mens|womens|wmns|ladies)", s, I) for s in segments):
            lead = "a " if noun.startswith("a ") else ""
            noun = f"{lead}{'women' if product['women'] else 'men'}'s {noun[len(lead):]}"
        worn = ", worn open over a top," if found.get("garment") == "jacket" and found.get("style") == "cardigan" else ""
        return {**found, "link_note": f"{because}, so this is {noun}{worn} in usual sizes."}

    def from_photo(self, kind, style=None):
        kind = text(kind) if text(kind) in KINDS else "top"
        style = text(style) if PHOTO_NAMES[kind].get(text(style)) else None
        name = PHOTO_NAMES[kind].get(style) or {"top": "Top", "jacket": "Jacket", "coat": "Coat", "trousers": "Pants"}[kind]
        product = {"name": f"{name} from your photo", "brand": None, "color": None, "category": None, "description": None}
        # (Jeans, shorts and skirts go by their names, as a shop's would: bottom_style_of.)
        if kind == "trousers":
            chart = self.usual_skirts(product) if self.bottom_style_of(product) == "skirt" else self.usual_trousers(product)
        elif text(style).startswith("dress"):
            chart = dress_cut.usual_sizes(dress_cut.read(product))
        else:
            chart = self.usual_sizes(kind, style or "tee")
        if style == "dress_long":
            style = "dress"
        found = self.garment(product, chart, kind=kind, source_url=None)
        return {**found, "style": style} if style else found

    def from_page(self, html, source_url):
        page = Page(html)
        product = page.product()
        kind = self.kind_of(product)
        if kind in ACCESSORIES:
            return self.accessory({**product, "sizes": page.size_names()}, kind, source_url)
        if kind == "onepiece":
            sized = {**product, "sizes": page.size_names(), "women": self.women(product, source_url)}
            return self.one_piece(sized, source_url, lambda part, part_kind: self.usual_for(part_kind, self.top_style_of(part), part))

        # The table that gives the most measurements wins; a resale listing's own measurements come next.
        charts = [c for c in (chart_reader.read(t.rows, context=t.context, garment=kind) for t in page.tables()) if c]
        chart = min(charts, key=lambda c: len(c.missing)) if charts else None
        if chart is None:
            item = page.item_measurements()
            if item:
                chart = chart_reader.read(item, context="item measurements", single=True, garment=kind)
        if chart is None:
            chart = self.kiwi_chart(page, kind)
        if chart is None:
            chart = self.linked_guide_chart(page, kind, product, source_url)
        if chart is None and self.dress(kind, product):
            stated = page.stated_size()
            chart = dress_cut.usual_sizes(dress_cut.read(product), [stated] if stated is not None else [])
        if chart is None:
            chart = self.usual_chart(kind, page.stated_size(), self.usual_key(kind, self.top_style_of(product), product))
        # No chart anywhere: the sizes the page offers, with their usual measurements (marked as guessed), so the
        # link still works and the person picks their size on the mannequin. Pants always get some (by waist, or the
        # usual waists); other clothes only when the page lists its sizes.
        if chart is None:
            product = {**product, "sizes": page.size_names()}
            product["women"] = self.women(product, source_url)
            if kind == "trousers":
                chart = self.usual_skirts(product) if self.bottom_style_of(product) == "skirt" else self.usual_trousers(product)
            elif product["sizes"] and not self.dress(kind, product):
                chart = self.usual_sizes(kind, self.top_style_of(product), product)
        if chart is None:
            raise Error("no_size_chart", "Couldn't find a size chart on that page. Many shops load it in a pop-up: "
                                         "copy the chart from there and paste it instead.")
        return self.garment(product, chart, kind=kind, source_url=source_url)

    def from_shopify(self, url, given=None):
        """Shopify shops answer a product's details as JSON at /products/<handle>.json: quick and small, where the
        product page itself can be megabytes, slow, or shown only to browsers. The size chart then comes from Kiwi
        Sizing, when the shop uses it. None when the link isn't a Shopify product or the shop has no chart there, so
        the page is read instead. given: the same details as the person's browser read them ({"product", "shop",
        "sizing"}); with no chart there, the sizes' usual measurements stand in (marked as guessed)."""
        try:
            return self._from_shopify(url, given)
        except fetcher.Error as error:
            # A shop that stalls here stalls on its page too, and one that turns apps away turns away the page.
            if isinstance(error, fetcher.TooSlow) or "doesn't let apps" in str(error):
                raise
            return None
        except (ValueError, TypeError, AttributeError, KeyError, IndexError):
            if os.environ.get("RENDERER_STRICT") == "1":
                raise
            return None

    def _from_shopify(self, url, given):
        parts = urlsplit(text(url))
        handle = SHOPIFY_PRODUCT.search(parts.path)
        if not handle:
            return None
        handle = handle.group(1)
        base = f"{parts.scheme}://{parts.hostname}"
        data = given.get("product") if given is not None else self.fetch_json(f"{base}/products/{handle}.json")["product"]
        if not (isinstance(data, dict) and not blank(data.get("title"))):
            return None
        if given is not None and not blank(data.get("handle")) and text(data.get("handle")).lower() != handle.lower():
            return None
        if given is not None:
            shop = given.get("shop")
        else:
            try:
                shop = self.fetch_json(f"{base}/meta.json")["myshopify_domain"]
            except Exception:  # noqa: BLE001 - as the page does: no shop name, no chart from here
                shop = None
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]*\.myshopify\.com", text(shop)):
            return None

        description = squish(fragment_text(data.get("body_html")))
        tags = [tag.strip() for tag in ruby_split(r",\s*", ",".join(text(t) for t in ruby_array(data.get("tags"))))][:40]
        colour = re.search(r"\s[-–]\s([^-–]+)\Z", text(data.get("title")))
        material = re.search(r"(?:Material|Fabric|Composition):\s*([^.]+?)(?=\s+[A-Z][a-z]+:|\Z)", description)
        product = {
            "name": truncate(squish(data.get("title")), 120),
            "brand": truncate(presence(text(data.get("vendor"))), 80) if presence(text(data.get("vendor"))) else None,
            "color": squish(colour.group(1)) if colour else None,
            "category": truncate(presence(text(data.get("product_type"))), 80) if presence(text(data.get("product_type"))) else None,
            "description": truncate(description, 400),
            "fabric": material.group(1) if material else None,
            "image": self.shop_image((ruby_array(data.get("images")) or [None])[0]),
            "sizes": self.shop_sizes(data),
            "tags": tags,
            "sorted": not blank(text(data.get("product_type"))),
            "shape": self.photo_shape(dig(given, "shape")),
            "bottom_shape": self.photo_bottom_shape(dig(given, "bottom_shape")),
            "dress_shape": self.photo_dress_shape(dig(given, "dress_shape")),
        }
        product["women"] = self.women(product, url)
        kind = self.kind_of(product)
        if kind in ACCESSORIES:
            return self.accessory(product, kind, url)

        style = self.usual_key(kind, self.top_style_of(product), product)
        if given is not None:
            sizing = given.get("sizing")
        else:
            sizing = self.kiwi_answer({
                "shop": shop, "product": text(data.get("id")), "title": data.get("title"),
                "tags": ",".join(ruby_split(r",\s*", ",".join(text(t) for t in ruby_array(data.get("tags"))))),
                "type": data.get("product_type"), "vendor": data.get("vendor"),
            })
        if kind == "onepiece":
            return self.one_piece(product, url, lambda part, part_kind: self.read_kiwi(sizing, part_kind) or self.usual_for(part_kind, self.top_style_of(part), part))
        # Read by the server, a shop with no chart there may have one on its page; read by the browser, the page is
        # what the shop wouldn't give the server.
        if self.dress(kind, product):
            # A dress's own chart, or its shop's sizes with their usual measurements.
            chart = self.read_kiwi(sizing, kind) or dress_cut.usual_sizes(dress_cut.read(product), product["sizes"])
            return self.garment(product, chart, kind=kind, source_url=url)
        if kind == "trousers" and self.bottom_style_of(product) == "skirt":
            chart = self.read_kiwi(sizing, kind) or self.usual_skirts(product)
            return self.garment(product, chart, kind=kind, source_url=url)
        chart = self.read_kiwi(sizing, kind) or (self.usual_for(kind, style, product) if given is not None else None)
        if chart is None:
            return None
        return self.garment(product, self.with_usual(chart, kind, style, self.size_names(sizing), product), kind=kind, source_url=url)

    def from_text(self, chart_text, garment="jacket"):
        kind = text(garment) if text(garment) in KINDS else "jacket"
        said = text(chart_text).strip()
        # Just a size ("M"), as a listing that has no chart gives: that size's usual measurements.
        if re.fullmatch(r"(XXXL|3XL|XXL|2XL|XL|L|M|S|XS)", said, I):
            chart = self.usual_chart(kind, said.upper(), "tee")
            if chart:
                name = f"Your {'pants' if kind == 'trousers' else kind} in {said.upper()}"
                return self.garment({"name": name, "brand": None, "color": None, "category": None, "description": None}, chart, kind=kind, source_url=None)
        rows = [row for row in (self.split_line(line) for line in text(chart_text).split("\n")) if not all(blank(cell) for cell in row)]
        chart = chart_reader.read(rows, context=text(chart_text), garment=kind)
        if chart is None:
            raise Error("no_size_chart", "Couldn't read that as a size chart. Copy the whole table, header row included.")
        name = {"top": "Pasted top chart", "jacket": "Pasted jacket chart", "coat": "Pasted coat chart", "trousers": "Pasted trousers chart"}[kind]
        return self.garment({"name": name, "brand": None, "color": None, "category": None, "description": None}, chart, kind=kind, source_url=None)

    # ---- size charts from elsewhere: Kiwi Sizing, a shop's own size guide page

    def kiwi_chart(self, page, kind):
        """The chart a Kiwi Sizing shop loads after its page opens: the first of its tables that reads as one."""
        params = page.kiwi_sizing()
        return self.read_kiwi(self.kiwi_answer(params), kind) if params else None

    def kiwi_answer(self, params):
        try:
            return self.fetch_json(f"{KIWI_SIZING}?{to_query(params)}")
        except (fetcher.Error, ValueError):
            return None

    def read_kiwi(self, answer, kind):
        """Of a Kiwi Sizing answer's tables, the one that reads best as a size chart."""
        charts = [c for c in (chart_reader.read(rows, context="size chart", garment=kind) for rows in self.kiwi_tables(answer)) if c]
        return min(charts, key=lambda c: len(c.missing)) if charts else None

    @staticmethod
    def kiwi_tables(answer):
        if not isinstance(answer, dict):
            return []
        tables = []
        for sizing in ruby_array(answer.get("sizings"))[:10]:
            found = sizing.get("tables") if isinstance(sizing, dict) else None
            if isinstance(found, dict):
                tables.extend(list(found.values())[:10])
        out = []
        for table in tables:
            if not isinstance(table, dict):
                continue
            rows = []
            for row in ruby_array(table.get("data"))[:60]:
                rows.append([squish(fragment_text(text(cell.get("value") if isinstance(cell, dict) else cell)[:200])) for cell in ruby_array(row)[:20]])
            out.append(rows)
        return out

    def size_names(self, answer):
        """A size conversion table's other names for letter sizes ("S/M/L" next to "1/2/3"): {"M": "2", ...}."""
        for rows in self.kiwi_tables(answer):
            if not rows:
                continue
            header = rows[0]
            column = next((i for i, cell in enumerate(header) if re.fullmatch(r"\d+(\s*/\s*\d+)+", cell)), None)
            if column is None:
                continue
            names = {}
            for row in rows[1:]:
                letter = text(row[0] if row else "").upper().replace("3XL", "XXXL", 1).replace("2XL", "XXL", 1)
                value = row[column] if column < len(row) else None
                if letter in USUAL_SIZES and re.fullmatch(r"\d+", text(value)):
                    names[letter] = value
            if names:
                return names
        return {}

    def linked_guide_chart(self, page, kind, product, source_url):
        """A shop's own size guide page, when the product page links to one on the same site and has no chart of its
        own. Of its tables, the one for the product's gender and kind of garment that reads best."""
        link = page.size_guide_link(source_url)
        if not link:
            return None
        try:
            guide = Page(self.fetch_page(link))
        except fetcher.Error:
            return None
        said = GENDER.search(joined(product, "name", "category", "description"))
        gender = ("women" if WOMEN.search(said.group(0)) else "men") if said else None
        charts = []
        for table in guide.tables():
            if gender and (WOMEN if gender == "men" else MEN_ONLY).search(table.context):
                continue
            chart = chart_reader.read(table.rows, context=table.context, garment=kind)
            if chart:
                charts.append((chart, 0 if GARMENT_WORDS[kind].search(table.context) else 1))
        return min(charts, key=lambda pair: (pair[1], len(pair[0].missing)))[0] if charts else None

    # ---- usual sizes, when a listing has no chart

    def usual_trousers(self, product=None):
        """Pants by waist size (inches), or by letter size, with the usual seat, thigh, leg length and opening for each,
        in cm: named as the shop names them, women's cut for a women's listing, and as wide at the hem as it says."""
        product = product or {}
        names = ruby_array(product.get("sizes"))
        women = product.get("women")
        words = joined(product, "name", "description")
        opening, roomy = next((leg for pattern, leg in TROUSER_LEGS if pattern.search(words)), (38 if women else 40, 0))
        if re.search(r"oversized|baggy|relaxed", words, I):
            roomy += 8
        waists = [int(m.group(1)) for m in (re.fullmatch(r"(2[2-9]|3\d|4[0-6])", text(name).strip()) for name in names) if m]
        european = None if women else self.european_waists(names)
        inseam = self.shorts_inseam(product) if self.bottom_style_of(product) == "shorts" else None
        letters = list(dict.fromkeys(letter for letter in (self.letter_of(name) for name in names) if letter))
        if european:
            sizes = [self.trouser_size(name, w * 2.54, women, opening, roomy, inseam=inseam) for name, w in european.items()]
        elif len(waists) >= 2:
            sizes = [self.trouser_size(str(w), w * 2.54, women, opening, roomy, inseam=inseam) for w in sorted(set(waists))]
        elif len(letters) >= 2:
            sizes = []
            for letter in sorted(letters, key=ALL_LETTERS.index):
                waist = dress_cut.LETTERS[letter][1] + 2 if women else MEN_WAIST[letter]
                sizes.append(self.trouser_size(letter, waist, women, opening, roomy, inseam=inseam))
        else:
            sizes = [self.trouser_size(str(w), w * 2.54, False, opening, roomy, inseam=inseam) for w in range(28, 41, 2)]
        # Capri and cropped pants end above the ankle.
        short = 0.72 if re.search(r"\bcapri", words, I) else 0.88 if re.search(r"\bcropped\b", words, I) else None
        if short and not inseam:
            sizes = [{**size, "inseam": rnd(size["inseam"] * short, 1)} for size in sizes]
        if inseam and dig(product, "bottom_shape", "length") is not None and not self.named_inseam(product):
            sizes = self.shorts_as_photographed(sizes, product["bottom_shape"], product.get("women"))
        if product.get("bottom_shape"):
            sizes = self.as_photographed_legs(sizes, product["bottom_shape"])
        return Chart(sizes=sizes, unit="cm", kind="sizes", missing=[])

    @staticmethod
    def as_photographed_legs(sizes, shape):
        """The shop photo shows how wide the legs are: one leg's flat width at the thigh and the hem, as a share of the
        waist's flat width, is its round over the waist's round. Only within what pants are made like, and only when
        the photo's crotch is where a crotch is (a fifth to a half of the way down)."""
        rise = shape.get("rise")
        if not (rise is not None and 0.18 <= rise <= 0.5):
            return sizes
        out = []
        for size in sizes:
            thigh = rnd(clamp((shape.get("thigh") or 0) * size["waist"], size["seat"] * 0.5, size["seat"] * 0.75), 1)
            if shape.get("thigh") is None and size.get("thigh") is not None:
                thigh = clamp(size["thigh"], size["seat"] * 0.5, size["seat"] * 0.75)
            shorts = size["inseam"] < 40
            least = min(thigh * 0.9 if shorts else max(18, thigh * 0.35), 80)
            opening = rnd(clamp(shape["hem"] * size["waist"], least, 80), 1)
            out.append({**size, "leg_opening": opening, "thigh": max(thigh, opening)})
        return out

    @staticmethod
    def european_waists(names):
        """Men's pants numbered the European way, not by waist inches: French sizes are the waist in inches plus 10;
        Italian ones (from 44, running past 50) plus 16. {"44": 34, ...} (waist inches), or None for waist sizes."""
        numbers = sorted(set(int(text(name).strip()) for name in ruby_array(names) if re.fullmatch(r"\d{2}", text(name).strip())))
        if len(numbers) < 2 or min(numbers) < 36 or any(n % 2 for n in numbers):
            return None
        less = 16 if min(numbers) >= 42 and max(numbers) > 50 else 10
        return {str(n): n - less for n in numbers}

    @staticmethod
    def trouser_size(name, waist, women, opening, roomy, inseam=None):
        seat = waist + (26 if women else 20) + roomy
        thigh = rnd(seat * (0.58 if women else 0.6), 1)
        return {"name": name, "waist": rnd(waist, 1), "seat": rnd(seat, 1), "thigh": thigh,
                "inseam": float(inseam if inseam is not None else (76.0 if women else 81.0)),
                "leg_opening": rnd(float(max(opening, thigh * 0.95) if inseam is not None else opening), 1)}

    def usual_skirts(self, product):
        """A skirt's usual measurements in each of its shop's women's sizes: its waist and hips (by its cut) and its
        length (mini to maxi). A low-rise skirt's waist is made bigger, so it sits lower; a high-waisted one's sits at
        the waist."""
        cut = dress_cut.read(product)
        letters = list(dict.fromkeys(letter for letter in (self.letter_of(name) for name in ruby_array(product.get("sizes"))) if letter))
        if len(letters) < 2:
            letters = ["XS", "S", "M", "L", "XL"]
        words = joined(product, "name", "description")
        risen = next((rise for rise, pattern in SKIRT_RISES if pattern.search(words)), None)
        sizes = []
        for letter in sorted(letters, key=ALL_LETTERS.index):
            _, waist, hips = dress_cut.LETTERS[letter]
            ease = -2 if cut["stretch"] else {"fitted": 2, "slim": 3, "relaxed": 8, "flared": 6}.get(cut["fit"], 3)
            sizes.append({"name": letter, "waist": rnd(waist + (risen if risen is not None else min(ease, 2)), 1), "seat": rnd(hips + ease, 1),
                          "length": float(SKIRT_LENGTHS.get(cut["length"], 56) + (ALL_LETTERS.index(letter) - 3))})
        if dig(product, "bottom_shape", "skirt"):
            sizes = self.skirt_as_photographed(sizes, product["bottom_shape"])
        return Chart(sizes=sizes, unit="cm", kind="sizes", missing=[])

    @staticmethod
    def skirt_as_photographed(sizes, shape):
        out = []
        for size in sizes:
            seen = PHOTO_SKIRT_LENGTH * shape["length"] * size["waist"] / 2
            out.append({**size, "length": rnd(max(seen, SKIRT_SHORTEST), 1)} if seen < size["length"] * 0.88 else size)
        return out

    def shorts_inseam(self, product):
        """A pair of shorts' inseam (cm): the one its name gives ('2.5"', "7 inch"), or the usual (a women's about 10 cm,
        a men's 18)."""
        inches = self.named_inseam(product)
        if inches:
            return rnd(inches * 2.54, 1)
        return 10.0 if product.get("women") else 18.0

    @staticmethod
    def named_inseam(product):
        """The inseam in inches a pair of shorts' listing gives, or None."""
        found = re.search(r"(\d+(?:\.\d+)?)\s*(?:\"|”|''|-?inch|in\b)(?:\s*inseam)?", joined(product, "name", "description"), I)
        inches = float(found.group(1)) if found else None
        return inches if inches is not None and 1.5 <= inches <= 14 else None

    @staticmethod
    def shorts_as_photographed(sizes, shape, women):
        """Shorts as long as their photo shows them: their length from the waist is the photo's length over the waist's
        flat width times half the waist round, times PHOTO_SHORTS_LENGTH, less the rise, and only when that's more
        than 4 cm from the usual."""
        rise, least = (26, 6) if women else (30, 12)
        out = []
        for size in sizes:
            inseam = rnd(clamp(PHOTO_SHORTS_LENGTH * shape["length"] * size["waist"] / 2 - rise, least, 40), 1)
            if abs(inseam - size["inseam"]) <= 4:
                out.append(size)
            else:
                out.append({**size, "inseam": inseam, "leg_opening": rnd(max(size["leg_opening"], size["thigh"] * 0.95), 1)})
        return out

    def usual_sizes(self, kind, style, product=None):
        """Every letter size's usual measurements, when the shop has no chart: a guide, marked as guessed. product: its
        listing, for whether it's a women's (smaller and shorter) and how it says it fits; its shop's letter sizes
        (XXS to 4XL) are the ones given."""
        product = product if product is not None else {}
        if kind == "trousers":
            return None
        # A top's own style ("tee"), else its kind's: a coat, whose name gives no top style, is a coat (cut long).
        key = style if kind == "top" and style in USUAL else self.usual_key(kind, style)
        # A coat its photo or its name shows short (a short parka, a peacoat, an aviator): a jacket's length.
        short = key == "coat" and self.short_coat(product)
        if short:
            key = "jacket"
        if product.get("women") and f"{key}_women" in USUAL:
            key = f"{key}_women"
        base, step = USUAL[key]
        letters = list(dict.fromkeys(letter for letter in (self.letter_of(name) for name in ruby_array(product.get("sizes"))) if letter))
        numbered = self.brand_numbers(product.get("sizes")) if len(letters) < 2 else None
        if len(letters) < 2:
            letters = list(numbered.keys()) if numbered else USUAL_SIZES
        sizes = []
        for letter in sorted(letters, key=ALL_LETTERS.index):
            n = ALL_LETTERS.index(letter) - 1  # XS is the base
            chest, shoulders, sleeve, length = (rnd(b + d * n, 1) for b, d in zip(base, step))
            sizes.append({"name": f"{letter} ({numbered[letter]})" if numbered else letter, "chest": chest, "waist": None,
                          "shoulders": shoulders, "sleeve": sleeve, "length": rnd(length * SHORT_COAT_LENGTH if short else length, 1)})
        usual = sizes
        if product.get("description") is not None:
            sizes = self.cut_as_listed(sizes, product, kind)
        if dig(product, "shape", "length") is not None:
            sizes = self.photographed_length(usual, sizes, product, kind)
        return Chart(sizes=sizes, unit="cm", kind="sizes", missing=["waist"])

    @staticmethod
    def short_coat(product):
        name = re.sub(r"\s+[-–]\s+[^-–]+\Z", "", text(product.get("name")))
        return bool(SHORT_COAT_NAME.search(name)) or float(dig(product, "shape", "sleeve_down") or 0) >= 0.88

    def photographed_length(self, usual, sizes, product, kind):
        """A top's length as its photo shows it, on its usual sizes (usual) as its words made them (sizes)."""
        family = self.length_family(product, kind)
        if not family:
            return sizes
        shape = product["shape"]
        seen = float(shape["length"])
        typical = TYPICAL_PHOTO_LENGTH[family]
        named_crop = bool(re.search(r"crop(?:ped)?\b", text(product.get("name")), I))
        words = joined(product, "name", "description")
        if product.get("women") or re.search(r"crop(?:ped)?\b|boxy|shrunken|baby tee|mini tee", words, I):
            least = 0.8
        elif re.search(r"regular fit", words, I):
            least = 0.95
        else:
            least = 0.9
        out = []
        for i, size in enumerate(sizes):
            before = usual[i]["length"]
            length = size["length"]
            if length < before * 0.97 and seen >= typical * UNCROP.get(family, 9):
                length = before
            if family == "tee" and size.get("chest") is not None and float(shape.get("sleeve_down") or 0) < 0.7:
                read = PHOTO_TEE_LENGTH * seen * size["chest"] / 2
                if abs(read / length - 1) > 0.12:
                    length = clamp(read, min(before * least, length), max(before * 1.3, length))
            if family == "sweat" and seen < typical * 0.85:
                length = min(length, before * max(seen / typical, 0.8))
            if family == "jacket" and named_crop and seen < typical * 0.95:
                length = before * 0.8
            out.append({**size, "length": rnd(length, 1)})
        return out

    def length_family(self, product, kind):
        if kind == "jacket":
            return "jacket"
        if kind != "top":
            return None
        style = self.top_style_of(product)
        if style in ("tee", "polo", "tank", "rugby"):
            return "tee"
        if style in ("hoodie", "sweatshirt", "sweater"):
            return "sweat"
        if style == "shirt":
            return "shirt"
        return None

    def usual_for(self, kind, style, product):
        """The usual sizes for a listing with no chart: a top's or a jacket's, or pants by waist size or letter."""
        return self.usual_trousers(product) if kind == "trousers" else self.usual_sizes(kind, style, product)

    @staticmethod
    def brand_numbers(names):
        """{"XS": "0", "S": "1", ...} for the numbers a shop sells, when it sells at least three of 0 to 6."""
        numbers = sorted(set(int(text(name).strip()) for name in ruby_array(names) if re.fullmatch(r"[0-6]", text(name).strip())))
        if len(numbers) < 3:
            return None
        return {BRAND_SIZE_LETTERS[n]: str(n) for n in numbers}

    @staticmethod
    def letter_of(name):
        found = re.match(r"(4XL|XXXXL|XXXL|3XL|XXL|2XL|XL|L|M|S|XS|XXS|2XS)\b", text(name).upper().strip())
        if not found:
            return None
        label = found.group(1)
        return {"XXXXL": "4XL", "3XL": "XXXL", "2XL": "XXL", "2XS": "XXS"}.get(label, label)

    def cut_as_listed(self, sizes, product, kind):
        if kind != "top":
            return sizes
        words = joined(product, "name", "description")
        change = [rule for pattern, rule in FIT_WORDS if pattern.search(words)]
        change = self.as_photographed(change, product, words)
        if not change:
            return sizes

        def product_of(values):
            out = 1
            for value in values:
                out *= value
            return out

        out = []
        for size in sizes:
            chest = size["chest"] + sum(int(c.get("chest", 0)) for c in change)
            shoulders = size["shoulders"] + sum(int(c.get("shoulders", 0)) for c in change)
            length = (size["length"] + sum(int(c.get("length", 0)) for c in change)) * product_of(c["length_share"] for c in change if "length_share" in c)
            sleeve = size["sleeve"] * (product_of(c["sleeve_share"] for c in change if "sleeve_share" in c) if size["sleeve"] < 30 else 1)
            out.append({**size, "chest": rnd(chest, 1), "shoulders": rnd(shoulders, 1), "length": rnd(length, 1), "sleeve": rnd(sleeve, 1)})
        return out

    def as_photographed(self, change, product, words):
        shape = product.get("shape")
        if not shape:
            return change
        sewn = self.sleeves_sewn(shape)
        if sewn == "high":
            change = [c for c in change if c not in ROOMY_WORDS]
        if self.baby_tee(product, words):
            change = change + [BABY_TEE]
        if sewn == "low" and not any(c in ROOMY_WORDS for c in change):
            change = change + [ROOMY_TOP]
        if shape.get("sleeve") is not None and shape["sleeve"] < 0.75 and float(shape.get("sleeve_down") or 0) < 0.45 and not re.search(r"cap sleeves?", words, I):
            change = change + [SHORT_SLEEVES]
        return change

    @staticmethod
    def sleeves_sewn(shape):
        """Where a photographed top's arms are sewn in: "high" (close-cut), "low" (dropped shoulders) or None."""
        shape = shape or {}
        armpit, waist, length = shape.get("armpit"), shape.get("waist"), shape.get("length")
        if armpit is None or length is None:
            return None
        depth = armpit * length  # shoulders to armpit, over the chest's width
        if depth < 0.62 and float(waist or 0) < 1.05:
            return "high"
        if depth >= 0.72:
            return "low"
        return None

    def baby_tee(self, product, words=None):
        """A women's tee whose photo shows it cut close, with no words saying how close: a baby tee, made snug and
        short."""
        words = joined(product, "name", "description") if words is None else words
        return bool(product.get("women") and product.get("shape") and self.sleeves_sewn(product["shape"]) == "high"
                    and not FIT_WORDS[3][0].search(words))

    @staticmethod
    def photo_shape(shape):
        """The shape the browser read off the shop photo ({"length", "waist", "sleeve", "sleeveDown", "armpit"}, each a
        share of the front's width or length), checked: None unless every part is a plausible number."""
        if not isinstance(shape, dict):
            return None
        read = {"armpit": shape.get("armpit"), "waist": shape.get("waist"), "sleeve": shape.get("sleeve"),
                "sleeve_down": shape.get("sleeveDown"), "length": shape.get("length")}
        for value in read.values():
            if value is None:
                continue
            if number_or_none(value) is None or not (value == value and abs(value) != float("inf")) or not 0 <= value <= 5:
                return None
        return {key: value for key, value in read.items() if value is not None} or None

    @staticmethod
    def photo_bottom_shape(shape):
        """The pants' shape the browser read off the shop photo ({"thigh", "hem", "rise", "length"}: one leg's width at
        the thigh and the hem, over the waist's width), checked: None unless plausible. A skirt's is its hips' and
        hem's widths over its waist's, and its length over it ({"skirt": True, "hips", "hem", "length"})."""
        if not isinstance(shape, dict):
            return None

        def fine(value, low, high):
            return number_or_none(value) is not None and value == value and abs(value) != float("inf") and low <= value <= high

        if shape.get("skirt") is True:
            read = {"hips": shape.get("hips"), "hem": shape.get("hem"), "length": shape.get("length")}
            if not all(fine(value, 0.3, 6) for value in read.values()):
                return None
            return {**read, "skirt": True}
        # (Wide legs laid touching hide where the thigh is: that one may be missing.)
        read = {"thigh": shape.get("thigh"), "hem": shape.get("hem"), "rise": shape.get("rise"), "length": shape.get("length")}
        if any(not fine(value, 0.05, 6) and not (key == "thigh" and value is None) for key, value in read.items()):
            return None
        return read

    @staticmethod
    def photo_dress_shape(shape):
        """A dress's shape the browser read off the shop photo: its widths over its chest's, heights over its length,
        where it widens for its hem, its neckline, and whether it's a halter, strapless or has sleeves."""
        if not isinstance(shape, dict):
            return None

        def number(key, low, high):
            value = shape.get(key)
            ok = number_or_none(value) is not None and value == value and abs(value) != float("inf") and low <= value <= high
            return rnd(float(value), 3) if ok else None

        read = {
            "waist": number("waist", 0.5, 1.3), "waist_at": number("waistAt", 0.15, 0.7), "hips": number("hips", 0.6, 2),
            "hem": number("hem", 0.6, 3.5), "neck_depth": number("neckDepth", 0, 0.6), "neck_width": number("neckWidth", 0, 0.95),
            "flare_from": shape.get("flareFrom") if shape.get("flareFrom") in DRESS_FLARES else None,
            "halter": shape.get("halter") is True, "strapless": shape.get("strapless") is True,
            "sleeves": shape.get("sleeves") if shape.get("sleeves") in ("long", "short") else None,
            # Its length over its chest's width (see dress_cut.with_photo).
            "length": number("length", 0.8, 8),
        }
        return {key: value for key, value in read.items() if value is not None and value is not False} or None

    @staticmethod
    def women(product, url):
        """A women's listing: its shop tags it so ("wmns", "womens") or files it there, or its name says so."""
        tags = {text(tag).lower() for tag in ruby_array(product.get("tags"))}
        if tags & {"wmns", "womens", "women", "woman", "ladies"}:
            return True
        if tags & {"mens", "men", "man"}:
            return False
        return bool(re.search(r"\bwom[ae]n'?s?\b|\bwmns\b|ladies", " ".join(text(part) for part in (product.get("name"), product.get("category"), url)), I))

    def with_usual(self, chart, kind, style, names=None, product=None):
        """A chart read from size names alone (a conversion table gives only the chest) with each letter size's usual
        shoulders, sleeve and length filled in; and each size named as the shop names it when it has its own."""
        names = names or {}
        if not (chart.kind == "sizes" and kind != "trousers"):
            return chart
        usual = {size["name"]: size for size in self.usual_sizes(kind, style, product or {}).sizes}
        sizes = []
        for size in chart.sizes:
            found = LETTER.search(text(size.get("name")))
            letter = found.group(1).upper().replace("3XL", "XXXL", 1).replace("2XL", "XXL", 1) if found else None
            known = usual.get(letter)
            if not known:
                sizes.append(size)
                continue
            merged = {**size, **{part: size.get(part) if size.get(part) is not None else known.get(part) for part in ("shoulders", "sleeve", "length")}}
            if names.get(letter):
                merged["name"] = f"{letter} ({names[letter]})"
            sizes.append(merged)
        return chart.with_(sizes=sizes, missing=[part for part in chart.missing if any(size.get(part) is None for size in sizes)])

    @staticmethod
    def shop_image(image):
        """A product photo's address (the server fetches it with the usual checks)."""
        src = text(image.get("src")) if isinstance(image, dict) else ""
        if src.startswith("//"):
            src = "https:" + src
        return src if src.startswith("https://") else None

    @staticmethod
    def usual_key(kind, style, product=None):
        """Which usual sizes a top's take: a T-shirt's, a dress's (with long sleeves when its listing says so), or
        another top's."""
        if kind != "top":
            return kind
        if style in ("tee", "polo", "tank", "shortshirt"):
            return "tee"
        if style == "dress":
            return "dress_long" if re.search(r"long[- ]?sleeve|\bl/s\b", joined(product or {}, "name", "description"), I) else "dress"
        return "top"

    def usual_chart(self, kind, stated, style):
        """A one-size chart from the size a listing says it is, marked as estimated from the size's name."""
        if kind == "trousers" or stated is None:
            return None
        found = LETTER.search(stated)
        if not found:
            return None
        letter = found.group(1).upper().replace("3XL", "XXXL", 1).replace("2XL", "XXL", 1)
        base, step = USUAL[style if style in USUAL else self.usual_key(kind, style)]
        n = USUAL_SIZES.index(letter)
        chest, shoulders, sleeve, length = (rnd(b + d * n, 1) for b, d in zip(base, step))
        size = {"name": stated, "chest": chest, "waist": None, "shoulders": shoulders, "sleeve": sleeve, "length": length}
        return Chart(sizes=[size], unit="cm", kind="sizes", missing=["waist"])

    # ---- things worn but not fitted

    def accessory(self, product, kind, source_url):
        """Shoes, socks, a belt or a bag: their look, colour and cloth, and the shop's sizes to pick from. Nothing is
        measured: they're drawn on the mannequin as they look."""
        if kind == "shoes" and not footwear_on():
            raise not_supported("shoes")
        if kind == "bag" and not bags_on():
            raise not_supported("bags")
        # (The shop's tags count as its category: a boot filed only under "boots".)
        tags = " ".join(text(tag) for tag in ruby_array(product.get("tags"))
                        if not (" - " in text(tag) or text(tag).lower() == text(product.get("name")).lower()))
        words = " ".join([text(product.get("name")), text(product.get("category")), text(product.get("description")), tags])
        named = " ".join([text(product.get("name")), text(product.get("category")), tags])
        if kind == "shoes":
            style = shoe_style(product.get("name"), product.get("category"), tags)
        elif kind == "socks":
            style = first_match(SOCK_STYLES, named) or "crew"
        elif kind == "bag":
            style = bag_style(named, product.get("description"))
        else:
            style = "belt"
        if re.search(r"suede|nubuck", words, I):
            cloth = "suede"
        elif re.search(r"leather", words, I):
            cloth = "leather"
        elif re.search(r"canvas|nylon|webbing|mesh|knit", words, I):
            cloth = "canvas"
        else:
            cloth = "knit" if kind == "socks" else "leather" if kind == "belt" else "canvas"
        # A bag is one size: its own measurements (cm), when the listing gives them, are what's drawn.
        size_of_bag = bag_size(text(product.get("description")), style=style) if kind == "bag" else None
        names = [text(name) for name in ruby_array(product.get("sizes")) if not re.fullmatch(r"default title", text(name), I)] or ["One size"]
        if kind == "bag":
            names = ["One size"]
        # A shoe's fit (shoes.py): the sizes' scale, the width the listing gives, and how it's worn.
        shoe_fit = {}
        if kind == "shoes":
            width = None
            if not re.search(r"\bwide[- ]leg|\bwide fit\b.*pants", words, I):
                width = next((code for pattern, code in fit_shoes.WIDTH_WORDS if pattern.search(words)), None)
            if re.search(r"running|runner|racer|trail|gel|pegasus|cloud|hoka|asics|speed", named, I):
                wear = "runner"
            elif re.search(r"heel|pump|stiletto|platform", named, I):
                wear = "heel"
            elif re.search(r"flat|ballet|ballerina", named, I):
                wear = "flat"
            else:
                wear = style
            shoe_fit = {key: value for key, value in {"scale": fit_shoes.scale_for(names, women=bool(product.get("women"))), "width": width,
                                                       "wear": wear}.items() if value is not None}
        out = {"name": presence(product.get("name")) or kind.capitalize()}
        if kind == "shoes":
            # (The listing's words, for a shoe's last.)
            out["words"] = truncate(squish(words), 300)
        out.update(shoe_fit)
        out.update({"brand": product.get("brand"), "color_name": product.get("color"),
                    "color": self.color_hex([product.get("color"), product.get("description"), product.get("name")]),
                    "fabric": cloth, "style": style})
        if product.get("image"):
            out["image_url"] = product["image"]
        out["source_url"] = source_url
        out["garment"] = kind
        if kind == "belt":
            out["buckle"] = "gold" if re.search(r"gold|brass", words, I) else "silver"
        if size_of_bag:
            out["bag_size"] = size_of_bag
        if product.get("women"):
            out["women"] = True
        out["chart"] = {"sizes": [{"name": name} for name in names[:30]], "unit": "cm", "kind": "sizes", "missing": []}
        return out

    def one_piece(self, product, source_url, chart_for):
        """A romper or a jumpsuit as its two halves, each fitted as its own kind: a top (a tank on straps, else a tee or
        a long-sleeve top, by its sleeves) and shorts or pants, with its colour and cloth. chart_for(part, kind) gives
        each half's chart."""
        cut = dress_cut.read(product)
        words = joined(product, "name", "category", "description")
        top_style = {"long": "Long Sleeve Tee", "short": "Tee"}.get(cut["sleeves"], "Tank")
        shorts = bool(re.search(r"romper|playsuit|short", words, I)) and not re.search(r"jumpsuit|boiler|coverall|overall|dungaree|flight suit", words, I)
        name = re.sub(r"\s+[-–]\s+[^-–]+\Z", "", text(product.get("name")))
        description = ONE_PIECES.sub("", text(product.get("description")))
        top = {**product, "name": f"{name} {top_style}", "category": top_style, "description": description}
        bottom = {**product, "name": f"{name} {'Shorts' if shorts else 'Pants'}", "category": "Shorts" if shorts else "Pants", "description": description}
        parts = {"top": self.garment(top, chart_for(top, "top"), kind="top", source_url=source_url),
                 "trousers": self.garment(bottom, chart_for(bottom, "trousers"), kind="trousers", source_url=source_url)}
        for part in parts.values():
            part.update({"name": product.get("name"), "color_name": product.get("color"), "one_piece": True})
        out = {"name": product.get("name"), "brand": product.get("brand"), "color_name": product.get("color"), "color": parts["top"]["color"],
               "fabric": parts["top"]["fabric"], "garment": "onepiece", "style": "romper" if shorts else "jumpsuit"}
        if product.get("image"):
            out["image_url"] = product["image"]
        out["source_url"] = source_url
        if product.get("women"):
            out["women"] = True
        out["parts"] = parts
        return out

    # ---- what it is

    def kind_of(self, product):
        """Top, jacket, coat or trousers (or a one-piece, or something worn but not fitted), from the product's name and
        category."""
        # Not the colour after the name: "Track Jacket - Peacoat" is a jacket, not a pea coat. But a name that says
        # nothing of what it is before its dash says it after.
        full = text(product.get("name"))
        head = re.sub(r"\s+[-–]\s+[^-–]+\Z", "", full)
        words = " ".join([head if NAMES_A_GARMENT.search(head) else full, text(product.get("category"))])
        # The shop's own category and tags say first what something is: a sneaker is shoes, whatever its name says.
        # (Not a tag that's the product's own name, as some shops tag every product.)
        tags = [tag for tag in ruby_array(product.get("tags"))
                if re.match(r"(?!mens\Z|wmns\Z|womens\Z)", text(tag), I) and not (" - " in text(tag) or text(tag).lower() == full.lower())]
        sorted_as = " ".join(text(part) for part in [product.get("category"), *tags] if part is not None)
        category = text(product.get("category"))
        # The category alone first: a "Wallet Short", filed under Shorts, is shorts, not a wallet.
        not_fitted = next((rule for rule in NOT_FITTED if rule[1].search(category)), None)
        if not not_fitted and not FITTED_KINDS.search(category):
            not_fitted = next((rule for rule in NOT_FITTED
                               if rule[1].search(sorted_as) or (rule[1].search(words) and not FITTED_KINDS.search(words))), None)
        # Shoes, socks and belts are drawn (on the feet, on the legs, round the waist), with no fit to check.
        if not_fitted:
            worn = next((kind for kind, pattern in WORN_ON if not_fitted[0] == ACCESSORY_GROUPS[kind]
                         and (pattern.search(words) or pattern.search(sorted_as)) and not re.search(r"\bbags?\b|backpack|wallet", words, I)), None)
            if worn:
                return worn
            # A bag (a belt bag is one, not a belt), unless it's a wallet, a case or a suitcase filed with the bags.
            if not_fitted[0] in ("bags", "belts", "accessories") and (BAGS.search(words) or BAGS.search(sorted_as)) \
                    and not (not_fitted[0] == "belts" and not re.search(r"belt bag|waist (?:bag|pack)", words, I)) and not NOT_BAGS.search(words):
                return "bag"
            raise not_supported(not_fitted[0])
        # A romper or jumpsuit: a top and shorts or pants made as one piece.
        if ONE_PIECES.search(words):
            return "onepiece"
        # A "Maxi Coat" is a coat, not a dress (a "Trench Dress" is still a dress).
        if COATS.search(words) and not NOT_COATS.search(words) and not re.search(r"\bdress\b", words, I):
            return "coat"
        # A "maxi skirt" is a skirt, not a dress.
        if DRESSES.search(words) and not re.search(r"skirts?\b|skort", words, I):
            return "top"
        if COATS.search(words) and not NOT_COATS.search(words):
            return "coat"
        # A sweater vest is worn over a shirt or a tee, as a jacket is, and drawn as a tank; a padded vest is outerwear.
        if self.vest(product):
            return "jacket"
        # A cardigan is worn open over a top, as a jacket is.
        if re.search(r"cardigan", words, I):
            return "jacket"
        # So is a knit that zips all the way down, but not a half-zip pullover.
        if re.search(r"\bzip\b|zip[- ]up|full[- ]zip", words, I) and re.search(r"sweater|knit|crochet|cable|track", words, I) \
                and not re.search(r"half[- ]zip|quarter[- ]zip|1/4|hood", words, I):
            return "jacket"
        # Pants named for their cloth ("Suiting Trouser") are pants, not a suit's jacket.
        if re.search(r"\b(?:trousers?|pants?|jeans?|shorts?(?![- ]?sleeve)|skirts?)\s*(?:[-–].*)?\Z", full, I) or TROUSERS.search(category):
            return "trousers"
        if JACKETS.search(words):
            return "jacket"
        description = text(product.get("description"))
        if re.search(r"hoodie|hooded", words, I) and HOODED_OUTERWEAR.search(description):
            # A knit hoodie that zips is still a knit top; an insulated one is a jacket whatever it's made of.
            if INSULATED.search(description) or not (self.knitwear(product) or SWEATSHIRT_MAKE.search(description)):
                return "jacket"
        if TROUSERS.search(words):
            return "trousers"
        if TOPS.search(words):
            return "top"
        # One the shop files under outerwear is worn as a jacket (a "Court Shrug").
        if OUTERWEAR.search(category) or any(re.fullmatch(r"outerwear", text(tag).strip(), I) for tag in tags):
            return "jacket"
        # A shop's page that names nothing else is most often a jacket (a "Hudson"); a Shopify listing says what it is.
        if not (UNSUPPORTED.search(words) or product.get("sorted")):
            return "jacket"
        raise Error("not_supported", "Can't try this on yet. It works with tops, dresses, jackets, coats and pants.")

    @staticmethod
    def puffer(product):
        words = QUILTED_INSIDE.sub(" ", joined(product, "name", "description"))
        if LIGHT_QUILT.search(text(product.get("name"))):
            return bool(FILLED.search(words))
        return bool(PUFFER.search(words))

    def vest(self, product):
        return self.vest_named(product) and not INSULATED.search(joined(product, "name", "description"))

    @staticmethod
    def vest_named(product):
        return bool(re.search(r"\bvests?\b", joined(product, "name", "category"), I))

    def dress(self, kind, product):
        return kind == "top" and self.top_style_of(product) == "dress" and not re.search(r"skirts?\b|skort", joined(product, "name", "category"), I)

    @staticmethod
    def bottom_style_of(product):
        found = next((style for style in (first_match(BOTTOM_STYLES, product.get(key)) for key in ("name", "category")) if style), None) or "trousers"
        # Pants whose photo shows them shorts: the photo's length is under 1.85 of the waist's flat width.
        length = dig(product, "bottom_shape", "length")
        if found in ("trousers", "joggers", "jeans") and length is not None and length < 1.85:
            return "shorts"
        return found

    @staticmethod
    def shop_sizes(data):
        """A Shopify product's size names, from its "Size" option (or its variants' names)."""
        option = next((o for o in ruby_array(data.get("options")) if isinstance(o, dict) and re.search(r"size", text(o.get("name")), I)), None)
        if option:
            names = ruby_array(option.get("values"))
        else:
            names = []
            for variant in ruby_array(data.get("variants")):
                head = ruby_split(" / ", text(variant.get("title"))) if isinstance(variant, dict) else []
                names.append(head[0] if head else None)
        out = [text(name).strip() for name in names if name is not None]
        return list(dict.fromkeys(name for name in out if name))[:30]

    # ---- the garment, as the page draws and fits it

    def garment(self, product, chart, kind, source_url):
        if kind != "trousers":
            chart = self.shoulder_sleeves(self.plausible(chart, kind), product)
        # (A vest is drawn without sleeves, a padded one too.)
        if kind == "top":
            style = self.top_style_of(product)
        elif kind == "trousers":
            style = self.bottom_style_of(product)
        elif kind == "jacket" and self.vest_named(product):
            style = "tank"
        else:
            style = None
        # Shorts' "inseam" past 40 cm is their whole length from the waist: less the rise.
        if style == "shorts":
            rise = 26 if product.get("women") else 30
            chart = chart.with_(sizes=[{**s, "inseam": rnd(s["inseam"] - (s.get("rise") if s.get("rise") is not None else rise), 1)}
                                       if float(s.get("inseam") or 0) > 40 else s for s in chart.sizes])
        # A sweater with short sleeves (a knit tee, a mock neck) is drawn with short sleeves.
        if style == "sweater" and self.short_sleeved(product, chart):
            style = "shortknit"
        if style in ("tee", "polo", "shortshirt", "shortknit"):
            chart = self.tee_sleeves(chart)
        # A tank top has no sleeves, and its straps sit in from the shoulders: neither is measured.
        if style == "tank":
            chart = chart.with_(sizes=[{**s, "sleeve": None, "shoulders": None} for s in chart.sizes],
                                missing=[part for part in chart.missing if part not in ("sleeve", "shoulders")])
        # A skirt's cut, read as a dress's is (its length, how it flares, its cloth), and the shape its photo showed.
        skirt_cut = None
        if style == "skirt":
            read = dress_cut.read({key: value for key, value in product.items() if key != "dress_shape"})
            skirt_cut = {key: read.get(key) for key in ("length", "fit", "stretch", "fabric", "printed", "details", "hem_flare", "pleats", "tiers", "flounce")}
            if re.search(r"pleat", joined(product, "name", "description"), I):
                skirt_cut["fit"] = "pleated"
            if not skirt_cut.get("hem_flare"):
                skirt_cut.pop("hem_flare", None)
            shape = product.get("bottom_shape")
            if shape and shape.get("skirt") and shape["hem"] >= shape["hips"] * 0.85:
                skirt_cut["shape"] = {"hips": shape["hips"], "hem": shape["hem"]}
        # Pants: pull-on, how loose the shop says they're cut, and whether they come unhemmed.
        if kind == "trousers" and style != "skirt":
            skirt_cut = self.bottoms_cut(product, style, chart)
        if style == "dress":
            cut = dress_cut.read(product)
            chart = chart.with_(missing=[part for part in chart.missing if part not in dress_cut.not_needed(cut)])
            return self.dress_garment(product, chart, cut, source_url)
        # A top's cut, when its listing says it sits close or is made oversized; a jacket's, when it's oversized or
        # made to end at the waist.
        if kind == "top":
            fit_cut = self.top_cut(product)
        elif kind == "jacket":
            fit_cut = self.jacket_cut(product)
        elif kind == "coat" and self.hooded(product):
            fit_cut = {"hood": True}
        else:
            fit_cut = None
        # A bodysuit fastens below, so it's always worn tucked in, and it's cut to sit close and stretch on.
        bodysuit = kind == "top" and bool(re.search(r"bodysuit", joined(product, "name", "category"), I))
        if bodysuit:
            fit_cut = {**(fit_cut or {}), "fit": "fitted", "stretch": True}
        # A half-zip or quarter-zip pullover: a stand collar with a short zip down from it (a hoodie keeps its hood).
        if kind == "top" and style not in ("hoodie", "dress", "tank") and HALF_ZIP.search(joined(product, "name", "description")):
            fit_cut = {**(fit_cut or {}), "half_zip": True}
        # A collar the listing names: drawn turned down over its stand, whatever the photo's outline made of it.
        if self.named_collar(product, kind, style, fit_cut):
            fit_cut = {**(fit_cut or {}), "collar": "shirt"}
        words = joined(product, "name", "description")
        out = {"name": presence(product.get("name")) or "Jacket"}
        # The listing's words, for what the page reads of the make itself (a dress's hood and zip).
        if presence(product.get("description")):
            out["description"] = truncate(product["description"], 400)
        out.update({"brand": product.get("brand"), "color_name": product.get("color"),
                    "color": self.color_hex([product.get("color"), product.get("description"), product.get("name")]),
                    "fabric": self.fabric_of(product, kind)})
        if kind == "jacket":
            out["style"] = self.style_of(product, source_url)
        if style:
            out["style"] = style
        if product.get("image"):
            out["image_url"] = product["image"]
        out["source_url"] = source_url
        out["garment"] = kind
        if product.get("women"):
            out["women"] = True
        if kind in ("top", "jacket") and re.search(r"crop(?:ped)?\b", words, I):
            out["cropped"] = True
        if kind == "top" and chart.kind == "sizes" and self.baby_tee(product):
            out["snug"] = True
        if skirt_cut is not None:
            out["cut"] = skirt_cut
        elif fit_cut is not None:
            out["cut"] = fit_cut
        if kind == "top" and product.get("shape") and self.sleeves_sewn(product["shape"]) == "low":
            out["dropped"] = True
        # (A cardigan that zips is drawn with its zip, not buttons.)
        if (style == "hoodie" or (kind == "jacket" and self.style_of(product, source_url) == "cardigan")) and self.zipped(product):
            out["zip"] = True
        # Its length taken from its photo (photographed_length, short_coat): the page doesn't crop it again.
        if kind in ("top", "jacket", "coat") and chart.kind == "sizes" and dig(product, "shape", "length") is not None:
            out["photo_length"] = True
        if bodysuit:
            out["bodysuit"] = True
        if kind in ("jacket", "coat") and self.puffer(product):
            out["puffer"] = True
        out["chart"] = chart.as_json()
        return out

    def knitwear(self, product, fibres=True):
        """Knitted, by what it is (a sweater, a cardigan, "knit"), or by what it's spun from when that's what it's made
        of: a "Cashmere Hoodie", a "Merino wool" crewneck, "100% Cashmere". Not a polo with 5% cashmere in its blend,
        nor (fibres False) a coat or jacket, whose cashmere or merino is woven."""
        if KNITWEAR.search(joined(product, "name", "category", "description")):
            return True
        if not fibres:
            return False
        lead = re.search(r"\A\W*(\w+(?:\s+\w+){0,2})", text(product.get("description")))
        main = self.main_fibre(presence(product.get("fabric")) or product.get("description"))
        return any(KNIT_FIBRES.search(text(part)) for part in (product.get("name"), lead.group(1) if lead else None, main))

    def top_cut(self, product):
        """How a top is cut, when its listing says it sits close: {"fit": "fitted", "stretch": True/False}, or
        {"fit": "oversized"}; None for a top that says nothing about its fit (the usual)."""
        words = joined(product, "name", "description")
        if not FITTED_TOP.search(words):
            return {"fit": "oversized"} if self.oversized(product, words) else None
        return {"fit": "fitted", "stretch": bool(self.knitwear(product) or dress_cut.STRETCH.search(words))}

    def oversized(self, product, words=None):
        """A top or jacket the shop says is made big, unless its photo shows it cut close."""
        words = joined(product, "name", "description") if words is None else words
        return bool(OVERSIZED.search(words)) and not (product.get("shape") and self.sleeves_sewn(product["shape"]) == "high")

    def jacket_cut(self, product):
        """{"fit": "oversized"}, {"ends": "waist"} for one made to end at the waist, {"hood": True}; None for none."""
        cut = {}
        if self.oversized(product):
            cut["fit"] = "oversized"
        if WAIST_LENGTH.search(text(product.get("name"))):
            cut["ends"] = "waist"
        if self.hooded(product):
            cut["hood"] = True
        return cut or None

    @staticmethod
    def hooded(product):
        """A jacket or coat with a hood: drawn with one. A hood stowed in the collar, or one it hasn't, isn't drawn."""
        words = joined(product, "name", "description")
        return bool(HOODED.search(words)) and not NO_HOOD.search(words)

    def bottoms_cut(self, product, style, chart):
        """{"elastic": True} for pull-on pants, {"fit": "loose"} or "slim" by the shop's words, {"hem": "unfinished"}
        for pants sold long, {"open_hem": True} for joggers with an open hem. None for none of these."""
        words = joined(product, "name", "description")
        loose, slim = bool(LOOSE_BOTTOMS.search(words)), bool(SLIM_BOTTOMS.search(words))
        cut = {}
        if style not in ("joggers", "leggings") and ELASTIC_WAIST.search(words):
            cut["elastic"] = True
        if style != "leggings" and loose != slim:
            cut["fit"] = "loose" if loose else "slim"
        if style not in ("shorts", "leggings") and self.unfinished_hem(chart, words, product.get("women")):
            cut["hem"] = "unfinished"
        if style == "joggers" and self.open_hem(product, words):
            cut["open_hem"] = True
        return cut or None

    @staticmethod
    def open_hem(product, words):
        """Sweatpants sold as joggers whose hem is open, not gathered into a rib cuff."""
        if re.search(r"\bcuff(?:ed|s)?\b|elastic(?:ated)? (?:hem|cuffs?|ankles?)|ribbed (?:hem|cuffs?)", words, I):
            return False
        return bool(OPEN_HEM.search(words)) or float(dig(product, "bottom_shape", "hem") or 0) >= 0.58

    @staticmethod
    def unfinished_hem(chart, words, women):
        """Pants sold unhemmed: the listing says so, or every size has the same inseam, far longer than a usual leg's.
        A raw hem is only a cut edge unless the leg is long too."""
        leg = 76 if women else 81
        inseams = [size.get("inseam") for size in chart.sizes]
        given = [inseam for inseam in inseams if inseam is not None]
        long = len(given) == len(inseams) and len(inseams) >= 2 and min(inseams) > leg + UNHEMMED_PAST and max(inseams) - min(inseams) <= 2
        return bool(long or UNHEMMED.search(words) or (re.search(r"raw[- ]hem", words, I) and given and min(given) > leg + 6))

    @staticmethod
    def zipped(product, words=None):
        """A hoodie that zips all the way down the front (drawn with a zip; a half-zip pullover isn't)."""
        words = joined(product, "name", "description") if words is None else words
        return bool(re.search(r"full[- ]zip|zip[- ]up|zip(?:per)? (?:closure|front|hoodie|hoody|sweatshirt)|zip[- ]?thr(?:ough|u)|two-way zip|\bzipped\b", words, I)) \
            and not re.search(r"half[- ]zip|quarter[- ]zip|1/4[- ]zip", words, I)

    def dress_garment(self, product, chart, cut, source_url):
        out = {"name": presence(product.get("name")) or "Dress", "brand": product.get("brand"), "color_name": product.get("color"),
               "color": self.color_hex([product.get("color"), product.get("description"), product.get("name")]), "fabric": cut["fabric"],
               "style": "dress", "cut": cut}
        if product.get("image"):
            out["image_url"] = product["image"]
        # The listing's words, for what the page reads of the make itself (a hood, a zip down the front).
        if presence(product.get("description")):
            out["description"] = truncate(product["description"], 400)
        out.update({"source_url": source_url, "garment": "top", "women": True, "chart": chart.as_json()})
        return out

    def fabric_of(self, product, kind="jacket"):
        parts = ruby_split(r"[;,]?\s*lining", text(product.get("fabric")), flags=I)
        shell = parts[0] if parts else None  # "100% Cashmere; Lining 55% Silk, 45% Cotton"
        # What it's made of says it best; else its name and description.
        name = text(product.get("name")).removeprefix(text(product.get("brand")))
        words = " ".join([name, text(product.get("category")), text(product.get("description"))])
        # A blend ("80% Wool / 20% Nylon") is its main fibre.
        shell = self.main_fibre(shell) or (blank(shell) and self.main_fibre(product.get("description"))) or shell
        found = next((part for part in (shell, words) if any(pattern.search(text(part)) for _, pattern in FABRICS)), None)
        cloth = first_match(FABRICS, found) or ("cotton" if kind == "top" else "wool")
        # Denim is a cotton cloth: a "Denim Jacket" made of "100% Cotton" is denim.
        if cloth == "cotton" and dict(FABRICS)["denim"].search(" ".join([name, text(product.get("category"))])):
            return "denim"
        # Knitwear is a knit whatever it's spun from: ribbed and matte, never a woven cloth or a shell. Silk and
        # leather keep their look.
        if kind != "trousers" and self.knitwear(product, fibres=kind == "top") and cloth not in ("silk", "leather"):
            return "knit"
        return cloth

    @staticmethod
    def main_fibre(material):
        """The largest share of a blend that's a cloth this knows: "Wool" in "80% Wool / 20% Nylon". None for a
        material with no shares given."""
        parts = re.findall(r"(\d+(?:\.\d+)?)\s*%\s*([A-Za-z][A-Za-z -]*)", text(material))
        if not parts:
            return None
        main = max(parts, key=lambda part: float(part[0]))[1]
        if any(pattern.search(main) for _, pattern in FABRICS):
            return main
        # Polyamide is nylon; viscose, lyocell, modal, cupro and the matte synthetics hang and look like cotton here.
        if re.search(r"polyamide", main, I):
            return "nylon"
        if re.search(r"lyocell|tencel|modal|viscose|rayon|cupro|polyester|acrylic|elastane|spandex|flax", main, I):
            return "cotton"
        return None

    @staticmethod
    def plausible(chart, kind):
        sizes = [{key: (None if number_or_none(value) is not None and key in PLAUSIBLE and not PLAUSIBLE[key][0] <= value <= PLAUSIBLE[key][1] else value)
                  for key, value in size.items()} for size in chart.sizes]
        return chart if sizes == chart.sizes else chart.with_(sizes=sizes)

    @staticmethod
    def short_sleeved(product, chart):
        """Whether a sweater has short sleeves: its name says so, or every sleeve on its chart is short."""
        if re.search(r"short[- ]?sleeve|\bs/s\b", joined(product, "name", "description"), I):
            return True
        sleeves = [size["sleeve"] for size in chart.sizes if size.get("sleeve") is not None]
        return bool(sleeves) and all(sleeve < fit.SHORT_SLEEVE for sleeve in sleeves)

    def tee_sleeves(self, chart):
        """A T-shirt's sleeve is short, so a long one on its chart was measured from the centre of the back: take off
        half the shoulders."""
        if chart.sleeve_from:
            return chart
        return chart.with_(sizes=[{**size, "sleeve": self.from_shoulder(size)} if size.get("sleeve") is not None and size["sleeve"] > fit.SHORT_SLEEVE else size
                                  for size in chart.sizes])

    def shoulder_sleeves(self, chart, product):
        """Sleeves kept from the shoulder seam: converted here, once, when the chart says it runs from the centre back
        or when its sleeves are too long to be from the shoulder ("centre_back_guessed"), judged on the chart's middle
        size, so every size is read the same way."""
        if chart.sleeve_from and chart.sleeve_from != "centre_back":
            return chart
        sleeves = sorted(size["sleeve"] for size in chart.sizes if size.get("sleeve") is not None)
        if not sleeves:
            return chart
        sleeve_from = chart.sleeve_from
        shoulders = sorted(size["shoulders"] for size in chart.sizes if size.get("shoulders") is not None)
        women = product.get("women") or (bool(shoulders) and shoulders[len(shoulders) // 2] < WOMEN_SHOULDERS)
        if not sleeve_from and sleeves[len(sleeves) // 2] > USUAL_ARM["women" if women else "men"] + SHOULDER_SLEEVE_PAST_ARM \
                and not self.long_in_photo(chart, product.get("shape")):
            sleeve_from = "centre_back_guessed"
        if not sleeve_from:
            return chart
        return chart.with_(sizes=[{**size, "sleeve": self.from_shoulder(size)} if size.get("sleeve") is not None else size for size in chart.sizes],
                           sleeve_from=sleeve_from)

    def long_in_photo(self, chart, shape):
        """Whether the shop photo shows sleeves as long as the chart's, read from the shoulder seam: the nearer reading
        of the middle size's sleeve over its length, from the shoulder or from the centre back, wins."""
        shape = shape or {}
        reach, length = shape.get("sleeve"), shape.get("length")
        if reach is None or not (length is not None and length > 0):
            return False
        measured = [size for size in chart.sizes if size.get("sleeve") is not None and size.get("length") is not None]
        if not measured:
            return False
        size = measured[len(measured) // 2]
        seen = reach / length
        return abs(size["sleeve"] / size["length"] - seen) < abs(self.from_shoulder(size) / size["length"] - seen)

    @staticmethod
    def from_shoulder(size):
        """A size's sleeve from the shoulder seam, when the chart gives it from the centre back: less half the
        shoulders (a man's usual 46 cm when the chart doesn't give them)."""
        shoulders = size.get("shoulders") if size.get("shoulders") is not None else 46
        return rnd(size["sleeve"] - shoulders / 2.0)

    @staticmethod
    def named_collar(product, kind, style, cut):
        if kind not in ("top", "jacket", "coat") or style in ("hoodie", "dress", "tank") or (cut or {}).get("hood"):
            return False
        words = joined(product, "name", "description")
        return bool(NAMED_COLLAR.search(words)) and not NOT_TURNED_DOWN.search(words)

    def top_style_of(self, product):
        style = None
        for key in ("name", "category"):
            style = first_match(TOP_STYLES, product.get(key))
            if style:
                break
        style = style or "tee"
        name, category, description = text(product.get("name")), text(product.get("category")), text(product.get("description"))
        # A henley the shop files under short-sleeve ones is a tee with buttons.
        if style == "longsleeve" and re.search(r"short[- ]?sleeve", category, I) and not re.search(r"long[- ]?sleeve|\bl/s\b", name, I):
            return "tee"
        # A top on straps (a bodysuit or a cami named for neither) is a tank.
        if style == "tee" and re.search(r"sleeveless|(?:shoulder|spaghetti|thin|wide|adjustable) straps?|\bcami(?:sole)?\b", description, I):
            return "tank"
        # A crewneck or sweater the shop files under short-sleeve tops, or whose description says its sleeves are
        # short, is a T-shirt or a short-sleeve knit.
        if style in ("sweatshirt", "sweater"):
            short = bool(re.search(r"short[- ]?sleeve", category, I)) or \
                (bool(re.search(r"short[- ]?sleeves?|\bs/s\b", description, I)) and not re.search(r"long[- ]?sleeves?", description, I))
            if short and not re.search(r"long[- ]?sleeve|\bl/s\b", name, I):
                return "shortknit" if style == "sweater" else "tee"
            return style
        # A button-up whose description says its sleeves are short, or whose photo shows them ending well above the
        # elbow, is a short-sleeve one.
        if style == "shirt":
            if re.search(r"short[- ]?sleeves?|\bs/s\b", description, I) and not re.search(r"long[- ]?sleeves?", description, I):
                return "shortshirt"
            return "shortshirt" if self.short_sleeves_in_photo(product.get("shape")) else style
        if style != "tee":
            return style
        # A "T-shirt" with a shirt's collar buttoned down the front is a short-sleeve shirt.
        if SHIRT_COLLAR.search(description) and FRONT_BUTTONS.search(description):
            return "shirt" if re.search(r"long[- ]?sleeve", description, I) else "shortshirt"
        if re.search(r"long[- ]?sleeve", description, I):
            return "longsleeve"
        # (Or one the shop files under long-sleeve tees.)
        if re.search(r"long[- ]?sleeve", category, I) and not re.search(r"short[- ]?sleeve|\bs/s\b", name, I):
            return "longsleeve"
        if self.long_sleeves_in_photo(product.get("shape")) and not re.search(r"short[- ]?sleeve|\bs/s\b|\bt[- ]?shirt|\btee\b", name, I):
            return "longsleeve"
        return style

    @staticmethod
    def long_sleeves_in_photo(shape):
        """Whether a top's photo shows long sleeves: their reach at least the chest's width, and hanging well down."""
        return isinstance(shape, dict) and float(shape.get("sleeve") or 0) >= 1.0 and float(shape.get("sleeve_down") or 0) >= 0.7

    @staticmethod
    def short_sleeves_in_photo(shape):
        """Whether its photo shows short sleeves: they hang down less than about three fifths of the chest's width."""
        return isinstance(shape, dict) and float(shape.get("sleeve") or 0) > 0 and 0 < float(shape.get("sleeve_down") or 0) < 0.62

    def style_of(self, product, source_url):
        # The name first: a "Trucker Jacket" whose description mentions a zip pocket is still a trucker.
        named = joined(product, "name", "category")
        found = first_match(STYLES, named)
        # A utility, field or work jacket the description says zips up the front is a zip-up.
        description = text(product.get("description"))
        if found == "shirt" and not SHIRT_NAMED.search(named) and ZIP_FRONT.search(description) and not FRONT_BUTTONS.search(description):
            return "zip"
        if found:
            return found
        found = first_match(STYLES, joined(product, "name", "category", "description"))
        if found:
            return found
        if self.fabric_of(product) == "denim":
            return "shirt"
        if self.fabric_of(product) in ("leather", "nylon"):
            return "zip"
        # Nothing it's called says what it is: a blazer has lapels, so one with a hood or without a collar to turn back
        # is a casual jacket.
        if self.hooded(product) or re.search(r"crew ?neck|collarless|mock neck|funnel neck|stand collar", description, I):
            return "zip"
        return "zip" if OUTERWEAR.search(" ".join([text(product.get("category")), text(source_url)])) else "tailored"

    @staticmethod
    def color_hex(texts):
        """The first of the texts (the product's colour, its description, its name) that names a colour, and the colour
        it names first: "White / Brown" is a white garment with brown on it. "Heather" is how a cloth is knitted as
        much as a colour: "Heather Green" is green."""
        for words in texts:
            if words is None:
                continue
            words = text(words)
            found = []
            for name, hex_value in COLORS.items():
                at = COLOR_WORDS[name].search(words)
                if at:
                    found.append((1 if name == "heather" else 0, at.start(), -len(name), hex_value))
            if found:
                return min(found)[-1]
        return DEFAULT_COLOR

    @staticmethod
    def split_line(line):
        """Copied tables come through as tabs, pipes, or columns of spaces."""
        cells = [cell for cell in ruby_split(r"\t|\s*\|\s*|\s{2,}", line.strip()) if not blank(cell)]
        return cells if len(cells) >= 3 else [part for part in re.split(r"\s+", line.strip()) if part]
