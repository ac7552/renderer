import re

import pytest

from renderer import fit, size_charts
from renderer.util import rnd

# A made-up 40R build: 40 in chest, 34 in waist, 5 ft 10 in.
BODY = {"chest": 101.6, "waist": 86.4, "shoulders": 45.5, "arm": 65.5, "height": 178}
MAN = {**BODY, "hips": 101, "inseam": 81}
WOMAN = {"chest": 91.5, "waist": 74, "shoulders": 39.5, "arm": 58, "height": 165, "hips": 99, "inseam": 76}


@pytest.fixture
def sizes():
    return size_charts.find("sample_suit_jacket").sizes


def named(sizes, name):
    return next(size for size in sizes if size["name"] == name)


def part(result, name):
    return next(check for check in result.checks if check.part == name)


def ranked_as(results, name):
    return next(result for result in results if result.size == name)


def letters(names, rows, keys):
    return [{"name": name, **dict(zip(keys, row))} for name, row in zip(names, rows)]


def inches(*values):
    return [rnd(value * 2.54) for value in values]


def test_a_40r_body_gets_40r_in_a_regular_cut_with_nothing_to_fix(sizes):
    best = fit.rank(BODY, sizes, "regular")[0]
    assert best.size == "40R"
    assert best.verdict() == "fits"
    assert best.penalty == 0


def test_longer_arms_are_a_sleeve_alteration_not_a_different_size(sizes):
    result = fit.check_size({**BODY, "arm": 68.5}, named(sizes, "40R"))
    sleeve = part(result, "sleeve")
    assert sleeve.status == "short"
    assert sleeve.fix.action == "lengthen_sleeves"
    assert result.verdict() == "alter"


def test_shoulders_that_are_too_narrow_cant_be_fixed(sizes):
    result = fit.check_size(BODY, named(sizes, "36R"))
    shoulders = part(result, "shoulders")
    assert shoulders.status == "tight"
    assert shoulders.fix is None
    assert result.verdict() == "compromise"


def test_a_slim_cut_never_picks_a_bigger_size_than_regular(sizes):
    assert int(re.match(r"\d+", fit.rank(BODY, sizes, "slim")[0].size).group(0)) <= 40


def test_a_waist_thats_too_loose_is_taken_in_up_to_a_limit(sizes):
    roomy = fit.check_size({**BODY, "waist": 81}, named(sizes, "40R"))
    assert part(roomy, "waist").fix.action == "take_in_waist"

    far_too_roomy = fit.check_size({**BODY, "waist": 70}, named(sizes, "40R"))
    assert part(far_too_roomy, "waist").fix is None


def test_a_coat_gets_room_for_a_jacket_underneath_and_its_length_is_described_not_judged():
    coat = {"name": "L", "chest": 101.6 + 18, "waist": None, "shoulders": 46, "sleeve": 64, "length": 95}
    result = fit.check_size(BODY, coat, "regular", "coat")

    assert part(result, "chest").status == "good"
    length = part(result, "length")
    assert length.status == "good"
    assert length.note == "Ends just above the knee"

    as_jacket = fit.check_size(BODY, coat, "regular", "jacket")
    assert part(as_jacket, "chest").status == "loose"


def test_a_top_made_big_on_purpose_with_dropped_shoulders_is_judged_as_its_meant_to_be_worn():
    # A boxy crewneck's chart (cm): every size about 47 cm bigger round the chest than its usual body.
    rows = [["XS", 135.3, 69.2, 54.0, 62.2], ["S", 140.3, 70.5, 54.3, 63.5], ["M", 145.4, 71.8, 54.6, 64.8],
            ["L", 150.5, 73.0, 54.9, 66.0], ["XL", 158.1, 74.9, 55.2, 68.0]]
    sizes = [{"name": name, "chest": chest, "waist": None, "shoulders": shoulders, "sleeve": sleeve, "length": length}
             for name, chest, shoulders, sleeve, length in rows]
    assert fit.design(sizes)["dropped"]

    best = fit.rank(BODY, sizes, "regular", "top")[0]
    assert best.size == "M"
    assert [check.status for check in best.checks if check.part in ("shoulders", "chest")] == ["good", "good"]
    assert fit.rank(BODY, sizes, "slim", "top")[0].size == "S"


def test_a_dress_sits_closer_than_a_t_shirt_and_its_length_is_where_it_ends():
    woman = {"chest": 91.5, "waist": 74, "shoulders": 39.5, "arm": 58, "height": 165}
    best = fit.rank(woman, size_charts.find("sample_dress").sizes, "regular", "top", style="dress")[0]
    assert best.size == "M"
    assert "knee" in part(best, "length").note


