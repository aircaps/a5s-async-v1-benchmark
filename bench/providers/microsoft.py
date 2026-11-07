"""Microsoft MAI-Transcribe-2 on Azure AI Speech (https://learn.microsoft.com/azure/ai-services/speech-service/mai-transcribe).

One synchronous multipart request: a `definition` JSON part and the `audio` file. Needs an Azure Speech resource
in a region that offers MAI-Transcribe-2; its endpoint goes in AZURE_SPEECH_ENDPOINT. Without word timestamps
(off by default) the response has speaker-attributed phrases with phrase times.
"""
import json
import os

from .base import Provider, Word, send

PATH = "/speechtotext/transcriptions:transcribe?api-version=2025-10-15"
LOCALES = {"en": "en-US", "zh": "zh-CN"}


class Microsoft(Provider):
    name = "microsoft"

    def language_param(self, language: str) -> dict:
        return {"locales": [LOCALES[language]]}

    async def transcribe(self, client, audio, language, dataset):
        url = os.environ["AZURE_SPEECH_ENDPOINT"].rstrip("/") + PATH
        definition = json.dumps(self.request(language, dataset))
        r = await send(client, "POST", url, headers={"Ocp-Apim-Subscription-Key": self.key},
                       files={"definition": (None, definition, "application/json")}, upload=audio, upload_field="audio")
        return r.json()

    def words(self, response):
        return [Word(str(p.get("speaker", "unknown")), p["offsetMilliseconds"] / 1000,
                     (p["offsetMilliseconds"] + p["durationMilliseconds"]) / 1000, p["text"])
                for p in response.get("phrases") or []]
