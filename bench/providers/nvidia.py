"""NVIDIA Nemotron 3.5 Transcribe, self-hosted with NVIDIA's documented vLLM server (serving/nemotron/).

An OpenAI-style chat request with the audio and NVIDIA's own benchmark prompt for that kind of recording
(configs/providers.yaml). The model writes text with inline speaker tags <spk:N>. NVIDIA's generation-loop
guardrail from the model card is applied before splitting into turns. At most 1 hour per request, so longer
files are split.
"""
import base64
import os
import re

from .base import Provider, Word, send

TAG = re.compile(r"<spk:(\d+)>")
REPEATED_CHAR = re.compile(r"(.)\1{20,}", re.DOTALL)
REPEATED_BLOCK = re.compile(r"(.{1,4096}?)\1{19,}", re.DOTALL)


class NVIDIA(Provider):
    name = "nvidia"

    def request(self, language: str, dataset: str) -> dict:
        kind = self.settings["prompt_by_dataset"].get(dataset, "multi_speaker")
        return {**self.params, "prompt": self.settings["prompts"][kind]}

    async def transcribe(self, client, audio, language, dataset):
        params = self.request(language, dataset)
        prompt = params.pop("prompt")
        data = base64.b64encode(audio.read_bytes()).decode()
        body = {"model": self.model, **params, "messages": [{"role": "user", "content": [
            {"type": "audio_url", "audio_url": {"url": f"data:audio/wav;base64,{data}"}},
            {"type": "text", "text": prompt}]}]}
        url = os.environ["NEMOTRON_BASE_URL"].rstrip("/") + "/chat/completions"
        headers = {"Authorization": f"Bearer {self.key}"} if self.key else {}
        return (await send(client, "POST", url, headers=headers, json=body)).json()

    def words(self, response):
        text = guardrail(response["choices"][0]["message"]["content"] or "")
        parts = TAG.split(text)  # [text before any tag, tag, text, tag, text, ...]
        turns = [("unknown", parts[0])] + list(zip(parts[1::2], parts[2::2]))
        return [Word(f"spk{s}" if s != "unknown" else s, None, None, t.strip()) for s, t in turns if t.strip()]


def guardrail(text: str) -> str:
    """NVIDIA's model-card post-processing: collapse runaway repetitions to one copy."""
    return REPEATED_BLOCK.sub(r"\1", REPEATED_CHAR.sub(r"\1", text))
