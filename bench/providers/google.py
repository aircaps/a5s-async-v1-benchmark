"""Google Gemini 3.5 Transcribe (https://ai.google.dev/gemini-api/docs/transcribe).

Upload with the Files API, transcribe with the Interactions API, then delete the upload (uploads count against a
20 GB per-project store). With speaker diarization on, a request may be at most 30 minutes, so longer files are
split (configs/providers.yaml, max_seconds).
"""
import asyncio

from .base import Provider, Word, send

API = "https://generativelanguage.googleapis.com/v1beta"
UPLOAD = "https://generativelanguage.googleapis.com/upload/v1beta/files"
LANGUAGES = {"en": "en-US", "zh": "zh-CN"}


class Google(Provider):
    name = "google"

    def language_param(self, language: str) -> dict:
        return {"language_codes": [LANGUAGES[language]]}

    async def transcribe(self, client, audio, language, dataset):
        key = {"x-goog-api-key": self.key}
        start = await send(client, "POST", UPLOAD, json={"file": {"display_name": audio.name}}, headers={
            **key, "X-Goog-Upload-Protocol": "resumable", "X-Goog-Upload-Command": "start",
            "X-Goog-Upload-Header-Content-Length": str(audio.stat().st_size),
            "X-Goog-Upload-Header-Content-Type": "audio/wav"})
        file = (await send(client, "POST", start.headers["X-Goog-Upload-URL"], upload=audio, upload_field=None,
                           headers={"X-Goog-Upload-Offset": "0", "X-Goog-Upload-Command": "upload, finalize"})).json()["file"]
        try:
            while file.get("state") == "PROCESSING":
                await asyncio.sleep(1)
                file = (await send(client, "GET", f"{API}/{file['name']}", headers=key)).json()
            body = {"model": self.model,
                    "input": [{"type": "audio", "uri": file["uri"], "mime_type": "audio/wav"}],
                    "generation_config": {"transcription_config": self.request(language, dataset)}}
            return (await send(client, "POST", f"{API}/interactions", headers=key, json=body)).json()
        finally:
            await client.delete(f"{API}/{file['name']}", headers=key)

    def words(self, response):
        out = []
        _collect(response, out)
        return out


def _collect(node, out: list) -> None:
    """Every `word_info` annotation, wherever it sits in the response, in order."""
    if isinstance(node, dict):
        if node.get("type") == "word_info":
            out.append(Word(node.get("speaker") or "unknown", _seconds(node.get("start_offset")),
                            _seconds(node.get("end_offset")), node["text"]))
            return
        for value in node.values():
            _collect(value, out)
    elif isinstance(node, list):
        for value in node:
            _collect(value, out)


def _seconds(offset: str | None) -> float | None:
    return float(offset.removesuffix("s")) if offset else None
