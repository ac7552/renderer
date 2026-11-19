import json
from urllib.parse import parse_qs, urlsplit

import pytest

import renderer.garment_import as gi
from renderer.garment_import import COLORS, GarmentImport, chart_reader, fetcher
from renderer.garment_import.chart_reader import Chart

from .conftest import page


def query_of(url):
    return {key: values[0] for key, values in parse_qs(urlsplit(url).query, keep_blank_values=True).items()}


def raises(error):
    def fail(_):
        raise error

    return fail


def sole(items):
    assert len(items) == 1
    return items[0]


def values_at(garment, *keys):
    return [garment.get(key) for key in keys]


def test_reads_a_garment_chart_in_inches_from_a_product_page():
    garment = GarmentImport().from_page(page("navy-suit-jacket"), source_url="https://shop.example/navy")

    assert garment["name"] == "Navy Wool Suit Jacket"
    assert garment["brand"] == "Sample Tailoring Co."
    assert garment["color"] == COLORS["navy"]
    chart = garment["chart"]
    assert values_at(chart, "unit", "kind", "missing") == ["in", "garment", []]
    forty = next(size for size in chart["sizes"] if size["name"] == "40R")
    assert forty["chest"] == pytest.approx(44.5 * 2.54, abs=0.01)
    assert forty["shoulders"] == pytest.approx(18 * 2.54, abs=0.01)


def test_turns_a_sideways_body_measurement_chart_in_cm_into_estimated_jacket_sizes():
    garment = GarmentImport().from_page(page("charcoal-blazer"), source_url="https://shop.example/charcoal")

    chart = garment["chart"]
    assert values_at(chart, "unit", "kind") == ["cm", "body"]
    assert chart["missing"] == ["shoulders", "length"]
    fifty = next(size for size in chart["sizes"] if size["name"] == "50")
    assert fifty["chest"] == pytest.approx(100 + 11, abs=0.01)
    assert fifty["length"] is None
    assert garment["color"] == COLORS["charcoal"]


def test_reads_a_pasted_chart_with_tabs_fractions_and_ranges():
    garment = gi.from_text("Size\tChest\tWaist\tSleeve\n40R\t44 ½\t39-40\t25\n42R\t46 1/2\t41.5\t25.25\n")

    forty = garment["chart"]["sizes"][0]
    assert forty["chest"] == pytest.approx(44.5 * 2.54, abs=0.01)
    assert forty["waist"] == pytest.approx(39.5 * 2.54, abs=0.01)


def test_doubles_pit_to_pit_widths():
    garment = gi.from_text("Size | Pit to pit (cm) | Length (cm)\nM | 54 | 74\nL | 57 | 76\n")

    assert [size["chest"] for size in garment["chart"]["sizes"]] == [108.0, 114.0]


def test_says_when_theres_no_size_chart():
    with pytest.raises(gi.Error) as error:
        GarmentImport().from_page("<html><title>Blazer</title></html>", source_url="x")
    assert error.value.code == "no_size_chart"


def test_turns_away_things_it_cant_fit_yet():
    html = page("navy-suit-jacket").replace("Navy Wool Suit Jacket", "Navy Wool Scarf").replace("Suit jackets", "Accessories")
    with pytest.raises(gi.Error) as error:
        GarmentImport().from_page(html, source_url="x")
    assert error.value.code == "not_supported"


def top(name, category="Tops", description=None):
    html = page("navy-suit-jacket").replace("Navy Wool Suit Jacket", name).replace("Suit jackets", category)
    if description:
        html = html.replace('"color": "Navy",', f'"color": "Navy", "description": {json.dumps(description)},', 1)
        html = html.replace("Two-button, notch lapel, half-canvassed. Super 110s wool.", description, 1)
    return GarmentImport().from_page(html, source_url="x")


def test_a_t_shirt_is_a_top_drawn_as_a_tee_never_as_a_button_up_shirt():
    assert values_at(top("Ocra Arctic T-Shirt"), "garment", "style") == ["top", "tee"]
    assert top("Ocra Arctic T-Shirt", "Shirts")["style"] == "tee"
    assert top("Pima Tee")["style"] == "tee"
    assert top("Long Sleeve T-Shirt")["style"] == "longsleeve"


def test_shirts_sweatshirts_and_hoodies_are_tops_in_their_own_styles():
    assert values_at(top("Navy Oxford Shirt", "Shirts"), "garment", "style") == ["top", "shirt"]
    assert top("Linen Shirt")["style"] == "shirt"
    assert top("Heavyweight Crewneck Sweatshirt")["style"] == "sweatshirt"
    assert top("Pullover Hoodie")["style"] == "hoodie"
    # A hoodie that zips all the way down is drawn with a zip; a pullover or a half-zip isn't.
    assert top("Striped Zip-Up Hoodie")["zip"] is True
    assert top("Pullover Hoodie").get("zip") is None
    assert top("Half-Zip Hoodie").get("zip") is None


def test_a_charts_impossible_numbers_are_left_out_to_be_estimated():
    chart = Chart(sizes=[{"name": "0", "waist": 73.7, "seat": 101.6, "leg_opening": 3.18}], unit="cm", kind="garment", missing=[])
    size = GarmentImport().plausible(chart, "trousers").sizes[0]
    assert size["leg_opening"] is None
    assert size["waist"] == 73.7


def test_pants_named_for_their_cloth_are_pants():
    html = page("navy-suit-jacket").replace("Navy Wool Suit Jacket", "Sample House Waist Strap Suiting Trouser - Black").replace("Suit jackets", "Trousers")
    assert GarmentImport().from_page(html, source_url="x")["garment"] == "trousers"


def test_a_two_colour_name_is_the_colour_it_names_first():
    importer = GarmentImport()
    assert importer.color_hex(["White / Brown"]) == COLORS["white"]
    assert importer.color_hex(["Navy/Grey"]) == COLORS["navy"]
    assert importer.color_hex([None, "Black cotton jersey"]) == COLORS["black"]
    # Heather is the knit: a "Heather Green" shirt is green, a "Homestead Heather" tee heather until its photo says.
    assert importer.color_hex(["Heather Green"]) == COLORS["green"]
    assert importer.color_hex(["Homestead Heather"]) == COLORS["heather"]


def test_a_blend_is_its_main_fibre():
    importer = GarmentImport()
    assert importer.fabric_of({"name": "Mulberry IV Wool Jersey Tee", "fabric": "80% Wool / 20% Nylon"}, "top") == "wool"
    assert importer.fabric_of({"name": "Shirt", "fabric": "60% Cotton / 40% Rayon"}, "top") == "cotton"
    assert importer.fabric_of({"name": "Track Pant", "fabric": "100% Nylon"}, "trousers") == "nylon"
    assert importer.fabric_of({"name": "Camilla Plunge Shirt", "fabric": "76% Lyocell / 22% Nylon / 2% Polyurethane"}, "top") == "cotton"
    assert importer.fabric_of({"name": "Tee", "fabric": "80% Polyamide / 20% Elastane"}, "top") == "nylon"


def test_pull_on_pants_with_an_elastic_or_drawcord_waist_are_marked_so():
    def pants(name):
        html = page("navy-suit-jacket").replace("Navy Wool Suit Jacket", name).replace("Suit jackets", "Pants")
        return GarmentImport().from_page(html, source_url="x")

    assert pants("Drawcord Linen Pant")["cut"] == {"elastic": True}
    assert pants("Elastic Waist Trouser")["cut"] == {"elastic": True}
    assert pants("Pleated Wool Trouser")["cut"] == {"fit": "loose"}
    assert pants("Fleece Jogger Drawstring").get("cut") is None


def test_a_romper_is_a_tank_tucked_into_shorts_a_jumpsuit_a_top_tucked_into_pants():
    importer = GarmentImport()

    def usual(part, kind):
        return importer.usual_for(kind, importer.top_style_of(part), part)

    romper = importer.one_piece({"name": "Sample Label Women Aria Plunge Cross Back Romper - Cream", "category": "Rompers", "description": "Elasticated straps",
                                 "sizes": ["XS", "S", "M", "L"], "women": True}, "x", usual)
    assert values_at(romper, "garment", "style") == ["onepiece", "romper"]
    assert [romper["parts"]["top"]["style"], romper["parts"]["trousers"]["style"]] == ["tank", "shorts"]
    assert all(part["one_piece"] for part in romper["parts"].values())
    jumpsuit = importer.one_piece({"name": "Long Sleeve Utility Jumpsuit", "category": "Jumpsuits", "sizes": ["S", "M", "L"]}, "x", usual)
    assert [jumpsuit["parts"]["top"]["style"], jumpsuit["parts"]["trousers"]["style"]] == ["longsleeve", "trousers"]


def test_with_footwear_off_a_shoes_link_says_shoes_arent_tried_on_yet_and_socks_still_are():
    gi.footwear = False
    importer = GarmentImport()
    product = {"name": "New Balance Made in UK 991v1 Luxe Suede - Cocoa", "category": "Low Top Sneakers", "sizes": ["8", "9", "10"]}
    with pytest.raises(gi.Error) as error:
        importer.accessory(product, "shoes", None)
    assert error.value.code == "not_supported"
    assert "can't try on shoes yet" in str(error.value).lower()
    assert importer.accessory({"name": "Crew Socks", "sizes": ["M"]}, "socks", None)["garment"] == "socks"


