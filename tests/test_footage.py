import httpx
import pytest

from shortstock.footage import FootageError, fill_shots


def pexels(calls):
    def handler(request):
        calls.append(str(request.url))
        if request.url.path.startswith("/videos/videos/"):
            vid = int(request.url.path.rsplit("/", 1)[1])
            return httpx.Response(
                200,
                json={
                    "id": vid,
                    "duration": 9,
                    "image": "https://img/pinned.jpg",
                    "user": {"name": "Pin"},
                    "url": "https://pexels.com/v/pinned",
                    "video_files": [{"link": "https://cdn/pinned.mp4", "width": 1080, "height": 1920}],
                },
            )
        if request.url.host == "api.pexels.com":
            query = request.url.params["query"]
            videos = (
                []
                if query == "nothing here"
                else [
                    {
                        "id": 100 + i + (50 if "city" in query else 0),
                        "duration": 2 + i,
                        "url": f"https://pexels.com/v/{i}",
                        "user": {"name": "Ann"},
                        "video_files": [
                            {"link": f"https://cdn/{query}/{i}-720.mp4", "width": 720, "height": 1280},
                            {"link": f"https://cdn/{query}/{i}-1080.mp4", "width": 1080, "height": 1920},
                        ],
                    }
                    for i in range(3)
                ]
            )
            return httpx.Response(200, json={"videos": videos})
        return httpx.Response(200, content=b"video-bytes")

    return httpx.MockTransport(handler)


def shots(*queries):
    return [{"index": i, "query": q, "duration": 3.0} for i, q in enumerate(queries)]


def test_unique_clips_and_stock_bank(shortstock_home):
    calls = []
    result = fill_shots(shots("forest", "forest", "nothing here"), "key", "9:16", 1080, pexels(calls))
    ids = [s["clip_id"] for s in result["shots"]]
    assert len(set(ids)) == 3
    assert result["shots"][2]["matched_query"] != "nothing here"  # fell back to a generic query
    assert any("-1080.mp4" in c for c in calls)
    assert (shortstock_home / "stock" / "pexels" / f"{ids[0]}.mp4").exists()
    assert {c["author"] for c in result["credits"]} == {"Ann"}

    calls.clear()
    fill_shots(shots("forest"), "key", "9:16", 1080, pexels(calls))
    assert not any("cdn" in c for c in calls)  # reused from the stock bank


def test_requires_key():
    with pytest.raises(FootageError, match="Pexels"):
        fill_shots(shots("x"), "", "9:16", 1080)


def test_pinned_clip_is_used_and_not_reused():
    calls = []
    plan = shots("forest", "forest")
    plan[0]["pin"] = 100
    result = fill_shots(plan, "key", "9:16", 1080, pexels(calls))
    assert result["shots"][0]["clip_id"] == 100
    assert result["shots"][0]["thumb"] == "https://img/pinned.jpg"
    assert result["shots"][1]["clip_id"] != 100


def test_new_footage_avoids_clips_from_the_last_cut(shortstock_home):
    first = fill_shots(shots("forest"), "key", "9:16", 1080, pexels([]))["shots"][0]["clip_id"]
    again = fill_shots(shots("forest"), "key", "9:16", 1080, pexels([]), avoid={first})
    assert again["shots"][0]["clip_id"] != first
    # When every result has been used, an earlier clip is still better than failing.
    every = fill_shots(shots("forest"), "key", "9:16", 1080, pexels([]), avoid={100, 101, 102})
    assert every["shots"][0]["clip_id"] in {100, 101, 102}
