# cpwer results

Pooled within each dataset (errors over reference words, in %). Mandarin sets are scored per character.
Where a provider had to split a recording, its parts overlap and are joined without the reference;
"macro, strict" scores those parts as different speakers instead.

## Main meeting sets

| Provider | NOTSOFAR-1 | AMI | CHiME-6 | AISHELL-4 (cpCER) | AliMeeting (cpCER) | Macro | Macro, strict |
|---|---|---|---|---|---|---|---|
| aircaps | 16.65 | 15.83 | 42.27 | 18.43 | 14.39 | 21.51 | 21.51 |
| nvidia | 24.27 | 19.05 | 51.84 | 31.11 | 25.72 | 30.40 | 43.73 |
| assemblyai | 34.10 | 25.80 | 51.31 | 19.27 | 29.50 | 32.00 | 32.00 |
| meta | 35.17 | 29.12 | 51.44 | 27.90 | 29.20 | 34.57 | 102.96 |
| elevenlabs | 34.65 | 32.91 | 64.87 | 32.34 | 35.77 | 40.11 | 40.11 |
| microsoft | 35.93 | 42.73 | 64.06 | 35.20 | 30.03 | 41.59 | 49.76 |
| xai | 44.60 | 46.94 | 81.45 | 58.23 | 58.18 | 57.88 | 57.88 |
| deepgram | 58.84 | 53.48 | 90.90 | 68.19 | 62.02 | 66.69 | 66.69 |
| google | 39.16 | 62.81 | 108.86 | 54.77 | 69.09 | 66.94 | 82.00 |

## Supplementary meeting sets

Not in the macro. NVIDIA lists ICSI and DiPCo as Nemotron 3.5 Transcribe (`nvidia`) training data.

| Provider | ICSI | DiPCo | Agentic |
|---|---|---|---|
| aircaps | 14.63 | 32.04 | 8.46 |
| nvidia | 10.04 | 29.42 | 13.35 |
| assemblyai | 24.06 | 37.69 | 18.98 |
| meta | 28.48 | 39.56 | 15.40 |
| elevenlabs | 36.91 | 48.97 | 14.96 |
| microsoft | 37.60 | 41.33 | 10.10 |
| xai | 42.20 | 82.23 | 34.08 |
| deepgram | 41.67 | 92.42 | 25.54 |
| google | 57.90 | 94.98 | 17.14 |

## Easier speech

Two-person conversations (DAI English) and single-speaker clips, where cpWER equals WER.

| Provider | DAI English | VoxPopuli | LibriSpeech test-clean | Earnings-22 clips | Mean, single-speaker |
|---|---|---|---|---|---|
| aircaps | 5.12 | 6.47 | 1.58 | 10.78 | 6.28 |
| nvidia | 5.72 | 6.76 | 1.44 | 9.88 | 6.03 |
| assemblyai | 12.44 | 6.74 | 1.62 | 10.64 | 6.33 |
| meta | 11.98 | 10.65 | 5.15 | 12.25 | 9.35 |
| elevenlabs | 4.39 | 7.51 | 1.82 | 9.33 | 6.22 |
| microsoft | 4.10 | 7.10 | 1.91 | 8.69 | 5.90 |
| xai | 15.48 | 7.67 | 2.11 | 9.74 | 6.51 |
| deepgram | 16.89 | 8.61 | 2.57 | 15.00 | 8.73 |
| google | 8.70 | 6.73 | 2.30 | 11.10 | 6.71 |

## Internal recordings

7 recordings made by AirCaps (data not published).

| Provider | All 7 | Office meeting 1 | Office meeting 2 | Office meeting 3 | Ad-hoc technical discussion | Office meeting 4 | High-overlap crosstalk | Open-plan office |
|---|---|---|---|---|---|---|---|---|
| aircaps | 21.89 | 9.39 | 13.86 | 19.11 | 20.81 | 24.48 | 29.84 | 32.15 |
| nvidia | 33.80 | 14.34 | 19.13 | 26.15 | 29.87 | 37.29 | 37.84 | 64.45 |
| assemblyai | 31.82 | 18.51 | 23.85 | 25.86 | 33.63 | 39.60 | 39.55 | 32.05 |
| meta | 30.85 | 16.71 | 20.61 | 25.54 | 33.41 | 39.50 | 36.66 | 30.80 |
| elevenlabs | 50.80 | 11.14 | 18.30 | 58.28 | 71.99 | 49.75 | 81.51 | 56.90 |
| microsoft | 43.80 | 24.20 | 17.72 | 28.58 | 48.79 | 52.33 | 48.67 | 68.70 |
| xai | 52.65 | 33.72 | 61.89 | 52.26 | 55.30 | 60.14 | 52.85 | 46.23 |
| deepgram | 82.26 | 33.15 | 69.14 | 96.54 | 94.59 | 95.25 | 100.53 | 64.45 |
| google | 53.05 | 20.45 | 20.57 | 62.20 | 68.12 | 60.22 | 60.98 | 53.71 |

## Error composition, English main sets

Pooled over NOTSOFAR-1, AMI and CHiME-6, in % of reference words.

| Provider | Deletions | Substitutions | Insertions |
|---|---|---|---|
| aircaps | 7.99 | 7.41 | 4.88 |
| nvidia | 9.52 | 11.60 | 6.04 |
| assemblyai | 25.80 | 6.23 | 2.70 |
| meta | 28.73 | 4.33 | 3.12 |
| elevenlabs | 18.79 | 9.03 | 10.94 |
| microsoft | 24.73 | 8.13 | 8.86 |
| xai | 38.91 | 9.78 | 1.95 |
| deepgram | 39.79 | 10.84 | 11.74 |
| google | 26.62 | 15.02 | 13.44 |

Failed requests, scored as empty transcripts: google voxpopuli 1.

By overlap and by number of speakers: [`breakdown/`](breakdown/). Speed: [`speed.md`](speed.md).