def test_bags_are_read_as_bags_each_as_its_worn_at_the_size_its_listing_gives():
    importer = GarmentImport()

    def kind(name, category):
        return importer.kind_of({"name": name, "category": category, "sorted": True})

    assert kind("Sample Works Trail 15 Backpack - Purple", "Backpacks") == "bag"
    assert kind("Sample House Tote Bag - Black", "Tote Bags") == "bag"
    assert kind("Sample Works Trail 2 Waist Pack - Olive", "Mini Bags") == "bag"
    assert kind("Sample House Belt Bag - Tan", "Belts") == "bag"
    assert kind("Sample Goods Leather Black Belt - Black", "Belts") == "belt"
    for name, category in [("Sample Label Carry-On - Blue Ombre", "Bags"), ("Sample Label Sunglass Case - Purple Ombre", "Bags"),
                           ("Sample Label Leather Wallet - Black", "Small Leather Goods")]:
        with pytest.raises(gi.Error):
            kind(name, category)

    gi.bags = True

    def read(name, category, description=None):
        return importer.accessory({"name": name, "category": category, "description": description, "sizes": ["Default Title"]}, "bag", None)

    pack = read("Sample Works Trail 15 Backpack - Purple", "Backpacks", 'Printed nylon blend. Dimensions: L 17.3" x W 9.8" x D 8.2"')
    assert values_at(pack, "garment", "style", "fabric") == ["bag", "backpack", "canvas"]
    assert [size["name"] for size in pack["chart"]["sizes"]] == ["One size"]
    # (A length and a width, no height: a backpack's greater is its height, marked as not sure.)
    assert pack["bag_size"] == {"height": 43.9, "depth": 20.8, "width": 24.9, "sure": False}
    assert read("Sample Works Trail 2 Waist Pack - Olive", "Mini Bags")["style"] == "sling"
    assert read("Sample House Belt Bag - Tan", "Belts")["style"] == "sling"
    assert read("Sample Label Vintage Textured Leather Duffle Bag - Brown", "Duffle Bags")["style"] == "duffle"
    assert read("Sample House Mini Bag - Grey", "Mini Bags")["style"] == "crossbody"
    assert read("Sample House Tote Bag - Black", "Tote Bags")["style"] == "tote"
    assert read("Sample Atelier Large Soft Game Bag - Chocolate", "Bags").get("bag_size") is None

    # What the listing calls its own shape comes before where the shop files it.
    assert gi.bag_style("Sample House Tower Bag - Grape Crossbody Bags", "<li>Silhouette: Tote</li><li>Dimensions: 18 in. wide, 16 in. high</li>") == "tote"
    assert gi.bag_style("Sample House Tower Bag - Grape Crossbody Bags") == "crossbody"
    assert gi.bag_style("Sample Label Bag - Black", "Silhouette: Backpack") == "backpack"

    def size(words, style="tote"):
        return gi.bag_size(words, style=style)

    # H is the height and D the depth; of a length and a width, the greater is across its face.
    assert size('Dimensions: L 21.65" x H 9.84" x W 11.02"', "duffle") == {"height": 25.0, "depth": 28.0, "width": 55.0}
    assert size('Dimensions: W 18" x H 16" x D 4.7"') == {"height": 40.6, "depth": 11.9, "width": 45.7}
    assert size('Dimensions: L 11" x W 4.5" x H 8.5"') == {"height": 21.6, "depth": 11.4, "width": 27.9}
    assert size("Height: 40cm, Width: 30cm, Depth: 12cm. Handle drop: 22cm") == {"height": 40.0, "depth": 12.0, "width": 30.0, "drop": 22.0}
    assert size('12"W x 16"H x 5"D') == {"height": 40.6, "depth": 12.7, "width": 30.5}
    assert size("Measures 43 x 28 x 15 cm") == {"width": 43.0, "height": 28.0, "depth": 15.0, "sure": False}
    # (A capacity in litres isn't a length; nor is one number alone enough.)
    assert size("Capacity: 31 L. Weight: 11 lbs") is None
    assert size("100% nylon. Zip closure.") is None


def test_with_bags_off_a_bags_link_says_bags_arent_tried_on_yet():
    gi.bags = False
    with pytest.raises(gi.Error) as error:
        GarmentImport().accessory({"name": "Sample Label Tote Bag - Black", "category": "Tote Bags", "sizes": []}, "bag", None)
    assert error.value.code == "not_supported"
    assert "can't try on bags yet" in str(error.value).lower()


def test_shoes_socks_and_belts_are_drawn_in_their_own_styles_with_the_shops_sizes():
    importer = GarmentImport()

    def kind(name, category):
        return importer.kind_of({"name": name, "category": category, "sorted": True})

    assert kind("New Balance Made in UK 991v1 Luxe Suede - Cocoa", "Low Top Sneakers") == "shoes"
    assert kind("Dr. Martens Wayborne Boot Mayhem - Dark Brown", "Boots") == "shoes"
    assert kind("Sample Label Classic Crew Sock - White", "Socks") == "socks"
    assert kind("Sample Goods Leather Black Belt - Black", "Belts") == "belt"
    # (A belt bag is a bag, not a belt: see the bags' test.)
    assert kind("Sample House Belt Bag - Tan", "Belts") == "bag"
    with pytest.raises(gi.Error):
        kind("Sample Label Boxer Brief - Black", "Underwear")
    # A shoe the shop files only by its tags (no type, no shoe word in the name) is still shoes, in its style.
    tagged = {"name": "Vasque Skywalk GTX - Olive / Dress Blues", "category": None, "tags": ["boot", "boots", "footwear", "mens"], "sizes": ["9", "10"]}
    assert importer.kind_of(tagged) == "shoes"
    assert importer.accessory(tagged, "shoes", "x")["style"] == "boot"
    shoe = importer.accessory({"name": "Timberland 6 Inch Premium Boot - Wheat", "category": "Boots", "sizes": ["8", "9", "10"]}, "shoes", "x")
    assert values_at(shoe, "garment", "style") == ["shoes", "boot"]
    assert [size["name"] for size in shoe["chart"]["sizes"]] == ["8", "9", "10"]
    assert importer.accessory({"name": "G.H. Bass Larson Penny Loafer", "category": "Shoes"}, "shoes", "x")["style"] == "loafer"
    # What the name calls it, before the pages the shop's tags file it under.
    margiela = {"name": "Maison Margiela Decortique Loafers - Black", "category": "Loafers", "tags": ["footwear", "sneakers", "mens boots"]}
    assert importer.accessory(margiela, "shoes", "x")["style"] == "loafer"
    assert gi.shoe_style("Maison Margiela Decortique Loafers - Black", None, "sneakers boots") == "loafer"
    assert gi.shoe_style("Timberland 6-Inch Premium Waterproof Boot - Wheat", "Boots", "sneakers") == "boot"
    assert gi.shoe_style("Nike Air Force 1 - Chelsea Blue", "Low Top Sneakers") == "sneaker"
    assert gi.shoe_style("Converse Chuck 70", "High Top Sneakers") == "hightop"
    assert gi.shoe_style("Dr. Martens Lowell - Black / Aniline", "Derbies") == "loafer"
    assert gi.shoe_style("Sample House Geo", None, "boots") == "boot"
    assert gi.shoe_style("Mystery Shoe") == "sneaker"
    assert importer.accessory({"name": "Sample Label Ankle Sock 3-Pack", "category": "Socks"}, "socks", "x")["style"] == "ankle"
    belt = importer.accessory({"name": "Leather Belt", "category": "Belts", "description": "Brass buckle", "sizes": ["Default Title"]}, "belt", "x")
    assert [belt["buckle"], [size["name"] for size in belt["chart"]["sizes"]]] == ["gold", ["One size"]]


def test_shorts_whose_chart_gives_their_whole_length_as_the_inseam_are_measured_from_the_crotch():
    chart = Chart(sizes=[{"name": "48", "waist": 87, "inseam": 58.0}, {"name": "50", "waist": 91, "inseam": 20.0}], unit="cm", kind="garment", missing=[])
    shorts = GarmentImport().garment({"name": "Cupro Cargo Short", "category": "Shorts"}, chart, kind="trousers", source_url="x")
    assert [size["inseam"] for size in shorts["chart"]["sizes"]] == [28.0, 20.0]


def test_a_short_sleeve_shirt_is_a_button_up_with_short_sleeves_and_a_short_sleeve_tee_is_still_a_tee():
    assert top("by Parra Abstract Mountain Short Sleeve Shirt - Red")["style"] == "shortshirt"
    assert top("Camp Collar Shirt")["style"] == "shortshirt"
    assert top("Short Sleeve T-Shirt")["style"] == "tee"
    assert top("Short Sleeve Polo")["style"] == "polo"
    # Some shops file their tees as "Jerseys".
    assert values_at(top("Sample Works Flatlock Short Sleeve Jersey - White", "Jerseys"), "garment", "style") == ["top", "tee"]


