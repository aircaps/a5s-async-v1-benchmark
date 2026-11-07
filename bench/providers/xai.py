"""xAI Grok Voice Transcribe 2.0 (https://docs.x.ai/developers/model-capabilities/audio/speech-to-text).

One synchronous multipart request; the file must be the last form field (httpx sends files after other fields).
"""
from .base import Provider, Word, form, send

URL = "https://api.x.ai/v1/stt"


class XAI(Provider):
    name = "xai"

    def language_param(self, language: str) -> dict:
        return {"language": language}

    async def transcribe(self, client, audio, language, dataset):
        fields = form({"model": self.model, **self.request(language, dataset)})
        return (await send(client, "POST", URL, headers={"Authorization": f"Bearer {self.key}"},
                           data=fields, upload=audio)).json()

    def words(self, response):
        return [Word(str(w.get("speaker", "unknown")), w["start"], w["end"], w["text"]) for w in response.get("words") or []]
