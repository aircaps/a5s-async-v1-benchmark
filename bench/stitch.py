"""Long recordings sent in overlapping parts, joined again without the reference.

A recording longer than a provider's per-request limit (`max_seconds`) is sent as the fewest equal parts no longer
than the limit, each overlapping the next by OVERLAP seconds. The parts are joined with only what a customer has:

1. The words at the end of one part are aligned with the words at the start of the next, as text (difflib on
   normalised tokens; Chinese by character), so no word times are needed. Only runs of two or more matching tokens
   count as aligned.
2. Speaker labels are linked across the two parts one-to-one, by how many aligned words they share (Hungarian
   assignment, most shared first). A label with no shared words stays a new speaker.
3. The duplicated stretch is cut at the middle aligned pair: the earlier part keeps the words before it, the later
   part the words from it on. With nothing aligned, each part keeps half of the overlap window.

The reference is never used, so this is the most a customer could do with the provider's own output. Scoring the
same responses strictly, with a separate set of speakers per part, is `bench hyp --strict`.
"""
import difflib
import math
import re

from scipy.optimize import linear_sum_assignment

OVERLAP = 120.0   # seconds shared by consecutive parts
CJK = re.compile(r"[㐀-鿿]")


def plan(seconds: float, limit: float) -> list[tuple[float, float]]:
    """(start, end) of the fewest equal parts no longer than `limit` that overlap by OVERLAP seconds."""
    n = math.ceil((seconds - OVERLAP) / (limit - OVERLAP))
    length = (seconds + (n - 1) * OVERLAP) / n
    return [(k * (length - OVERLAP), min(seconds, k * (length - OVERLAP) + length)) for k in range(n)]


def tokens(text: str) -> list[str]:
    """Words, or characters for Chinese (written without spaces between words)."""
    return [c for c in text if not c.isspace()] if CJK.search(text) else text.split()


def _norm(token: str) -> str:
    return re.sub(r"[^\w']+", "", token.lower())


def stitch(provider, parts: list[dict], overlap: float) -> tuple[list[dict], list[dict]]:
    """Join the parts' words. Returns SegLST-style entries (one per token, speakers linked across parts, times in
    the whole recording) and, per joint, how many words were aligned and how many speakers linked."""
    words = [[{"speaker": w.speaker, "token": tok,
               "start": None if w.start is None else part["start"] + w.start,
               "end": None if w.end is None else part["start"] + w.end}
              for w in provider.words(part["response"]) for tok in tokens(w.text)] for part in parts]
    length = parts[0]["end"] - parts[0]["start"]
    window = min(1.0, 1.5 * overlap / length)   # share of each part's words searched for the overlap
    names = [{s: f"p0:{s}" for s in {w["speaker"] for w in words[0]}}]
    keep = [[0, len(ws)] for ws in words]
    joints = []
    for k in range(1, len(words)):
        prev, cur = words[k - 1], words[k]
        na, nb = math.ceil(len(prev) * window), math.ceil(len(cur) * window)
        off = len(prev) - na
        a, b = [_norm(w["token"]) for w in prev[off:]], [_norm(w["token"]) for w in cur[:nb]]
        pairs = [(off + m.a + i, m.b + i) for m in difflib.SequenceMatcher(None, a, b, autojunk=False).get_matching_blocks()
                 if m.size >= 2 for i in range(m.size)]
        linked = {}
        if pairs:
            earlier = sorted({names[k - 1][prev[i]["speaker"]] for i, _ in pairs})
            later = sorted({cur[j]["speaker"] for _, j in pairs})
            shared = [[sum(1 for i, j in pairs if names[k - 1][prev[i]["speaker"]] == e and cur[j]["speaker"] == l)
                       for l in later] for e in earlier]
            rows, cols = linear_sum_assignment([[-n for n in row] for row in shared])
            linked = {later[c]: earlier[r] for r, c in zip(rows, cols) if shared[r][c] > 0}
            cut_prev, cut_cur = pairs[len(pairs) // 2]
        else:
            cut_prev, cut_cur = len(prev) - na // 2, nb // 2
        keep[k - 1][1], keep[k][0] = cut_prev, cut_cur
        names.append({s: linked.get(s, f"p{k}:{s}") for s in {w["speaker"] for w in cur}})
        joints.append({"aligned_words": len(pairs), "linked_speakers": len(linked)})
    segments = [{"speaker": names[k][w["speaker"]], "start_time": w["start"], "end_time": w["end"], "words": w["token"]}
                for k, ws in enumerate(words) for w in ws[keep[k][0]:keep[k][1]]]
    return segments, joints
