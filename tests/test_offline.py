"""Offline checks: response parsing, splitting, hypothesis conversion and scoring. No network."""
import asyncio
import json
import wave

from bench import breakdown, hyp, paths, run, score, stitch
from bench.providers import load

RESPONSES = {
    "aircaps": {"words": [{"text": "hello", "start": 0.1, "end": 0.4, "speaker": "speaker_0"}]},
    "elevenlabs": {"words": [{"text": "hello", "type": "word", "start": 0.1, "end": 0.4, "speaker_id": "speaker_0"},
                             {"text": " ", "type": "spacing", "start": 0.4, "end": 0.5, "speaker_id": "speaker_0"},
                             {"text": "(laughs)", "type": "audio_event", "start": 0.5, "end": 0.9}]},
    "assemblyai": {"words": [{"text": "Hello.", "start": 100, "end": 400, "speaker": "A"}]},
    "meta": {"turns": [{"turnId": 1, "startMs": 100, "endMs": 400, "transcript": "Hello.", "speaker": "A"}]},
    "microsoft": {"phrases": [{"offsetMilliseconds": 100, "durationMilliseconds": 300, "text": "Hello.", "speaker": 1}]},
    "xai": {"words": [{"text": "hello", "start": 0.1, "end": 0.4, "speaker": 0}]},
    "google": {"steps": [{"content": [{"annotations": [
        {"type": "word_info", "text": "Hello", "speaker": "spk_1", "start_offset": "0.100s", "end_offset": "0.400s"}]}]}]},
    "nvidia": {"choices": [{"message": {"content": "<spk:0> hello"}}]},
}


def test_every_adapter_reads_one_word():
    for name, response in RESPONSES.items():
        words = load(name).words(response)
        assert len(words) == 1 and words[0].text.strip(".").lower() == "hello", name


def test_nemotron_guardrail_and_turns():
    response = {"choices": [{"message": {"content": "<spk:0> yes " + "no " * 30 + "<spk:1> ok"}}]}
    words = load("nvidia").words(response)
    assert [w.speaker for w in words] == ["spk0", "spk1"]
    assert words[0].text.split().count("no") == 1