def test_polos_tank_tops_sweaters_and_cardigans_are_drawn_as_themselves():
    importer = GarmentImport()
    assert top("Sample Label Tide Polo")["style"] == "polo"
    assert top("Sample Label Crest Ribbed Tank")["style"] == "tank"
    assert top("Wyona Sweater")["style"] == "sweater"
    assert top("Merino Crewneck Sweater")["style"] == "sweater"
    assert top("Mock Neck Short Sleeve Sweater")["style"] == "shortknit"
    # A turtleneck filed under "Turtlenecks", which named nothing it knew: it's a knit top.
    assert importer.kind_of({"name": "&Kin Interlock Cyrus Turtleneck - Black", "category": "Turtlenecks", "tags": ["Apparel", "apparels"]}) == "top"
    assert values_at(top("&Kin Interlock Cyrus Turtleneck - Black", "Turtlenecks"), "garment", "style") == ["top", "sweater"]
    assert importer.style_of({"name": "Sample Label Denim Hale Jacket - Black", "category": "Jackets"}, "x") == "shirt"
    assert importer.style_of({"name": "Japanese Denim Trucker Jacket", "category": "Jackets", "description": "Zip pocket at the chest."}, "x") == "shirt"
    assert importer.kind_of({"name": "Sample Label Night Track Jacket - Peacoat", "category": "Jackets"}) == "jacket"
    assert importer.kind_of({"name": "Sample Label Women Isla Crochet Cable Zip Track - Charcoal", "category": "Sweaters"}) == "jacket"
    assert importer.kind_of({"name": "Merino Half-Zip Sweater", "category": "Sweaters"}) == "top"
    assert importer.kind_of({"name": "Sample Atelier Dora Suede Maxi Coat - Graphite", "category": "Coats"}) == "coat"
    # A coat with no chart gets a coat's usual length, not a tee's.
    coat = importer.usual_sizes("coat", "tee", {"name": "Sample House Poise Coat", "sizes": ["S", "M", "L"]})
    assert next(size for size in coat.sizes if size["name"] == "M")["length"] > 90
    assert importer.kind_of({"name": "Sample Label Women Aria Plunge Cross Back Romper - Cream", "category": "Rompers"}) == "onepiece"
    assert importer.fabric_of({"name": "Polo", "description": "Body 1: 100% Lyocell / Body 2: 60% Viscose / 35% Nylon / 5% Cashmere"}, "top") == "cotton"
    # A cardigan is worn open over a top, as a jacket is, so a tee can go under it.
    assert values_at(top("Color-Blocked Cardigan"), "garment", "style") == ["jacket", "cardigan"]
    assert top("Sample House Portrait Sweatshirt")["style"] == "sweatshirt"
    # A fitted rib "Crewneck Top" filed under short-sleeve tops is a T-shirt, not a sweatshirt.
    assert top("Sample House Crewneck Top with Jacquard Logo - Black", "Short Sleeve Tops")["style"] == "tee"


def test_a_one_word_shirt_dress_is_a_dress_a_quarter_zip_a_top_and_a_bodysuit_a_top_worn_tucked_in():
    assert values_at(top("Sample Goods Rhea Long Sleeve Shirtdress - Stone Lurex", "Mini Dresses"), "garment", "style") == ["top", "dress"]
    assert values_at(top("Sample Label Cal Quarter Zip - Black", "Quarter Zips"), "garment", "style") == ["top", "sweatshirt"]
    assert top("Sample House Quarter-Zip Shirt - Grey", "Button Up Shirts")["style"] == "shirt"
    suit = top("Sample Goods Mae Bodysuit - White", "Bodysuits",
               description="Viscose blend Wide shoulder straps Scoop neckline Snap closure on the gusset Fitted silhouette")
    assert values_at(suit, "garment", "bodysuit") == ["top", True]
    assert suit["cut"] == {"fit": "fitted", "stretch": True}
    assert suit["style"] == "tank", "on straps"
    # (A blazer is still a jacket: only a body- or catsuit isn't a suit.)
    assert top("Sample Label Women Kai Cropped Blazer - Charcoal", "Blazers")["garment"] == "jacket"
    assert top("Sample Label Women Rosa Polo Bodysuit - Black", "Bodysuits")["style"] == "polo"
    # A sweater vest goes over a top, as a jacket does, drawn as a tank; a tag that's the product's own name, and a
    # "Tie-front" in it, isn't a tie.
    assert values_at(top("Sample Label Boucle V-Neck Sweater Vest - Navy", "Vests"), "garment", "style") == ["jacket", "tank"]
    assert GarmentImport().kind_of({"name": "Sample House Tie-front Cardigan Layered V-neck Vest - Heather Grey", "category": "Vests",
                                    "tags": ["Sample House Tie-front Cardigan Layered V-neck Vest - Heather Grey", "vest"]}) == "jacket"
    assert top("Sample Label Micro Waffle Henley - White", "Short Sleeve Henleys")["style"] == "tee"
    assert top("Sample Label Micro Waffle Henley - White", "Long Sleeve Tees")["style"] == "longsleeve"
    with pytest.raises(gi.Error) as error:
        top("Stretch Unitard", "Unitards")
    assert error.value.code == "not_supported"


def test_shorts_skirts_leggings_and_joggers_are_bottoms_in_their_own_styles():
    importer = GarmentImport()

    def read(name, category):
        product = {"name": name, "category": category, "sorted": True}
        return [importer.kind_of(product), importer.bottom_style_of(product)]

    assert read("Sample Works Wallet Short Resort", "Shorts") == ["trousers", "shorts"]
    assert read("Sample Label Dune Skirt", "Mini Skirts") == ["trousers", "skirt"]
    assert read("Sample Label Women Ava Tights", "Leggings") == ["trousers", "leggings"]
    assert read("Loose Fit Sweatpant", "Sweatpants") == ["trousers", "joggers"]
    assert read("Maria Slim Bootcut Jean", "Jeans") == ["trousers", "jeans"]


def test_reads_a_resale_listings_own_measurements_skipping_style_tags_between_label_and_value():
    garment = GarmentImport().from_page(page("resale-coat"), source_url="https://shop.example/coat")

    assert garment["garment"] == "coat"
    assert garment["color"] == COLORS["charcoal"]
    chart = garment["chart"]
    assert values_at(chart, "unit", "kind", "missing") == ["in", "garment", ["waist"]]
    size = sole(chart["sizes"])
    assert size["name"] == "L / US42, IT52"
    assert size["chest"] == pytest.approx(46.5 * 2.54, abs=0.01)
    # 34.5" was measured from the back of the neck; from the shoulder seam it's 34.5" minus half of 18".
    assert size["sleeve"] == pytest.approx((34.5 - 9) * 2.54, abs=0.01)
    assert chart["sleeve_from"] == "centre_back_guessed"


def resale(name, description, fabric=None):
    """The resale coat fixture, rewritten as a different listing: name, description and "Fabric" field."""
    html = page("resale-coat").replace("Wool Overcoat", name).replace("Charcoal wool overcoat.", description).replace('"category":"Coats",', "")
    if fabric:
        html = html.replace("</div>\n</body>", f"</div>\n<div><div>Fabric</div><div>{fabric}</div></div>\n</body>", 1)
    return html


OUTERWEAR = "https://shop.example/products/men/clothing/outerwear/item"


def test_a_jacket_that_says_nothing_about_itself_in_the_outerwear_section_made_of_leather_is_a_zip_up():
    garment = GarmentImport().from_page(resale("Jacket", "Jacket. Black.", fabric="Not listed, feels like leather"), source_url=OUTERWEAR)

    assert values_at(garment, "garment", "style", "fabric") == ["jacket", "zip", "leather"]
    assert garment["color"] == COLORS["black"]


def test_a_denim_jacket_with_a_point_collar_is_a_button_up_coloured_by_its_colour_word():
    garment = GarmentImport().from_page(resale("Denim Jacket", "Denim Jacket. Neutrals. Point Collar.", fabric="100% Cotton"), source_url=OUTERWEAR)

    assert values_at(garment, "style", "fabric") == ["shirt", "denim"]
    assert garment["color"] == COLORS["neutrals"]


def test_bombers_and_blazers_sold_as_outerwear_are_drawn_as_such():
    bomber = GarmentImport().from_page(resale("Bomber Jacket", "Bomber Jacket. Black."), source_url=OUTERWEAR)
    blazer = GarmentImport().from_page(resale("Wool Blazer", "Wool Blazer. Navy."), source_url=OUTERWEAR)

    assert bomber["style"] == "bomber"
    assert blazer["style"] == "tailored"


def test_a_lining_doesnt_decide_the_fabric():
    garment = GarmentImport().from_page(resale("Cashmere Coat", "Cashmere Coat. Black.", fabric="100% Cashmere; Lining 55% Silk, 45% Cotton"),
                                        source_url=OUTERWEAR)

    assert values_at(garment, "garment", "fabric") == ["coat", "wool"]
    assert garment.get("style") is None


def test_a_suit_jacket_from_a_shop_page_is_tailored():
    assert GarmentImport().from_page(page("navy-suit-jacket"), source_url="https://shop.example/navy")["style"] == "tailored"


def cell(value):
    return {"type": "single", "value": value}