def test_a_baby_tee_is_made_the_size_of_the_body_short_and_its_size_is_picked_so():
    body = {"chest": 91.5, "waist": 74, "shoulders": 39.5, "arm": 58, "height": 165}
    sizes = [{"name": name, "chest": chest, "waist": None, "shoulders": shoulders, "sleeve": 12, "length": length}
             for name, chest, shoulders, length in [["S", 85, 35.5, 53], ["M", 90, 37, 54], ["L", 95, 38.5, 55.5], ["XL", 100, 40, 57]]]

    assert fit.rank(body, sizes, "regular", "top", style="tee", details={"women": True})[0].size == "L"
    snug = fit.rank(body, sizes, "regular", "top", style="tee", details={"women": True, "snug": True})
    assert snug[0].size == "M"
    assert "baby tee" in part(snug[0], "length").note


def test_a_fitted_knit_hoodie_stretches_on_its_picked_a_little_smaller_than_the_body():
    body = {"chest": 91.5, "waist": 74, "shoulders": 39.5, "arm": 58, "height": 165}
    rows = [["XS", 76.2, 35.56, 63.82, 48.9], ["S", 81.28, 36.83, 64.77, 50.8], ["M", 86.36, 38.1, 65.72, 52.71],
            ["L", 91.44, 39.37, 66.68, 54.61], ["XL", 99.06, 41.28, 67.95, 56.52], ["XXL", 106.68, 43.18, 69.22, 58.42]]
    sizes = [{"name": name, "chest": chest, "waist": None, "shoulders": shoulders, "sleeve": sleeve, "length": length}
             for name, chest, shoulders, sleeve, length in rows]
    knit = {"women": True, "fit": "fitted", "stretch": True}

    # Read as a jacket, it wanted a jacket's room: XL. As an ordinary women's top it still wants some: XL.
    assert fit.rank(body, sizes, "regular", "jacket")[0].size == "XL"
    assert fit.rank(body, sizes, "regular", "top", style="hoodie", details={"women": True})[0].size == "XL"
    ranked = fit.rank(body, sizes, "regular", "top", style="hoodie", details=knit)
    assert ranked[0].size in ("S", "M")
    best = ranked[0]
    chest = part(best, "chest")
    assert chest.status == "good"
    assert chest.ease < 0
    assert "stretches" in chest.note
    # Its shoulder seam sits a little inside the shoulder bone; a shrunken knit ends at the waist.
    assert part(best, "shoulders").status == "good"
    assert part(best, "length").status == "good"
    assert "waist" in part(best, "length").note
    # Slim and classic move at most one size either way; none of them picks XL.
    assert fit.rank(body, sizes, "slim", "top", style="hoodie", details=knit)[0].size in ("S", "M")
    assert fit.rank(body, sizes, "classic", "top", style="hoodie", details=knit)[0].size in ("M", "L")
    # Much smaller than the body is too tight, and a size with a jacket's room is loose.
    assert part(ranked_as(ranked, "XS"), "chest").status == "tight"
    assert part(ranked_as(ranked, "XL"), "chest").status == "loose"
    # A fitted top in a cloth that doesn't stretch is judged as any other top.
    assert fit.rank(body, sizes, "regular", "top", style="hoodie", details={"women": True, "fit": "fitted", "stretch": False})[0].size == "XL"


def test_a_tee_whose_photo_shows_dropped_shoulders_is_meant_to_be_wide_there_and_boxy():
    sizes = [{"name": "S", "chest": 110.5, "waist": None, "shoulders": 50.8, "sleeve": 19.4, "length": 68.6}]

    plain = fit.rank(BODY, sizes, "regular", "top", style="tee")[0]
    assert [plain.checks[0].status, plain.checks[4].status] == ["loose", "short"]
    boxy = fit.rank(BODY, sizes, "regular", "top", style="tee", details={"dropped": True})[0]
    assert [boxy.checks[0].status, boxy.checks[4].status] == ["good", "good"]


def test_joggers_elastic_waist_stretches_onto_the_body_and_a_tailor_cant_let_it_out():
    sizes = [{"name": "L", "waist": 86, "seat": 112, "thigh": 67, "inseam": 81, "leg_opening": 26},
             {"name": "XS", "waist": 71, "seat": 97, "thigh": 58, "inseam": 81, "leg_opening": 26}]
    body = {**BODY, "waist": 87.6}

    snug = part(fit.check_trousers(body, sizes[0], style="joggers"), "waist")
    assert snug.status == "good"
    assert re.search("elastic", snug.note, re.I)
    small = part(fit.check_trousers(body, sizes[1], style="joggers"), "waist")
    assert small.status == "tight"
    assert small.fix is None
    # Trousers with no elastic are let out by a tailor.
    assert part(fit.check_trousers(body, sizes[0]), "waist").fix.action == "let_out_waist"


