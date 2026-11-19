"""Reads a product page: what the item is (from its schema.org Product data, falling back to the page title), every
table on it that could be a size chart, with the text around it for clues, and, for single-item listings (resale
shops), the item's own measurements written as "Chest  50.5"" pairs."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup, Tag
from bs4.element import Comment, Declaration, Doctype, NavigableString, ProcessingInstruction

from ..util import blank, presence, ruby_array, squish, text, truncate

I = re.I
WORDS = (r"chest|bust|pit to pit|p2p|shoulders?|waist|sleeves?|sleeve length|length|back length|"
         r"seat|hips?|thigh|inseam|inside leg|rise|leg opening|hem|ankle opening")
LABEL = re.compile(rf"\A({WORDS})\Z", I)
INLINE = re.compile(rf"\A({WORDS})\s*[:\-–]\s*(\d.*)\Z", I)
# A measurement written beside its label: a number, maybe with a unit ("46.5\"", "18 in", "58 cm"), not a size's
# name ("28W", "30L").
MEASUREMENT = re.compile(r"\A\d+(?:[.,]\d+)?(?:\s+\d/\d)?\s*(?:\"|”|''|in\.?|inch(?:es)?|cm)?\Z", I)

# The sizes a shop's page offers, as its size buttons, lists and drop-downs name them: letters ("S", "XL"), and
# waist sizes, written "32W" anywhere, or as plain numbers inside something marked as sizes.
WAIST_W = re.compile(r"\A(2[2-9]|3\d|4[0-6])\s*W\Z", I)
WAIST = re.compile(r"\A(2[2-9]|3\d|4[0-6])\Z")
LETTER_SIZE = re.compile(r"\A(XXS|XS|S|M|L|XL|XXL|XXXL|[2-4]XL)\Z", I)
SIZEISH = re.compile(r"size|waist", I)
SIZE_ATTRIBUTES = ("class", "id", "name", "aria-label", "data-testid", "for")
SKIPPED_SIBLINGS = ("style", "script", "noscript", "template")
NOT_TEXT = (Comment, Declaration, Doctype, ProcessingInstruction)


@dataclass(frozen=True)
class Table:
    rows: list
    context: str


def node_text(node) -> str:
    """All the text in a node, scripts' and styles' included, as a parser's DOM gives it."""
    if node is None:
        return ""
    if isinstance(node, NavigableString):
        return "" if isinstance(node, NOT_TEXT) else str(node)
    return "".join(str(piece) for piece in node.descendants if isinstance(piece, NavigableString) and not isinstance(piece, NOT_TEXT))


def is_leaf(node) -> bool:
    return not any(isinstance(child, Tag) for child in node.children)


def next_element(node):
    return node.find_next_sibling() if node is not None else None


