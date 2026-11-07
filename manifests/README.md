# Dataset manifests

The benchmark redistributes **no audio and no transcripts**. This folder says, for every test set, where to get
the data, which part of it is the test set, and how the test files and references are built, plus a manifest with
checksums so you can confirm you built exactly the same files.

To rebuild a test set, run its recipe on the official download:

```bash
git clone https://github.com/aircaps/a5s-async-v1-benchmark && cd a5s-async-v1-benchmark && uv sync --extra prep
bench prep <dataset> --source <folder with the official download>
bench verify <dataset> --manifest manifests/<dataset>.jsonl
```

`bench prep` writes, for each recording, the exact audio every provider receives (16 kHz, mono, 16-bit PCM WAV,
made with ffmpeg in bit-exact mode; these manifests were built with ffmpeg 6.1.1 on Ubuntu 24.04) and the
reference transcript (SegLST: speaker, start, end, words).
Each manifest line has:

| Field | Meaning |
|---|---|
| `id` | recording id |
| `audio` | path of the prepared WAV |
| `duration` | seconds |
| `language` | `en` or `zh` (the language sent to every provider) |
| `sha256` | checksum of the prepared WAV |
| `reference_sha256` | checksum of the recording's reference segments |
| `reference_words` | words in the reference before normalisation |
| `source` | the original file, channel and cut it came from |

## Test sets

Hours are test audio as sent to the providers; "measured" means we built the set, otherwise the figure is the
publisher's.

**Multi-speaker (scored with cpWER, or cpCER for Mandarin)**

| Dataset | Test set | Recordings | Hours | Language | Access, licence |
|---|---|---|---|---|---|
| `notsofar` | NOTSOFAR-1 eval (eval_small, = CHiME-8 eval), single-channel devices | 160 | 16.67 | English | free, CC BY 4.0 |
| `ami` | AMI Meeting Corpus, full-corpus-ASR test, distant mic Array1-01 | 16 | 9.06 | English | free, CC BY 4.0 |
| `chime6` | CHiME-6 eval S01 and S21, array U06 channel 1 | 2 | 5.19 | English | free, CC BY-SA 4.0 |
| `aishell4` | AISHELL-4 test, array channel 0 | 20 | 12.73 | Mandarin | free, CC BY-SA 4.0 |
| `alimeeting` | AliMeeting Eval + Test, far-field channel 0 | 28 | 14.98 | Mandarin | free, CC BY-SA 4.0 |
| `icsi` | ICSI Meeting Corpus, Bmr013 / Bmr018 / Bro021, desk mic chan6 | 3 | 2.77 | English | free, CC BY 4.0 |
| `dipco` | DiPCo (Dinner Party Corpus), all 10 sessions (dev + eval), array U01 channel 1 | 10 | 5.33 | English | free, CDLA-Permissive-1.0 |
| `dai_en` | DAI-ASR-I18N English public split, David AI mono-mix-v1 | 48 | 2.01 | English | gated (approval), evaluation use, no redistribution |

The first 5 are the main meeting set; `icsi` and `dipco` are supplementary (NVIDIA lists both as Nemotron 3.5
Transcribe training data, and neither has a training split).

**Single-speaker clips (scored the same way; with one speaker cpWER equals WER)**: the Hugging Face
[Open ASR Leaderboard](https://huggingface.co/spaces/hf-audio/open_asr_leaderboard) short-form English sets, from
the leaderboard's own copies.

| Dataset | Test set | Clips | Hours | Access, licence |
|---|---|---|---|---|
| `openasr_earnings22` | Earnings-22, 6 calls, segmented | 2,741 | 5.43 | free, CC BY-SA 4.0 |
| `openasr_librispeech_clean` | LibriSpeech test-clean | 2,620 | 5.40 | free, CC BY 4.0 |
| `voxpopuli` | VoxPopuli English test | 1,842 | 4.93 | free, CC0 |

## How each test set is built

Every recipe is a short file in [`bench/datasets/`](../bench/datasets/); its docstring is the authoritative
description. In brief:

- **ami, icsi, aishell4, alimeeting**: the official annotations (NXT word files for AMI and ICSI, TextGrid
  utterances for AISHELL-4 and AliMeeting; text kept as published, punctuation tokens dropped except sentence
  ends); one distant-mic channel is taken whole.
- **notsofar**: every utterance of `gt_transcription.json` for each meeting; the two single-channel devices of a
  meeting are two recordings with the same reference.
- **chime6**: the official utterance transcripts; each session starts at its first annotated utterance, as in
  the CHiME-8 scoring setup.
- **dipco**: the official utterance transcripts with their U01 times; one far-field channel taken whole.
- **dai_en**: the published segments, and David AI's own mono mix of the two channels.
- **Open ASR sets**: the leaderboard's own clips and `text` column, unfiltered, one segment per clip.

Before scoring, references and hypotheses go through the same normaliser: for English, the Hugging Face Open ASR
Leaderboard's normaliser, one sentence at a time, after two formatting rules ("…" removed like a dash; numerals
written apart joined, "20 21" -> "2021"); for Mandarin, its basic normaliser and per-character scoring.
[`bench/normalize.py`](../bench/normalize.py) has the details.

## Not included, and why

- **Far-Field ASR Leaderboard (Treble Technologies)**: its test set is private.
- **`agentic`**: 4 online meetings licensed from the Agentic Data Company, with machine-made references. The
  benchmark reports its scores; the data is not published and is available on request.
- **`internal`**: 7 recordings made by AirCaps. Only scores are published; the data is available on request.

## Licence

These manifests: CC BY 4.0. Each dataset keeps its own licence and terms, listed above; get the data from its
publisher.
