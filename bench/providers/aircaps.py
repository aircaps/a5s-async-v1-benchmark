"""AirCaps A5S Async v1, through the public API (https://docs.aircaps.com).

One request (POST /v1/transcribe): the audio is the request body, the options are query parameters, and the
answer is the finished transcript. A file not finished within 120 s is answered with 202; GET
/v1/transcripts/{id}?wait=120 then returns as soon as the transcript is finished. The Idempotency-Key stops a
retried request from creating a second job.
"""
import uuid

from .base import Provider, Word, send

BASE = "https://api.aircaps.com/v1"


class AirCaps(Provider):
    name = "aircaps"

    def language_param(self, language: str) -> dict:
        return {"language_code": language}

    async def transcribe(self, client, audio, language, dataset):
        auth = {"Authorization": f"Bearer {self.key}"}
        params = {"model": self.model, **self.request(language, dataset)}
        headers = {**auth, "Content-Type": "application/octet-stream", "Idempotency-Key": str(uuid.uuid4())}
        job = (await send(client, "POST", f"{BASE}/transcribe", upload=audio, upload_field=None,
                          params=params, headers=headers)).json()
        while job["status"] not in ("completed", "error"):
            job = (await send(client, "GET", f"{BASE}/transcripts/{job['id']}", headers=auth,
                              params={"wait": 120})).json()
        if job["status"] == "error":
            raise RuntimeError(f"transcript {job['id']} failed: {job.get('error')}")
        return job

    def words(self, response):
        return [Word(w["speaker"], w["start"], w["end"], w["text"]) for w in response.get("words") or []]
