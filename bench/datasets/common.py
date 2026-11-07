"""Shared steps of every dataset recipe: cut and convert audio, write the manifest and references."""
import hashlib
import json
import subprocess
import wave
from pathlib import Path


def to_wav(src: Path, dst: Path, channel: int | None = None, start: float | None = None,
           end: float | None = None) -> None:
    """Decode with ffmpeg to 16 kHz mono 16-bit PCM WAV.

    channel: take this input channel (0-based) as is; None means the file is already mono.
    start/end: keep only this part of the file, in seconds.
    """
    dst.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-nostdin", "-v", "error", "-y"]
    if start is not None:
        cmd += ["-ss", f"{start:.3f}"]
    if end is not None:
        cmd += ["-to", f"{end:.3f}"]
    cmd += ["-i", str(src)]
    if channel is not None:
        cmd += ["-af", f"pan=mono|c0=c{channel}"]
    # bitexact: no encoder version or metadata in the header, so the same input gives the same bytes anywhere
    cmd += ["-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", "-map_metadata", "-1",
            "-fflags", "+bitexact", "-flags:a", "+bitexact", str(dst)]
    subprocess.run(cmd, check=True)


def wav_seconds(path: Path) -> float:
    with wave.open(str(path)) as w:
        return w.getnframes() / w.getframerate()


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def reference_sha256(segments: list[dict]) -> str:
    """Hash of one recording's reference segments in a fixed key order, for verification."""
    keys = ("session_id", "speaker", "start_time", "end_time", "words")
    rows = [[s[k] for k in keys] for s in segments]
    return hashlib.sha256(json.dumps(rows, ensure_ascii=False).encode()).hexdigest()


def write_dataset(out: Path, recordings: list[dict], segments: list[dict]) -> None:
    """Write manifest.jsonl and references.seglst.json for prepared audio under out/audio/.

    recordings: dicts with id, language and source (where the audio came from, channel and cut).
    segments:   reference SegLST for all recordings.
    """
    # stable sort: segments without times keep their original order
    segments = sorted(segments, key=lambda s: (s["session_id"], s["start_time"] or 0.0))
    by_recording = {}
    for s in segments:
        by_recording.setdefault(s["session_id"], []).append(s)
    lines = []
    for rec in sorted(recordings, key=lambda r: r["id"]):
        audio = out / "audio" / f"{rec['id']}.wav"
        refs = by_recording.get(rec["id"], [])
        lines.append(json.dumps({
            "id": rec["id"],
            "audio": f"audio/{rec['id']}.wav",
            "duration": round(wav_seconds(audio), 3),
            "language": rec["language"],
            "sha256": file_sha256(audio),
            "reference_sha256": reference_sha256(refs),
            "reference_words": sum(len(s["words"].split()) for s in refs),
            "source": rec["source"],
        }, ensure_ascii=False))
    (out / "manifest.jsonl").write_text("\n".join(lines) + "\n")
    (out / "references.seglst.json").write_text(json.dumps(segments, ensure_ascii=False, indent=1))
