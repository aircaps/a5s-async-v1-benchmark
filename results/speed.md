## Provider limits

| Provider | Slots | Rate limit | Per-request limit |
|---|---|---|---|
| aircaps |  |  |  |
| assemblyai |  |  |  |
| deepgram |  |  |  |
| elevenlabs | 4 per file over 8 min |  |  |
| google |  |  | 30 min |
| microsoft |  | 600 per 60 s | 120 min |
| xai |  | 10 per 1 s |  |

## C. Single-request latency (one file at a time)

| Provider | 45-75 min p50 / p90 s | Audio ÷ latency | Failures | Cap gate |
|---|---|---|---|---|
| aircaps | 9.8 / 10.9 | 311 | 0 | ok |
| assemblyai | 18.0 / 18.8 | 171 | 0 | ok |
| deepgram | 6.3 / 7.3 | 477 | 0 | ok |
| elevenlabs | 53.8 / 79.4 | 52 | 0 | ok |
| google | 34.3 / 83.4 | 65 | 0 | ok |
| microsoft | 12.3 / 13.7 | 245 | 0 | ok |
| xai | 17.6 / 21.7 | 178 | 0 | ok |

## B2. Hour-long meetings, 14 in flight (median round)

| Provider | In flight | Audio-h per h | 45-75 min p50 / p90 s | Audio ÷ latency | 429s | Rate waits | Retries | Failures | Cap gate | Flags |
|---|---|---|---|---|---|---|---|---|---|---|
| aircaps | 14 | 3739 | 11.0 / 13.0 | 267 | 0 | 0 | 0 | 0 | ok |  |
| assemblyai | 14 | 2278 | 17.1 / 22.1 | 163 | 0 | 0 | 0 | 0 | ok |  |
| deepgram | 14 | 6578 | 6.1 / 8.6 | 470 | 0 | 0 | 0 | 0 | ok |  |
| elevenlabs | 14 | 750 | 55.0 / 71.8 | 54 | 0 | 0 | 0 | 0 | ok |  |
| google | 14 | 673 | 30.9 / 78.1 | 65 | 0 | 0 | 0 | 0 | ok | split |
| microsoft | 14 | 3109 | 13.2 / 17.1 | 222 | 0 | 0 | 0 | 0 | ok |  |
| xai | 14 | 2012 | 14.8 / 28.9 | 144 | 0 | 0 | 0 | 0 | ok |  |

## Rounds (audio-h per wall-clock h, in order)

| Provider | B2 |
|---|---|
| aircaps | 3759 / 3677 / 3739 |
| assemblyai | 2360 / 2278 / 2176 |
| deepgram | 6608 / 6578 / 6297 |
| elevenlabs | 750 / 660 / 863 |
| google | 662 / 686 / 673 |
| microsoft | 3109 / 3031 / 3198 |
| xai | 1972 / 2451 / 2012 |

## Accuracy against speed

cpWER: pooled over exactly the panel's recordings, from the accuracy run. Speed: audio length ÷ latency over the panel's files (total audio over total latency), median round of B2; p50: median latency per file.

### Hour-long meetings

| Provider | Recordings | Audio h | cpWER % | Audio ÷ latency | p50 latency s | Cap gate |
|---|---|---|---|---|---|---|
| aircaps | 16 | 13.4 | 24.47 | 267 | 11.0 | ok |
| assemblyai | 16 | 13.4 | 34.11 | 163 | 17.1 | ok |
| deepgram | 16 | 13.4 | 67.16 | 470 | 6.1 | ok |
| elevenlabs | 16 | 13.4 | 44.98 | 54 | 55.0 | ok |
| google | 16 | 13.4 | 109.74 | 65 | 30.9 | ok |
| microsoft | 16 | 13.4 | 41.35 | 222 | 13.2 | ok |
| xai | 16 | 13.4 | 63.50 | 144 | 14.8 | ok |

## Client

| Provider process | Max CPU (% of one core) | Max event-loop lag s |
|---|---|---|
| aircaps | 11 | 0.04 |
| assemblyai | 9 | 0.01 |
| deepgram | 17 | 0.00 |
| elevenlabs | 4 | 0.01 |
| google | 3 | 0.47 |
| microsoft | 10 | 0.00 |
| xai | 6 | 0.00 |

Machine, every 5 s over the run: CPU mean 0%, max 7%; network out max 686 MB/s, in max 5 MB/s.

