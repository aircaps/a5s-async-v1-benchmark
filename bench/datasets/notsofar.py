"""NOTSOFAR-1 single-channel (SC) evaluation set: the 160 SC recordings (80 meetings x 2 devices) of
240629.1_eval_small_with_GT, the set used for the CHiME-8 NOTSOFAR evaluation. CC BY 4.0.

Download:
    hf download microsoft/NOTSOFAR --repo-type dataset --revision ba8fd0f034ce185fe4d24f47e53b4b8194795f07 \
        --include "benchmark-datasets/eval_set/240629.1_eval_small_with_GT/*" --local-dir <source>

Each meeting folder has gt_transcription.json (utterances with speaker, times and text) and one folder per
device; single-channel devices are the `sc_*` folders, each with ch0.wav. Every utterance is kept.
"""
import json
from pathlib import Path

from .common import to_wav, write_dataset


def prepare(source: Path, out: Path) -> None:
    recordings, segments = [], []
    for meeting in sorted(source.rglob("240629.1_eval_small_with_GT/MTG/MTG_*")):
        if not (meeting / "gt_transcription.json").exists():  # e.g. download-cache folders
            continue
        utterances = json.loads((meeting / "gt_transcription.json").read_text())
        for device in sorted(meeting.glob("sc_*")):
            rid = f"{meeting.name}_{device.name}"
            to_wav(device / "ch0.wav", out / "audio" / f"{rid}.wav")
            recordings.append({"id": rid, "language": "en", "source": f"MTG/{meeting.name}/{device.name}/ch0.wav"})
            segments += [{"session_id": rid, "speaker": u["speaker_id"], "start_time": u["start_time"],
                          "end_time": u["end_time"], "words": u["text"]} for u in utterances]
    write_dataset(out, recordings, segments)
