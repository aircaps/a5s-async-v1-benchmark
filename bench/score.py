"""Score hypotheses against references with MeetEval.

cpWER (concatenated minimum-permutation WER) is the headline metric: it counts word errors after the best
one-to-one mapping between reference and hypothesis speakers, so it measures words and speaker attribution
together. tcpWER and tcORC-WER (5 s collar) need word times and are available from the same stored outputs.

A recording the provider failed to return is scored as an empty hypothesis (every reference word deleted) and
listed under "failed".

MeetEval's cpWER stops at more than 20 speakers on either side, as a guard against input mistakes
(doc/num_speaker_limits.md). Some recordings really have more: Earnings-22 calls with 23 speakers, and files a
provider takes in parts, whose speakers are counted per part. Those sessions are scored by `cpwer_without_limit`,
MeetEval's own cpWER computation with that guard left out (the speaker assignment is a linear assignment, so its
cost grows only polynomially with the number of speakers).
"""
from meeteval.io import SegLST
from meeteval.wer import api
from meeteval.wer.matching.cy_levenshtein import levenshtein_distance
from meeteval.wer.preprocess import preprocess
from meeteval.wer.wer.cp import CPErrorRate, _minimum_permutation_assignment, apply_cp_assignment
from meeteval.wer.wer.error_rate import ErrorRate
from meeteval.wer.wer.siso import _siso_error_rate

from . import paths
from .normalize import normalize

METRICS = {
    "cpwer": lambda ref, hyp: api.cpwer(ref, hyp),
    "tcpwer": lambda ref, hyp: api.tcpwer(ref, hyp, collar=5),
    "tcorcwer": lambda ref, hyp: api.tcorcwer(ref, hyp, collar=5),
}


def score(provider: str, dataset: str, metric: str = "cpwer", strict: bool = False) -> dict:
    recordings = {r["id"]: r for r in paths.manifest(dataset)}
    ref = _normalized(paths.references(dataset), recordings)
    hyp = _normalized(paths.read_json(paths.hypothesis_path(provider, dataset, strict)), recordings)
    failed = sorted(i for i in recordings if not paths.raw_path(provider, dataset, i).exists()
                    and not (strict and paths.raw_path(provider, dataset, i, strict=True).exists()))
    # MeetEval needs every session on both sides; an empty segment stands in for "no output", and for a reference
    # with no words (silence, or only fillers the normaliser removes), so whatever a provider wrote there counts
    # as insertions.
    stand_in = lambda i: {"session_id": i, "speaker": "none", "start_time": 0.0, "end_time": 0.0, "words": ""}
    in_hyp, in_ref = {s["session_id"] for s in hyp}, {s["session_id"] for s in ref}
    empty, blank = [i for i in recordings if i not in in_hyp], [i for i in recordings if i not in in_ref]
    hyp += [stand_in(i) for i in empty]
    ref += [stand_in(i) for i in blank]

    ref, hyp = SegLST(ref), SegLST(hyp)
    many = {i for s in (ref, hyp) for i, g in s.groupby("session_id").items() if len(g.unique("speaker")) > 20}
    if metric == "cpwer" and many:
        refs, hyps = ref.groupby("session_id"), hyp.groupby("session_id")
        results = {i: cpwer_without_limit(refs[i], hyps[i]) for i in many}
        ref, hyp = (s.filter(lambda seg: seg["session_id"] not in many) for s in (ref, hyp))
        results |= METRICS[metric](ref, hyp) if len(ref) else {}
    else:
        results = METRICS[metric](ref, hyp)
    per_recording = {i: {"errors": e.errors, "length": e.length, "insertions": e.insertions,
                         "deletions": e.deletions, "substitutions": e.substitutions,
                         "error_rate": e.error_rate,
                         # speakers: in the reference, with no hypothesis speaker mapped, invented by the provider
                         "reference_speakers": getattr(e, "scored_speaker", None),
                         "missed_speakers": getattr(e, "missed_speaker", None),
                         "invented_speakers": getattr(e, "falarm_speaker", None)}
                     for i, e in sorted(results.items())}
    for i in empty:  # the stand-in segment is not a speaker the provider found
        r = per_recording[i]
        if r["reference_speakers"] is not None:
            r["missed_speakers"], r["invented_speakers"] = r["reference_speakers"], 0
    for i in blank:  # nor is it a reference speaker
        r = per_recording[i]
        if r["reference_speakers"] is not None:
            r["reference_speakers"], r["missed_speakers"] = 0, 0
            r["invented_speakers"] = 0 if i in empty else r["invented_speakers"] + 1
    errors = sum(r["errors"] for r in per_recording.values())
    length = sum(r["length"] for r in per_recording.values())
    summary = {"metric": metric, "provider": provider, "dataset": dataset,
               "recordings": len(recordings), "failed": failed,
               "errors": errors, "length": length, "error_rate": errors / length,
               "per_recording": per_recording}
    paths.write_json(paths.score_path(metric, provider, dataset, strict), summary)
    return summary


