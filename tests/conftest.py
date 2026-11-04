import pytest

KEY_VARS = (
    "OPENROUTER_API_KEY",
    "PEXELS_API_KEY",
    "BUFFER_API_KEY",
    "ELEVENLABS_API_KEY",
    "ELEVENLABS_VOICE_ID",
    "FISH_API_KEY",
    "FISH_VOICE_ID",
    "SHORTSTOCK_TTS_PROVIDER",
)


@pytest.fixture(autouse=True)
def shortstock_home(tmp_path, monkeypatch):
    """Every test gets an empty SHORTSTOCK_HOME and no keys from the developer's environment."""
    monkeypatch.setenv("SHORTSTOCK_HOME", str(tmp_path / "home"))
    for var in KEY_VARS:
        monkeypatch.delenv(var, raising=False)
    from shortstock import footage

    footage._cache.clear()
    return tmp_path / "home"


SCRIPT = """# Walking

[visual: person walking in park]
A short walk helps your brain. It sends fresh blood to your memory.

And it lowers your blood sugar after dinner.
"""


@pytest.fixture
def script():
    return SCRIPT


@pytest.fixture
def words():
    """Spoken words for SCRIPT, two words per second, a pause between sentences."""
    text = (
        "A short walk helps your brain. It sends fresh blood to your memory. "
        "And it lowers your blood sugar after dinner."
    )
    out, t = [], 0.0
    for token in text.split():
        out.append({"word": token, "start": round(t, 3), "end": round(t + 0.4, 3)})
        t += 0.5 + (0.4 if token.endswith(".") else 0)
    return out