def test_pull_on_trousers_stretch_onto_the_body_as_joggers_do():
    size = {"name": "M", "waist": 81.3, "seat": 122.6, "inseam": 73.7, "leg_opening": 45.7}
    waist = part(fit.check_trousers({**BODY, "waist": 86.4}, size, details={"elastic": True}), "waist")
    assert waist.status == "good"
    assert re.search("elastic", waist.note, re.I)


def test_a_skirt_and_shorts_say_where_they_end():
    body = {**BODY, "hips": 100, "inseam": 81}
    skirt = part(fit.check_trousers(body, {"name": "M", "waist": 72, "seat": 98, "length": 96}, style="skirt"), "length")
    assert skirt.note == "Ends near the ankle"
    shorts = part(fit.check_trousers(body, {"name": "M", "waist": 86, "seat": 108, "inseam": 18}, style="shorts"), "inseam")
    assert "above the knee" in shorts.note


def test_an_elastic_waist_stretches_about_8_percent_not_15_cm():
    # A drawstring pant's chart in inches: XS waist 28 and seat 44.3, 2 in a size.
    sizes = letters(["XS", "S", "M", "L", "XL", "XXL"], [[*inches(28 + 2 * i, 44.27 + 2 * i), 73.4, 45.72] for i in range(6)],
                    ["waist", "seat", "inseam", "leg_opening"])
    ranked = fit.rank(MAN, sizes, "regular", "trousers", style="trousers", details={"elastic": True})

    assert ranked[0].size == "M"
    assert part(ranked[0], "waist").status == "good"
    # The XS (15 cm smaller than the waist) and the S (10 cm) won't stretch that far, and no tailor can let them out.
    for name in ("XS", "S"):
        waist = part(ranked_as(ranked, name), "waist")
        assert [waist.status, waist.fix] == ["tight", None]


def test_elastic_waist_shorts_and_track_pants_are_picked_by_the_waist_they_stretch_to():
    shorts = letters(["XS", "S", "M", "L", "XL", "XXL"], [[*inches(28 + 2 * i, 40.5 + 2 * i), 12] for i in range(6)], ["waist", "seat", "inseam"])
    assert fit.rank(MAN, shorts, "regular", "trousers", style="shorts", details={"elastic": True})[0].size == "M"
    track = letters(["XS", "S", "M", "L", "XL"], [[71.04 + 5 * i, 105.03 + 5 * i, 81, 30] for i in range(5)], ["waist", "seat", "inseam", "leg_opening"])
    # (The body's 86.4 cm waist is where an M's stretch ends and an L's begins.)
    best = fit.rank(MAN, track, "regular", "trousers", style="joggers")[0]
    assert best.size in ("M", "L")
    assert "stretches" in part(best, "waist").note


def test_pants_made_loose_on_purpose_are_picked_by_the_waist_their_roomy_seat_as_its_meant_to_be():
    rows = [[79, 118, 69.7], [83, 122, 70.6], [87, 126, 71.5], [91, 130, 72.4], [95, 134, 72.8], [99, 138, 73.2]]
    sizes = letters(["44", "46", "48", "50", "52", "54"], [[*row, 40] for row in rows], ["waist", "seat", "inseam", "leg_opening"])
    best = fit.rank(MAN, sizes, "regular", "trousers", style="trousers", details={"fit": "loose"})[0]
    assert best.size == "48"
    seat = part(best, "seat")
    assert seat.status == "good"
    assert "meant to be" in seat.note

    # French sizes 38 to 46 with no chart (see garment_import's european_waists): the 44 (a 34 in waist), not the smallest.
    loewe = letters(["38", "40", "42", "44", "46"], [[*inches(w), rnd(w * 2.54 + 28, 1), 81, 40] for w in range(28, 37, 2)],
                    ["waist", "seat", "inseam", "leg_opening"])
    assert fit.rank(MAN, loewe, "regular", "trousers", style="jeans", details={"fit": "loose"})[0].size == "44"

    # A pleated pant: elastic, its relaxed waist 77 cm in a 44 (4 cm a size), 124 over the hip.
    pleated = letters(["44", "46", "48", "50", "52"], [[77 + 4 * i, 124 + 4 * i, 72, 40] for i in range(5)], ["waist", "seat", "inseam", "leg_opening"])
    best = fit.rank(MAN, pleated, "regular", "trousers", style="trousers", details={"elastic": True, "fit": "loose"})[0]
    assert best.size == "48"
    assert "stretches" in part(best, "waist").note


def test_a_tailored_trouser_a_little_loose_over_the_seat_has_it_taken_in():
    size = {"name": "48", "waist": 87, "seat": 114, "inseam": 87.8, "leg_opening": 48}
    seat = part(fit.check_trousers(MAN, size), "seat")
    assert [seat.status, seat.fix.action] == ["loose", "take_in_seat"]