KIWI_CHART = {
    "sizings": [{
        "name": "Generic Tops",
        "tables": {"t1": {"data": [[cell(value) for value in row] for row in [
            ["S/M/L", "US", "UK", "EU", "IT"], ["S", "38", "38", "39", "48"], ["M", "40", "40", "40", "50"], ["L", "42", "42", "41", "52"],
        ]]}},
    }],
}


def test_reads_a_kiwi_sizing_shops_chart_from_kiwi_and_a_down_hoodie_as_a_zip_up_jacket():
    asked = []

    def answer(url):
        asked.append(url)
        return KIWI_CHART

    garment = GarmentImport(fetch_json=answer).from_page(page("kiwi-hoodie"), source_url="https://shop.example/products/hoodie")

    query = query_of(asked[0])
    assert asked[0].startswith(gi.KIWI_SIZING)
    assert [query["shop"], query["product"], query["type"]] == ["sample-shop.myshopify.com", "123456", "Hoodies"]
    assert query["tags"] == 'hoodies,mens,Sample "Outdoor"'
    assert values_at(garment, "garment", "style", "fabric") == ["jacket", "zip", "nylon"]
    assert garment["color"] == COLORS["black"]
    # A down hoodie has its hood.
    assert garment["cut"]["hood"]


def test_a_photo_the_browser_sent_is_kept_when_its_a_small_base64_data_url():
    assert gi.browser_photo("data:image/jpeg;base64," + "QUJD" * 500_000)
    assert not gi.browser_photo("data:image/jpeg;base64,QUJD<script>")
    assert not gi.browser_photo("data:text/html;base64,QUJD")
    assert not gi.browser_photo("data:image/jpeg;base64," + "A" * 3_600_000)
    assert not gi.browser_photo("")


def test_a_puffer_a_shrug_or_anything_the_shop_files_under_outerwear_is_worn_as_a_jacket():
    importer = GarmentImport()
    assert importer.kind_of({"name": "Sample Label Women Shea Cropped Denim Puffer - Washed Black", "category": "Puffers", "tags": ["cropped", "denim", "outerwear"], "sorted": True}) == "jacket"
    assert importer.kind_of({"name": "Sample Label Women's Court Shrug - White", "category": "Outerwear", "tags": ["outerwear", "tops"], "sorted": True}) == "jacket"


def test_capri_pants_end_above_the_ankle_and_shorts_are_as_long_as_their_photo_shows():
    importer = GarmentImport()
    capri = importer.usual_trousers({"name": "Sample Works Studio Stretch Capri Legging - Brown", "sizes": ["XS", "S", "M", "L", "XL"], "women": True})
    assert capri.sizes[0]["inseam"] == pytest.approx(76 * 0.72, abs=0.2)
    # A knee-length short photographed 1.9 times as long as its waist is wide: 0.78 of that over half the waist
    # round, less a men's 30 cm rise.
    shorts = importer.usual_trousers({"name": "Sample Atelier Tara Shorts - Brown", "sizes": ["46", "48", "50", "52", "54"],
                                      "bottom_shape": {"thigh": 0.66, "hem": 0.62, "rise": 0.33, "length": 1.9}})
    m = next(size for size in shorts.sizes if size["name"] == "50")
    assert m["inseam"] == pytest.approx(0.78 * 1.9 * m["waist"] / 2 - 30, abs=0.2)
    # Within 4 cm of the usual 18, the usual stands; a named inseam always does.
    usual = importer.usual_trousers({"name": "Sample Atelier Tara Shorts - Brown", "sizes": ["46", "48", "50", "52", "54"], "bottom_shape": {"rise": 0.9, "length": 1.45}})
    assert next(size for size in usual.sizes if size["name"] == "50")["inseam"] == 18.0
    named = importer.usual_trousers({"name": 'Gym Short 5"', "sizes": ["S", "M", "L"], "bottom_shape": {"rise": 0.9, "length": 1.9}})
    assert named.sizes[0]["inseam"] == pytest.approx(12.7, abs=0.1)
    # Pants photographed shorts are shorts.
    assert importer.bottom_style_of({"name": "Sample Atelier Homme Men's Pant - Black", "category": "Pants", "bottom_shape": {"length": 1.62}}) == "shorts"
    assert importer.bottom_style_of({"name": "Kiko Kostadinov Votive Trouser", "category": "Pants", "bottom_shape": {"length": 2.49}}) == "trousers"


def test_a_coats_a_tops_and_a_skirts_length_as_their_photos_show_them():
    importer = GarmentImport()

    def length(chart, name="M"):
        return next(size for size in chart.sizes if size["name"] == name)["length"]

    # A short parka filed under coats, by its name or by its sleeves reaching its hem: a jacket's length, not a coat's.
    parka = importer.usual_sizes("coat", None, {"name": "Sample Goods Short Parka - Navy", "sizes": ["S", "M", "L"]})
    pilot = importer.usual_sizes("coat", None, {"name": "Engineered Garments Pilot Twill Parka", "sizes": ["S", "M", "L"], "shape": {"sleeve_down": 1.0, "length": 0.89}})
    long = importer.usual_sizes("coat", None, {"name": "Sample Atelier Double Breasted Coat", "sizes": ["S", "M", "L"], "shape": {"sleeve_down": 0.85, "length": 1.15}})
    assert length(parka) < 75
    assert length(pilot) < 75
    assert length(long) > 90
    # A women's top its words crop whose photo shows it of usual length: its usual length.
    cropped = {"name": "Cropped Tee", "description": "Cropped fit", "women": True, "sizes": ["S", "M", "L"]}
    assert length(importer.usual_sizes("top", "tee", {**cropped, "shape": {"length": 1.7, "sleeve_down": 0.5}})) > \
        length(importer.usual_sizes("top", "tee", {**cropped, "shape": {"length": 1.05, "sleeve_down": 0.5}}))
    # A men's tee laid flat that its words call regular isn't cut to a crop.
    flat = {"name": "by Parra A Chair Tee - White", "description": "Regular fit", "sizes": ["S", "M", "L"], "shape": {"length": 1.25, "sleeve_down": 0.43}}
    assert length(importer.usual_sizes("top", "tee", flat), "L") > 69
    assert length(importer.usual_sizes("top", "tee", {**flat, "women": True}), "L") < 60
    # A skirt shortened to its photo, never lengthened by it.
    midi = importer.usual_skirts({"name": "Sample House Zip Front Midi Skort", "women": True, "sizes": ["S", "M", "L"],
                                  "bottom_shape": {"skirt": True, "hips": 1.36, "hem": 1.59, "length": 1.73}})
    assert length(midi) < 60
    mini = importer.usual_skirts({"name": "Sample Label Dune Mini Skirt", "women": True, "sizes": ["S", "M", "L"],
                                  "bottom_shape": {"skirt": True, "hips": 1.2, "hem": 1.2, "length": 2.4}})
    assert length(mini) < 45
    # A vest is drawn without sleeves (as a tank), a quilted one too, though it isn't worn as a sweater vest is.
    quilted = {"name": "Sample Label Quilted Nylon Vest - Black", "category": "Vests", "description": "Quilted nylon shell"}
    assert importer.vest_named(quilted)
    assert not importer.vest(quilted)


def test_a_half_zip_or_quarter_zip_pullover_has_its_stand_collar_and_short_zip():
    assert top("vowels Fleece Quarter Zip - Black", "Sweatshirts")["cut"]["half_zip"]
    assert not (top("Sample Label Willet Crewneck - Black", "Crewnecks").get("cut") or {}).get("half_zip")


def test_a_quilted_lining_doesnt_make_a_jacket_a_puffer():
    importer = GarmentImport()
    assert not importer.puffer({"name": "Sample Works Varsity Full-Snap Jacket - Blue / White", "description": "Melton wool Quilted lining Stand collar"})
    assert importer.puffer({"name": "Sample Goods Down Jacket", "description": "Quilted nylon Down filling"})
    assert not importer.puffer({"name": "Sample Label Quilted Flannel Boxy Collared Overshirt - Blue", "description": "Brushed cotton flannel Combo padded nylon on the front and back"})
    assert importer.puffer({"name": "Sample Label Quilted Down Overshirt", "description": "Nylon Down fill"})


def test_a_jacket_or_coat_with_a_hood_is_drawn_with_one_unless_the_hood_stows_away():
    importer = GarmentImport()
    assert importer.hooded({"name": "Sample Goods Wyn Parka - Black"})
    assert importer.hooded({"name": "Sample Goods Vigo Jacket", "description": "Shearling-effect fleece Hood Zip closure"})
    assert not importer.hooded({"name": "Sample Works Alpine Jacket", "description": "Stowable hood in the collar"})
    assert not importer.hooded({"name": "Sample Label Bomber Jacket", "description": "Rib collar"})


def test_a_size_conversion_chart_is_read_as_the_chest_each_size_fits():
    chart = GarmentImport(fetch_json=lambda _: KIWI_CHART).from_page(page("kiwi-hoodie"), source_url="x")["chart"]

    assert values_at(chart, "kind", "missing") == ["sizes", ["waist", "shoulders", "sleeve", "length"]]
    assert [size["name"] for size in chart["sizes"]] == ["S / US 38", "M / US 40", "L / US 42"]
    # A US 40 fits a 40 inch chest; the jacket is that plus a regular cut's room.
    assert chart["sizes"][1]["chest"] == pytest.approx(40 * 2.54 + 11, abs=0.01)


