"""Send every recording of the chosen datasets to the chosen providers, once, and keep the raw responses.

Each provider gets one concurrency limit shared across all datasets (limits are per account): that many workers
send the requests in order, longest recording first, so no long file starts last. Run one process per provider
when several run at once: response handling is CPU work, and one process uses one core. A recording that already
has a raw response is skipped, so a run can be stopped and restarted. Failures are written to results/errors/ and
can be retried by running again after deleting the error file.

Files longer than a provider's per-request limit are sent as equal parts that overlap by two minutes, each as its
own request; the raw record then holds one response per part with the part's start and end (bench/stitch.py joins
them).
"""
import asyncio
import collections
import math
import os
import resource
import tempfile
import time
import wave
from datetime import datetime, timezone
from pathlib import Path

import httpx

from . import paths, stitch
from .providers import load
from .providers.base import ATTEMPTS, request_ids

TIMEOUT = httpx.Timeout(connect=60, read=3600, write=900, pool=None)


async def run(providers: list[str], datasets: list[str], concurrency: int | None = None, sample: float = 1.0) -> None:
    # Hundreds of requests can be in flight at once, each holding a socket and a file.
    resource.setrlimit(resource.RLIMIT_NOFILE, (hard := resource.getrlimit(resource.RLIMIT_NOFILE)[1], hard))
    await asyncio.gather(*(_run_provider(p, datasets, concurrency, sample) for p in providers))


def sampled(recordings: list[dict], fraction: float) -> list[dict]:
    """Every k-th recording by id (at least one), for a quick timed trial on a fixed subset."""
    if fraction >= 1:
        return recordings
    step = max(1, round(1 / fraction))
    return sorted(recordings, key=lambda r: r["id"])[::step]


async def _run_provider(name: str, datasets: list[str], concurrency: int | None, sample: float) -> None:
    provider = load(name)
    jobs = [(d, r) for d in datasets for r in sampled(paths.manifest(d), sample)
            if not paths.raw_path(name, d, r["id"]).exists() and not paths.error_path(name, d, r["id"]).exists()]
    jobs.sort(key=lambda job: -job[1]["duration"])  # longest first, so no long file starts last
    # (dataset, recording, part, spans): one request per recording, or per part of a file over the limit
    requests = iter([(d, r, k, spans) for d, r in jobs for spans in [_spans(provider, r)] for k in range(len(spans))])
    progress = Progress(name, datasets, jobs)
    rate = Rate(provider.settings.get("rate_limit"))
    answered, failed = {}, set()  # parts answered so far per split recording; recordings that failed

    async def worker(client, folder: Path) -> None:
        for dataset, rec, k, spans in requests:
            if (dataset, rec["id"]) in failed:
                continue
            n = len(spans)
            try:
                call = await _request(provider, client, rate, dataset, rec, spans[k] if n > 1 else None, folder)
            except Exception as e:
                failed.add((dataset, rec["id"]))
                paths.write_json(paths.error_path(provider.name, dataset, rec["id"]), {
                    "provider": provider.name, "dataset": dataset, "recording": rec["id"],
                    "failed_at": _utc(time.time()), "error": _describe(e, provider.key),
                    "retried_attempts": getattr(e, "retried_attempts", [])})
                progress.failed(dataset, rec, e)
                continue
            if n > 1:
                done = answered.setdefault((dataset, rec["id"]), {})
                done[k] = call
                if len(done) < n:
                    continue
                del answered[(dataset, rec["id"])]
                parts = [done[i] for i in range(n)]
                call = {"submitted_at": min(c["submitted_at"] for c in parts),
                        "completed_at": max(c["completed_at"] for c in parts),
                        "response": {"overlap": stitch.OVERLAP, "parts": parts}}
            paths.write_json(paths.raw_path(provider.name, dataset, rec["id"]), {
                "provider": provider.name,
                "model": provider.model,
                "dataset": dataset,
                "recording": rec["id"],
                "audio_sha256": rec["sha256"],
                "audio_seconds": rec["duration"],
                "request": provider.request(rec["language"], dataset),
                **call,
            })
            progress.done(rec)

    with tempfile.TemporaryDirectory() as folder:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            ticker = asyncio.create_task(progress.tick())
            workers = concurrency or provider.settings["concurrency"]
            await asyncio.gather(*(worker(client, Path(folder)) for _ in range(workers)))
            ticker.cancel()
    progress.finish()


async def _request(provider, client, rate, dataset: str, rec: dict, span: tuple | None, folder: Path) -> dict:
    """One request (the whole file, or the part `span`), timed from the moment it is sent (after its turn, if the
    provider is rate-limited)."""
    audio = paths.DATA / dataset / rec["audio"]
    if span:
        audio = cut_span(audio, *span, folder)
    try:
        await rate.turn()
        started, t0 = time.time(), time.monotonic()
        ATTEMPTS.set(retried := [])
        try:
            response = await provider.transcribe(client, audio, rec["language"], dataset)
        except Exception as e:
            e.retried_attempts = [{**a, "at": _utc(a["at"])} for a in retried]
            raise
    finally:
        if span:
            audio.unlink()
    call = {"submitted_at": _utc(started), "completed_at": _utc(time.time()),
            "elapsed_seconds": round(time.monotonic() - t0, 3), "response": response}
    if retried:   # attempts that failed and were retried, for tracing with the provider
        call["retried_attempts"] = [{**a, "at": _utc(a["at"])} for a in retried]
    return {"start": span[0], "end": span[1], **call} if span else call


