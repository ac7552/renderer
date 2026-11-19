"""Seven made-up listings, worded as shops word theirs: what each dress is, read from its name, category and
description."""

import pytest

from renderer import fit
from renderer.garment_import import dress_cut

LISTINGS = {
    "tessa": ["Sample Label Women Tessa Suiting Dress - Black", "Mini Dresses",
              "Stretch nylon blend Straight neckline Princess seams Belt at the waist Form-fitting silhouette Material: 75% Nylon / 25% Elastane"],
    "noor": ["Sample Label Women Noor Strapless Faux Leather Mini Dress - Black", "Mini Dresses",
             "Faux leather Strapless construction Boning details at the seams Form-fitting silhouette"],
    "bodice": ["Sample House Leather Dress with Faux Fur Bodice - Black", "Mini Dresses",
             "Leather Wide straps Scoop neck Darts on the front and back Slim fit Material: Body Face: 100% Leather"],
    "lio": ["Sample Atelier Lio Slip Dress - Rose", "Mini Dresses",
               "Printed polyester blend Contrast trims Thin straps Plunging neck Open back Mini fit Material: 65% Polyester / 35% Silk"],
    "odile": ["Sample Works Odile Dress - Peach", "Mini Dresses",
                 "Lightweight chiffon polyester Sculpted one shoulder neckline Integrated high neck scarf Draped sash self-tie closure on hip Fitted silhouette Mini length"],
    "sela": ["Sample Label Sela Layered Gown - Caramel", "Maxi Dresses",
             "Lyocell blend Adjustable straps on the front Cutouts on the shoulder Raw sleeve cuffs Sweetheart neck Flared hem Maxi fit Material: 90% Lyocell / 10% Silk"],
    "rhea": ["Sample Goods Rhea Long Sleeve Shirtdress - Stone Lurex", "Mini Dresses",
              "Knitted viscose blend Semi-sheer Classic collar Button closure on the front and sleeve cuffs Slim fit Material: 75% Viscose / 20% Lurex / 5% Nylon"],
}


def cut(key):
    name, category, description = LISTINGS[key]
    return dress_cut.read({"name": name, "category": category, "description": description})


def values_at(found, *keys):
    return [found.get(key) for key in keys]


def test_each_dresss_sleeves_neckline_length_fit_and_cloth():
    # A suiting holds its shape, stretch or not.
    assert values_at(cut("tessa"), "sleeves", "neckline", "length", "fit", "stretch", "fabric") == ["none", "straight", "mini", "fitted", True, "structured"]
    assert values_at(cut("noor"), "sleeves", "length", "fit", "fabric") == ["strapless", "mini", "fitted", "leather"]
    assert values_at(cut("bodice"), "sleeves", "neckline", "fit", "fabric") == ["straps", "scoop", "slim", "leather"]
    assert values_at(cut("lio"), "sleeves", "neckline", "fabric", "printed") == ["thin_straps", "plunge", "silk", True]
    assert values_at(cut("odile"), "sleeves", "fabric", "printed") == ["one_shoulder", "silk", False]
    assert "tie" in cut("odile")["details"]
    # Knitted viscose is a knit, not a silky woven.
    assert values_at(cut("rhea"), "sleeves", "stretch", "fabric", "sheer_kind", "collar") == ["long", True, "jersey", "semi", True]
    assert not cut("sela")["collar"]
    pia = dress_cut.read({"name": "Sample Atelier Pia Midi Skirt - Pistachio", "category": "Maxi Skirts", "description": "Nylon Flared construction Relaxed fit"})
    assert pia["length"] == "midi", "its own name, before the shop's category"
    talia = dress_cut.read({"name": "Sample House Talia Dress - Sequin Pink", "category": "Maxi Dresses",
                              "description": "Lustrous knit woven fabric All-over sequins Frayed hem Mini length"})
    assert talia["length"] == "mini", "its description's length, before the shop's category"


