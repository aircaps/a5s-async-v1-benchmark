"""End-to-end API speed test, run apart from the accuracy run: how fast each provider's public API turns an
hour-long meeting into a speaker-labelled transcript, one request at a time and with several in flight.

Audio: every English multi-speaker meeting of 45-75 minutes in the benchmark (AMI EN2002c; ICSI Bmr013, Bmr018,
Bro021; DiPCo S01, S03, S04, S05: 8 meetings, 6.4 h), whole, sent with the accuracy run's request settings
(speaker labels on, language English, nothing else). Shorter recordings are not part of the speed test.

Tests, in this order for each provider; all providers run at the same time, one process each:
  C   latency         one untimed meeting, then each meeting one at a time (the parts of a split file are sent
                      together, as a customer would send them);
  B2  throughput      every meeting twice per round (16 requests), 14 in flight, 3 rounds; one untimed wave first.

Rules:
- Order: the same for every provider, longest file first, with the parts of split files (files over the
  provider's per-request limit, `max_seconds`, sent as parts overlapping by two minutes, as in the accuracy run)
  before whole files.
- In flight counts requests, as providers count them against account limits: each part of a split file is one.
  A provider's own limits apply on top: `concurrency`, and ElevenLabs' rule that a file over 8 minutes takes 4 of
  its concurrency slots (`slots`). A test where they bind is flagged as plan-limited.
- Latency of a file: from sending its (first) request to having the whole transcript, uploads, polls and retries
  included; a split file is done when its last part is back. Throughput: in flight x audio / latency over the
  requests (Little's law).
- Published request-rate limits (`rate_limit`) are kept on the client. Cap gate: every 429 response and every wait
  on the client's rate limiter is counted, and a test with either is reported as limited, not as speed.
- Every retried attempt is kept with its request (status, the provider's request-ID headers, start of the body).
- The client is measured too: the machine's CPU and network every 5 s, and per provider process its CPU use and
  event-loop lag (how late a 1 s timer fires), to show the client was not the bottleneck.

Output in results/speed/: <provider>/requests.jsonl (one line per request), <provider>/summary.json (per test and
round: wall time, 429s and other retries, rate-limit waits, failures, process CPU and loop lag) and client.jsonl.
"""
import asyncio
import collections
import json
import math
import shutil
import statistics
import sys
import tempfile
import time
from pathlib import Path

import httpx

from . import paths, stitch
from .providers import load
from .providers.base import ATTEMPTS, RETRIES
from .run import TIMEOUT, Rate, _describe, _utc, cut_span

SETS = ("ami", "icsi", "dipco")          # English multi-speaker sets with meetings of about an hour
HOUR = (45 * 60, 75 * 60)                # the meetings tested
BANDS = (("45-75 min", *HOUR),)
LEVELS = {"C": 1, "B2": 14}
ROUNDS = {"C": 1, "B2": 3}
TESTS = ("C", "B2")
OUT = paths.RESULTS / "speed"


def meetings(sets=SETS) -> list[dict]:
    return [{"id": f"{d}/{r['id']}", "dataset": d, "seconds": r["duration"], "audio": f"{d}/{r['audio']}"}
            for d in sets for r in paths.manifest(d) if HOUR[0] <= r["duration"] <= HOUR[1]]


def recording(file_id: str) -> str:
    """dataset/recording of a request's file id (a repeated file carries a #k suffix)."""
    return file_id.split("#")[0]


def plan(tests=TESTS, rounds: int | None = None, sample: float = 1.0) -> list[tuple]:
    """(test, round, timed files, untimed files sent first) in the order they run; `rounds` overrides ROUNDS."""
    every = sorted(meetings(), key=lambda m: m["id"])
    if sample < 1:   # a trial: every k-th meeting
        every = every[::max(1, round(1 / sample))]
    twice = every + [{**m, "id": m["id"] + "#2"} for m in every]
    shortest = min(every, key=lambda m: m["seconds"])
    out = [("C", 1, every, [{**shortest, "id": shortest["id"] + "#warm"}])] if "C" in tests else []
    for k in range(1, (rounds or ROUNDS["B2"]) + 1):
        out += [("B2", k, twice, [])] if "B2" in tests else []
    return out


