"""DiPCo, the Dinner Party Corpus: all 10 sessions (dev and eval; there is no training split), 4 speakers each,
dinner-table conversations. CDLA-Permissive-1.0.

Download DipCo.tgz from Zenodo record 8122551 (https://zenodo.org/records/8122551) and extract it under <source>.

Single channel: far-field array U01, channel 1 (<session>_U01.CH1.wav), the whole session. References are the
official utterance transcripts, with the utterance times given for U01 (no word times).
"""
import json
from pathlib import Path

from .common import to_wav, write_dataset

SESSIONS = {"dev": ["S02", "S04", "S05", "S09", "S10"], "eval": ["S01", "S03", "S06", "S07", "S08"]}


def prepare(source: Path, out: Path) -> None:
    recordings, segments = [], []
    for split, sessions in SESSIONS.items():
        for session in sessions:
            utterances = json.loads(next(source.rglob(f"transcriptions/{split}/{session}.json")).read_text())
            audio = next(source.rglob(f"audio/{split}/{session}_U01.CH1.wav"))
            to_wav(audio, out / "audio" / f"{session}.wav")
            recordings.append({"id": session, "language": "en", "source": f"audio/{split}/{audio.name}"})
            segments += [{"session_id": session, "speaker": u["speaker_id"],
                          "start_time": _seconds(u["start_time"]["U01"]), "end_time": _seconds(u["end_time"]["U01"]),
                          "words": u["words"]} for u in utterances]
    write_dataset(out, recordings, segments)


def _seconds(t: str) -> float:
    h, m, s = t.split(":")
    return round(int(h) * 3600 + int(m) * 60 + float(s), 3)