def test_a_listing_with_only_its_size_gets_that_sizes_usual_measurements_marked_as_a_guess():
    garment = GarmentImport().from_page(page("resale-tee"), source_url="https://shop.example/tee")

    assert values_at(garment, "garment", "style", "fabric") == ["top", "longsleeve", "cotton"]
    assert garment["image_url"] == "https://images.example/tee_1.jpg"
    chart = garment["chart"]
    assert values_at(chart, "kind", "missing") == ["sizes", ["waist"]]
    size = sole(chart["sizes"])
    assert size["name"] == "M"
    assert size["chest"] == pytest.approx(108, abs=0.01)
    assert size["sleeve"] > 55


def test_a_jacket_named_for_nothing_is_a_blazer_only_if_it_could_have_lapels():
    def style(name, description):
        return GarmentImport().style_of({"name": name, "category": "Jackets", "description": description}, "x")

    assert style("Sample Goods x Sample Works Waxed Jacket - Tobacco / Brown", "Waxed cotton Classic corduroy collar Detachable wax cotton hood") == "zip"
    assert style("Sample Atelier Hale Jacket - Beige", "Faux fur fabric Snap closure on front Crewneck Padded shoulder") == "zip"
    assert style("Sample House Concord Jacket - Black", "Cotton Slim lapel collar Double button closure on the front") == "tailored"
    assert style("Wool Jacket", "Wool. Fully lined.") == "tailored"
    # A tracksuit's top isn't a suit's jacket.
    assert GarmentImport().style_of({"name": "Sample House Bicolor Tracksuit Top - Black", "category": "Track Jackets",
                                     "description": "Polyester Mock neckline Two-way zipper closure on the front"}, "x") == "zip"


def test_a_utility_jacket_that_zips_is_drawn_as_a_zip_up():
    garment = GarmentImport().from_page(resale("Utility Jacket", "Nylon utility jacket. Two-way zipper closure."), source_url=OUTERWEAR)
    assert values_at(garment, "garment", "style", "fabric") == ["jacket", "zip", "nylon"]


def test_a_shopify_shops_product_is_read_from_its_json_with_its_kiwi_sizing_chart():
    asked = []
    answers = {
        "https://shop.example/products/graphic-tee.json": {"product": {
            "id": 42, "title": "Graphic Tee - White", "vendor": "Sample Label", "product_type": "Short Sleeve Tees",
            "tags": "tees, mens", "body_html": "<p>Logo print on the front</p><p>Material: 100% Cotton</p>",
            "images": [{"src": "https://cdn.example/tee.jpg"}]}},
        "https://shop.example/meta.json": {"myshopify_domain": "sample-shop.myshopify.com"},
    }

    def answer(url):
        asked.append(url)
        return answers.get(url, KIWI_CHART)

    garment = GarmentImport(fetch_json=answer).from_shopify("https://shop.example/collections/tops/products/graphic-tee")

    assert values_at(garment, "garment", "style", "fabric") == ["top", "tee", "cotton"]
    assert values_at(garment, "name", "image_url") == ["Graphic Tee - White", "https://cdn.example/tee.jpg"]
    assert garment["color"] == COLORS["white"]
    kiwi = query_of(asked[-1])
    assert [kiwi["shop"], kiwi["product"], kiwi["tags"]] == ["sample-shop.myshopify.com", "42", "tees,mens"]


def test_a_shopify_product_the_browser_read_with_only_a_size_conversion_table_gets_guessed_sizes_named_as_the_shop_names_them():
    sizing = {"sizings": [{"tables": {"a": {"data": [[cell(v) for v in row] for row in [
        ["S/M/L", "1/2/3", "US"], ["S", "1", "38"], ["M", "2", "40"], ["L", "3", "42"]]]}}}]}
    given = {"shop": "sample-shop.myshopify.com", "sizing": sizing, "product": {
        "id": 7, "handle": "label-tee-2", "title": "Label Portrait Tee - White", "vendor": "Label", "product_type": "Short Sleeve Tees",
        "body_html": "<p>Graphic printed at front</p>", "images": [{"src": "//cdn.shopify.com/tee.jpg"}]}}
    importer = GarmentImport(fetch_json=raises(AssertionError("the browser's answers are used, not fetched again")))
    garment = importer.from_shopify("https://shop.example/collections/tops/products/label-tee-2", given=given)

    assert values_at(garment, "garment", "style", "image_url") == ["top", "tee", "https://cdn.shopify.com/tee.jpg"]
    assert garment["chart"]["kind"] == "sizes"
    assert "M (2)" in [size["name"] for size in garment["chart"]["sizes"]]
    assert importer.from_shopify("https://shop.example/products/other-tee", given=given) is None, "details for another product are ignored"


def test_a_cotton_zip_up_hoodie_with_ribbed_cuffs_and_a_kangaroo_pocket_is_a_hoodie_that_zips_not_a_jacket():
    importer = GarmentImport()
    product = {"name": "Sample Label Boxy Camo Zip Up Hoodie - Stone Gray", "category": "Hoodies",
               "description": "100% cotton All-over Croc Camo print Drawcord-adjustable two-piece hood Front zipper closure Kangaroo pocket Ribbed cuffs and hem Relaxed fit"}
    assert importer.kind_of(product) == "top"
    # A nylon one with the same zip is still a jacket.
    assert importer.kind_of({**product, "description": "Nylon shell Fixed hood Front zipper closure"}) == "jacket"


def test_a_shrunken_sweater_hoodie_with_a_two_way_zip_is_a_fitted_knit_top_not_a_zip_jacket():
    sizing = {"sizings": [{"tables": {"a": {"data": [[cell(v) for v in row] for row in [
        ["Size", "Chest", "Shoulders", "Sleeve Length", "Body Length"], ["XS", "30", "14", "25.125", "19.25"], ["S", "32", "14.5", "25.5", "20"],
        ["M", "34", "15", "25.875", "20.75"], ["L", "36", "15.5", "26.25", "21.5"], ["XL", "39", "16.25", "26.75", "22.25"]]]}}}]}
    given = {"shop": "sample-label.myshopify.com", "sizing": sizing, "product": {
        "id": 9, "handle": "sl-ada-hoodie", "title": "Sample Label Women Ada Shrunken Multi Sweater Hoodie - Cream", "vendor": "Sample Label Women",
        "product_type": "Hoodies", "tags": "hoodies, sweaters, Tops, wmns",
        "body_html": "<p>Cotton blend with a fixed hood, a two-way zipper on the front, embroidery at the chest, and ribbed sleeve cuffs, sides, and hem.</p><p>Material: 60% Cotton / 40% Viscose</p>",
        "images": [{"src": "//cdn.shopify.com/adley.jpg"}], "options": [{"name": "Size", "values": ["XS", "S", "M", "L", "XL"]}]}}
    importer = GarmentImport(fetch_json=raises(AssertionError("the browser's answers are used")))
    garment = importer.from_shopify("https://sample-label.example/collections/womens-apparel-hoodies/products/sl-ada-hoodie", given=given)

    assert values_at(garment, "garment", "style", "fabric", "zip", "women") == ["top", "hoodie", "knit", True, True]
    assert garment["cut"] == {"fit": "fitted", "stretch": True}
    assert garment.get("cropped") is None
    assert garment["chart"]["kind"] == "garment"
    medium = next(size for size in garment["chart"]["sizes"] if size["name"] == "M")
    assert medium["chest"] == pytest.approx(34 * 2.54, abs=0.01)
    # Its 25.875" sleeve (65.7 cm) is from the shoulder seam: extra-long sleeves on a shrunken body are the look.
    assert medium["sleeve"] == pytest.approx(25.875 * 2.54, abs=0.01)
    assert garment["chart"].get("sleeve_from") is None
    # The same hoodie, insulated, is still a jacket.
    down = {**given, "product": {**given["product"], "title": "Lodge Hoodie - Black", "body_html": "<p>Nylon, downproof. Two-way zipper closure.</p>"}}
    assert values_at(importer.from_shopify("https://sample-label.example/products/sl-ada-hoodie", given=down), "garment", "style") == ["jacket", "zip"]
    # A plain fleece hoodie isn't fitted ("ribbed fitted cuffs" don't count), and its fleece isn't a knit.
    fleece = {**given, "product": {**given["product"], "title": "Sample Label Willet Hoodie - Black", "body_html": "<p>Cotton fleece. Kangaroo pocket. Ribbed fitted cuffs and hem.</p>"}}
    plain = importer.from_shopify("https://sample-label.example/products/sl-ada-hoodie", given=fleece)
    assert values_at(plain, "garment", "style", "fabric", "cut") == ["top", "hoodie", "cotton", None]
    # A sweater is a knit whatever its fibre; a slim-fit woven shirt is fitted but doesn't stretch.
    assert importer.fabric_of({"name": "Merino Crewneck Sweater", "fabric": "100% Merino Wool"}, "top") == "knit"
    assert importer.top_cut({"name": "Slim Fit Oxford Shirt", "description": "Cotton poplin."}) == {"fit": "fitted", "stretch": False}


