"""Deep comparison YouTube must be allowed to finish, and a timeout is not a stale binary.

A deep search issues several yt-dlp calls per entity, and comparison fan-out
shares one process-wide yt-dlp gate. The suite injects a virtual clock so the
gate's queue is real while the wall clock is not: no network and no long sleeps.
"""

import json
import threading
import time

from lib import fetch_memo, health, prescriptions, youtube_yt
from lib import pipeline


ENTITIES = ("Alpha", "Bravo", "Charlie", "Delta", "Echo", "Foxtrot")
SLOTS = youtube_yt._YTDLP_MAX_CONCURRENT


class _VirtualClock:
    """Wall clock advanced only by paired yt-dlp searches holding the real gate."""

    def __init__(self, parties: int):
        self.cv = threading.Condition()
        self.now = 10_000.0
        self.parties = parties
        self.arrived = 0
        self.cohort: list[float] = []
        self.gen = 0
        self.needs_ack = False
        self.phase_limit = float("inf")
        self.aborted = False
        self.searches = 0

    def monotonic(self) -> float:
        with self.cv:
            return self.now

    def set_limit(self, limit: float) -> None:
        with self.cv:
            self.phase_limit = limit

    def arrive(self) -> None:
        with self.cv:
            self.arrived += 1
            self.cv.notify_all()
            while self.arrived < self.parties and not self.aborted:
                if not self.cv.wait(timeout=8):
                    raise AssertionError(
                        f"youtube workers stalled before the fan-out was running ({self.arrived})"
                    )

    def occupy(self, seconds: float) -> None:
        """Hold the simulated search open until the stream wait has seen its cost."""
        with self.cv:
            if self.aborted:
                return
            my_gen = self.gen
            self.cohort.append(seconds)
            self.searches += 1
            if len(self.cohort) < SLOTS:
                while self.gen == my_gen and not self.aborted:
                    if not self.cv.wait(timeout=8):
                        raise AssertionError("yt-dlp cohort stalled")
                return
            self.now += max(self.cohort)
            self.cohort.clear()
            self.needs_ack = True
            self.cv.notify_all()
            while self.needs_ack and not self.aborted:
                if not self.cv.wait(timeout=8):
                    raise AssertionError("stream wait never observed the yt-dlp cohort")
            if self.aborted:
                return
            self.gen += 1
            self.cv.notify_all()

    def release(self) -> None:
        with self.cv:
            self.aborted = True
            self.needs_ack = False
            self.gen += 1
            self.cv.notify_all()


def _virtual_wait(clock: _VirtualClock, pending, timeout=None, return_when=None):
    if timeout is not None and float(timeout) <= 0:
        done = {future for future in pending if future.done()}
        return done, set(pending) - done
    real_deadline = time.time() + 8
    while time.time() < real_deadline:
        done = {future for future in pending if future.done()}
        if done:
            return done, set(pending) - done
        with clock.cv:
            if clock.needs_ack:
                if clock.now + 1e-9 >= clock.phase_limit:
                    return set(), set(pending)
                clock.needs_ack = False
                clock.cv.notify_all()
                continue
            if clock.aborted:
                return set(), set(pending)
            clock.cv.wait(timeout=0.05)
    raise AssertionError(
        f"youtube stream wait stalled at t={clock.now} limit={clock.phase_limit}"
    )


def _plan(topic: str) -> dict:
    return {
        "intent": "comparison",
        "freshness_mode": "balanced_recent",
        "cluster_mode": "story",
        "subqueries": [{
            "label": "primary",
            "search_query": topic,
            "ranking_query": topic,
            "sources": ["youtube"],
            "weight": 1.0,
        }],
        "source_weights": {"youtube": 1.0},
    }


