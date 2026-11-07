"""Agentic Data Company "multi-party conversations": a 4-call sample (3 speakers per call, one headset track each).

Licensed from the Agentic Data Company (https://theagenticdatacompany.com/datasets/multi-party-conversations), and
its references are the vendor's machine transcripts (word-level, not human-verified). Scores are published; the data
is not, and is available on request.

<source> holds the delivered folders conv_*/ with meta.json, speaker_<seat>.flac and speaker_<seat>_transcript.json.
The headset tracks are mixed to one channel (resampled to 16 kHz, added, divided by the peak only if it exceeds 1);
references are each track's transcript words with their times.
"""
import json
from pathlib import Path

from .common import write_dataset
from .dai_en import mix


def prepare(source: Path, out: Path) -> None:
    recordings, segments = [], []
    for meta in sorted(source.rglob("conv_*/meta.json")):
        conv = meta.parent
        seats = [s["seat"] for s in json.loads(meta.read_text())["speakers"]]
        mix([conv / f"speaker_{seat}.flac" for seat in seats], out / "audio" / f"{conv.name}.wav")
        recordings.append({"id": conv.name, "language": "en", "source": f"{conv.name}: headset tracks {seats} mixed"})
        for seat in seats:
            words = json.loads((conv / f"speaker_{seat}_transcript.json").read_text()).get("words") or []
            segments += [{"session_id": conv.name, "speaker": seat, "start_time": w["start"], "end_time": w["end"],
                          "words": w["word"]} for w in words if w.get("type", "word") == "word" and w.get("word")]
    write_dataset(out, recordings, segments)
