import pytest

from renderer import shoes as S


def test_size_names_parse_on_their_scale_with_widths():
    assert S.parse_size("9.5") == {"number": 9.5, "scale": "us_m", "width": None}
    assert S.parse_size("EU 42.5", "us_m") == {"number": 42.5, "scale": "eu", "width": None}
    assert S.parse_size("UK 8") == {"number": 8.0, "scale": "uk", "width": None}
    assert S.parse_size("27 cm") == {"number": 27.0, "scale": "cm", "width": None}
    assert S.parse_size("9 Wide")["width"] == "2E"
    assert S.parse_size("US 10 (2E)")["width"] == "2E"
    assert S.parse_size("9 Narrow")["width"] == "B"
    assert S.parse_size("W 8")["width"] is None
    assert S.parse_size("W 8", "us_w")["number"] == 8.0
    assert S.parse_size("One size") is None


def test_the_scales_a_us_mens_9_a_uk_8_and_an_eu_42_are_all_a_27_cm_last():
    assert S.last_length(S.parse_size("9")) == pytest.approx(27.0, abs=0.01)
    assert S.last_length(S.parse_size("UK 8")) == pytest.approx(27.0, abs=0.01)
    assert S.last_length(S.parse_size("EU 42")) == pytest.approx(27.0, abs=0.01)
    assert S.last_length(S.parse_size("9", "us_w")) == pytest.approx(25.5, abs=0.01)
    assert S.last_length(S.parse_size("10")) == pytest.approx(27.0 + 2.54 / 3, abs=0.01)
    # Brands: Nike runs short, Converse long.
    assert S.last_length(S.parse_size("9"), "Nike Air Force 1") == pytest.approx(26.6, abs=0.01)
    assert S.last_length(S.parse_size("9"), "Converse") == pytest.approx(27.5, abs=0.01)


def test_the_charts_scale_from_its_names():
    assert S.scale_for(["7", "7.5", "8", "8.5", "9", "10", "11", "12"]) == "us_m"
    assert S.scale_for(["6", "7", "8", "9"], women=True) == "us_w"
    assert S.scale_for(["W 6", "W 7", "W 8"]) == "us_w"
    assert S.scale_for(["40", "41", "42", "43", "44"]) == "eu"
    assert S.scale_for(["EU 42", "EU 43"]) == "eu"
    assert S.scale_for(["25.5", "26", "26.5", "27"]) == "cm"


def test_a_26_5_cm_foot_in_a_sneaker_is_a_us_10():
    sizes = [{"name": name} for name in ["8", "8.5", "9", "9.5", "10", "10.5", "11", "11.5"]]
    results = S.rank({"foot": 26.5, "ball": 9.8}, sizes, brand="New Balance", style="sneaker", fabric="mesh")
    assert results[0].size == "10"
    by = {result.size: result for result in results}

    def part(result, name):
        return next(check for check in result.checks if check.part == name)

    assert part(by["9"], "toe").status == "tight"
    assert part(by["11.5"], "toe").status == "loose"
    assert part(by["10"], "width").status == "good"


def test_a_loafer_holds_the_foot_less_room_a_wide_foot_wants_a_2e():
    sizes = [{"name": name} for name in ["9", "9.5", "10", "10.5"]]
    assert S.rank({"foot": 26.5}, sizes, style="loafer", fabric="leather")[0].size == "9.5"
    wide = S.rank({"foot": 26.5, "ball": 10.8}, [{"name": "10"}, {"name": "10 Wide"}], style="sneaker", fabric="leather")
    assert wide[0].size == "10 Wide"
    assert next(check for check in wide[-1].checks if check.part == "width").status == "tight"


def test_warnings_for_a_foot_outside_the_usual_range():
    assert S.warnings({"foot": 26.5, "ball": 9.8}) == []
    assert len(S.warnings({"foot": 34, "ball": 9.8})) == 1