def test_deep_multi_entity_youtube_is_not_cut_off(monkeypatch):
    """Six deep entities sharing the yt-dlp gate still return videos.

    Each deep search is allowed to consume its own search timeout. The fixed
    stream cap is shorter than that queue, so an unscaled budget records a
    timeout and zero videos.
    """
    clock = _VirtualClock(len(ENTITIES))
    ids = {"n": 0}
    id_lock = threading.Lock()

    def fake_run(cmd, timeout=120, **kwargs):
        if not any("ytsearch" in str(part) for part in cmd):
            return youtube_yt.subproc.SubprocResult(returncode=0, stdout="", stderr="")
        clock.occupy(float(timeout))
        with id_lock:
            ids["n"] += 1
            video_id = f"vid{ids['n']:04d}"
        subject = ""
        for part in cmd:
            text = str(part)
            if "ytsearch" in text:
                subject = text.split(":", 1)[-1]
                break
        payload = {
            "id": video_id,
            "title": subject or video_id,
            "description": subject,
            "channel": "Desk",
            "view_count": 1000,
            "upload_date": "20261001",
        }
        return youtube_yt.subproc.SubprocResult(
            returncode=0,
            stdout=json.dumps(payload) + "\n",
            stderr="",
        )

    def fake_transcript(video_id, *args, **kwargs):
        return f"{video_id} walks through the comparison with specific numbers and dates."

    original_wait = pipeline._wait_for_research

    def wrapped_wait(futures, config, *args, **kwargs):
        until = kwargs.get("until")
        limit = config.get("_research_deadline", clock.now)
        if until is not None:
            limit = min(limit, until)
        clock.set_limit(limit)
        return original_wait(futures, config, *args, **kwargs)

    original_fetch = pipeline._fetch_youtube_stream
    inflight = {"n": 0}
    inflight_cv = threading.Condition()

    def wrapped_fetch(*args, **kwargs):
        with inflight_cv:
            inflight["n"] += 1
        clock.arrive()
        try:
            return original_fetch(*args, **kwargs)
        finally:
            with inflight_cv:
                inflight["n"] -= 1
                inflight_cv.notify_all()

    monkeypatch.setattr(pipeline.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(pipeline, "futures_wait", lambda *a, **k: _virtual_wait(clock, *a, **k))
    monkeypatch.setattr(pipeline, "_wait_for_research", wrapped_wait)
    monkeypatch.setattr(pipeline, "_fetch_youtube_stream", wrapped_fetch)
    monkeypatch.setattr(pipeline, "which", lambda cmd: "/usr/bin/yt-dlp" if cmd == "yt-dlp" else None)
    monkeypatch.setattr(youtube_yt, "is_ytdlp_installed", lambda: True)
    monkeypatch.setattr(youtube_yt.subproc, "run_with_timeout", fake_run)
    monkeypatch.setattr(youtube_yt, "fetch_transcript", fake_transcript)
    monkeypatch.setattr(youtube_yt, "_fetch_transcript_direct", lambda *a, **k: None)
    monkeypatch.setattr(youtube_yt, "enrich_with_comments", lambda items, token, **k: items)

    youtube_yt.reset_search_cache()
    fetch_memo.reset()

    config = {
        "EXCLUDE_SOURCES": "youtube_comments",
        # Comparison fan-out width. The CLI records this so each entity run
        # can budget for the shared yt-dlp gate. Ignoring it leaves the
        # fixed stream cap in place.
        "_comparison_entity_count": len(ENTITIES),
    }
    errors: list[BaseException] = []
    reports: dict[str, object] = {}
    lock = threading.Lock()

    def run_one(entity: str) -> None:
        try:
            report = pipeline.run(
                topic=entity,
                config=dict(config),
                depth="deep",
                requested_sources=["youtube"],
                mock=False,
                external_plan=_plan(entity),
                web_backend="none",
                lookback_days=90,
                as_of_date="2026-10-23",
                internal_subrun=True,
            )
        except BaseException as exc:  # noqa: BLE001 - surfaced as a test failure
            with lock:
                errors.append(exc)
            return
        with lock:
            reports[entity] = report

    threads = [threading.Thread(target=run_one, args=(entity,)) for entity in ENTITIES]
    try:
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(20)
            assert not thread.is_alive(), "entity run did not finish"
    finally:
        clock.release()
        with inflight_cv:
            deadline = time.time() + 8
            while inflight["n"] and time.time() < deadline:
                inflight_cv.wait(timeout=0.2)
        youtube_yt.reset_search_cache()
        fetch_memo.reset()

    assert not errors, errors[0]
    assert set(reports) == set(ENTITIES)
    for entity, report in reports.items():
        outcome = report.source_status["youtube"]
        assert outcome.state != health.TIMEOUT, (entity, outcome.state, outcome.detail)
        assert outcome.items_returned > 0, (entity, outcome.state, outcome.detail)


def test_youtube_timeout_does_not_recommend_updating_ytdlp(monkeypatch):
    """An engine timeout is not evidence that the yt-dlp binary is stale."""
    from lib.quality_nudge import compute_quality_score

    monkeypatch.setattr(youtube_yt, "is_ytdlp_installed", lambda: True)
    quality = compute_quality_score(
        {},
        {"youtube_error": "youtube timed out after 180s"},
    )
    nudge = quality["nudge_text"] or ""
    stale = prescriptions.get("youtube", "ytdlp_stale")

    assert "youtube" in quality["core_errored"]
    assert nudge
    assert stale.fix_nl not in nudge
    assert stale.fix_cli not in nudge
    for alternate in stale.alt_cli:
        assert alternate not in nudge
    lowered = nudge.lower()
    assert "timed out" in lowered or "ran out of time" in lowered or "timeout" in lowered
