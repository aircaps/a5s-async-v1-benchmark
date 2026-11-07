"""DAI-ASR-I18N, English public split (David AI): two-speaker conversations.

Access: https://huggingface.co/datasets/davidai-labs/DAI-ASR-I18N is gated; request access on that page and
accept its data use agreement (evaluation of commercial models is permitted; no redistribution). Then:
    hf download davidai-labs/DAI-ASR-I18N --repo-type dataset --include "data/en/*" --local-dir <source>
    (and the audio folders the English rows point to: audio/<sample_id>/ch1.flac, ch2.flac)

Audio is David AI's own mono mix, mono-mix-v1 (https://github.com/withdavid-ai/dai-asr-i18n,
src/dai_asr_i18n/audio/mixing.py): resample each channel to 16 kHz with soxr "HQ", pad the shorter one with
silence, add them, and divide by the peak only if it exceeds 1. References are the published segments
(`word_alignments`), with their speakers and times.
"""
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq
import soundfile
import soxr

from .common import write_dataset


def prepare(source: Path, out: Path) -> None:
    rows = pq.read_table(next(source.rglob("data/en/en.parquet"))).to_pylist()
    recordings, segments = [], []
    for row in rows:
        sid = row["sample_id"]
        mix([source / "audio" / sid / "ch1.flac", source / "audio" / sid / "ch2.flac"], out / "audio" / f"{sid}.wav")
        recordings.append({"id": sid, "language": "en", "source": f"audio/{sid}/ch1.flac + ch2.flac, mono-mix-v1"})
        segments += [{"session_id": sid, "speaker": str(seg["speaker"]), "start_time": seg["start"],
                      "end_time": seg["end"], "words": " ".join(w["text"] for w in seg["words"])}
                     for seg in row["word_alignments"]]
    write_dataset(out, recordings, segments)


def mix(tracks: list[Path], dst: Path) -> None:
    """mono-mix-v1: each track to 16 kHz (soxr HQ), padded, added, divided by the peak only if it exceeds 1."""
    channels = []
    for track in tracks:
        x, rate = soundfile.read(track, dtype="float64")
        channels.append(x if rate == 16000 else soxr.resample(x, rate, 16000, quality="HQ"))
    total = np.zeros(max(len(c) for c in channels))
    for c in channels:
        total[:len(c)] += c
    peak = np.abs(total).max()
    if peak > 1.0:
        total /= peak
    dst.parent.mkdir(parents=True, exist_ok=True)
    soundfile.write(dst, total, 16000, subtype="PCM_16")