class Provider:
    """One provider's run: its client, rate limiter, request log and summary."""

    def __init__(self, name: str, folder: Path, client: httpx.AsyncClient):
        self.api = load(name)
        self.folder, self.client = folder, client
        self.rate = Rate(self.api.settings.get("rate_limit"))
        self.limit = self.api.settings["concurrency"]
        self.slot_rule = self.api.settings.get("slots")   # {over_seconds, slots}: a long file takes several slots
        self.out = OUT / self.api.name
        if self.out.exists():
            raise SystemExit(f"{self.out} exists: move it away to run the speed test again")
        self.out.mkdir(parents=True)
        paths.LOGS.mkdir(parents=True, exist_ok=True)
        self.t0 = time.monotonic()
        self.lags: list[float] = []
        self.done = self.total = 0
        self.summary = {"provider": self.api.name, "model": self.api.model, "slots": self.slot_rule,
                        "rate_limit": self.api.settings.get("rate_limit"), "max_seconds": self.api.max_seconds,
                        "tests": []}

    def requests(self, files: list[dict]) -> list[tuple]:
        """(file, part, parts): parts of split files first, then whole files, longest first."""
        files = sorted(files, key=lambda f: (-f["seconds"], f["id"]))
        n = {f["id"]: len(self.spans(f)) for f in files}
        return ([(f, k, n[f["id"]]) for f in files if n[f["id"]] > 1 for k in range(n[f["id"]])] +
                [(f, 0, 1) for f in files if n[f["id"]] == 1])

    def spans(self, f: dict) -> list:
        """[None] for a whole file, else its overlapping parts' (start, end), as the accuracy run sends them."""
        limit = self.api.max_seconds
        return stitch.plan(f["seconds"], limit) if limit and f["seconds"] > limit else [None]

    def weight(self, req: tuple) -> int:
        f, _, n = req
        rule = self.slot_rule
        return rule["slots"] if rule and f["seconds"] / n > rule["over_seconds"] else 1

    async def test(self, name: str, rnd: int, files: list[dict], untimed: list[dict]) -> None:
        level = LEVELS[name]
        in_flight = min(level, self.limit)
        reqs = self.requests(files)
        counts = {True: collections.Counter(), False: collections.Counter()}   # retried responses: timed, untimed
        rows, busy = [], {"now": 0, "most": 0}
        self.done, self.total = 0, len(reqs)
        self.log(f"start {name} round {rnd}: {len(files)} files, {len(reqs)} requests, {in_flight} in flight")
        cpu, start, lag_start = time.process_time(), time.monotonic(), len(self.lags)

        async def go(req, timed):
            busy["now"] += 1
            if timed:
                busy["most"] = max(busy["most"], busy["now"])
            try:
                row = await self.send(req)
            finally:
                busy["now"] -= 1
            self.write({"test": name, "round": rnd, "timed": timed, **row})
            if timed:
                rows.append(row)
                self.done += 1

        if name == "C":   # one file at a time; a split file's parts together
            for f, timed in [(f, False) for f in untimed] + [(f, True) for f in files]:
                RETRIES.set(counts[timed])
                await asyncio.gather(*(go(req, timed) for req in self.requests([f])))
        else:
            requests, slots, tasks = asyncio.Semaphore(in_flight), asyncio.Semaphore(self.limit), []

            async def release_after(req, weight, timed):
                try:
                    await go(req, timed)
                finally:
                    requests.release()
                    for _ in range(weight):
                        slots.release()

            warm = [(req, False) for req in reqs[::-1][:in_flight]]   # one wave of the shortest files
            for req, timed in warm + [(req, True) for req in reqs]:
                await requests.acquire()
                weight = self.weight(req)
                for _ in range(weight):
                    await slots.acquire()
                RETRIES.set(counts[timed])
                tasks.append(asyncio.create_task(release_after(req, weight, timed)))
            await asyncio.gather(*tasks)

        wall = max(r["t_done"] for r in rows) - min(r["t_sent"] for r in rows) if rows else 0.0
        elapsed = time.monotonic() - start
        result = {"test": name, "round": rnd, "level": level, "in_flight": in_flight, "most_in_flight": busy["most"],
                  "files": len(files), "requests": len(rows), "audio_seconds": sum(f["seconds"] for f in files),
                  "wall_seconds": round(wall, 3), "failures": len({r["file"] for r in rows if r["error"]}),
                  "status_429": counts[True][429], "retried": {str(k): v for k, v in counts[True].items()},
                  "rate_waits": sum(r["rate_wait"] > 0 for r in rows),
                  "rate_wait_seconds": round(sum(r["rate_wait"] for r in rows), 3),
                  "untimed_429": counts[False][429],
                  "cpu_percent": round(100 * (time.process_time() - cpu) / elapsed, 1) if elapsed else 0.0,
                  "loop_lag_max_seconds": round(max(self.lags[lag_start:], default=0.0), 3)}
        self.summary["tests"].append(result)
        paths.write_json(self.out / "summary.json", self.summary)
        self.log(f"done {name} round {rnd}: {result['requests']} requests in {wall:.0f} s, {result['failures']} "
                 f"failed, {result['status_429']} 429s, {result['rate_waits']} rate waits")

    async def send(self, req: tuple) -> dict:
        """One request, timed from sending to having the answer (a part is cut first, untimed)."""
        f, k, n = req
        folder = Path(tempfile.mkdtemp(dir=self.folder))
        try:
            span = self.spans(f)[k]
            audio = cut_span(paths.DATA / f["audio"], *span, folder) if span else paths.DATA / f["audio"]
            wait = await self.rate.turn()
            ATTEMPTS.set(retried := [])
            sent, at = time.monotonic(), time.time()
            try:
                answer, error = await self.api.transcribe(self.client, audio, "en", f["dataset"]), None
            except Exception as e:
                answer, error = None, _describe(e, self.api.key)
            done = time.monotonic()
        finally:
            shutil.rmtree(folder)
        return {"file": f["id"], "file_seconds": round(f["seconds"], 3), "part": k, "parts": n,
                "seconds": round(span[1] - span[0] if span else f["seconds"], 3), "slots": self.weight(req), "sent_at": _utc(at),
                "t_sent": round(sent - self.t0, 3), "t_done": round(done - self.t0, 3),
                "latency": round(done - sent, 3), "rate_wait": round(wait, 3),
                "words": None if answer is None else len(self.api.words(answer)), "error": error,
                "retried_attempts": [{**a, "at": _utc(a["at"])} for a in retried]}

    def write(self, row: dict) -> None:
        with (self.out / "requests.jsonl").open("a") as f:
            f.write(json.dumps(row) + "\n")

    def log(self, line: str) -> None:
        with (paths.LOGS / f"speed_{self.api.name}.log").open("a") as f:
            f.write(f"{_utc(time.time())} {line}\n")

    async def watch(self) -> None:
        """Event-loop lag every second; a progress line every minute."""
        while True:
            for _ in range(60):
                t = time.monotonic()
                await asyncio.sleep(1)
                self.lags.append(time.monotonic() - t - 1)
            self.log(f"{self.done}/{self.total} timed requests of the current test done")


