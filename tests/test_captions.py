from shortstock.captions import STYLES, _ass_color, _ts, chunk_words, emphasis_index, write_ass


def test_chunks_respect_limits(words):
    style = STYLES["bold"]
    for chunk in chunk_words(words, style):
        assert len(chunk) <= style.max_words


def test_emphasis_picks_long_content_word():
    assert emphasis_index([{"word": w} for w in ["we", "built", "everything"]]) == 2
    assert emphasis_index([{"word": "it"}, {"word": "was"}]) is None


def test_write_ass_with_overrides(tmp_path, words):
    path = write_ass(words, tmp_path / "c.ass", 1920, 1080, "bold", position=0.1)
    text = path.read_text()
    assert "PlayResX: 1920" in text and ",108,1" in text  # MarginV = 10% of 1080
    assert 0 < sum(line.startswith("Dialogue:") for line in text.splitlines()) <= len(words)


def test_ass_helpers():
    assert _ass_color("FFD400") == "&H0000D4FF&"
    assert _ts(3661.257) == "1:01:01.26"
