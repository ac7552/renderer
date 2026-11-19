import re

import pytest

from renderer import size_charts


def test_every_chart_has_every_measurement_for_every_size():
    for chart in size_charts.all_charts():
        assert chart.sizes, f"{chart.key} has no sizes"
        needed = ["chest", "length"] if chart.garment == "top" else size_charts.MEASUREMENTS
        for size in chart.sizes:
            for m in needed:
                assert isinstance(size.get(m), (int, float)) and size[m] > 0, f"{chart.key} {size['name']} is missing {m}"


def test_chest_grows_with_the_size_number():
    chart = size_charts.find("sample_suit_jacket")
    regulars = [size for size in chart.sizes if size["name"].endswith("R")]
    assert sorted(regulars, key=lambda s: int(re.match(r"\d+", s["name"]).group(0))) == sorted(regulars, key=lambda s: s["chest"])


def test_rejects_chart_names_that_arent_plain_words():
    with pytest.raises(size_charts.NotFound):
        size_charts.find("../secrets")


def test_a_built_in_chart_is_shaped_as_an_imported_garment():
    garment = size_charts.find("sample_dress").as_garment()
    assert [garment["garment"], garment["style"], garment["color_name"]] == ["top", "dress", "Wine"]
    assert garment["chart"]["kind"] == "garment"
