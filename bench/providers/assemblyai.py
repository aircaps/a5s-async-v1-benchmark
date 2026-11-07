"""AssemblyAI Universal-3.5 Pro (https://www.assemblyai.com/docs/api-reference/transcripts/submit).

Upload the file (POST /v2/upload), submit a transcript job, poll every second until done
(the API has no one-request mode). Times come back in milliseconds.
"""
from .base import Provider, Word, poll, send

BASE = "https://api.assemblyai.com/v2"


class AssemblyAI(Provider):
    name = "assemblyai"

    def language_param(self, language: str) -> dict:
        return {"language_code": language}

    async def transcribe(self, client, audio, language, dataset):
        auth = {"authorization": self.key}
        upload = await send(client, "POST", f"{BASE}/upload", headers=auth, upload=audio, upload_field=None)
        body = {"audio_url": upload.json()["upload_url"], **self.request(language, dataset)}
        job = (await send(client, "POST", f"{BASE}/transcript", headers=auth, json=body)).json()
        job = await poll(client, f"{BASE}/transcript/{job['id']}", auth, {"completed", "error"}, every=1.0)
        if job["status"] == "error":
            raise RuntimeError(f"transcript {job['id']} failed: {job.get('error')}")
        job.pop("audio_url", None)  # link to our uploaded audio; not part of the result
        return job

    def words(self, response):
        return [Word(w.get("speaker") or "unknown", w["start"] / 1000, w["end"] / 1000, w["text"])
                for w in response.get("words") or []]