def test_a_sleeve_measured_from_the_centre_back_is_read_from_the_shoulder_seam_once_at_import():
    # A women's knit whose sleeves are longer than any arm: the usual 58 cm arm plus half the shoulders.
    cb = gi.from_text("Size | Chest | Shoulders | Sleeve | Length (cm)\nS | 84 | 37 | 75 | 58\nM | 88 | 38 | 76 | 60\nL | 92 | 39 | 77 | 62\n", garment="top")
    assert cb["chart"]["sleeve_from"] == "centre_back_guessed"
    assert [size["sleeve"] for size in cb["chart"]["sizes"]] == [56.5, 57.0, 57.5]
    # A men's T-shirt's short sleeve is what it says.
    tee = gi.from_text("Size | Chest | Shoulders | Sleeve | Length (cm)\nM | 104 | 46 | 22 | 70\nL | 110 | 48 | 23 | 72\n", garment="top")
    assert tee["chart"].get("sleeve_from") is None
    assert [size["sleeve"] for size in tee["chart"]["sizes"]] == [22.0, 23.0]
    # A chart that says its sleeve runs from the centre back is converted even when the sleeve is short.
    said = gi.from_text("Size | Chest | Shoulders | Sleeve (from center back) | Length (cm)\nM | 104 | 46 | 44 | 70\nL | 110 | 48 | 45 | 72\n", garment="top")
    assert said["chart"]["sleeve_from"] == "centre_back"
    assert [size["sleeve"] for size in said["chart"]["sizes"]] == [21.0, 21.0]
    # A men's long sleeve from the shoulder is left alone; a chart with no shoulders takes off half a man's usual 46.
    long = gi.from_text("Size | Chest | Shoulders | Sleeve | Length (cm)\nM | 108 | 47 | 66 | 72\nL | 114 | 49 | 67 | 74\n", garment="top")
    assert long["chart"].get("sleeve_from") is None
    raglan = gi.from_text("Size | Chest | Sleeve | Length (cm)\nM | 108 | 86 | 72\nL | 114 | 88 | 74\n", garment="top")
    assert [size["sleeve"] for size in raglan["chart"]["sizes"]] == [63.0, 65.0]
    assert raglan["chart"]["sleeve_from"] == "centre_back_guessed"


def test_a_site_that_turns_away_every_app_gives_the_links_own_garment_in_usual_sizes_without_asking_it():
    garment = gi.from_url("https://www.therealreal.com/products/men/clothing/sweaters/sample-label-cashmere-collar-cardigan-x6alq")
    assert garment["name"] == "Sample Label Cashmere Collar Cardigan"
    # A cardigan is worn open over a top, as a jacket is.
    assert values_at(garment, "garment", "style") == ["jacket", "cardigan"]
    assert not garment.get("women")
    assert garment["chart"]["kind"] == "sizes"
    assert garment["link_note"] == "therealreal.com doesn't let apps read its pages, so this is a men's cardigan, worn open over a top, in usual sizes."
    # Grey until a photo gives it its colour.
    assert garment["color"] == gi.LINK_GREY


def test_a_link_the_store_wont_give_reads_its_words():
    gave_up = "shop.example took too long to answer"
    dress = gi.from_link("https://shop.example/en-us/women/dresses/satin-slip-midi-dress-123456.html", because=gave_up)
    assert values_at(dress, "garment", "style") == ["top", "dress"]
    assert dress["women"]
    assert dress["cut"]["length"] == "midi"
    assert "a women's dress in usual sizes" in dress["link_note"]
    pants = gi.from_link("https://shop.example/p/black-pleated-wool-trousers/AB1234", because=gave_up)
    assert pants["garment"] == "trousers"
    assert pants["color"] == COLORS["black"]
    assert pants["link_note"] == "shop.example took too long to answer, so this is pants in usual sizes."
    nothing = gi.from_link("https://shop.example/p/8812734", because=gave_up)
    assert values_at(nothing, "garment", "name") == ["top", "Top"]
    assert "so this is a T-shirt in usual sizes" in nothing["link_note"]


def test_a_link_the_store_wont_give_read_by_the_shops_own_name_and_kind_for_it_when_theyre_known():
    gave_up = "brand.example doesn't let apps read its pages"
    url = "https://brand.example/products/1m73-115-902-org"
    assert gi.from_link(url, because=gave_up)["name"] == "Org", "the link's words are only an item code"
    hoodie = gi.from_link(url, because=gave_up, name="SAMPLE WORKS X SAMPLE LABEL - CAMO FULL ZIP HOODIE MENS", category="CUT AND SEWN")
    assert values_at(hoodie, "garment", "style") == ["top", "hoodie"]
    assert hoodie["name"] == "Sample Works X Sample Label - Camo Full Zip Hoodie Mens"
    assert hoodie["link_note"] == "brand.example doesn't let apps read its pages, so this is a hoodie in usual sizes."
    varsity = gi.from_link("https://brand.example/products/1m73-141-901-nvy", because=gave_up, name="SAMPLE LABEL X SAMPLE WORKS - VARSITY JACKET MENS", category="JACKETS")
    assert varsity["garment"] == "jacket"


def test_a_name_that_says_what_it_is_only_after_its_dash_is_read_by_whats_after_it():
    importer = GarmentImport()
    assert importer.kind_of({"name": "SAMPLE WORKS X SAMPLE LABEL - CAMO FULL ZIP HOODIE MENS", "category": "CUT AND SEWN", "sorted": True}) == "top"
    assert importer.kind_of({"name": "Track Jacket - Peacoat", "category": None}) == "jacket"


def test_a_link_that_isnt_a_shopify_product_is_left_to_the_page():
    assert GarmentImport(fetch_json=raises(fetcher.Error("no"))).from_shopify("https://shop.example/item/1") is None


def test_a_pasted_size_on_its_own_gets_that_sizes_usual_measurements():
    garment = gi.from_text("M", garment="top")
    assert values_at(garment, "garment", "style") == ["top", "tee"]
    assert garment["chart"]["kind"] == "sizes"
    assert sole(garment["chart"]["sizes"])["chest"] == pytest.approx(106, abs=0.01)


def test_a_sweatshirt_hoodie_is_a_top_drawn_as_a_hoodie():
    import re

    html = re.sub(r"Nylon\. .*?Color: Black", "Cotton fleece. Kangaroo pocket.", page("kiwi-hoodie")).replace("Sample Down Hoodie", "Sample Fleece Hoodie")
    garment = GarmentImport(fetch_json=lambda _: KIWI_CHART).from_page(html, source_url="x")
    assert values_at(garment, "garment", "style", "fabric") == ["top", "hoodie", "cotton"]


def test_a_kiwi_shop_whose_chart_service_is_down_says_theres_no_chart():
    with pytest.raises(gi.Error) as error:
        GarmentImport(fetch_json=raises(fetcher.Error("down"))).from_page(page("kiwi-hoodie"), source_url="x")
    assert error.value.code == "no_size_chart"


def test_a_sport_coat_is_a_jacket_not_a_coat():
    html = page("navy-suit-jacket").replace("Navy Wool Suit Jacket", "Navy Sport Coat")
    assert GarmentImport().from_page(html, source_url="x")["garment"] == "jacket"


def test_reads_a_trousers_chart_inseam_and_all():
    chart = ("Size\tWaist (in)\tSeat\tThigh\tInseam\tLeg opening\n"
             "32\t32\t41\t24.5\t32\t16\n"
             "34\t34\t43\t25.5\t32\t16.5\n")
    garment = gi.from_text(chart, garment="trousers")

    assert garment["garment"] == "trousers"
    first = garment["chart"]["sizes"][0]
    assert first["name"] == "32"
    assert first["waist"] == pytest.approx(32 * 2.54 + 2.5, abs=0.01)  # a 32 waist chart is for the body: the waistband's room is added
    assert first["inseam"] == pytest.approx(32 * 2.54, abs=0.01)
    assert first["leg_opening"] == pytest.approx(16 * 2.54, abs=0.01)


def test_pants_with_no_size_chart_get_the_waist_sizes_their_page_offers():
    html = """<html><head><title>Athletic-Fit Linen-Blend Pant | Sample Outlet</title></head><body>
      <h1>Athletic-Fit Linen-Blend Pant</h1><p>$39.99</p>
      <div class="pdp-dimension--waist"><h3>Waist</h3><button>28W</button><button>30W</button><button>32W</button><button>34W</button></div>
      <div class="pdp-dimension--length"><h3>Length</h3><button>30L</button><button>32L</button></div>
      <a href="/size-guide">Size Guide</a>
    </body></html>
    """
    garment = GarmentImport(fetch_page=lambda _: "<html></html>").from_page(html, source_url="https://outlet.example/browse/product.do?pid=1")

    assert values_at(garment, "garment", "style") == ["trousers", "trousers"]
    assert [size["name"] for size in garment["chart"]["sizes"]] == ["28", "30", "32", "34"]
    assert garment["chart"]["sizes"][2]["waist"] == pytest.approx(32 * 2.54, abs=0.1)


def test_pants_whose_page_shows_no_sizes_at_all_still_get_the_usual_waists():
    garment = GarmentImport().from_page("<html><title>Pleated Wool Trousers</title></html>", source_url="x")

    assert garment["garment"] == "trousers"
    assert len(garment["chart"]["sizes"]) >= 5