async def _run_provider(name: str, tests, rounds: int | None, sample: float) -> None:
    paths.LOGS.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as folder:
        limits = httpx.Limits(max_connections=None, max_keepalive_connections=None)
        async with httpx.AsyncClient(timeout=TIMEOUT, limits=limits) as client:
            p = Provider(name, Path(folder), client)
            watcher = asyncio.create_task(p.watch())
            for test, rnd, files, untimed in plan(tests, rounds, sample):
                await p.test(test, rnd, files, untimed)
            watcher.cancel()
            p.log("finished")


async def run(providers: list[str], tests=TESTS, rounds: int | None = None, sample: float = 1.0) -> None:
    """All providers at once, one process each, while this process samples the machine's CPU and network."""
    OUT.mkdir(parents=True, exist_ok=True)
    paths.LOGS.mkdir(parents=True, exist_ok=True)
    args = json.dumps({"tests": list(tests), "rounds": rounds, "sample": sample})
    procs = []
    for p in providers:
        with (paths.LOGS / f"speed_{p}.out").open("ab") as out:
            procs.append(await asyncio.create_subprocess_exec(sys.executable, "-m", "bench.speed", p, args,
                                                              stdout=out, stderr=out, cwd=paths.ROOT))
    monitor = asyncio.create_task(_monitor(OUT / "client.jsonl"))
    codes = await asyncio.gather(*(p.wait() for p in procs))
    monitor.cancel()
    if any(codes):
        raise SystemExit(f"speed test failed for {[p for p, c in zip(providers, codes) if c]}: see logs/speed_*.out")


async def _monitor(path: Path, every: float = 5.0) -> None:
    """The machine's CPU use and network traffic (Linux /proc), one line every `every` seconds."""
    def sample():
        cpu = [int(x) for x in Path("/proc/stat").read_text().split("\n")[0].split()[1:]]
        rx = tx = 0
        for line in Path("/proc/net/dev").read_text().splitlines()[2:]:
            name, data = line.split(":", 1)
            if name.strip() != "lo":
                fields = data.split()
                rx, tx = rx + int(fields[0]), tx + int(fields[8])
        return time.monotonic(), sum(cpu), cpu[3] + cpu[4], rx, tx

    if not Path("/proc/stat").exists():
        return
    last = sample()
    while True:
        await asyncio.sleep(every)
        now = sample()
        dt, total, idle = now[0] - last[0], now[1] - last[1], now[2] - last[2]
        row = {"at": _utc(time.time()), "cpu_percent": round(100 * (1 - idle / total), 1) if total else 0.0,
               "rx_MBps": round((now[3] - last[3]) / dt / 1e6, 2), "tx_MBps": round((now[4] - last[4]) / dt / 1e6, 2)}
        with path.open("a") as f:
            f.write(json.dumps(row) + "\n")
        last = now


