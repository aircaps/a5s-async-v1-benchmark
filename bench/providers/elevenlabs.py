"""ElevenLabs Scribe v2 (https://elevenlabs.io/docs/api-reference/speech-to-text/convert).

One synchronous multipart request with the file. Audio events such as "(laughter)" come back as words of type
`audio_event` (on by default) and are not counted as words.
"""
from .base import Provider, Word, form, send

URL = "https://api.elevenlabs.io/v1/speech-to-text"


class ElevenLabs(Provider):
    name = "elevenlabs"

    def language_param(self, language: str) -> dict:
        return {"language_code": language}

    async def transcribe(self, client, audio, language, dataset):
        fields = form({"model_id": self.model, **self.request(language, dataset)})
        return (await send(client, "POST", URL, headers={"xi-api-key": self.key}, data=fields, upload=audio)).json()

    def words(self, response):
        return [Word(w.get("speaker_id", "unknown"), w["start"], w["end"], w["text"])
                for w in response.get("words") or [] if w["type"] == "word"]