def test_a_top_with_no_chart_gets_the_letter_sizes_its_page_lists():
    html = """<html><title>Heavyweight Pocket Tee</title><body>
      <fieldset class="size-selector"><label>S</label><label>M</label><label>L</label><label>XL</label></fieldset>
    </body></html>
    """
    garment = GarmentImport().from_page(html, source_url="x")

    assert [size["name"] for size in garment["chart"]["sizes"]] == ["S", "M", "L", "XL"]


def test_a_page_for_trousers_is_read_as_trousers():
    import re

    table = ("<table><tr><th>Size</th><th>Waist</th><th>Seat</th><th>Inseam</th></tr>\n"
             "<tr><td>32</td><td>33.5</td><td>41</td><td>32</td></tr><tr><td>34</td><td>35.5</td><td>43</td><td>32</td></tr></table>\n")
    html = page("navy-suit-jacket").replace("Navy Wool Suit Jacket", "Navy Wool Trousers").replace("Suit jackets", "Trousers")
    html = re.sub(r"<table>.*</table>", lambda _: table, html, count=1, flags=re.S)
    garment = GarmentImport().from_page(html, source_url="x")

    assert garment["garment"] == "trousers"
    assert garment["chart"]["kind"] == "garment"
    assert garment["chart"]["sizes"][0]["waist"] == pytest.approx(33.5 * 2.54, abs=0.01)


def test_clothes_read_from_a_photo_get_every_usual_size_of_that_kind():
    hoodie = gi.from_photo(kind="top", style="hoodie")
    assert values_at(hoodie, "garment", "style", "name") == ["top", "hoodie", "Hoodie from your photo"]
    assert hoodie["chart"]["kind"] == "sizes"
    assert [size["name"] for size in hoodie["chart"]["sizes"]] == ["XS", "S", "M", "L", "XL", "XXL", "XXXL"]

    pants = gi.from_photo(kind="trousers")
    assert pants["garment"] == "trousers"
    assert next(size for size in pants["chart"]["sizes"] if size["name"] == "32")["waist"] == pytest.approx(81.3, abs=0.1)


def test_bottoms_from_a_photo_can_be_jeans_shorts_or_a_skirt():
    assert values_at(gi.from_photo(kind="trousers", style="jeans"), "garment", "style", "name") == ["trousers", "jeans", "Jeans from your photo"]
    shorts = gi.from_photo(kind="trousers", style="shorts")
    assert shorts["style"] == "shorts"
    assert shorts["chart"]["sizes"][0]["inseam"] < 40
    skirt = gi.from_photo(kind="trousers", style="skirt")
    assert skirt["style"] == "skirt"
    assert [size["name"] for size in skirt["chart"]["sizes"]] == ["XS", "S", "M", "L", "XL"]
    # Anything else is plain pants.
    assert gi.from_photo(kind="trousers", style="cape")["style"] == "trousers"


def test_a_dress_is_a_dress_not_a_jacket_with_long_sleeves_when_its_listing_says_so():
    importer = GarmentImport(fetch_json=raises(fetcher.Error("no chart")))
    garment = importer.from_page(resale("Cut-Out Long-Sleeve Maxi Dress", "Ribbed knit maxi dress with long sleeves."), source_url="x")
    assert values_at(garment, "garment", "style") == ["top", "dress"]
    assert sole(garment["chart"]["sizes"])["sleeve"] > 40

    assert GarmentImport().kind_of({"name": "Oxford Dress Shirt"}) == "top"
    assert GarmentImport().top_style_of({"name": "Oxford Dress Shirt"}) != "dress"


def test_a_rugby_shirt_is_a_long_sleeve_polo_and_a_jersey_whose_photo_shows_long_sleeves_has_them():
    style = GarmentImport().top_style_of
    assert style({"name": "Sample Atelier Club Rugby Jersey - Black / Navy", "category": "Jerseys", "description": "Spread collar Dropped shoulders"}) == "rugby"
    assert style({"name": "Long Sleeve Polo - Navy"}) == "rugby"
    # A jersey named for nothing: its photo's sleeves reach down past the hem, or barely leave the shoulder.
    assert style({"name": "Dazzle Jersey - Black", "category": "Jerseys", "shape": {"sleeve": 1.28, "sleeve_down": 1.0, "length": 1.28}}) == "longsleeve"
    assert style({"name": "Home Jersey - Red", "category": "Jerseys", "shape": {"sleeve": 0.45, "sleeve_down": 0.3, "length": 1.3}}) == "tee"
    assert style({"name": "Home Jersey - Red", "category": "Jerseys"}) == "tee"


def test_a_shirt_whose_description_or_photo_shows_short_sleeves_is_a_short_sleeve_shirt():
    style = GarmentImport().top_style_of
    assert style({"name": "Sample House Solstice Shirt - Green", "category": "Button Up Shirts", "shape": {"sleeve": 1.01, "sleeve_down": 0.55}}) == "shortshirt"
    assert style({"name": "Sample Works Wide Shirt - Black", "description": "Boxy fit Short sleeves"}) == "shortshirt"
    # A long-sleeve one hangs down past seven tenths, and one with no photo stays long.
    assert style({"name": "Sample Atelier Shirt - Black", "shape": {"sleeve": 1.23, "sleeve_down": 0.92}}) == "shirt"
    assert style({"name": "Oxford Shirt - Blue"}) == "shirt"
    # An undershirt is a tee.
    assert style({"name": "Sample Label 3-Pack Undershirt - White"}) == "tee"
    # A "Long Sleeve Shirt" is a button-up, not a long-sleeve tee.
    assert style({"name": "Sample Atelier Long Sleeve Shirt - Black"}) == "shirt"
    assert style({"name": "Sample House Linen Long Sleeve Button Shirt - Pale Blue"}) == "shirt"
    assert style({"name": "Long Sleeve T-Shirt - White"}) == "longsleeve"


def trouser_chart(inseams):
    return Chart(sizes=[{"name": str(44 + 2 * i), "waist": 79.0 + 4 * i, "seat": 108.0 + 4 * i, "inseam": inseam} for i, inseam in enumerate(inseams)],
                 unit="cm", kind="garment", missing=[])


def test_sweatpants_whose_photo_shows_an_open_wide_hem_have_no_cuffs_and_their_legs_are_as_wide_as_the_photos():
    importer = GarmentImport()
    # Wide legs laid touching (no thigh found), the hem 0.69 of the waist.
    shape = importer.photo_bottom_shape({"thigh": None, "hem": 0.687, "rise": 0.331, "length": 2.65})
    assert shape == {"thigh": None, "hem": 0.687, "rise": 0.331, "length": 2.65}
    lounge = {"name": "Sample Label Lounge Sweatpant - Black", "description": "Elastic waistband Drawcord Relaxed fit", "bottom_shape": shape}
    assert importer.bottoms_cut(lounge, "joggers", trouser_chart([81, 81]))["open_hem"]
    legs = importer.as_photographed_legs([{"name": "L", "waist": 86.0, "seat": 110.0, "inseam": 81}], shape)
    assert legs[0]["leg_opening"] == pytest.approx(59, abs=1)
    # A cuffed jogger, or one whose listing says it's cuffed, keeps its cuffs.
    cargo = {"name": "Sample Goods Loose Fit Sweatpant", "description": "Elasticated cuffs", "bottom_shape": {**shape, "hem": 0.45}}
    assert (importer.bottoms_cut(cargo, "joggers", trouser_chart([81, 81])) or {}).get("open_hem") is None
    assert (importer.bottoms_cut({**lounge, "description": "Ribbed cuffs"}, "joggers", trouser_chart([81, 81])) or {}).get("open_hem") is None
    # Big shorts (a 4XL's thigh past what an 80 cm opening allows) don't raise.
    big = importer.as_photographed_legs([{"name": "4XL", "waist": 117.0, "seat": 146.0, "thigh": 104.0, "inseam": 20}], shape)
    assert big[0]["leg_opening"] == 80


def test_pants_the_shop_calls_baggy_wide_relaxed_or_pleated_are_cut_loose_slim_skinny_or_tapered_ones_slim():
    importer = GarmentImport()

    def cut(name, description="", style="trousers"):
        return importer.bottoms_cut({"name": name, "description": description}, style, trouser_chart([81, 81]))

    assert cut("Sample House Baggy Jeans - Denim Blue", "", "jeans") == {"fit": "loose"}
    assert cut("Sample House Pleated Pant - Mustard", "Elasticated waistband with drawcord") == {"elastic": True, "fit": "loose"}
    assert cut("Sample House Cargo Pant - Sand", "Pleats at the waist. Relaxed, straight leg fit") == {"fit": "loose"}
    assert cut("Wide-Leg Trouser") == {"fit": "loose"}
    assert cut("Slim Tapered Chino") == {"fit": "slim"}
    assert cut("Sample House Cashmere Trouser - Iron", "Button closure at the waistband. Straight-leg fit") is None
    # A wide waistband isn't a wide leg; leggings aren't cut loose or slim.
    assert cut("Twill Trouser", "Wide waistband") is None
    assert cut("Slim Leggings", "", "leggings") is None