def _pct(values, p):
    values = sorted(values)
    return values[max(0, math.ceil(p * len(values)) - 1)] if values else math.nan


def _files(rows):
    """Per file: audio seconds, latency (first send to last answer), failed."""
    by = collections.defaultdict(list)
    for r in rows:
        by[r["file"]].append(r)
    return [{"file": f, "seconds": rs[0]["file_seconds"], "failed": any(r["error"] for r in rs),
             "latency": max(r["t_done"] for r in rs) - min(r["t_sent"] for r in rs)} for f, rs in by.items()]


def _speed(files) -> float:
    """Audio length / latency over the files, weighted by audio hours (total audio over total latency)."""
    ok = [f for f in files if not f["failed"]]
    return sum(f["seconds"] for f in ok) / sum(f["latency"] for f in ok) if ok else math.nan


def _throughput(rows, in_flight) -> float:
    """Audio seconds per wall-clock second at `in_flight` requests: in flight x audio / latency over the requests
    (Little's law; exact while every slot is busy). Computed from requests, so it holds for any subset of files."""
    ok = [r for r in rows if not r["error"]]
    return in_flight * sum(r["seconds"] for r in ok) / sum(r["latency"] for r in ok) if ok else math.nan


def report() -> str:
    """Markdown tables from results/speed, and the accuracy-against-speed comparison. Only files of the
    hour-long meetings (SETS, HOUR) count; others in an older run's results are ignored."""
    def bands(files):
        ok = [f for f in files if not f["failed"]]
        cells = []
        for _, lo, hi in BANDS:
            t = [f["latency"] for f in ok if lo < f["seconds"] <= hi]
            cells.append(f"{statistics.median(t):.1f} / {_pct(t, .9):.1f}" if t else "")
        return cells

    def gate(t):
        if not t["status_429"] and not t["rate_waits"]:
            return "ok"
        return f"limited ({t['status_429']} 429s, {t['rate_waits']} waits)"

    def tput(name, t):
        return _throughput(rows[name][(t["test"], t["round"])], t["in_flight"])

    def median_round(s, test, name):
        runs = [t for t in s["tests"] if t["test"] == test and rows[name][(test, t["round"])]]
        return sorted(runs, key=lambda t: tput(name, t))[len(runs) // 2] if runs else None

    providers, rows = {}, {}
    for folder in sorted(p for p in OUT.iterdir() if (p / "summary.json").exists()):
        providers[folder.name] = paths.read_json(folder / "summary.json")
        rows[folder.name] = collections.defaultdict(list)
        for line in (folder / "requests.jsonl").read_text().splitlines():
            r = json.loads(line)
            if r["timed"] and recording(r["file"]).split("/")[0] in SETS:
                rows[folder.name][(r["test"], r["round"])].append(r)
    head = " | ".join(f"{b} p50 / p90 s" for b, _, _ in BANDS)
    out = ["## Provider limits", "", "| Provider | Slots | Rate limit | Per-request limit |", "|---|---|---|---|"]
    for name, s in providers.items():
        slots = f"{s['slots']['slots']} per file over {s['slots']['over_seconds'] / 60:.0f} min" if s["slots"] else ""
        rate = f"{s['rate_limit'][0]} per {s['rate_limit'][1]} s" if s["rate_limit"] else ""
        limit = f"{s['max_seconds'] / 60:.0f} min" if s["max_seconds"] else ""
        out.append(f"| {name} | {slots} | {rate} | {limit} |")

    out += ["", "## C. Single-request latency (one file at a time)", "",
            f"| Provider | {head} | Audio ÷ latency | Failures | Cap gate |", "|---|" + "---|" * (len(BANDS) + 3)]
    for name, s in providers.items():
        t = median_round(s, "C", name)
        if t:
            files = _files(rows[name][("C", 1)])
            out.append(f"| {name} | " + " | ".join(bands(files)) + f" | {_speed(files):.0f} | {t['failures']} | {gate(t)} |")

    for test, title in [("B2", "B2. Hour-long meetings, 14 in flight")]:
        out += ["", f"## {title} (median round)", "",
                f"| Provider | In flight | Audio-h per h | {head} | Audio ÷ latency | 429s | Rate waits | "
                "Retries | Failures | Cap gate | Flags |", "|---|" + "---|" * (len(BANDS) + 9)]
        for name, s in providers.items():
            t = median_round(s, test, name)
            if not t:
                continue
            runs = [r for r in s["tests"] if r["test"] == test and rows[name][(test, r["round"])]]
            speed = lambda r: tput(name, r)
            files = _files(rows[name][(test, t["round"])])
            flags = [f"plan-limited (at most {t['most_in_flight']} in flight)"] if t["most_in_flight"] < t["level"] else []
            flags += ["split"] if any(r["parts"] > 1 for r in rows[name][(test, t["round"])]) else []
            first = next((r for r in runs if r["round"] == 1), None)
            if first and any(speed(r) > 1.5 * speed(first) for r in runs if r["round"] > 1):
                flags.append("a later round much faster than round 1")
            out.append(f"| {name} | {t['in_flight']} | {speed(t):.0f} | " +
                       " | ".join(bands(files)) + f" | {_speed(files):.0f} | {t['status_429']} | {t['rate_waits']} | "
                       f"{sum(t['retried'].values())} | {t['failures']} | {gate(t)} | {', '.join(flags)} |")

    out += ["", "## Rounds (audio-h per wall-clock h, in order)", "", "| Provider | B2 |", "|---|---|"]
    for name, s in providers.items():
        cell = lambda test: " / ".join(f"{tput(name, t):.0f}" for t in s["tests"]
                                       if t["test"] == test and rows[name][(test, t["round"])])
        out.append(f"| {name} | {cell('B2')} |")

    out += ["", "## Accuracy against speed", "",
            "cpWER: pooled over exactly the panel's recordings, from the accuracy run. Speed: audio length ÷ latency "
            "over the panel's files (total audio over total latency), median round of B2; p50: median latency per "
            "file."]
    for test, title in [("B2", "Hour-long meetings")]:
        out += ["", f"### {title}", "", "| Provider | Recordings | Audio h | cpWER % | Audio ÷ latency | p50 latency s | "
                "Cap gate |", "|---|---|---|---|---|---|---|"]
        for name, s in providers.items():
            t = median_round(s, test, name)
            if not t:
                continue
            files = _files(rows[name][(test, t["round"])])
            p50 = statistics.median(f["latency"] for f in files if not f["failed"]) if files else math.nan
            out.append(f"| {name} | {len(files)} | {sum(f['seconds'] for f in files) / 3600:.1f} | "
                       f"{_cpwer(name, files)} | {_speed(files):.0f} | {p50:.1f} | {gate(t)} |")

    out += ["", "## Client", "", "| Provider process | Max CPU (% of one core) | Max event-loop lag s |", "|---|---|---|"]
    for name, s in providers.items():
        out.append(f"| {name} | {max(t['cpu_percent'] for t in s['tests']):.0f} | "
                   f"{max(t['loop_lag_max_seconds'] for t in s['tests']):.2f} |")
    client = OUT / "client.jsonl"
    samples = [json.loads(x) for x in client.read_text().splitlines()] if client.exists() else []
    if samples:
        col = lambda k: [x[k] for x in samples]
        out += ["", f"Machine, every 5 s over the run: CPU mean {statistics.mean(col('cpu_percent')):.0f}%, "
                    f"max {max(col('cpu_percent')):.0f}%; network out max {max(col('tx_MBps')):.0f} MB/s, "
                    f"in max {max(col('rx_MBps')):.0f} MB/s."]
    return "\n".join(out) + "\n"


def _cpwer(provider: str, files: list[dict]) -> str:
    """Pooled cpWER (%) of the accuracy run over these recordings; blank if any is not scored."""
    errors = length = 0
    for f in files:
        dataset, recording = f["file"].split("#")[0].split("/", 1)
        path = paths.score_path("cpwer", provider, dataset)
        per = paths.read_json(path)["per_recording"].get(recording) if path.exists() else None
        if per is None:
            return ""
        errors, length = errors + per["errors"], length + per["length"]
    return f"{100 * errors / length:.2f}" if length else ""


if __name__ == "__main__":
    options = json.loads(sys.argv[2])
    asyncio.run(_run_provider(sys.argv[1], options["tests"], options["rounds"], options["sample"]))
