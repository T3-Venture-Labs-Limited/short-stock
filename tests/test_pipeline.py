import os

import pytest

from shortstock import db, pipeline


def test_failed_run_resumes_from_failed_stage(monkeypatch):
    calls = []
    fail = {"footage": True}

    def make(name):
        def fn(ctx):
            calls.append(name)
            if fail.get(name):
                raise RuntimeError("kaboom")
            return {"stage": name}

        return fn

    names = ["voice", "plan", "footage", "render"]
    monkeypatch.setattr(pipeline, "STAGES", [(n, n, make(n)) for n in names])
    monkeypatch.setattr(pipeline, "STAGE_NAMES", names)
    run = db.create_run("Hello there.", pipeline.VideoOptions().model_dump(), status="running")

    pipeline.execute(run)
    assert db.get_run(run["id"])["error"] == "footage: kaboom"
    assert calls == ["voice", "plan", "footage"]

    fail["footage"] = False
    pipeline.retry(run["id"])
    pipeline.execute(db.claim_next_run())
    assert calls[3:] == ["footage", "render"]  # the voiceover is not paid for twice
    assert db.get_run(run["id"])["status"] == "completed"


def test_default_title():
    assert pipeline.default_title("# My video\n\nHello world.") == "My video"
    assert pipeline.default_title("Hello world. Second.") == "Hello world."


def test_options_validation():
    with pytest.raises(ValueError):
        pipeline.VideoOptions(speed=2)
    assert pipeline.VideoOptions().aspect_ratio == "9:16"


def test_requeue_only_touches_runs_of_dead_processes():
    mine = db.create_run("a.", {}, status="running")
    orphan = db.create_run("b.", {}, status="running")
    db.update_run(orphan["id"], claimed_by=2**22 + 12345)
    db.update_run(mine["id"], claimed_by=os.getppid())
    db.requeue_interrupted_runs()
    assert db.get_run(mine["id"])["status"] == "running"
    assert db.get_run(orphan["id"])["status"] == "queued"
