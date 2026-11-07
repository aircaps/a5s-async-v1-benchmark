# A5S Async v1 Benchmark

The benchmark behind AirCaps' A5S Async v1 report: an open, reproducible comparison of speaker-attributed
transcription APIs (who said what), scored with **cpWER** (concatenated minimum-permutation word error rate).

Everything needed to check or redo the numbers is here: the adapter for every provider, the exact request
settings, the dataset recipes, every raw API response, the hypotheses and the scores. Audio and reference
transcripts are not redistributed; the [dataset manifests](manifests/) say where to
get each dataset and how the test files are built, with checksums to confirm you built the same files.

## Rules

Every provider is treated the same way, as an ordinary customer of its public API would use it:

- **Default settings.** Only three things are set: the model, the language (English), and speaker diarization
  switched on where it is optional. No speaker counts, no vocabulary or key terms, no prompts, no other options.
  The single exception is Nemotron 3.5 Transcribe, a model that is prompted; it gets NVIDIA's own published
  benchmark prompt for the kind of recording. All settings are in [`configs/providers.yaml`](configs/providers.yaml).
- **Same audio.** Every provider receives the same 16 kHz mono 16-bit WAV of the whole recording.
- **Per-request limits.** Meta's file endpoint takes at most 10 minutes, so longer recordings go whole through
  Meta's realtime endpoint (same model and mode), streamed at real time. Where a recording is longer than a
  provider's maximum per request (Gemini 30 min with diarization, Nemotron 1 h, Meta's realtime sessions about
  1 h, Microsoft 2 h), it is sent as the fewest equal parts under that limit, overlapping by two minutes, and the
  parts are joined the way a customer could, without the reference ([`bench/stitch.py`](bench/stitch.py)): the
  shared words are aligned, speakers are linked across parts by the words they share, and the repeat is removed.
  This can only help those providers. `bench hyp --strict` and `bench score --strict` score the parts as separate
  speakers instead (results in `results/strict/`).
- **No post-processing** of provider output, except NVIDIA's own generation-loop guardrail for Nemotron, which
  is part of NVIDIA's published inference recipe.
- **Failures count.** A recording a provider fails to return is scored as an empty transcript and listed.
- **Same scoring.** References and hypotheses go through the same text normaliser, then MeetEval: the Hugging
  Face Open ASR Leaderboard's normaliser (copied unchanged in `bench/open_asr`), one sentence at a time, after two
  formatting rules: "…" is removed like a dash, and numerals written apart are joined ("20 21" -> "2021",
  "7:30" -> "730"). Text is normalised per speaker run: one speaker's words in time order, kept together while
  that speaker keeps talking (pauses of up to 1 s), even where someone else's words fall in between.
  `bench/normalize.py` and `bench/score.py` give the details.

## Providers

| Provider | Model | Settings |
|---|---|---|
| AirCaps | A5S Async v1 | `language_code: en` |
| ElevenLabs | Scribe v2 (`scribe_v2`) | `language_code: en`, `diarize: true` |
| AssemblyAI | Universal-3.5 Pro (`universal-3-5-pro`) | `language_code: en`, `speaker_labels: true` |
| Meta | Muse Voice Transcribe 1.0 | `languageBias: [English]`, `mode: DIARIZATION` |
| Microsoft | MAI-Transcribe-2 (preview) | `locales: [en-US]`, `diarization.enabled: true` |
| xAI | Grok Voice Transcribe 2.0 | `language: en`, `diarize: true` |
| Google | Gemini 3.5 Transcribe | `language_codes: [en-US]`, `diarization_mode: speaker` |
| Deepgram | Nova-3 (`nova-3`) | `language: en`, `diarize_model: latest` |
| NVIDIA | Nemotron 3.5 Transcribe, self-hosted (1x H100, BF16) | model card settings and prompts, see [`serving/nemotron`](serving/nemotron) |

At the time of this run, AirCaps returns transcripts without smart formatting by default, so the request sets only
the language. If that default changes, turn smart formatting off to reproduce these results.

## Datasets

Test or evaluation splits only. Build instructions, licences and checksums: [`manifests/`](manifests/).

| Kind | Datasets |
|---|---|
| Meetings, main set (English) | `notsofar` (single-channel), `ami` (SDM), `chime6` |
| Meetings, main set (Mandarin, cpCER) | `aishell4`, `alimeeting` |
| Meetings, supplementary | `icsi` (SDM), `dipco`, `agentic` (private, scores only) |
| Two-person conversations | `dai_en` (scores only) |
| Single-speaker clips (Open ASR Leaderboard short-form sets) | `openasr_earnings22`, `openasr_librispeech_clean`, `voxpopuli` |
| Internal recordings, multi-speaker (private, scores only) | `internal` |

NVIDIA lists ICSI and DiPCo as Nemotron 3.5 Transcribe training data; its scores on them are kept but are not a
fair comparison.

**`agentic`** is 4 online meetings licensed from the Agentic Data Company, with machine-made references. The
data is not published; it is available on request. **`dai_en`** is published by David AI under a data use
agreement that allows evaluation but not redistribution. For these two sets and `internal`, only the scores are
published: no raw responses or hypotheses.