def test_trousers_sold_unhemmed_are_marked_so():
    importer = GarmentImport()

    def hem(inseams, description="", name="Trouser"):
        return importer.bottoms_cut({"name": name, "description": description}, "trousers", trouser_chart(inseams))

    assert hem([103.97] * 5) == {"hem": "unfinished"}
    assert hem([87.8, 87.8, 87.8, 88.3, 88.8]) is None
    assert hem([82] * 3, "Unhemmed, to be finished to your length.") == {"hem": "unfinished"}
    # A raw hem is a cut edge (frayed jeans), unless the legs are long too.
    assert hem([82] * 3, "Raw hem", "Raw Hem Jean") is None


def test_french_and_italian_sizes_are_read_as_the_waists_theyre_for_not_as_inches():
    importer = GarmentImport()
    # French 38 to 46: a 44 is a 34 in waist, not a 44.
    baggy = importer.usual_trousers({"name": "Sample House Baggy Jeans", "sizes": ["38", "40", "42", "44", "46"]})
    assert next(s for s in baggy.sizes if s["name"] == "44")["waist"] == pytest.approx(34 * 2.54, abs=0.1)
    italian = importer.usual_trousers({"name": "Wool Trouser", "sizes": ["44", "46", "48", "50", "52", "54"]})
    assert next(s for s in italian.sizes if s["name"] == "48")["waist"] == pytest.approx(32 * 2.54, abs=0.1)
    # Waist sizes stay waist sizes.
    straight = importer.usual_trousers({"name": "Classic Straight Jean", "sizes": ["28", "29", "30", "31", "32", "33", "34", "36", "38", "40"]})
    assert next(s for s in straight.sizes if s["name"] == "34")["waist"] == pytest.approx(34 * 2.54, abs=0.1)


def test_a_womens_jacket_or_coat_with_no_chart_gets_a_womens_usual_sizes():
    importer = GarmentImport()
    jacket = next(s for s in importer.usual_sizes("jacket", "zip", {"women": True, "sizes": ["XS", "S", "M", "L", "XL"]}).sizes if s["name"] == "M")
    assert [jacket["chest"], jacket["shoulders"], jacket["sleeve"], jacket["length"]] == [101, 40.5, 57, 60]
    coat = importer.usual_sizes("coat", None, {"women": True, "sizes": ["S", "M", "L"]})
    assert next(s for s in coat.sizes if s["name"] == "M")["shoulders"] < 42


def test_a_jacket_made_to_end_at_the_waist_and_an_oversized_top_or_jacket_say_so_in_their_cut():
    importer = GarmentImport()
    assert importer.jacket_cut({"name": "Sample Label Women Isla Terry Track Zip - Navy"}) == {"ends": "waist"}
    assert importer.jacket_cut({"name": "Sample House Lamb Leather Aviator Blouson Jacket - Grey"}) == {"ends": "waist"}
    assert importer.jacket_cut({"name": "Utility Jacket", "description": "An oversized fit with dropped shoulders."}) == {"fit": "oversized"}
    assert importer.jacket_cut({"name": "Sample Label Harbour Utility Jacket - Brown", "description": "Nylon. Mock neckline."}) is None
    assert importer.top_cut({"name": "Boxy Pocket Tee", "description": "Cotton."}) == {"fit": "oversized"}
    assert importer.style_of({"name": "Sample House Lamb Leather Aviator Blouson Jacket - Grey", "category": "Leather Jackets"}, "x") == "bomber"


def test_a_long_sleeve_the_shop_photo_shows_hanging_past_the_hem_is_read_from_the_shoulder_not_the_centre_back():
    from renderer.util import rnd

    rows = [[14, 33, 26.83, 20.5], [14.5, 35, 27.08, 21], [15, 37, 27.33, 21.5], [15.5, 39, 27.58, 22], [16, 41, 27.83, 22.5], [16.5, 43, 28.08, 23]]
    sizes = [{"name": name, **dict(zip(["shoulders", "chest", "sleeve", "length"], [rnd(value * 2.54) for value in row]))}
             for name, row in zip(["XS", "S", "M", "L", "XL", "XXL"], rows)]
    chart = Chart(sizes=sizes, unit="in", kind="garment", missing=["waist"])
    importer = GarmentImport()

    assert importer.shoulder_sleeves(chart, {"women": True}).sleeve_from == "centre_back_guessed"
    seen = importer.shoulder_sleeves(chart, {"women": True, "shape": {"sleeve": 2.66, "length": 1.84}})
    assert seen.sleeve_from is None
    assert next(s for s in seen.sizes if s["name"] == "L")["sleeve"] == pytest.approx(70.05, abs=0.01)
    # A photo of sleeves that end at the wrist (as long as the body) keeps the centre-back reading.
    assert importer.shoulder_sleeves(chart, {"women": True, "shape": {"sleeve": 1.7, "length": 1.84}}).sleeve_from == "centre_back_guessed"


def test_what_a_listing_is_from_words_that_misled_it():
    importer = GarmentImport()
    # Padded elbows don't make a hoodie a padded jacket.
    assert importer.kind_of({"name": "Sample Goods Padded Elbow Zip-Up Hoodie - Sand", "category": "Hoodies",
                             "description": "Cotton Drawstring-adjustable hood Two-way zipper closure on the front Split kangaroo pockets Padded elbows Ribbed sleeve cuffs and hem"}) == "top"
    assert importer.kind_of({"name": "Padded Hoodie", "category": "Hoodies", "description": "Padded throughout Hood Zip closure"}) == "jacket"
    # A stowaway hood isn't drawn, and a hook-and-eye closure (spelled "hood-and-eye") isn't a hood.
    assert not importer.hooded({"name": "&Kin 2L Flannel Rainier Jacket", "description": "Drawcord-adjustable stowaway hood Snap at back collar"})
    assert not importer.hooded({"name": "Sample Label Women Mara Faux Fur Duster", "description": "Faux fur Hood-and-eye closure on the front"})
    # A duster is a coat; a shrug is worn open, as a cardigan is.
    assert importer.kind_of({"name": "Sample Label Women Mara Faux Fur Duster - Brown", "category": "Outerwear"}) == "coat"
    assert importer.style_of({"name": "Sample Goods Dahlia Shrug - Army", "category": "Tank Tops", "description": "Off-shoulder neckline Ribbed texture"}, "x") == "cardigan"
    # A coach jacket that zips, its snaps on the collar and pockets; a utility jacket that snaps shut stays a shirt jacket.
    assert importer.style_of({"name": "Sample Goods Denim Studio Coach Jacket - Navy Blue", "category": "Coaches Jackets",
                              "description": "Classic collar with three-position snap closure Two-way concealed zip closure Pleated patch pockets with snap closure"}, "x") == "zip"
    assert importer.style_of({"name": "Utility Jacket", "category": "Jackets", "description": "Zip closure on the chest pocket Snap closure on the front"}, "x") == "shirt"
    # A "T-shirt" with a shirt's collar, buttoned down the front, is a short-sleeve shirt; a henley stays a tee.
    assert importer.top_style_of({"name": "Sample Atelier Homme Crinkle Finish T-Shirt - Black", "category": "Button Up Shirts",
                                  "description": "Classic collar Button closure on the front All-over crinkle effect"}) == "shortshirt"
    assert importer.top_style_of({"name": "Henley Tee", "category": "Tees", "description": "Three-button placket"}) == "tee"

    # A collar the listing names is drawn turned down; not a stand collar, a hood or a crewneck.
    def named(description, kind="jacket", style=None, cut=None):
        return importer.named_collar({"name": "X", "description": description}, kind, style, cut)

    assert named("Wool Notched lapels Double breasted closure", "coat")
    assert named("Classic collar with three-position snap closure Two-way concealed zip closure")
    assert named("Towelling Camp collar Button closure on the front", "top", "shortshirt")
    assert not named("Stand collar Zip closure")
    assert not named("Classic collar Drawcord hood", "jacket", None, {"hood": True})
    assert not named("Crewneck Ribbed cuffs", "top", "sweatshirt")
    assert not named("Spread collar", "top", "dress")
    # A tee filed under long-sleeve tees has long sleeves.
    assert importer.top_style_of({"name": "Sample Label Women Boatneck Tee - Black", "category": "Long Sleeve Tees", "description": "Boat neckline Fitted"}) == "longsleeve"


def test_a_photo_is_fetched_once_and_kept_inline(monkeypatch):
    """(The renderer's own: a shop photo comes inline as a data URL, and nothing is fetched when there's none.)"""
    asked = []

    def image(url):
        asked.append(url)
        return b"png", "image/png"

    monkeypatch.setattr(gi, "fetch_image", image)
    garment = gi.with_photo({"name": "Tee", "image_url": "https://images.example/tee.png"})
    assert garment["photo"] == "data:image/png;base64,cG5n"
    assert "image_url" not in garment
    assert gi.with_photo({"name": "Tee"}) == {"name": "Tee"}
    assert asked == ["https://images.example/tee.png"]


def test_chart_reader_reads_a_conversion_table_only_with_three_sizes():
    assert chart_reader.read([["S/M/L", "US"], ["S", "38"], ["M", "40"]], garment="jacket") is None
