from shortstock.plan import align_sentences, build_shots, keywords, match_ratio, write_queries
from shortstock.script import parse_script


def test_sentences_cover_the_timeline_without_gaps(script, words):
    sentences = align_sentences(parse_script(script)["sentences"], words)
    assert sentences[0]["start"] == 0.0
    for a, b in zip(sentences, sentences[1:], strict=False):
        assert a["end"] == b["start"]
        assert a["end"] > a["start"]
    # The cut falls inside the pause after "brain."
    assert 2.8 < sentences[0]["end"] < 3.6


def test_match_ratio(script, words):
    text = parse_script(script)["text"]
    assert match_ratio(text, words) == 1.0
    assert match_ratio(text, words[:10]) < 0.5


def test_queries_prefer_hints_then_ai_then_keywords(script, words):
    sentences = align_sentences(parse_script(script)["sentences"], words)

    class FakeLLM:
        model = "fake"

        def complete_json(self, system, user, schema, name):
            assert "0." not in user  # the hinted sentence is not sent
            return {"queries": [{"index": 1, "query": "blood flow animation"}]}

    result = write_queries(sentences, FakeLLM())
    assert [s["query_source"] for s in result] == ["hint", "ai", "keywords"]
    assert result[0]["query"] == "person walking in park"
    assert result[2]["query"] == " ".join(keywords(sentences[2]["text"]))


def test_ai_failure_falls_back_to_keywords(script, words):
    sentences = align_sentences(parse_script(script)["sentences"], words)

    class Broken:
        model = "x"

        def complete_json(self, *a):
            raise RuntimeError("down")

    assert {s["query_source"] for s in write_queries(sentences, Broken())} == {"hint", "keywords"}


def test_shots_respect_max_length_and_cover_total(script, words):
    sentences = write_queries(align_sentences(parse_script(script)["sentences"], words))
    total = words[-1]["end"] + 0.3
    shots = build_shots(sentences, max_shot=2.0, total=total)
    assert shots[0]["start"] == 0.0 and abs(shots[-1]["end"] - total) < 1e-6
    assert all(s["duration"] <= 2.0 + 1e-6 for s in shots)
    assert all(a["end"] == b["start"] for a, b in zip(shots, shots[1:], strict=False))