def cpwer_without_limit(reference: SegLST, hypothesis: SegLST) -> CPErrorRate:
    """MeetEval 0.4.3's cp_word_error_rate for one session, step for step, without the 20-speaker guard."""
    reference, hypothesis, _, _ = preprocess(
        reference, hypothesis, keep_keys=("speaker", "words"), remove_empty_segments=False,
        reference_sort="segment_if_available", hypothesis_sort="segment_if_available", segment_representation="segment")
    ref, hyp = ({k: [w for words in v.T["words"] for w in words] for k, v in s.groupby("speaker").items()}
                for s in (reference, hypothesis))
    speakers = len(ref), len(hyp)
    assignment, distance, _ = _minimum_permutation_assignment(ref, hyp, levenshtein_distance, SegLST([]))
    if assignment:  # an unpaired speaker is paired with an empty stand-in, one name per stand-in
        ref, hyp = apply_cp_assignment(assignment, reference=ref, hypothesis=hyp, missing=SegLST([]),
                                       fallback_keys=[f"unpaired {k}" for k in range(sum(speakers))])
    er = sum((_siso_error_rate(r, hyp[k]) for k, r in ref.items()), start=ErrorRate.zero())
    assert distance == er.errors, (distance, er)
    return CPErrorRate(er.errors, er.length, insertions=er.insertions, deletions=er.deletions,
                       substitutions=er.substitutions, missed_speaker=max(0, speakers[0] - speakers[1]),
                       falarm_speaker=max(0, speakers[1] - speakers[0]), scored_speaker=speakers[0],
                       assignment=assignment, reference_self_overlap=None, hypothesis_self_overlap=None)


def _normalized(segments: list[dict], recordings: dict) -> list[dict]:
    """Normalise words per the recording's language; drop segments left empty; fill missing times.
    An end before its start (one official CHiME-6 reference segment) is set to the start, as MeetEval requires."""
    out = []
    for s in _runs(segments):
        words = normalize(s["words"], recordings[s["session_id"]]["language"])
        if words:
            start = s["start_time"] if s["start_time"] is not None else 0.0
            end = s["end_time"] if s["end_time"] is not None else start
            out.append({**s, "words": words, "start_time": start, "end_time": max(start, end)})
    return out


RUN_GAP_S = 1.0     # a speaker's run continues across a pause of at most this long


def _runs(segments: list[dict]) -> list[dict]:
    """Join each speaker's segments into runs (in time order within a recording), one segment per run.

    The normaliser's rules depend on context ("twenty five" is "25", but "twenty" and "five" alone are "20" and
    "5"), and some providers and references give one entry per word, so text is normalised per run, not per entry.
    A speaker's run goes on while that speaker keeps talking, a pause of at most RUN_GAP_S since the run's last
    word, even where another speaker's words fall in between (a "yeah" from someone else does not cut a sentence
    or a number in two). A recording without times is joined by consecutive entries of one speaker.
    """
    sessions = {}
    for s in segments:
        sessions.setdefault(s["session_id"], []).append(s)
    out = []
    for segs in sessions.values():
        if not all(s["start_time"] is not None for s in segs):
            out += _consecutive(segs)
            continue
        runs, current, prev = [], {}, None      # current: each speaker's latest run
        for s in sorted(segs, key=lambda s: s["start_time"]):
            run = current.get(s["speaker"])
            pause = s["start_time"] - run["end_time"] if run is not None and run["end_time"] is not None else None
            if run is not None and (prev == s["speaker"] or (pause is not None and pause <= RUN_GAP_S)):
                ends = [t for t in (run["end_time"], s["end_time"]) if t is not None]
                run.update(words=f"{run['words']} {s['words']}", end_time=max(ends) if ends else None)
            else:
                run = dict(s)
                runs.append(run)
                current[s["speaker"]] = run
            prev = s["speaker"]
        out += runs
    return out


def _consecutive(segs: list[dict]) -> list[dict]:
    """One recording's consecutive segments by one speaker joined, in the order given."""
    out = []
    for s in segs:
        if out and out[-1]["speaker"] == s["speaker"]:
            last = out[-1]
            ends = [t for t in (last["end_time"], s["end_time"]) if t is not None]
            last.update(words=f"{last['words']} {s['words']}", end_time=max(ends) if ends else None)
        else:
            out.append(dict(s))
    return out
