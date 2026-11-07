"""CHiME-6 evaluation set: sessions S01 and S21 (dinner parties, 4 speakers each). CC BY-SA 4.0.

Download from OpenSLR 150 (https://www.openslr.org/150/): CHiME6_eval.tar.gz and CHiME6_transcriptions.tar.gz,
extracted under <source>.

Single channel: array U06, channel 1 (S01_U06.CH1.wav, S21_U06.CH1.wav), the array the Kaldi CHiME-6 track 2
baseline scores on. As in the CHiME-8 scoring setup, each session starts at its first annotated utterance.
References are the official utterance transcripts (no word times).
"""
import json
from pathlib import Path

from .common import to_wav, write_dataset

SESSIONS = ["S01", "S21"]


def prepare(source: Path, out: Path) -> None:
    recordings, segments = [], []
    for session in SESSIONS:
        utterances = json.loads(next(source.rglob(f"transcriptions/eval/{session}.json")).read_text())
        start = min(_seconds(u["start_time"]) for u in utterances)
        audio = next(source.rglob(f"audio/eval/{session}_U06.CH1.wav"))
        to_wav(audio, out / "audio" / f"{session}.wav", start=start)
        recordings.append({"id": session, "language": "en", "source": f"audio/eval/{audio.name} from {start:.2f} s"})
        segments += [{"session_id": session, "speaker": u.get("speaker", "unknown"),
                      "start_time": round(_seconds(u["start_time"]) - start, 3),
                      "end_time": round(_seconds(u["end_time"]) - start, 3), "words": u["words"]} for u in utterances]
    write_dataset(out, recordings, segments)


def _seconds(t: str) -> float:
    h, m, s = t.split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)
