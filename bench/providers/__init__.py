"""Provider registry. Request settings for each provider are in configs/providers.yaml.

configs/local.yaml (not published) may override any provider setting, e.g. `concurrency` for your account.
"""
from pathlib import Path

import yaml

from .aircaps import AirCaps
from .assemblyai import AssemblyAI
from .base import Provider
from .deepgram import Deepgram
from .elevenlabs import ElevenLabs
from .google import Google
from .meta import Meta
from .microsoft import Microsoft
from .nvidia import NVIDIA
from .xai import XAI

ADAPTERS = {p.name: p for p in (AirCaps, ElevenLabs, AssemblyAI, Meta, Microsoft, XAI, Google, NVIDIA, Deepgram)}
CONFIGS = Path(__file__).resolve().parents[2] / "configs"


def settings() -> dict:
    config = yaml.safe_load((CONFIGS / "providers.yaml").read_text())["providers"]
    local = CONFIGS / "local.yaml"
    if local.exists():
        for name, override in (yaml.safe_load(local.read_text()) or {}).get("providers", {}).items():
            config[name] = {**config[name], **override}
    return config


def load(name: str) -> Provider:
    return ADAPTERS[name](settings()[name])
