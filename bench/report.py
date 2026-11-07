"""Results tables (results/<metric>.md), laid out like the A5S Async v1 report: the main meeting sets and their macro,
the supplementary sets, easier speech, the internal recordings and the error composition. Pooled error rates in %,
from the stored scores only."""
from . import paths

MAIN = ["notsofar", "ami", "chime6", "aishell4", "alimeeting"]   # macro: unweighted mean of these five
ENGLISH_MAIN = ["notsofar", "ami", "chime6"]
SUPPLEMENTARY = ["icsi", "dipco", "agentic"]
SINGLE = ["voxpopuli", "openasr_librispeech_clean", "openasr_earnings22"]   # single-speaker clips; "mean" below
NAMES = {
    "notsofar": "NOTSOFAR-1", "ami": "AMI", "chime6": "CHiME-6", "aishell4": "AISHELL-4 (cpCER)",
    "alimeeting": "AliMeeting (cpCER)", "icsi": "ICSI", "dipco": "DiPCo", "agentic": "Agentic", "dai_en": "DAI English",
    "voxpopuli": "VoxPopuli", "openasr_librispeech_clean": "LibriSpeech test-clean", "openasr_earnings22": "Earnings-22 clips",
}
INTERNAL = {   # published recording id -> name
    "office_meeting_1": "Office meeting 1", "office_meeting_2": "Office meeting 2", "office_meeting_3": "Office meeting 3",
    "adhoc_technical_discussion": "Ad-hoc technical discussion", "office_meeting_4": "Office meeting 4",
    "high_overlap_crosstalk": "High-overlap crosstalk", "open_plan_office": "Open-plan office",
}


def _scores(metric: str, strict: bool = False) -> dict:
    root = (paths.STRICT if strict else paths.RESULTS) / "scores" / metric
    return {(s["provider"], s["dataset"]): s for s in map(paths.read_json, sorted(root.glob("*/*.json")))}


def _rate(errors: float, length: float) -> float:
    return round(100 * errors / length, 2)


def _cell(value) -> str:
    return "" if value is None else f"{value:.2f}"


def _table(head: list[str], rows: list[list]) -> list[str]:
    return ["| " + " | ".join(head) + " |", "|---" * len(head) + "|"] + ["| " + " | ".join(r) + " |" for r in rows]


def table(metric: str = "cpwer") -> str:
    scores, strict = _scores(metric), _scores(metric, strict=True)
    providers = sorted({p for p, _ in scores})
    rate = lambda p, d: _rate(scores[(p, d)]["errors"], scores[(p, d)]["length"]) if (p, d) in scores else None

    def macro(p, source):
        values = [source(p, d) for d in MAIN]
        return None if None in values else round(sum(values) / len(values), 2)

    # strict: parts of a split recording scored as different speakers, where a provider had to split one
    strict_rate = lambda p, d: (_rate(strict[(p, d)]["errors"], strict[(p, d)]["length"])
                                if (p, d) in strict else rate(p, d))
    order = sorted(providers, key=lambda p: (macro(p, rate) is None, macro(p, rate) or 0))
    failed = {(p, d): len(s["failed"]) for (p, d), s in scores.items() if s["failed"]}

    out = [f"# {metric} results", "",
           "Pooled within each dataset (errors over reference words, in %). Mandarin sets are scored per character.",
           "Where a provider had to split a recording, its parts overlap and are joined without the reference;",
           "\"macro, strict\" scores those parts as different speakers instead.", "",
           "## Main meeting sets", ""]
    out += _table(["Provider"] + [NAMES[d] for d in MAIN] + ["Macro", "Macro, strict"],
                  [[p] + [_cell(rate(p, d)) for d in MAIN] + [_cell(macro(p, rate)), _cell(macro(p, strict_rate))]
                   for p in order])
    out += ["", "## Supplementary meeting sets", "",
            "Not in the macro. NVIDIA lists ICSI and DiPCo as Nemotron 3.5 Transcribe (`nvidia`) training data.", ""]
    out += _table(["Provider"] + [NAMES[d] for d in SUPPLEMENTARY],
                  [[p] + [_cell(rate(p, d)) for d in SUPPLEMENTARY] for p in order])

    single_mean = lambda p: (None if None in (v := [rate(p, d) for d in SINGLE]) else round(sum(v) / len(v), 2))
    out += ["", "## Easier speech", "",
            "Two-person conversations (DAI English) and single-speaker clips, where cpWER equals WER.", ""]
    out += _table(["Provider", NAMES["dai_en"]] + [NAMES[d] for d in SINGLE] + ["Mean, single-speaker"],
                  [[p, _cell(rate(p, "dai_en"))] + [_cell(rate(p, d)) for d in SINGLE] + [_cell(single_mean(p))]
                   for p in order])

    if any(d == "internal" for _, d in scores):
        per = lambda p, rid: (lambda r: _rate(r["errors"], r["length"]) if r else None)(
            scores[(p, "internal")]["per_recording"].get(rid) if (p, "internal") in scores else None)
        out += ["", "## Internal recordings", "", "7 recordings made by AirCaps (data not published).", ""]
        out += _table(["Provider", "All 7"] + list(INTERNAL.values()),
                      [[p, _cell(rate(p, "internal"))] + [_cell(per(p, rid)) for rid in INTERNAL] for p in order])

    def composition(p):
        rs = [r for d in ENGLISH_MAIN for r in scores[(p, d)]["per_recording"].values()] if all(
            (p, d) in scores for d in ENGLISH_MAIN) else []
        words = sum(r["length"] for r in rs)
        return [_cell(_rate(sum(r[k] for r in rs), words)) if words else "" for k in ("deletions", "substitutions", "insertions")]
    out += ["", "## Error composition, English main sets", "",
            "Pooled over NOTSOFAR-1, AMI and CHiME-6, in % of reference words.", ""]
    out += _table(["Provider", "Deletions", "Substitutions", "Insertions"], [[p] + composition(p) for p in order])

    if failed:
        out += ["", "Failed requests, scored as empty transcripts: " +
                ", ".join(f"{p} {d} {n}" for (p, d), n in sorted(failed.items())) + "."]
    out += ["", "By overlap and by number of speakers: [`breakdown/`](breakdown/). Speed: [`speed.md`](speed.md).", ""]
    text = "\n".join(out)
    (paths.RESULTS / f"{metric}.md").write_text(text)
    return text
