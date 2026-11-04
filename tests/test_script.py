import pytest

from shortstock.script import parse_script


def test_hints_headings_and_markdown(script):
    parsed = parse_script(script)
    assert parsed["title"] == "Walking"
    assert parsed["text"].startswith("A short walk helps your brain.")
    assert "visual" not in parsed["text"] and "#" not in parsed["text"]
    hints = [s["hint"] for s in parsed["sentences"]]
    assert hints == ["person walking in park", None, None]


def test_inline_hint_and_stage_directions():
    parsed = parse_script("**Bold** opener [visual: ocean waves]. Then a pause (yes) [beat] here.")
    first = parsed["sentences"][0]
    assert (first["text"], first["hint"], first["pin"]) == ("Bold opener.", "ocean waves", None)
    assert parsed["sentences"][1]["text"] == "Then a pause (yes) here."


def test_empty_script_rejected():
    with pytest.raises(ValueError):
        parse_script("# Only a heading\n\n[visual: x]")


def test_offsets_and_clip_pins():
    script = (
        "# T\n\n[visual: ocean waves]\nFirst one. Second [clip: pexels 123] two!\n- Third [visual: x y] here."
    )
    sentences = parse_script(script)["sentences"]
    assert [s["text"] for s in sentences] == ["First one.", "Second two!", "Third here."]
    assert [s["pin"] for s in sentences] == [None, 123, None]
    first, second, third = sentences
    assert script[first["start"] : first["end"]] == "First one."
    assert script[slice(*first["hint_span"])] == "[visual: ocean waves]"
    assert script[slice(*second["pin_span"])] == "[clip: pexels 123]"
    assert script[third["start"] : third["end"]] == "Third [visual: x y] here."