class Page:
    def __init__(self, html):
        self.doc = BeautifulSoup(text(html), "lxml")

    def product(self) -> dict:
        data = self.product_json_ld() or {}
        name = presence(data.get("name")) or self.meta("og:title") or (node_text(self.doc.find("title")) if self.doc.find("title") else None)
        fabric = self.labelled("Fabric")
        return {
            "name": truncate(squish(name), 120),
            "brand": self.brand(data.get("brand")),
            "color": presence(squish(data.get("color"))),
            "category": presence(squish(data.get("category"))),
            "description": truncate(squish(data.get("description")), 400),
            "fabric": truncate(fabric, 80) if fabric is not None else None,
            "image": self.image(data.get("image")),
        }

    def image(self, given):
        for item in ruby_array(given):
            url = (item.get("url") or item.get("contentUrl")) if isinstance(item, dict) else item
            if text(url).startswith("http"):
                return url
        return self.meta("og:image")

    def tables(self) -> list:
        out = []
        for table in self.doc.select("table"):
            rows = [[node_text(cell) for cell in tr.select("th, td")] for tr in table.select("tr")]
            caption = table.find("caption")
            parts = [node_text(caption) if caption else None, self.heading_before(table), node_text(table)]
            out.append(Table(rows=rows, context=squish(" ".join(part for part in parts if part is not None))))
        return out

    def kiwi_sizing(self):
        """Shopify shops using the Kiwi Sizing app load their size chart from Kiwi's API after the page opens. The
        page carries what Kiwi needs to pick the chart: the shop and the product's id, title, tags, type, vendor and
        collections. Returns them, or None when the page doesn't use Kiwi."""
        script = "\n".join(t for t in (node_text(s) for s in self.doc.select("script")) if "KiwiSizing" in t)
        shop = re.search(r"KiwiSizing\.shop\s*=\s*\"([^\"]+)\"", script)
        shop = shop.group(1) if shop else None
        fields = {}
        for name in ("product", "title", "tags", "type", "vendor", "collections"):
            found = re.search(rf"^\s*{name}:\s*\"((?:[^\"\\]|\\.)*)\"", script, re.M)
            if not found:
                fields[name] = None
                continue
            try:
                fields[name] = json.loads(f'"{found.group(1)}"')
            except ValueError:
                fields[name] = found.group(1)
        if not (shop and shop.endswith(".myshopify.com") and re.fullmatch(r"\d+", text(fields["product"]))):
            return None
        return {"shop": shop, **{key: value for key, value in fields.items() if value is not None}}

    def size_guide_link(self, page_url):
        """A link to the shop's size guide on the same site, as an absolute URL, or None."""
        try:
            base = urlsplit(text(page_url))
        except ValueError:
            return None
        guide = re.compile(r"size[\s_-]*(guide|chart)", I)
        links = [a for a in self.doc.select("a[href]") if guide.search(f"{node_text(a)} {a.get('href')}")]
        # Links whose address says size guide first; a "Size guide" button that opens a pop-up goes nowhere.
        links.sort(key=lambda a: 0 if guide.search(a.get("href")) else 1)
        here = urlunsplit(base._replace(fragment=""))
        for a in links:
            if not base.scheme or not base.netloc:
                continue
            try:
                url = urlsplit(urljoin(text(page_url), a.get("href").strip()))
            except ValueError:
                continue
            if url.scheme not in ("http", "https") or not url.hostname or url.hostname != base.hostname:
                continue
            found = urlunsplit(url._replace(fragment=""))
            if found != here:
                return found
        return None

    def size_names(self) -> list:
        """["28", "30", "32"] or ["S", "M", "L"]; empty when the page shows none."""
        found = []
        for node in self.doc.select("option, button, label, li, span, a, div, input"):
            if node.name == "input":
                words = text(node.get("value")).strip()
            elif is_leaf(node):
                words = squish(node_text(node))
            else:
                continue
            if not words or len(words) > 6:
                continue
            waist = WAIST_W.search(words)
            if waist:
                found.append(waist.group(1))
            elif self.sizeish(node) and WAIST.search(words):
                found.append(words)
            elif self.sizeish(node) and LETTER_SIZE.search(words):
                found.append(words.upper())
        return list(dict.fromkeys(found))[:24]

    def stated_size(self):
        """The size a single-item listing says it is ("Size: M" on resale listings), or None."""
        # A resale listing's schema.org Product says its one size ("US M / EU 48-50 / 2"): its letter size when it
        # gives one.
        data = self.product_json_ld()
        given = squish(data.get("size")) if data else ""
        letter = re.search(r"(?<![A-Za-z])(XXS|XS|S|M|L|XL|XXL|XXXL|[2-4]XL)(?![A-Za-z])", given)
        if letter:
            return letter.group(1)
        if given:
            return truncate(given, 20, omission="")
        for node in self.doc.select("body *"):
            if not is_leaf(node):
                continue
            words = squish(node_text(node))
            if re.search(r"\ASize:\s*\S", words):
                label = words[len("Size:"):].strip().replace("|", "/")
                return truncate(squish(label), 20, omission="")
        return None

    def item_measurements(self):
        """A single item's measurements as a one-row table: [["Size", "Chest", ...], ["XXL", "50.5\"", ...]]."""
        pairs = {}
        for node in self.doc.select("body *"):
            if not is_leaf(node):
                continue
            words = squish(node_text(node))
            inline = INLINE.search(words)
            if inline:
                pairs.setdefault(inline.group(1).capitalize(), inline.group(2))
            elif LABEL.search(words):
                beside = self.next_content(node) or self.next_content(node.parent)
                value = squish(node_text(beside)) if beside is not None else None
                if value is not None and MEASUREMENT.search(value):
                    key = words.capitalize()
                    if not pairs.get(key):
                        pairs[key] = value
        if len(pairs) < 2:
            return None
        return [["Size", *pairs.keys()], [self.item_size(), *pairs.values()]]

    # ---- private

    @staticmethod
    def sizeish(node) -> bool:
        """Whether the node, or something it's in (a few levels up), is marked as being about sizes."""
        ancestors = [parent for parent in node.parents if isinstance(parent, Tag) and not isinstance(parent, BeautifulSoup)][:4]
        for el in [node, *ancestors]:
            for name, value in el.attrs.items():
                value = " ".join(value) if isinstance(value, list) else text(value)
                if name in SIZE_ATTRIBUTES and SIZEISH.search(value):
                    return True
        return False

    def labelled(self, label):
        """The value written beside a label on the page ("Fabric" then "100% wool"), as resale listings do."""
        for node in self.doc.select("body *"):
            if not (is_leaf(node) and squish(node_text(node)).lower() == label.lower()):
                continue
            beside = self.next_content(node) or self.next_content(node.parent)
            value = squish(node_text(beside)) if beside is not None else None
            if presence(value) and len(value) < 200:
                return value
        return None

    @staticmethod
    def next_content(node):
        """The next sibling that holds text, skipping the <style> and <script> tags some sites put in between."""
        sibling = next_element(node)
        while sibling is not None and sibling.name in SKIPPED_SIBLINGS:
            sibling = next_element(sibling)
        return sibling

    def item_size(self):
        """"Size: XXL | US44, IT54" on resale listings, else "One size"."""
        return self.stated_size() or "One size"

    def product_json_ld(self):
        for script in self.doc.select('script[type="application/ld+json"]'):
            try:
                found = self.find_product(json.loads(node_text(script)))
            except ValueError:
                continue
            if found:
                return found
        return None

    def find_product(self, node):
        if isinstance(node, list):
            for item in node:
                found = self.find_product(item)
                if found:
                    return found
            return None
        if isinstance(node, dict):
            types = ruby_array(node.get("@type"))
            if "Product" in types or "ProductGroup" in types:
                return node
            # A product with its type left off (Uniqlo's): a name with offers, or with a SKU and images.
            if blank(node.get("@type")) and not blank(node.get("name")) and (not blank(node.get("offers")) or (not blank(node.get("sku")) and not blank(node.get("image")))):
                return node
            if node.get("@graph"):
                return self.find_product(node["@graph"])
        return None

    @staticmethod
    def brand(value):
        return presence(squish(value.get("name") if isinstance(value, dict) else value))

    def meta(self, prop):
        found = self.doc.select_one(f'meta[property="{prop}"]')
        return presence(found.get("content")) if found is not None else None

    @staticmethod
    def heading_before(table):
        """The nearest heading above the table, which often says "Body measurements" or "Garment measurements"."""
        node = table
        for _ in range(12):
            node = next((sibling for sibling in node.previous_siblings if isinstance(sibling, Tag)), None) or node.parent
            if node is None or node.name == "body":
                break
            if re.fullmatch(r"h[1-6]", node.name or "") or node.name == "p":
                return node_text(node)
        return None