def test_the_cloth_is_what_most_of_it_is():
    mira = dress_cut.read({"name": "Sample Label Mira Mini Dress - Forest", "category": "Mini Dresses",
                           "description": "Viscose blend Ruffled trim on the straps and neck Plunging neck Lace-up closure on the front Ruffled hem Slim fit",
                           "fabric": "Main: 77% Viscose / 15% Nylon / 8% Silk / Contrast Body: 58% Rayon / 42% Cupro"})
    assert dress_cut.fibre_shares("Main: 77% Viscose / 15% Nylon / 8% Silk / Contrast Body: 58% Rayon / 42% Cupro") == {"viscose": 77.0, "nylon": 15.0, "silk": 8.0}
    assert mira["fabric"] == "silk", "a viscose hangs like silk: from its viscose, not its 8% silk"
    cleo = dress_cut.read({"name": "Sample Label Women Cleo Micro Wrap Skirt - Black", "category": "Mini Skirts",
                              "description": "Polyester blend Mid-rise waistband Wrap overlay on the front", "fabric": "45% Polyester / 35% Viscose / 15% PC / 5% Polyurethane"})
    assert values_at(cleo, "stretch", "fabric") == [True, "stretch"]
    assert dress_cut.read({"name": "Faux Leather Mini Dress", "description": "Material: 54% Polyurethane / 46% Viscose"})["fabric"] == "leather"
    assert dress_cut.read({"name": "Sample Label Women Sana Halter Maxi Dress", "description": "Viscose blend Halter neckline Back straps"})["sleeves"] == "halter"


def test_a_dresss_photo_gives_its_shape():
    tessa = dress_cut.read({"name": "Sample Label Women Tessa Suiting Dress - Black", "category": "Mini Dresses", "description": LISTINGS["tessa"][-1],
                            "dress_shape": {"waist": 0.81, "waist_at": 0.42, "hips": 1.07, "hem": 1.35, "flare_from": "waist", "neck_depth": 0.1, "neck_width": 0.75}})
    assert values_at(tessa, "fit", "waist_flare") == ["flared", True]
    assert tessa["shape"] == {"waist": 0.81, "waist_at": 0.42, "hips": 1.07, "hem": 1.35, "neck_depth": 0.1, "neck_width": 0.75}
    dara = dress_cut.read({"name": "Sample Atelier Dara Mini Dress - Brown", "description": "Nylon blend Shoulder pads Mock neckline Draped construction Relaxed fit",
                              "dress_shape": {"sleeves": "long", "neck_depth": 0}})
    assert dara["sleeves"] == "long"
    cloud = dress_cut.read({"name": "Sample Works Cloud Knit Mini Dress", "description": "Cowl neckline Self-tie closure on the back Fitted silhouette",
                           "dress_shape": {"halter": True, "waist": 0.98, "hem": 0.99, "hips": 1.1}})
    assert values_at(cloud, "sleeves", "fit") == ["halter", "fitted"]
    # Sleeves the words name stay, whatever the photo's top looks like; a polo dress has a collar.
    polo = dress_cut.read({"name": "Sample House Crystal Embellished Polo Dress - Light Pink", "description": "Stretch cotton jersey Crystal buttons",
                           "dress_shape": {"halter": True}})
    assert values_at(polo, "sleeves", "collar") == ["short", True]
    # A caftan's batwing sleeves are wide at the top of its photo, not a halter's narrow neck.
    caftan = dress_cut.read({"name": "Sample Atelier Short Cover-Up Caftan With Batwing Sleeves - Multi", "category": "Mini Dresses", "description": "",
                             "dress_shape": {"halter": True}})
    assert values_at(caftan, "sleeves", "length") == ["long", "mini"]
    # Only the shop's category calls the Iona a maxi; its photo is a mini's. A dress named a maxi stays one.
    iona = dress_cut.read({"name": "Sample Label Iona Dress - Champagne Beige", "category": "Maxi Dresses", "description": "Satin Ruched bodice", "dress_shape": {"length": 2.64}})
    assert iona["length"] == "mini"
    vida = dress_cut.read({"name": "Sample Goods Vida Satin Maxi Dress - White", "category": "Maxi Dresses", "description": "", "dress_shape": {"length": 2.64}})
    assert vida["length"] == "maxi"
    assert dress_cut.read({"name": "Sample House Duo Dress - Grey", "category": "Maxi Dresses", "description": "", "dress_shape": {"length": 3.91}})["length"] == "maxi"
    # A flounce's width at the hem isn't the body's: the body stays as it is, the flounce goes on.
    mira = dress_cut.read({"name": "Sample Label Mira Mini Dress", "description": "Ruffled hem Slim fit", "dress_shape": {"waist": 0.84, "hips": 1.1, "hem": 1.29, "flare_from": "knee"}})
    assert values_at(mira, "fit", "hem_flare") == ["slim", False]
    assert mira["shape"]["hem"] == 1.1