class Rate:
    """A provider's published request-rate limit, `rate_limit: [requests, seconds]`: at most that many requests start
    in any window of that many seconds. turn() waits for a place, first come first served, and returns how long
    it waited."""

    def __init__(self, limit: list | None = None):
        self.requests, self.seconds = limit or (0, 0)
        self.starts = collections.deque()
        self.queue = asyncio.Lock()

    async def turn(self) -> float:
        if not self.requests:
            return 0.0
        t0, waited = time.monotonic(), self.queue.locked()
        async with self.queue:
            while True:
                now = time.monotonic()
                while self.starts and self.starts[0] <= now - self.seconds:
                    self.starts.popleft()
                if len(self.starts) < self.requests:
                    self.starts.append(now)
                    return now - t0 if waited else 0.0
                await asyncio.sleep(self.starts[0] + self.seconds - now)
                waited = True


def _spans(provider, rec: dict) -> list[tuple | None]:
    """[None] for a whole file, else the (start, end) seconds of its overlapping parts."""
    if not provider.max_seconds or rec["duration"] <= provider.max_seconds:
        return [None]
    return stitch.plan(rec["duration"], provider.max_seconds)


def cut_span(audio: Path, start: float, end: float, folder: Path) -> Path:
    """The stretch [start, end) seconds of a WAV, as its own file."""
    with wave.open(str(audio)) as w:
        rate = w.getframerate()
        w.setpos(int(start * rate))
        path = folder / f"{audio.stem}.{start:.0f}s.wav"
        with wave.open(str(path), "wb") as out:
            out.setparams(w.getparams())
            out.writeframes(w.readframes(int((end - start) * rate)))
        return path


def cut(audio: Path, k: int, n: int, folder: Path) -> tuple[float, Path]:
    """Part k of n equal, non-overlapping parts of a WAV (the speed test); returns (start seconds, part)."""
    with wave.open(str(audio)) as w:
        size = math.ceil(w.getnframes() / n)
        w.setpos(k * size)
        path = folder / f"{audio.stem}.part{k}.wav"
        with wave.open(str(path), "wb") as out:
            out.setparams(w.getparams())
            out.writeframes(w.readframes(size))
        return k * size / w.getframerate(), path


def _utc(t: float) -> str:
    return datetime.fromtimestamp(t, timezone.utc).isoformat(timespec="milliseconds")


def _describe(e: Exception, secret: str) -> str:
    text = f"{type(e).__name__}: {e}"
    if isinstance(e, httpx.HTTPStatusError):
        text += f" | request ids: {request_ids(e.response)} | body: {e.response.text[:2000]}"
    return text.replace(secret, "<key>") if secret else text


class Progress:
    """One status line per minute in logs/<provider>.log, every error as it happens, and a final line."""

    def __init__(self, provider: str, datasets: list[str], jobs: list):
        self.path = paths.LOGS / f"{provider}.log"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.total, self.hours = len(jobs), sum(r["duration"] for _, r in jobs) / 3600
        self.n = self.failures = 0
        self.done_hours = 0.0
        self.t0 = time.monotonic()
        self._write(f"start {provider}: {self.total} recordings, {self.hours:.2f} audio-h, datasets {','.join(datasets)}")

    def done(self, rec: dict) -> None:
        self.n += 1
        self.done_hours += rec["duration"] / 3600

    def failed(self, dataset: str, rec: dict, e: Exception) -> None:
        self.n += 1
        self.failures += 1
        self._write(f"ERROR {dataset}/{rec['id']}: {type(e).__name__}")

    async def tick(self) -> None:
        while True:
            await asyncio.sleep(60)
            hours = (time.monotonic() - self.t0) / 3600
            rate = self.done_hours / hours if hours else 0.0
            eta = (self.hours - self.done_hours) / rate * 60 if rate else float("nan")
            self._write(f"{self.n}/{self.total} recordings, {self.done_hours:.2f}/{self.hours:.2f} audio-h, "
                        f"{rate:.1f} audio-h/h, {self.failures} failed, ETA {eta:.0f} min")

    def finish(self) -> None:
        state = "done" if not self.failures else "done with failures"
        self._write(f"{state}: {self.n - self.failures} ok, {self.failures} failed of {self.total}")

    def _write(self, line: str) -> None:
        with self.path.open("a") as f:
            f.write(f"{_utc(time.time())} {line}\n")
        if os.environ.get("BENCH_QUIET") != "1":
            print(line, flush=True)
