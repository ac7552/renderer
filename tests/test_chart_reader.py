from renderer.garment_import import chart_reader


def read(rows, **options):
    return chart_reader.read(rows, **options)


def test_a_charts_sleeve_is_left_as_the_shop_gives_it_and_where_its_measured_from_isnt_guessed_at():
    chart = read([["Size", "Chest", "Shoulders", "Sleeve", "Length"], ["M", "54", "46", "63", "70"], ["L", "57", "48", "64", "72"]],
                 context="garment measurements in cm")

    assert chart.sleeve_from is None
    assert [size["sleeve"] for size in chart.sizes] == [63.0, 64.0]
    assert chart.as_json() == {"sizes": chart.sizes, "unit": "cm", "kind": "garment", "missing": ["waist"]}


def test_a_chart_names_the_columns_it_didnt_read_so_a_pasted_one_can_say_what_it_left_out():
    chart = read([["Size", "Chest", "Hem", "Rise", "Length"], ["M", "54", "52", "30", "70"], ["L", "57", "55", "31", "72"]],
                 context="garment measurements in cm")

    assert chart.unused == ["Hem", "Rise"]
    assert chart.as_json()["unused"] == ["Hem", "Rise"]


def test_a_sleeve_column_that_says_it_runs_from_the_centre_back_is_marked_so_whatever_its_length():
    for label in ["Sleeve (from center back)", "CB Sleeve", "Sleeve from CB", "Centre back sleeve", "Sleeve length (C.B. to cuff)", "Sleeve from nape"]:
        chart = read([["Size", "Chest", "Shoulders", label, "Length"], ["M", "54", "46", "44", "70"], ["L", "57", "48", "45", "72"]], context="cm")
        assert chart.sleeve_from == "centre_back", label
        assert chart.sizes[0]["sleeve"] == 44.0, f"{label}: the numbers are left for the import to convert"


def test_the_words_round_a_chart_can_say_its_sleeves_run_from_the_centre_back_but_a_centre_back_length_doesnt():
    rows = [["Size", "Chest", "Shoulders", "Sleeve", "Length"], ["M", "54", "46", "83", "70"], ["L", "57", "48", "84", "72"]]

    assert read(rows, context="Measurements in cm. Sleeves are measured from the centre back neck to the cuff.").sleeve_from == "centre_back"
    assert read(rows, context="cm; center back to cuff sleeve measurement").sleeve_from == "centre_back"
    assert read(rows, context="cm. Length is the centre back length, collar seam to hem.").sleeve_from is None
    assert read([["Size", "Chest", "Shoulders", "Sleeve"], ["M", "54", "46", "63"], ["L", "57", "48", "64"]], context="Centre back length not given. cm").sleeve_from is None


def test_numbers_are_read_as_shops_write_them():
    assert chart_reader.number("38") == 38.0
    assert chart_reader.number("38,5") == 38.5
    assert chart_reader.number("38 ½") == 38.5
    assert chart_reader.number("38 1/2") == 38.5
    assert chart_reader.number("38-40") == 39.0
    assert chart_reader.number("97cm") == 97.0
    assert chart_reader.number("—") is None