**`internal`** is 7 recordings made by AirCaps, which is also one of the providers compared:
- **Content:** office meetings, an ad-hoc technical discussion and a high-overlap crosstalk session, 3.4 h in all, 3 to 5 speakers
  each.
- **Audio:** one distant microphone per recording, either a microphone array's first channel (level-normalised) or a
  laptop's built-in microphone.
- **References:** each person's close-talk microphone, transcribed by machine (ElevenLabs Scribe v2), then:
  - five recordings: corrected at names and terms only;
  - one meeting: reviewed by a person;
  - the high-overlap crosstalk session: corrected by a person.
- **Scored parts:** two recordings are scored on parts only. In one office session, the low-crosstalk windows are
  joined into one file. In the high-overlap crosstalk session, a few minutes of moving around are left out.
- **Access:** the audio, references and transcripts are not published and are available on request; only the scores
  are.

## Results

[`results/cpwer.md`](results/cpwer.md) (`bench report`): the main meeting sets and their macro, the supplementary sets,
easier speech, the internal recordings and the error composition. By overlap and by number of speakers:
[`results/breakdown/`](results/breakdown/) (`bench breakdown`). Speed: [`results/speed.md`](results/speed.md) (`bench speed-report`).

AirCaps' accuracy results come from a run on November 6, 2026; the other providers' from November 1-2, 2026. The speed
test ran on November 2, 2026.

## Reproduce

```bash
uv sync                                   # Python 3.12+, plus ffmpeg on PATH
cp .env.example .env                      # add your API keys
set -a; source .env; set +a

bench prep ami --source /path/to/ami      # build test audio + references from the official download
bench verify ami --manifest manifests/ami.jsonl

bench run --providers elevenlabs,assemblyai --datasets ami
bench hyp --providers elevenlabs,assemblyai --datasets ami
bench score --providers elevenlabs,assemblyai --datasets ami --metric cpwer
bench report
bench breakdown --by speakers          # or --by overlap
```

`bench run` is resumable: a recording that already has a stored response is never sent again. Progress, one
line a minute, goes to `logs/<provider>.log`.

## Speed

`bench speed --providers ...` times each provider's public API end to end on every English meeting of 45-75 minutes
(8 meetings, 6.7 h): each one at a time (latency), then three rounds with 14 requests in flight (throughput). All
providers run at once, one process each; requests, rounds and the client's own CPU and network go to
`results/speed/`, and `bench speed-report` prints the tables. Rules and details: [`bench/speed.py`](bench/speed.py).

## What is stored

| Path | Content |
|---|---|
| `results/raw/<provider>/<dataset>/<recording>.json.gz` | The provider's response, untouched apart from account identifiers, with the request settings, audio checksum, submit and completion times; for a file sent in parts, one response per part with the part's start and end |
| `results/errors/<provider>/<dataset>/<recording>.json` | Failed requests, with the provider's error |
| `results/hyp/<provider>/<dataset>.seglst.json.gz` | Hypothesis in [SegLST](https://github.com/fgnt/meeteval) form: one entry per word with the provider's speaker label and times |
| `results/scores/<metric>/<provider>/<dataset>.json` | Errors, length and error rate per recording and pooled over the dataset; per recording also the reference speakers, and how many the provider missed or invented |
| `results/strict/{raw,hyp,scores}/...` | Split files scored strictly, with a separate set of speakers per part. `raw` holds the first run's parts, which did not overlap (Meta: 10-minute file parts), where they were kept |
| `results/speed/<provider>/{requests.jsonl,summary.json}`, `results/speed.md` | Speed test: every request with its timing, per-round summaries, and the tables |
| `results/breakdown/<metric>_by_<speakers\|overlap>.{md,json}` | Error rates by number of reference speakers or by overlap (share of speech time with two or more people talking), pooled over recordings |

`bench breakdown` groups recordings by a property of their reference (speakers: 1, 2, 3, 4, 5-8, 9+; overlap:
<15%, 15-30%, 30-50%, 50%+) and pools errors and words within each group, over the English main sets (NOTSOFAR-1,
AMI, CHiME-6) by default. Overlap comes from the reference segment times; recordings without them appear as
"no times".

Raw responses keep word times wherever a provider returns them, so tcpWER, tcORC-WER (`bench score --metric
tcpwer|tcorcwer`), diarization error rate and per-request latency can be computed later without sending
anything again.

## Layout

```
bench/providers/   one adapter per provider (request + response parsing)
bench/datasets/    one recipe per dataset (download source, test split, reference building)
bench/run.py       sends recordings, keeps raw responses and timing
bench/hyp.py       raw responses -> SegLST hypotheses
bench/stitch.py    overlapping parts of a long file -> one transcript, without the reference
bench/score.py     MeetEval scoring
bench/breakdown.py error rates by number of speakers or by overlap
configs/           provider settings
manifests/         per-dataset manifests with checksums, and how each test set is built
serving/nemotron/  how the Nemotron server is run
results/           everything produced by a run
```

## License

Code: MIT. Manifests: CC BY 4.0. Each dataset keeps its own licence; see [`manifests/`](manifests/).
