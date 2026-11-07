"""What every provider adapter implements, plus one shared HTTP helper.

An adapter does two things:
  transcribe(): send one audio file with the documented request and return the provider's response, untouched.
  words():      read speaker-attributed words (or segments) out of that response.
Request settings are not in the code: they come from the provider's block in configs/providers.yaml. The only
per-recording input is the language (and, for Nemotron only, the dataset, which selects NVIDIA's prompt).
"""
import asyncio
import collections
import contextlib
import contextvars
import os
import time
from dataclasses import dataclass
from pathlib import Path

import httpx

RETRY_STATUS = {408, 429, 500, 502, 503, 504}
# Where a caller sets a Counter here (the speed test), send() counts the responses with a status in RETRY_STATUS
# and the dropped connections ("transport") it receives.
RETRIES: contextvars.ContextVar[collections.Counter | None] = contextvars.ContextVar("retries", default=None)
# Where a caller sets a list here, send() adds every attempt it retries: the status (or the connection error), the
# provider's request-ID headers and the start of the body, so that a failure can be traced with the provider.
ATTEMPTS: contextvars.ContextVar[list | None] = contextvars.ContextVar("attempts", default=None)


@dataclass
class Word:
    speaker: str
    start: float | None   # seconds from the start of the file; None if the provider gives no times
    end: float | None
    text: str             # one word, or a whole segment if the provider only returns segments


class Provider:
    name = ""

    def __init__(self, settings: dict):
        self.settings = settings
        self.model = settings["model"]
        self.params = dict(settings.get("params") or {})
        self.max_seconds = settings.get("max_seconds")  # per-request audio limit; longer files are split
        self.key = os.environ.get(settings.get("api_key_env", ""), "")

    def request(self, language: str, dataset: str) -> dict:
        """The exact non-audio request parameters, stored with every result."""
        return {**self.params, **self.language_param(language)}

    def language_param(self, language: str) -> dict:
        return {}

    async def transcribe(self, client: httpx.AsyncClient, audio: Path, language: str, dataset: str) -> dict:
        raise NotImplementedError

    def words(self, response: dict) -> list[Word]:
        raise NotImplementedError


async def send(client: httpx.AsyncClient, method: str, url: str, *, upload: Path | None = None,
               upload_field: str | None = "file", **kwargs) -> httpx.Response:
    """One HTTP request, retried on rate limits, server errors and dropped connections.

    `upload` is re-opened on every attempt: sent as a multipart field `upload_field`, or as the raw body if
    `upload_field` is None.
    """
    for attempt in range(6):
        with contextlib.ExitStack() as stack:
            req = dict(kwargs)
            if upload is not None:
                f = stack.enter_context(upload.open("rb"))
                if upload_field:
                    req["files"] = {**req.get("files", {}), upload_field: (upload.name, f, "audio/wav")}
                else:
                    req["content"] = _chunks(f)
                    req["headers"] = {**req.get("headers", {}), "Content-Length": str(upload.stat().st_size)}
            try:
                response = await client.request(method, url, **req)
                if response.status_code not in RETRY_STATUS:
                    break
                _count(response.status_code)
                _note({"status": response.status_code, **request_ids(response), "body": response.text[:300]})
            except httpx.TransportError as e:
                _count("transport")
                _note({"status": None, "error": f"{type(e).__name__}: {e}"[:300]})
                if attempt == 5:
                    raise
        await asyncio.sleep(min(120, 5 * 2 ** attempt))
    response.raise_for_status()
    return response


def _count(kind) -> None:
    if (counter := RETRIES.get()) is not None:
        counter[kind] += 1


def _note(attempt: dict) -> None:
    if (attempts := ATTEMPTS.get()) is not None:
        attempts.append({"at": time.time(), **attempt})


def request_ids(response: httpx.Response) -> dict:
    """The provider's request-ID headers (names differ: x-request-id, apim-request-id, ...)."""
    return {k.lower(): v for k, v in response.headers.items() if "request" in k.lower() and "id" in k.lower()}


async def _chunks(f):
    while block := f.read(1 << 20):
        yield block


def form(params: dict) -> dict:
    """Multipart form fields: booleans as 'true'/'false', lists repeated."""
    out = {}
    for k, v in params.items():
        out[k] = [form({k: x})[k] for x in v] if isinstance(v, list) else str(v).lower() if isinstance(v, bool) else str(v)
    return out


async def poll(client: httpx.AsyncClient, url: str, headers: dict, done: set, every: float = 5.0) -> dict:
    """GET `url` until the job's `status` is in `done`."""
    while True:
        job = (await send(client, "GET", url, headers=headers)).json()
        if job["status"] in done:
            return job
        await asyncio.sleep(every)
