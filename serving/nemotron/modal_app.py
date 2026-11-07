"""Serve NVIDIA Nemotron 3.5 Transcribe the way its model card's quick start does, on 1x H100 80 GB in BF16.

Environment and `vllm serve` flags are copied from the model card ("Environment Setup", "Start the Server");
only the hosting (Modal) is ours. Each container is one H100 running one vLLM server; Modal adds containers
when more requests are in flight than one server takes.

    modal deploy serving/nemotron/modal_app.py
    export NEMOTRON_BASE_URL=https://<printed url>/v1
"""
import os
import subprocess

import modal

MODEL = "nvidia/NVIDIA-Nemotron-3.5-Transcribe-30B-A4B"
MODEL_REVISION = "c17667641642c4265ff2b7037dd101b7d4567634"     # Hugging Face, 2026-10-29
NEMO_SPEECH_COMMIT = "e5d79d5a49cbec49d79440b0070aac0c32a8dbb8"  # NVIDIA-NeMo/Speech main, 2026-11-01
REQUESTS_PER_SERVER = 16
MAX_SERVERS = 8

image = (
    # the model card's locked environment is CUDA 13.0; the CUDA 13.0 compiler is there for FlashInfer's one
    # startup JIT kernel, and `vllm download-kernels` installs vLLM's precompiled FlashInfer kernels
    modal.Image.from_registry("nvidia/cuda:13.0.0-cudnn-devel-ubuntu24.04", add_python="3.13")
    .apt_install("git", "ffmpeg", "python3.12-dev")   # Triton compiles a C helper against the venv's Python 3.12
    .pip_install("uv")
    .run_commands(
        f"git clone https://github.com/NVIDIA-NeMo/Speech.git /nemo-speech && cd /nemo-speech && git checkout {NEMO_SPEECH_COMMIT}",
        "cd /nemo-speech && uv venv --python 3.13 .venv"
        " && UV_PROJECT_ENVIRONMENT=/nemo-speech/.venv uv sync --extra asr --extra vllm --locked --no-install-project"
        " && uv pip install --python .venv/bin/python --no-deps -e ."
        " && uv pip install --python .venv/bin/python --no-deps av==19.0.2"
        " && uv pip install --python .venv/bin/python --no-deps opencv-python-headless==5.0.0.93",
    )
    .run_commands("/nemo-speech/.venv/bin/vllm download-kernels", gpu="H100")   # it needs to see the GPU
    .env({
        "VLLM_PLUGINS": "nemo_speechlm",
        "VLLM_MAX_AUDIO_DECODE_DURATION_S": "3600",
        "VLLM_MAX_AUDIO_CLIP_FILESIZE_MB": "180",
        "VLLM_USE_V2_MODEL_RUNNER": "0",
        # the model card serves from the activated environment (puts ninja on PATH)
        "PATH": "/nemo-speech/.venv/bin:/usr/local/cuda/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
        "CUDA_HOME": "/usr/local/cuda",
    })
)

SERVE = [
    "/nemo-speech/.venv/bin/vllm", "serve", "/weights",
    "--served-model-name", MODEL,
    "--trust-remote-code", "--dtype", "bfloat16", "--gpu-memory-utilization", "0.94",
    "--max-model-len", "65536", "--max-num-batched-tokens", "4096", "--max-num-seqs", "192",
    "--enable-chunked-prefill", "--no-enable-prefix-caching",
    "--use-replayssm", "--mamba-backend", "flashinfer", "--mamba-cache-mode", "none",
    "--mm-processor-cache-gb", "0", "--no-async-scheduling",
    "--limit-mm-per-prompt", '{"audio":{"count":6,"length":120000000}}',
    "--speculative-config", '{"method":"mtp","num_speculative_tokens":8}',
    "--reasoning-parser", "nemotron_v3",
    "--trust-request-mm-kwargs",
    "--middleware", "nemo.collections.speechlm2.vllm.salm.ctc_serving.ctc_timestamp_middleware",
    "--host", "0.0.0.0", "--port", "8000",
]

app = modal.App("nemotron-transcribe-benchmark")
weights = modal.Volume.from_name("nemotron-3-5-transcribe-weights", create_if_missing=True)


@app.function(image=image, gpu="H100", volumes={"/weights": weights}, timeout=24 * 3600,
              scaledown_window=600, max_containers=MAX_SERVERS)
@modal.concurrent(max_inputs=REQUESTS_PER_SERVER)
@modal.web_server(port=8000, startup_timeout=1800)
def serve():
    marker = f"/weights/{MODEL_REVISION}.done"
    if not os.path.exists(marker):  # first start: fetch the pinned weights once
        subprocess.run(["/nemo-speech/.venv/bin/hf", "download", MODEL, "--revision", MODEL_REVISION,
                        "--local-dir", "/weights"], check=True)
        open(marker, "w").close()
        weights.commit()
    subprocess.Popen(SERVE)
