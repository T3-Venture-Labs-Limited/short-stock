import base64
import json

import httpx
import pytest

from shortstock import db
from shortstock.tts import ElevenLabs, Fish, TTSError, chunk_text, get_voice, words_from_characters


def test_words_from_characters():
    alignment = {
        "characters": list("Hi there"),
        "character_start_times_seconds": [0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7],
        "character_end_times_seconds": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8],
    }
    assert words_from_characters(alignment) == [
        {"word": "Hi", "start": 0, "end": 0.2},
        {"word": "there", "start": 0.3, "end": 0.8},
    ]


def test_elevenlabs_request_and_parse():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["key"] = request.headers["xi-api-key"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "audio_base64": base64.b64encode(b"mp3").decode(),
                "alignment": {
                    "characters": list("Go"),
                    "character_start_times_seconds": [0, 0.1],
                    "character_end_times_seconds": [0.1, 0.2],
                },
            },
        )

    speech = ElevenLabs(
        "k", "voice1", "eleven_multilingual_v2", 1.1, transport=httpx.MockTransport(handler)
    ).speak("Go")
    assert speech.audio == b"mp3" and speech.words == [{"word": "Go", "start": 0, "end": 0.2}]
    assert "/v1/text-to-speech/voice1/with-timestamps" in seen["url"] and seen["key"] == "k"
    assert seen["body"]["voice_settings"]["speed"] == 1.1


def test_fish_keeps_latest_alignment_per_chunk():
    def event(seq, offset, segs, audio=b""):
        return "data: " + json.dumps(
            {
                "audio_base64": base64.b64encode(audio).decode(),
                "chunk_seq": seq,
                "chunk_audio_offset_sec": offset,
                "alignment": {"segments": [{"text": t, "start": s, "end": e} for t, s, e in segs]},
            }
        )

    body = "\n\n".join(
        [
            event(0, 0.0, [("Hello", 0.0, 0.3)], b"a"),
            event(0, 0.0, [("Hello", 0.0, 0.3), ("world", 0.3, 0.6)], b"b"),  # repeated, fuller
            event(1, 0.6, [("again", 0.0, 0.4)], b"c"),
        ]
    )

    def handler(request):
        assert request.headers["model"] == "s2.1-pro"
        assert json.loads(request.content)["reference_id"] == "v"
        return httpx.Response(200, text=body)

    speech = Fish("k", "v", "s2.1-pro", transport=httpx.MockTransport(handler)).speak("Hello world again")
    assert speech.audio == b"abc"
    assert [w["word"] for w in speech.words] == ["Hello", "world", "again"]
    assert speech.words[2] == {"word": "again", "start": 0.6, "end": 1.0}


def test_errors_and_settings():
    with pytest.raises(TTSError, match="ElevenLabs API key"):
        get_voice("elevenlabs")
    db.set_setting("fish_api_key", "k")
    with pytest.raises(TTSError, match="Fish Audio voice"):
        get_voice("fish")
    db.set_setting("fish_voice_id", "abc")
    assert get_voice("fish").voice_id == "abc"
    with pytest.raises(TTSError, match="Unknown"):
        get_voice("nope")


def test_chunk_text_splits_long_scripts():
    text = " ".join(["This is a sentence."] * 400)
    chunks = chunk_text(text, limit=500)
    assert all(len(c) <= 500 for c in chunks)
    assert " ".join(chunks) == text


def test_provider_errors_read_as_sentences():
    from shortstock.tts import _error

    def response(status, body):
        return httpx.Response(status, json=body)

    fish = _error(
        "Fish Audio", response(402, {"status": 402, "message": "Insufficient API credit for this model."})
    )
    assert str(fish).startswith("Your Fish Audio account is out of credit.")
    assert "S2.1 Pro Free" in str(fish)
    eleven = _error(
        "ElevenLabs", response(401, {"detail": {"status": "invalid_api_key", "message": "Invalid"}})
    )
    assert "rejected the API key" in str(eleven)
    quota = _error(
        "ElevenLabs",
        response(
            400, {"detail": {"status": "quota_exceeded", "message": "This request exceeds your quota."}}
        ),
    )
    assert "out of credit" in str(quota)
    assert "rate limiting" in str(_error("Fish Audio", response(429, {})))
    assert (
        str(_error("ElevenLabs", response(422, {"detail": "Text too long"})))
        == "ElevenLabs said: Text too long"
    )
