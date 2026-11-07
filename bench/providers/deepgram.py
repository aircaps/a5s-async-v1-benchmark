"""Deepgram Nova-3, pre-recorded (https://developers.deepgram.com/reference/speech-to-text/listen-pre-recorded).

One synchronous request: the audio is the raw body, the options are query parameters. Speaker labels come from
`diarize_model`, Deepgram's documented replacement for the deprecated `diarize` flag.
"""
from .base import Provider, Word, send

URL = "https://api.deepgram.com/v1/listen"


class Deepgram(Provider):
    name = "deepgram"

    def language_param(self, language: str) -> dict:
        return {"language": language}

    async def transcribe(self, client, audio, language, dataset):
        headers = {"Authorization": f"Token {self.key}", "Content-Type": "audio/wav"}
        params = {"model": self.model, **self.request(language, dataset)}
        return (await send(client, "POST", URL, upload=audio, upload_field=None, params=params,
                           headers=headers)).json()

    def words(self, response):
        alternatives = response["results"]["channels"][0]["alternatives"]
        words = (alternatives[0].get("words") or []) if alternatives else []
        return [Word(str(w.get("speaker", "unknown")), w["start"], w["end"], w.get("punctuated_word") or w["word"])
                for w in words]
