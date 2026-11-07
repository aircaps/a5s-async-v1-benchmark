"""Meta Muse Voice Transcribe 1.0 (https://dev.meta.ai/docs/api-reference/voice/transcribe).

Files up to 10 minutes: one synchronous multipart request, a `request` JSON part and the `audio` WAV. The file
endpoint accepts at most 10 minutes per request, so longer recordings go whole through Meta's realtime endpoint
instead (same model and mode), streamed as 16 kHz PCM at real time, the fastest the server accepts. Either way the
result is a list of speaker turns with turn-level times (no word times); for a stream the turns are rebuilt from
the events (speechStart, speaker, speechComplete), which are stored as well.
"""
import asyncio
import json
import time
import wave

import websockets

from .base import Provider, Word, send

URL = "https://api.meta.ai/v1/asr/transcribe"
REALTIME_URL = "wss://api.meta.ai/v1/asr/realtime"
LANGUAGES = {"en": "English", "zh": "Chinese"}
CHUNK_MS = 100


class Meta(Provider):
    name = "meta"

    def language_param(self, language: str) -> dict:
        return {"languageBias": [LANGUAGES[language]]}

    async def transcribe(self, client, audio, language, dataset):
        with wave.open(str(audio), "rb") as w:
            seconds = w.getnframes() / w.getframerate()
        if seconds > self.settings["file_endpoint_max_seconds"]:
            return await self.stream(audio, language, dataset)
        settings = json.dumps({"model": self.model, **self.request(language, dataset)})
        r = await send(client, "POST", URL, headers={"Authorization": f"Bearer {self.key}"},
                       files={"request": (None, settings, "application/json")}, upload=audio, upload_field="audio")
        return r.json()

    async def stream(self, audio, language, dataset, attempts: int = 3) -> dict:
        """The whole file through the realtime endpoint, paced at real time; retried from the start on failure."""
        for attempt in range(attempts):
            try:
                return await self._stream(audio, language, dataset)
            except (OSError, websockets.WebSocketException, asyncio.TimeoutError, RuntimeError):
                if attempt == attempts - 1:
                    raise
                await asyncio.sleep(10 * (attempt + 1))

    async def _stream(self, audio, language, dataset) -> dict:
        header = {"authorization": {"accessToken": f"Bearer {self.key}"}, "model": self.model,
                  **self.request(language, dataset), "audioEncoding": "PCM_16KHZ"}
        events = []
        async with websockets.connect(REALTIME_URL, max_size=None, open_timeout=60) as ws:
            await ws.send(json.dumps(header))
            events.append(json.loads(await asyncio.wait_for(ws.recv(), 60)))

            async def receive():
                async for message in ws:
                    if isinstance(message, str):
                        events.append(json.loads(message))
                        if events[-1].get("type") == "error":
                            raise RuntimeError(f"meta realtime error: {events[-1]}")

            receiver = asyncio.create_task(receive())
            with wave.open(str(audio), "rb") as w:
                frames = w.getframerate() * CHUNK_MS // 1000
                start, k = time.monotonic(), 0
                while chunk := w.readframes(frames):
                    if receiver.done():
                        break
                    await ws.send(chunk)
                    k += 1
                    await asyncio.sleep(max(0.0, start + k * CHUNK_MS / 1000 - time.monotonic()))
            if not receiver.done():
                await ws.send(json.dumps({"type": "endStream"}))
            await asyncio.wait_for(receiver, 600)
        return {"transport": "realtime", "turns": turns_from_events(events), "events": events}

    def words(self, response):
        return [Word(t.get("speaker") or "unknown", t["startMs"] / 1000, t["endMs"] / 1000, t["transcript"])
                for t in response.get("turns") or []]


def turns_from_events(events: list[dict]) -> list[dict]:
    """Speaker turns from realtime events: a turn opens at speechStart, takes the speaker label(s) that follow and
    closes at speechComplete with its final text. With several labels in one turn, the latest one is used."""
    open_turns, current, turns = {}, None, []
    for e in events:
        kind = e.get("type")
        if kind == "speechStart":
            current = e["turnId"]
            open_turns[current] = {"startMs": e["audioProcessedMs"], "speaker": None}
        elif kind == "speaker" and current in open_turns:
            open_turns[current]["speaker"] = e["label"]
        elif kind == "speechComplete" and e.get("turnId") in open_turns:
            turn = open_turns.pop(e["turnId"])
            turns.append({"speaker": turn["speaker"], "startMs": turn["startMs"], "endMs": e["audioProcessedMs"],
                          "transcript": e.get("transcript", "")})
    return turns