def test_run_sends_longest_first_and_joins_parts(tmp_path, monkeypatch):
    for name in ("DATA", "RESULTS", "LOGS"):
        monkeypatch.setattr(paths, name, tmp_path / name.lower())
    (paths.DATA / "toy" / "audio").mkdir(parents=True)
    rows = []
    for rec, seconds in [("short", 5), ("long", 25)]:
        with wave.open(str(paths.DATA / "toy" / "audio" / f"{rec}.wav"), "wb") as w:
            w.setparams((1, 2, 16000, 0, "NONE", "NONE"))
            w.writeframes(b"\0\0" * 16000 * seconds)
        rows.append({"id": rec, "audio": f"audio/{rec}.wav", "duration": seconds, "language": "en", "sha256": "x"})
    (paths.DATA / "toy" / "manifest.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    sent = []

    class Fake:
        name, model, key, max_seconds, settings = "fake", "m", "", 10, {"concurrency": 1}

        def request(self, language, dataset):
            return {}

        async def transcribe(self, client, audio, language, dataset):
            sent.append(audio.name)
            return {"frames": wave.open(str(audio)).getnframes()}

    monkeypatch.setattr(run, "load", lambda name: Fake())
    monkeypatch.setattr(stitch, "OVERLAP", 2.0)
    monkeypatch.setenv("BENCH_QUIET", "1")
    asyncio.run(run.run(["fake"], ["toy"]))
    assert sent == ["long.0s.wav", "long.8s.wav", "long.15s.wav", "short.wav"]
    response = paths.read_json(paths.raw_path("fake", "toy", "long"))["response"]
    parts = response["parts"]
    assert response["overlap"] == 2.0
    assert [(round(p["start"], 3), round(p["end"], 3)) for p in parts] == [(0.0, 9.667), (7.667, 17.333), (15.333, 25.0)]
    assert all(p["response"]["frames"] == int((p["end"] - p["start"]) * 16000) for p in parts)


def test_hypothesis_and_score(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "DATA", tmp_path / "data")
    monkeypatch.setattr(paths, "RESULTS", tmp_path / "results")
    (paths.DATA / "toy").mkdir(parents=True)
    rows = [{"id": i, "audio": f"audio/{i}.wav", "duration": 20.0, "language": "en", "sha256": "x"} for i in ("r1", "r2")]
    (paths.DATA / "toy" / "manifest.jsonl").write_text("\n".join(json.dumps(r) for r in rows))
    ref = [{"session_id": "r1", "speaker": "A", "start_time": 0.0, "end_time": 1.0, "words": "Hello there."},
           {"session_id": "r1", "speaker": "B", "start_time": 12.0, "end_time": 13.0, "words": "General Kenobi!"},
           {"session_id": "r2", "speaker": "A", "start_time": 0.0, "end_time": 1.0, "words": "two words"}]
    (paths.DATA / "toy" / "references.seglst.json").write_text(json.dumps(ref))
    # r1 was sent in two parts with per-part speaker labels; r2 failed and has no raw response.
    parts = {"parts": [{"start": 0.0, "response": {"words": [
                           {"text": "hello", "start": 0.0, "end": 0.5, "speaker": "speaker_0"},
                           {"text": "there", "start": 0.5, "end": 1.0, "speaker": "speaker_0"}]}},
                       {"start": 10.0, "response": {"words": [
                           {"text": "general", "start": 2.0, "end": 2.5, "speaker": "speaker_0"},
                           {"text": "kenobi", "start": 2.5, "end": 3.0, "speaker": "speaker_0"}]}}]}
    paths.write_json(paths.raw_path("aircaps", "toy", "r1"), {"response": parts})
    assert hyp.build("aircaps", "toy") == 4
    segments = paths.read_json(paths.hypothesis_path("aircaps", "toy"))
    assert {s["speaker"] for s in segments} == {"part0:speaker_0", "part1:speaker_0"}
    assert segments[2]["start_time"] == 12.0
    result = score.score("aircaps", "toy", "cpwer")
    assert result["per_recording"]["r1"]["errors"] == 0
    assert result["per_recording"]["r2"]["deletions"] == 2 and result["failed"] == ["r2"]
    assert result["errors"] == 2 and result["length"] == 6
    # r1: 2 reference speakers, found as 2; r2: 1 speaker, nothing returned
    assert [result["per_recording"]["r1"][k] for k in ("missed_speakers", "invented_speakers")] == [0, 0]

    assert [result["per_recording"]["r2"][k] for k in ("missed_speakers", "invented_speakers")] == [1, 0]

    text = breakdown.table("speakers", datasets=["toy"])
    assert "| aircaps | 100.00 (1) | 0.00 (1) |" in text   # group "1" is r2 (failed), group "2" is r1
    assert "| aircaps | 1.00 / 0.00 | 0.00 / 0.00 |" in text


def test_overlap_percent():
    segs = [{"speaker": "A", "start_time": 0.0, "end_time": 6.0},
            {"speaker": "A", "start_time": 5.0, "end_time": 10.0},   # A's own segments overlap: merged
            {"speaker": "B", "start_time": 8.0, "end_time": 12.0}]   # A and B together for 2 s of 12 s
    assert round(breakdown.overlap_percent(segs), 2) == 16.67
    assert breakdown.overlap_percent([{"speaker": "A", "start_time": None, "end_time": None}]) is None
    assert breakdown.group_of(16.67, breakdown.OVERLAP_GROUPS) == "15-30%"
    assert breakdown.group_of(4, breakdown.SPEAKER_GROUPS) == "4"
    assert breakdown.group_of(42, breakdown.OVERLAP_GROUPS) == "30-50%"


def test_cpwer_without_limit_matches_meeteval():
    from meeteval.io import SegLST
    from meeteval.wer import api
    seg = lambda spk, t, words: {"session_id": "s", "speaker": spk, "start_time": t, "end_time": t + 1, "words": words}
    ref = SegLST([seg("a", 0, "one two three"), seg("b", 1, "four five"), seg("a", 2, "six")])
    hyp = SegLST([seg("x", 0, "one two tree"), seg("y", 1, "four"), seg("z", 2, "five six seven")])
    mine, theirs = score.cpwer_without_limit(ref, hyp), api.cpwer(ref, hyp)["s"]
    assert (mine.errors, mine.length, mine.falarm_speaker) == (theirs.errors, theirs.length, theirs.falarm_speaker)
    many = SegLST([seg(f"h{k}", k, "word") for k in range(60)])
    assert score.cpwer_without_limit(ref, many).falarm_speaker == 58


def test_normaliser_matches_spoken_and_written_forms():
    from bench.normalize import normalize
    for spoken, written in [("twenty twenty one", "20 21"), ("two three five one", "2 3 5 1"), ("seven thirty", "7:30"),
                            ("okay", "OK"), ("u s a", "U.S.A."), ("her mind in a tumult", "Her mind… …in a tumult…")]:
        assert normalize(spoken, "en") == normalize(written, "en")
    assert normalize("I have two. Three people came.", "en") == "i have 2 3 people came"


def test_speaker_runs_continue_across_another_speakers_words():
    seg = lambda spk, t, end, words: {"session_id": "s", "speaker": spk, "start_time": t, "end_time": end,
                                      "words": words}
    # a's pause across b's "yeah" is 0.4 s: one run; b's 1.2 s and a's 1.6 s pauses start new runs
    runs = score._runs([seg("a", 0.0, 0.5, "twenty"), seg("b", 0.6, 0.8, "yeah"), seg("a", 0.9, 1.4, "five"),
                        seg("b", 2.0, 2.3, "right"), seg("a", 3.0, 3.5, "six")])
    assert [(r["speaker"], r["words"]) for r in runs] == [("a", "twenty five"), ("b", "yeah"), ("b", "right"),
                                                          ("a", "six")]
    untimed = [seg("a", None, None, "one"), seg("b", 1, 2, "two"), seg("a", 3, 4, "three")]
    assert [r["words"] for r in score._runs(untimed)] == ["one", "two", "three"]




def test_speed_order_slots_rate_gate_and_report(tmp_path, monkeypatch):
    import httpx
    from bench import speed
    from bench.providers.base import RETRIES
    from bench.run import Rate
    for name in ("DATA", "RESULTS", "LOGS"):
        monkeypatch.setattr(paths, name, tmp_path / name.lower())
    monkeypatch.setattr(speed, "OUT", paths.RESULTS / "speed")
    monkeypatch.setattr(speed, "SETS", ("toy",))   # the report counts only the benchmark's datasets
    (paths.DATA / "toy").mkdir(parents=True)
    files = []
    for name, seconds in [("a", 3), ("b", 25), ("c", 10), ("d", 2)]:
        with wave.open(str(paths.DATA / "toy" / f"{name}.wav"), "wb") as w:
            w.setparams((1, 2, 16000, 0, "NONE", "NONE"))
            w.writeframes(b"\0\0" * 16000 * seconds)
        files.append({"id": f"toy/{name}", "dataset": "toy", "seconds": seconds, "audio": f"toy/{name}.wav"})
    sent, busy = [], {"now": 0, "most": 0}

    class Fake:
        name, model, key, max_seconds = "fake", "m", "", 10
        settings = {"concurrency": 5, "slots": {"over_seconds": 9, "slots": 4}, "rate_limit": [2, 0.05]}

        async def transcribe(self, client, audio, language, dataset):
            sent.append(audio.name)
            busy["now"] += 1
            busy["most"] = max(busy["most"], busy["now"])
            await asyncio.sleep(0.01)
            busy["now"] -= 1
            if audio.name == "c.wav":
                RETRIES.get()[429] += 1   # as if send() had been answered 429 once
            return {"frames": wave.open(str(audio)).getnframes()}

        def words(self, response):
            return [None] * response["frames"]

    monkeypatch.setattr(speed, "load", lambda name: Fake())
    monkeypatch.setitem(speed.LEVELS, "B2", 4)
    monkeypatch.setattr(stitch, "OVERLAP", 2.0)

    async def go():
        async with httpx.AsyncClient() as client:
            p = speed.Provider("fake", tmp_path, client)
            await p.test("B2", 1, files, [])
            p.rate = Rate(None)
            await p.test("C", 1, files[1:2], [])
            return p
    p = asyncio.run(go())
    # B2: one untimed wave of the 4 shortest requests, then the timed ones: b (25 s) in 3 overlapping parts first,
    # then whole files longest first; c (10 s) takes 4 of the 5 slots. C: b's 3 parts sent together.
    timed = ["b.0s.wav", "b.8s.wav", "b.15s.wav", "c.wav", "a.wav", "d.wav"]
    assert sent == ["d.wav", "a.wav", "c.wav", "b.15s.wav"] + timed + ["b.0s.wav", "b.8s.wav", "b.15s.wav"]
    assert busy["most"] <= 4
    a, c = p.summary["tests"]
    assert (a["requests"], a["failures"], a["status_429"]) == (6, 0, 1) and a["rate_waits"] > 0
    rows = [json.loads(x) for x in (p.out / "requests.jsonl").read_text().splitlines()]
    assert {r["slots"] for r in rows if r["file"] == "toy/c"} == {4} and {r["parts"] for r in rows if r["file"] == "toy/b"} == {3}
    parts = [r for r in rows if r["test"] == "C"]
    assert max(r["t_sent"] for r in parts) < min(r["t_done"] for r in parts) and c["most_in_flight"] == 3
    assert "limited (1 429s" in speed.report()

    async def three_turns():
        rate = Rate([2, 0.2])
        return await asyncio.gather(*(rate.turn() for _ in range(3)))
    waits = asyncio.run(three_turns())
    assert waits[:2] == [0.0, 0.0] and 0.15 < waits[2] < 0.3


def test_stitch_links_speakers_and_drops_the_repeat():
    # Two parts overlapping in "four five six": the second part calls the same person "B" and adds a new "C".
    w = lambda text, t, spk: {"text": text, "start": t, "end": t + 0.5, "speaker": spk}
    first = {"start": 0.0, "end": 10.0, "response": {"words": [w(x, i, "A") for i, x in enumerate("one two three four five six".split())]}}
    second = {"start": 7.0, "end": 17.0, "response": {"words": [w("four", 0, "B"), w("five", 1, "B"), w("six", 2, "B"),
                                                                w("seven", 3, "B"), w("eight", 4, "C")]}}
    segments, joints = stitch.stitch(load("aircaps"), [first, second], overlap=3.0)
    assert [s["words"] for s in segments] == "one two three four five six seven eight".split()
    assert {s["speaker"] for s in segments} == {"p0:A", "p1:C"}
    assert joints == [{"aligned_words": 3, "linked_speakers": 1}]
    assert segments[-1]["start_time"] == 11.0


def test_plan_covers_the_file_with_overlap():
    spans = stitch.plan(9000.0, 3600.0)
    assert len(spans) == 3 and spans[0][0] == 0.0 and spans[-1][1] == 9000.0
    assert all(round(a[1] - b[0], 6) == stitch.OVERLAP for a, b in zip(spans, spans[1:]))
    assert all(e - s <= 3600.0 for s, e in spans)
