"""Where everything lives. Data is local and never committed; results are committed."""
import gzip
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"          # prepared audio, manifests, references (built by `bench prep`)
RESULTS = ROOT / "results"    # raw responses, hypotheses, scores (published)
STRICT = RESULTS / "strict"   # the same, scored strictly: no speaker linked across the parts of a split file
LOGS = ROOT / "logs"          # progress logs of runs (not published)


def manifest(dataset: str) -> list[dict]:
    """One dict per recording: id, audio, duration, language, sha256, source."""
    path = DATA / dataset / "manifest.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def references(dataset: str) -> list[dict]:
    """Reference transcript as SegLST: session_id, speaker, start_time, end_time, words."""
    return json.loads((DATA / dataset / "references.seglst.json").read_text())


def raw_path(provider: str, dataset: str, recording: str, strict: bool = False) -> Path:
    """`strict`: the raw response from the first run, whose parts did not overlap (only where one was kept)."""
    return (STRICT if strict else RESULTS) / "raw" / provider / dataset / f"{recording}.json.gz"


def error_path(provider: str, dataset: str, recording: str) -> Path:
    return RESULTS / "errors" / provider / dataset / f"{recording}.json"


def hypothesis_path(provider: str, dataset: str, strict: bool = False) -> Path:
    return (STRICT if strict else RESULTS) / "hyp" / provider / f"{dataset}.seglst.json.gz"


def score_path(metric: str, provider: str, dataset: str, strict: bool = False) -> Path:
    return (STRICT if strict else RESULTS) / "scores" / metric / provider / f"{dataset}.json"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def write_json(path: Path, obj) -> None:
    """Atomic write; `.gz` paths are gzip-compressed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(obj, ensure_ascii=False, indent=1).encode()
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(gzip.compress(data, compresslevel=6, mtime=0) if path.suffix == ".gz" else data)
    tmp.replace(path)


def read_json(path: Path):
    data = path.read_bytes()
    return json.loads(gzip.decompress(data) if path.suffix == ".gz" else data)