def test_a_flared_hem_doesnt_make_a_gown_an_a_line():
    sela = cut("sela")
    assert values_at(sela, "sleeves", "length", "fit", "hem_flare") == ["long", "maxi", "slim", True]
    m = next(size for size in dress_cut.usual_sizes(sela, ["XS", "S", "M", "L"]).sizes if size["name"] == "M")
    assert m["hips"] == pytest.approx(106, abs=1), "the hips eased as a slim fit's, not a flared one's"
    assert not cut("tessa")["hem_flare"]


def test_womens_sizes_by_letter_and_by_us_number_at_the_dresss_length():
    letters = dress_cut.usual_sizes(cut("noor"), ["XXS", "XS", "S", "M", "L", "XL", "XXL"]).sizes
    m = next(size for size in letters if size["name"] == "M")
    assert m["length"] == pytest.approx(62, abs=1), "a strapless mini, measured from its top edge"
    assert m["sleeve"] is None

    numbers = dress_cut.usual_sizes(cut("bodice"), ["00", "0", "2", "4", "6", "8", "10", "12", "14"]).sizes
    assert [size["name"] for size in numbers] == ["00", "0", "2", "4", "6", "8", "10", "12", "14"]
    assert numbers[0]["chest"] < numbers[-1]["chest"]


def test_a_stretch_dress_made_smaller_than_the_body_fits_and_a_sleeveless_one_isnt_judged_on_sleeves():
    woman = {"chest": 91.5, "waist": 74, "shoulders": 39.5, "arm": 58, "height": 165, "hips": 99}
    sizes = [{"name": name, "chest": chest * 2.54, "waist": waist * 2.54, "shoulders": 31.75, "sleeve": None, "length": 80}
             for name, chest, waist in [("XS", 29, 23.5), ("S", 31, 25.5), ("M", 33, 27.5), ("L", 35, 29.5)]]
    best = fit.rank(woman, sizes, "regular", "top", style="dress", details={"stretch": True, "sleeves": "none"})[0]
    assert best.size == "M"
    assert best.verdict() == "fits"
    assert next(check for check in best.checks if check.part == "sleeve").note == "Sleeveless"
    assert not any(check.part == "shoulders" for check in best.checks)


