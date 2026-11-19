"""The fitting room page's measurement rows, made from the same table the API checks against (fit.MEASUREMENTS and
shoes.MEASUREMENTS), so the form's ranges and the server's never disagree."""

from __future__ import annotations

import html

from . import fit, shoes

# The measurements in the order the page asks for them, in short, plain words: what each is called and how to take
# it. (fit.MEASUREMENTS keeps the API's own wording.)
PLAIN = [
    ("height", "Height", "Stand up straight, with no shoes on."),
    ("chest", "Chest", "Wrap the tape around your chest, under your arms."),
    ("waist", "Waist", "Wrap the tape around your middle, at your belly button."),
    ("shoulders", "Shoulders", "Measure across your back, from one shoulder bone to the other."),
    ("arm", "Arm", "Measure from your shoulder bone down to your wrist."),
    ("hips", "Hips", "Wrap the tape around the widest part of your bottom."),
    ("inseam", "Leg", "Measure from your crotch down to the floor, on the inside of your leg."),
    ("foot", "Foot", "Stand on paper with your heel against a wall; mark your longest toe and measure to the wall."),
    ("ball", "Foot width", "Standing, measure across the widest part of your foot, where the toes join it."),
]


def number(value) -> str:
    return str(int(value)) if float(value).is_integer() else str(value)


def body_parts():
    """The body's measurements, then the feet's (for shoes)."""
    out = []
    for key, label, tip in PLAIN:
        found = next((m for m in fit.MEASUREMENTS if m["key"] == key), None)
        if found is None:
            found = {**next(m for m in shoes.MEASUREMENTS if m["key"] == key), "optional": True, "shoes": True}
        out.append({**found, "label": label, "tip": tip})
    return out


def body_parts_html() -> str:
    rows = []
    for part in body_parts():
        key, optional, for_shoes = part["key"], part.get("optional", False), part.get("shoes", False)
        target = ' data-fitting-room-target="shoesOnly"' if for_shoes else ' data-fitting-room-target="pantsOnly"' if optional else ""
        dress = ' data-also-dress="true"' if key == "hips" else ""
        note = ""
        if optional:
            note = f' <small>{"for shoes" if for_shoes else "for pants and dresses" if key == "hips" else "for pants"}</small>'
        if key == "height":
            box = ('<span class="height-feet" data-fitting-room-target="heightImperial">'
                   '<span class="field-input"><input id="body-height" type="number" inputmode="numeric" min="0" max="8" step="1" autocomplete="off" '
                   'aria-label="Height, feet" data-fitting-room-target="heightFeet" data-action="input->fitting-room#update"><span class="field-unit">ft</span></span>'
                   '<span class="field-input"><input type="number" inputmode="decimal" min="0" max="11.5" step="0.5" autocomplete="off" '
                   'aria-label="Height, inches" data-fitting-room-target="heightInches" data-action="input->fitting-room#update"><span class="field-unit">in</span></span>'
                   '</span>'
                   '<span class="field-input" data-fitting-room-target="heightMetric" hidden>'
                   '<input type="number" inputmode="decimal" min="0" step="0.5" autocomplete="off" aria-label="Height, cm" '
                   'data-part="height" data-fitting-room-target="input" data-action="input->fitting-room#update"><span class="field-unit">cm</span></span>')
        else:
            box = (f'<span class="field-input"><input id="body-{key}" type="number" inputmode="decimal" min="0" step="0.25" autocomplete="off" '
                   f'data-part="{key}"{" data-optional" if optional else ""} data-fitting-room-target="input" data-action="input->fitting-room#update">'
                   '<span class="field-unit" data-fitting-room-target="unitLabel">in</span></span>')
        usual = part["usual"]
        slider = (f'<input type="range" class="slider" min="{number(usual.min)}" max="{number(usual.max)}" step="0.5" autocomplete="off" '
                  f'aria-label="{html.escape(part["label"])} slider" data-min-cm="{number(usual.min)}" data-max-cm="{number(usual.max)}" '
                  f'data-slider-for="{key}" data-fitting-room-target="slider" data-action="input->fitting-room#slide">')
        rows.append(f'                <div class="field{" field--optional" if optional else ""}"{target}{dress}>\n'
                    f'                  <label class="field-label" for="body-{key}">{html.escape(part["label"])}{note}</label>\n'
                    f'                  {box}\n                  {slider}\n'
                    f'                  <span class="field-help">{html.escape(part["tip"])}</span>\n                </div>')
    return "\n".join(rows)
