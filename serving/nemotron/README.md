# Nemotron 3.5 Transcribe server

NVIDIA publishes no hosted API that returns speaker-attributed transcripts for this model (2026-11-01), so we run
it ourselves, following the model card exactly:

- **Code:** vLLM with NVIDIA's NeMo Speech plugin, set up with the model card's `uv` commands, pinned to NeMo
  Speech commit `e5d79d5` and model revision `c176676`.
- **Hardware:** 1x H100 80 GB in BF16, the model card's reference deployment. Each server is one GPU.
- **Server flags:** the model card's `vllm serve` command, unchanged (including MTP speculative decoding with
  8 tokens).
- **Requests** (`bench/providers/nvidia.py`, `configs/providers.yaml`): the model card's settings
  (temperature 0, top_p 1, seed 0, thinking off, special tokens kept) and NVIDIA's own benchmark prompt for
  the kind of recording. No system message. NVIDIA's generation-loop guardrail is applied to the output, as
  in NVIDIA's reported results.
- **Limits:** at most 1 hour of audio per request and 8 speakers (model card / technical report). Longer
  files are split into equal parts of at most 1 hour.

`modal_app.py` deploys this on Modal. Any machine with an H100 works the same way: run the commands from the
model card, then point `NEMOTRON_BASE_URL` at `http://<host>:8000/v1`.

Model card: https://huggingface.co/nvidia/NVIDIA-Nemotron-3.5-Transcribe-30B-A4B
