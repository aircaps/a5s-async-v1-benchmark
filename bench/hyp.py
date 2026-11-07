"""Turn raw provider responses into SegLST hypotheses.

One SegLST entry per word (or per segment, for providers that only return segments), with the provider's own
speaker label and times. Nothing is merged, re-timed or relabelled; normalisation happens only at scoring time.

A file sent in overlapping parts is joined by bench/stitch.py: speakers linked across parts by the words they share,
the duplicated stretch removed, without the reference. `strict` scores the parts as they are instead: times shifted
by the part's start, speaker labels prefixed with the part number, and, where the first run's non-overlapping parts
were kept (results/strict/raw), those parts.
"""
from . import paths, stitch
from .providers import load


def build(provider_name: str, dataset: str, strict: bool = False) -> int:
    provider = load(provider_name)
    segments = []
    for rec in paths.manifest(dataset):
        raw = paths.raw_path(provider_name, dataset, rec["id"], strict=True) if strict else None
        if not (raw and raw.exists()):
            raw = paths.raw_path(provider_name, dataset, rec["id"])
        if not raw.exists():
            continue
        response = paths.read_json(raw)["response"]
        parts = response["parts"] if "parts" in response else [{"start": 0.0, "response": response}]
        if len(parts) > 1 and "overlap" in response and not strict:
            joined, _ = stitch.stitch(provider, parts, response["overlap"])
            segments += [{"session_id": rec["id"], **s} for s in joined]
            continue
        for k, part in enumerate(parts):
            prefix = f"part{k}:" if len(parts) > 1 else ""
            for w in provider.words(part["response"]):
                segments.append({"session_id": rec["id"], "speaker": prefix + w.speaker,
                                 "start_time": None if w.start is None else part["start"] + w.start,
                                 "end_time": None if w.end is None else part["start"] + w.end,
                                 "words": w.text})
    paths.write_json(paths.hypothesis_path(provider_name, dataset, strict), segments)
    return len(segments)