def test_trousers_sold_unhemmed_say_so_and_how_long_to_hem_them():
    sizes = letters(["44", "46", "48", "50", "52"], [[79 + 4 * i, 108 + 4 * i, 103.97, 47] for i in range(5)], ["waist", "seat", "inseam", "leg_opening"])
    best = fit.rank(MAN, sizes, "regular", "trousers", style="trousers", details={"hem": "unfinished"})[0]
    assert best.size == "48"
    length = part(best, "inseam")
    assert length.status == "good"
    assert length.note == "Comes unhemmed. Have it hemmed to about 78 cm."
    assert part(fit.check_trousers(MAN, sizes[2]), "inseam").status == "long"


def test_a_jacket_made_big_on_purpose_is_picked_by_the_room_its_made_with():
    rows = [[59.3, 53.9, 118.4, 63], [60.5, 55.1, 122.4, 63.4], [61.7, 56.3, 126.4, 63.8], [62.9, 57.5, 130.4, 64.2], [64.1, 58.7, 134.4, 64.6],
            [65.3, 59.9, 139.4, 65], [65.8, 61.1, 144.4, 65.4], [66.3, 62.3, 149.4, 65.8], [66.8, 63.5, 154.4, 66.2]]
    aviator = letters(["44", "46", "48", "50", "52", "54", "56", "58", "60"], rows, ["length", "shoulders", "chest", "sleeve"])
    assert fit.design(aviator)["roomy"]
    best = fit.rank(BODY, aviator, "regular", "jacket", style="bomber")[0]
    assert best.size == "50"
    assert [check.status for check in best.checks if check.part in ("shoulders", "chest", "length")] == ["good", "good", "good"]
    assert "top of your hips" in part(best, "length").note

    rows = [[27, 47, 35.13], [27.5, 49, 35.5], [28, 51, 35.88], [28.5, 53, 36.25], [29.25, 56, 36.75], [30, 59, 37.25]]
    dejan = letters(["XS", "S", "M", "L", "XL", "XXL"], [[*inches(l, c), rnd(s * 2.54 - 23)] for l, c, s in rows], ["length", "chest", "sleeve"])
    best = fit.rank(BODY, dejan, "regular", "jacket", style="zip")[0]
    assert best.size in ("M", "L")
    assert part(best, "chest").status == "good"


def test_a_womens_hoodie_made_big_on_purpose_is_picked_as_its_meant_to_be_worn_even_when_the_listing_says_fitted():
    elvina = letters(["XS", "S", "M", "L", "XL", "XXL"], [[*inches(41.5 + 2 * i), None, None, *inches(19 + 0.5 * i)] for i in range(6)],
                     ["chest", "shoulders", "sleeve", "length"])
    best = fit.rank(WOMAN, elvina, "regular", "top", style="hoodie", details={"women": True})[0]
    assert best.size == "M"
    assert [check.status for check in best.checks if check.part in ("chest", "length")] == ["good", "good"]

    toyo = letters(["XS", "S", "M", "L", "XL", "XXL"], [inches(43 + 2 * i, 19.78 + 0.5 * i, 19.74 + 0.5 * i) for i in range(6)], ["chest", "sleeve", "length"])
    ranked = fit.rank(WOMAN, toyo, "regular", "top", style="hoodie", details={"women": True, "fit": "fitted", "stretch": True})
    assert ranked[0].size in ("M", "L")
    assert part(ranked[0], "chest").status == "good"


def test_a_cropped_jacket_a_bomber_or_a_track_jacket_says_where_it_ends_instead_of_being_too_short():
    syd = {"name": "M", "chest": 101.66, "shoulders": 39.5, "sleeve": 56.5, "length": 54.57}
    length = part(fit.check_size(WOMAN, syd, "regular", "jacket", style="bomber", details={"women": True}), "length")
    assert [length.status, length.penalty] == ["good", 0]
    assert "ends at the top of your hips" in length.note

    keshi = {"name": "L", "chest": 100.39, "shoulders": 40.77, "sleeve": 56.5, "length": 49.49}
    assert part(fit.check_size(WOMAN, keshi, "regular", "jacket", style="tailored", details={"women": True}), "length").status == "short"
    cropped = fit.check_size(WOMAN, keshi, "regular", "jacket", style="tailored", details={"women": True, "cropped": True})
    assert "ends at your waist" in part(cropped, "length").note
    track = fit.check_size(WOMAN, keshi, "regular", "jacket", style="zip", details={"women": True, "ends": "waist"})
    assert part(track, "length").status == "good"


def test_measurements_outside_most_peoples_are_flagged_with_how_to_measure_them_again():
    assert fit.warnings(BODY) == []
    found = fit.warnings({**BODY, "chest": 150})
    assert [w["part"] for w in found] == ["chest"]
    assert found[0]["message"].startswith("Chest looks larger than most people's.")
