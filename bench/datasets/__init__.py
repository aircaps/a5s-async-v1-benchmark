"""Dataset recipes.

Each recipe's docstring says where to download the data and how the test set is built. `bench prep <dataset>`
writes data/<dataset>/:
  audio/<id>.wav            16 kHz mono 16-bit PCM, the exact file every provider receives
  manifest.jsonl            id, audio, duration, language, sha256, reference_sha256, reference_words, source
  references.seglst.json    reference words with speaker labels and times (SegLST)
"""
import importlib
import json
from pathlib import Path

from .. import paths
from .common import file_sha256, reference_sha256

# dataset name -> (module, whether the module serves several datasets by name)
RECIPES = {
    "ami": ("nxt", True), "icsi": ("nxt", True),
    "aishell4": ("textgrid_sets", True), "alimeeting": ("textgrid_sets", True),
    "notsofar": ("notsofar", False), "chime6": ("chime6", False),
    "dai_en": ("dai_en", False),
    "agentic": ("agentic", False), "dipco": ("dipco", False),
    **{name: ("hf", True) for name in ("openasr_earnings22", "openasr_librispeech_clean", "voxpopuli")},
}


def prepare(dataset: str, source: str | None) -> None:
    if dataset not in RECIPES:
        raise SystemExit(f"unknown dataset {dataset!r}; known: {', '.join(sorted(RECIPES))}")
    module_name, by_name = RECIPES[dataset]
    module = importlib.import_module(f"{__name__}.{module_name}")
    out = paths.DATA / dataset
    source = Path(source).expanduser() if source else None
    module.prepare(dataset, source, out) if by_name else module.prepare(source, out)
    print(f"{dataset}: {sum(1 for _ in (out / 'manifest.jsonl').open())} recordings in {out}")


def verify(dataset: str, manifest: str) -> None:
    """Compare locally prepared audio and references with the published manifest; exit non-zero on mismatch."""
    published = [json.loads(line) for line in Path(manifest).read_text().splitlines() if line.strip()]
    by_recording = {}
    for s in paths.references(dataset):
        by_recording.setdefault(s["session_id"], []).append(s)
    bad = []
    for rec in published:
        audio = paths.DATA / dataset / rec["audio"]
        if not audio.exists() or file_sha256(audio) != rec["sha256"]:
            bad.append(f"{rec['id']}: audio")
        if reference_sha256(by_recording.get(rec["id"], [])) != rec["reference_sha256"]:
            bad.append(f"{rec['id']}: reference")
    if bad:
        raise SystemExit(f"{dataset}: {len(bad)} mismatches\n" + "\n".join(bad))
    print(f"{dataset}: all {len(published)} recordings match the published manifest")
