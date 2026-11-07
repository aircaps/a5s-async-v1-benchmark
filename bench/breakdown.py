"""Error rates broken down by a property of each recording's reference: number of speakers, or overlap.

Recordings are grouped by the property; within a group, errors and reference words are summed over recordings
(of all chosen datasets) and divided. Everything comes from stored scores and references, nothing is rerun.

  speakers  distinct speakers in the reference
  overlap   share of speech time with two or more reference speakers talking, from the reference segment
            times (segments include short pauses, so this reads slightly high; the same for every provider).
            Recordings whose reference has no times are grouped as "no times".
"""
from . import paths

# (low, high, label): a recording is in the group when low <= value < high
SPEAKER_GROUPS = [(1, 2, "1"), (2, 3, "2"), (3, 4, "3"), (4, 5, "4"), (5, 9, "5-8"), (9, float("inf"), "9+")]
OVERLAP_GROUPS = [(0, 15, "<15%"), (15, 30, "15-30%"), (30, 50, "30-50%"), (50, float("inf"), "50%+")]
DEFAULT_DATASETS = ["notsofar", "ami", "chime6"]   # the English main meeting sets


def reference_stats(dataset: str) -> dict:
    """Recording id -> {"speakers": n, "overlap": percent of speech time, or None without times}."""
    segments = {}
    for s in paths.references(dataset):
        segments.setdefault(s["session_id"], []).append(s)
    return {rid: {"speakers": len({s["speaker"] for s in segs}), "overlap": overlap_percent(segs)}
            for rid, segs in segments.items()}


def overlap_percent(segments: list[dict]) -> float | None:
    if any(s["start_time"] is None or s["end_time"] is None for s in segments):
        return None
    # +1 / -1 at each speaker's merged speech boundaries, then sweep: time with >=1 and >=2 speakers active
    events = []
    for speaker in {s["speaker"] for s in segments}:
        for start, end in _merge([(s["start_time"], s["end_time"]) for s in segments if s["speaker"] == speaker]):
            events += [(start, 1), (end, -1)]
    speech = both = 0.0
    active, last = 0, None
    for t, step in sorted(events):
        if last is not None:
            speech += (t - last) * (active >= 1)
            both += (t - last) * (active >= 2)
        active, last = active + step, t
    return 100 * both / speech if speech else 0.0


def _merge(intervals: list[tuple]) -> list[tuple]:
    merged = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def group_of(value: float | None, groups: list) -> str:
    if value is None:
        return "no times"
    return next(label for low, high, label in groups if low <= value < high)


def table(by: str, metric: str = "cpwer", providers: list[str] | None = None, datasets: list[str] | None = None) -> str:
    """Markdown table (also written to results/breakdown/) of pooled error rates per provider and group."""
    groups = SPEAKER_GROUPS if by == "speakers" else OVERLAP_GROUPS
    score_files = sorted((paths.RESULTS / "scores" / metric).glob("*/*.json"))
    datasets = datasets or DEFAULT_DATASETS   # English only by default: Mandarin is scored per character, not per word
    scores = [paths.read_json(f) for f in score_files]
    scores = [s for s in scores if (not providers or s["provider"] in providers) and s["dataset"] in datasets]
    stats = {d: reference_stats(d) for d in {s["dataset"] for s in scores}}

    pooled = {}  # (provider, group) -> [errors, words, recordings, missed speakers, invented speakers]
    for s in scores:
        for rid, r in s["per_recording"].items():
            group = group_of(stats[s["dataset"]][rid][by], groups)
            cell = pooled.setdefault((s["provider"], group), [0, 0, 0, 0, 0])
            cell[0] += r["errors"]
            cell[1] += r["length"]
            cell[2] += 1
            cell[3] += r.get("missed_speakers") or 0
            cell[4] += r.get("invented_speakers") or 0
    labels = [label for *_, label in groups] + ["no times"]
    labels = [g for g in labels if any(k[1] == g for k in pooled)]
    lines = [f"| {metric} (%) by {by} | " + " | ".join(labels) + " |", "|---" * (len(labels) + 1) + "|"]
    for p in sorted({k[0] for k in pooled}):
        cells = []
        for g in labels:
            c = pooled.get((p, g))
            cells.append("" if not c else f"{100 * c[0] / c[1]:.2f} ({c[2]})" if c[1] else f"- ({c[2]})")
        lines.append(f"| {p} | " + " | ".join(cells) + " |")
    if by == "speakers":
        lines += ["", "| speakers missed / invented, per recording | " + " | ".join(labels) + " |",
                  "|---" * (len(labels) + 1) + "|"]
        for p in sorted({k[0] for k in pooled}):
            cells = [f"{c[3] / c[2]:.2f} / {c[4] / c[2]:.2f}" if (c := pooled.get((p, g))) else "" for g in labels]
            lines.append(f"| {p} | " + " | ".join(cells) + " |")
    text = "\n".join(lines) + "\n\nCells: pooled error rate (recordings in the group).\n"
    out = paths.RESULTS / "breakdown" / f"{metric}_by_{by}"
    paths.write_json(out.with_suffix(".json"), {f"{p}|{g}": dict(zip(
        ["errors", "length", "recordings", "missed_speakers", "invented_speakers"], c)) for (p, g), c in pooled.items()})
    out.with_suffix(".md").write_text(text)
    return text