def test_where_a_dress_is_cut_out_sheer_or_has_a_scarf():
    def read(name, description):
        return dress_cut.read({"name": name, "category": "Dresses", "description": description})

    duo = read("Sample House Duo Dress - Grey", "Merino wool Halter strap Plunging neckline Attached scarf on the side Open back Slim fit")
    assert values_at(duo, "cutouts", "scarf", "sheer") == [["back"], "side", None]
    gown = read("Sample Label Sela Layered Gown - Caramel", "Lyocell blend Adjustable straps on the front Cutouts on the shoulder Raw sleeve cuffs Sweetheart neck Flared hem Maxi fit")
    assert values_at(gown, "cutouts", "sleeves") == [["shoulders"], "long"]
    evening = read("Sample Atelier Women Long Dress - Black", "Printed nylon Semi sheer Raw sleeve cuffs and hem Loop accent on the back Slim fit")
    assert values_at(evening, "sheer", "sheer_kind", "sleeves") == ["all", "semi", "long"]
    assert read("Mesh Dress", "Sheer sleeves")["sheer"] == "sleeves"
    # A shelf bra lined with power mesh doesn't make a tennis dress see-through.
    assert read("Sample Label Women's Padel Dress - Green", "Light compressive stretch Interior shelf bra lined with power mesh")["sheer"] is None
    assert [cut("odile")["scarf"]] == ["neck"]
    assert "cut-outs" not in cut("lio")["details"]
    assert cut("lio")["cutouts"] == ["back"]
    lala = read("Sample Works Lala Jersey Mini Dress - Pink",
                  "Rayon blend Mock neckline Asymmetrical cutout on the front and side Snap button closure on the back Keyhole cutout on the back Draped construction Relaxed fit")
    assert lala["cutouts"] == ["front_side", "back_keyhole"]
    assert read("Cut-Out Dress", "Cutouts on the front and back Slim fit")["cutouts"] == ["front", "back"]
    assert read("Keyhole Dress", "Keyhole neckline Slim fit")["cutouts"] == ["front"]
    # Off one shoulder, though its name says off shoulder.
    jersey = read("Sample Goods Fine Jersey Off Shoulder Dress - Charcoal",
                "Tencel lyocell Semi sheer Asymmetrical off-shoulder neckline Asymmetrical flared hem Paneled construction Relaxed fit")
    assert values_at(jersey, "sleeves", "sheer", "sheer_kind") == ["one_shoulder", "all", "semi"]
    assert read("Off Shoulder Dress", "Off-shoulder neckline Slim fit")["sleeves"] == "strapless"
    # Off the shoulders over sleeves: long sleeves under a wide straight neckline.
    kaia = read("Sample Label Kaia Dress - Moss", "Cashmere Ribbed neck, sleeve cuffs, and hem Foldover off-shoulder neckline Slim fit")
    assert values_at(kaia, "sleeves", "neckline") == ["long", "straight"]


def test_a_cowl_neck_a_wraps_tie_and_a_pleated_skirt_are_read():
    def read(description):
        return dress_cut.read({"name": "Midi Dress", "description": description})

    assert read("Satin slip with a cowl neckline")["neckline"] == "cowl"
    assert read("A wrap dress in crepe")["belt"] == "tie"
    assert read("Pleated midi skirt")["pleats"]
    assert not read("Straight midi skirt")["pleats"]


def test_a_tiered_skirt_is_read_with_how_many_tiers_it_has():
    def read(description):
        return dress_cut.read({"name": "Midi Dress", "description": description})

    assert values_at(read("Tiered midi dress"), "flounce", "tiers") == [True, 3]
    assert read("A two-tier skirt")["tiers"] == 2
    assert read("4-tiered maxi")["tiers"] == 4
    assert read("Ruffled hem")["tiers"] is None


def test_a_flounce_at_the_hem_a_side_slit_and_a_belt_are_drawn_so_they_arent_listed_as_left_out():
    def read(description):
        return dress_cut.read({"name": "Midi Dress", "category": "Dresses", "description": description})

    assert [cut("tessa")["belt"], "belt" in cut("tessa")["details"]] == ["buckle", False]
    assert values_at(read("Ruffled hem Slim fit"), "flounce", "details") == [True, []]
    # Ruffles elsewhere stay a note.
    assert read("Ruffle trim on the neck Ruffled hem")["details"] == ["ruffles"]
    assert read("Side slits Relaxed fit")["slit"] == "sides"
    assert read("Thigh-high slit Relaxed fit")["slit"] == "side"
    # A slit at the back isn't drawn, and belt loops aren't a belt.
    assert values_at(read("Slit at the back Belt loops at the waist"), "slit", "belt", "details") == [None, None, ["slit"]]
    assert values_at(read("Self-tie belt at the waist"), "belt", "details") == ["tie", []]
    # A tie that closes it, or a sash draped to the hip, isn't a belt.
    assert values_at(read("Cowl neckline Self-tie closure on the back"), "belt", "details") == [None, ["tie"]]
    assert values_at(read("Draped sash self-tie closure on hip"), "belt", "details") == [None, ["tie", "draping"]]
