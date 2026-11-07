"""Single-speaker test sets hosted on Hugging Face: the Open ASR Leaderboard's short-form English sets.

Source: the leaderboard's own copies (https://huggingface.co/datasets/hf-audio/open-asr-leaderboard), at a pinned
revision. Every clip is kept, unfiltered; its reference is the `text` column as published, one segment per clip.
Before downloading, accept the terms on the original pages where the leaderboard card asks you to.
"""
import re
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pyarrow.parquet as pq
from huggingface_hub import hf_hub_download, list_repo_files

from .common import to_wav, wav_seconds, write_dataset

OPEN_ASR = ("hf-audio/open-asr-leaderboard", "de79e57adf9983993bcc72586d7313460825f5eb")

# our name: (repo, revision, parquet file prefix)
SETS = {
    "openasr_earnings22": (*OPEN_ASR, "earnings22/test-"),
    "openasr_librispeech_clean": (*OPEN_ASR, "librispeech/test.clean-"),
    "voxpopuli": (*OPEN_ASR, "voxpopuli/test-"),
}


def prepare(name: str, source: Path | None, out: Path) -> None:
    repo, revision, prefix = SETS[name]
    files = sorted(f for f in list_repo_files(repo, repo_type="dataset", revision=revision)
                   if f.startswith(prefix) and f.endswith(".parquet"))
    recordings, segments, jobs = [], [], []
    with tempfile.TemporaryDirectory() as tmp:
        for f in files:
            table = pq.read_table(hf_hub_download(repo, f, repo_type="dataset", revision=revision,
                                                  cache_dir=source), columns=["audio", "id", "text"])
            for row in table.to_pylist():
                rid = re.sub(r"[^A-Za-z0-9._-]", "_", row["id"])
                src = Path(tmp) / f"{len(jobs)}.bin"
                src.write_bytes(row["audio"]["bytes"])
                jobs.append((src, out / "audio" / f"{rid}.wav"))
                recordings.append({"id": rid, "language": "en", "source": f"{repo}@{revision[:7]} {f} id={row['id']}"})
                segments.append({"session_id": rid, "speaker": "speaker", "start_time": 0.0, "words": row["text"]})
        if len({r["id"] for r in recordings}) != len(recordings):
            raise SystemExit(f"{name}: clip ids are not unique after sanitising")
        with ThreadPoolExecutor(8) as pool:
            list(pool.map(lambda job: to_wav(*job), jobs))
    for s in segments:
        s["end_time"] = round(wav_seconds(out / "audio" / f"{s['session_id']}.wav"), 3)
    write_dataset(out, recordings, segments)
