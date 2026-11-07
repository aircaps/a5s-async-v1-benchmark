"""AMI and ICSI meeting corpora: the test meetings, one distant microphone, references from the official NXT
word-level annotations (one file per speaker, a time per word). CC BY 4.0.

ami   AMI Meeting Corpus, full-corpus-ASR test split: ES2004a-d, IS1009a-d, TS3003a-d, EN2002a-d, single distant
      mic Array1-01. https://groups.inf.ed.ac.uk/ami/download/ : <meeting>.Array1-01.wav from
      AMICorpusMirror/amicorpus/<meeting>/audio/ and AMICorpusAnnotations/ami_public_manual_1.6.2.zip, extracted.
icsi  ICSI Meeting Corpus, the test meetings used by Kaldi and lhotse: Bmr013, Bmr018, Bro021, desk mic chan6.
      https://groups.inf.ed.ac.uk/ami/icsi/ : ICSIsignals/SPH/<meeting>/chan6.sph and
      ICSICorpusAnnotations/ICSI_core_NXT.zip, extracted.

Punctuation tokens are dropped (AMI punc="true"; ICSI classes ".", CM, HYPH, LQUOTE, RQUOTE), except that a
sentence end (. ? !) is kept on the word before it, since the scorer normalises one sentence at a time. ICSI's
separate possessive "'s" is joined to its word, and the few ICSI words without times take the previous word's time.
"""
import xml.etree.ElementTree as ET
from pathlib import Path

from .common import to_wav, write_dataset

SETS = {
    "ami": (["ES2004a", "ES2004b", "ES2004c", "ES2004d", "IS1009a", "IS1009b", "IS1009c", "IS1009d",
             "TS3003a", "TS3003b", "TS3003c", "TS3003d", "EN2002a", "EN2002b", "EN2002c", "EN2002d"],
            "{m}.Array1-01.wav", "words/{m}.*.words.xml"),
    "icsi": (["Bmr013", "Bmr018", "Bro021"], "{m}/chan6.sph", "Words/{m}.*.words.xml"),
}
PUNCTUATION = {".", "CM", "HYPH", "LQUOTE", "RQUOTE"}


def prepare(name: str, source: Path, out: Path) -> None:
    meetings, audio_pattern, words_pattern = SETS[name]
    recordings, segments = [], []
    for m in meetings:
        audio = next(source.rglob(audio_pattern.format(m=m)))
        to_wav(audio, out / "audio" / f"{m}.wav")
        recordings.append({"id": m, "language": "en", "source": audio.name if name == "ami" else f"{m}/{audio.name}"})
        files = {p.name: p for p in sorted(source.rglob(words_pattern.format(m=m)))}  # one per speaker, even if extracted twice
        for path in files.values():
            speaker = path.name.split(".")[1]
            segments += [{"session_id": m, "speaker": speaker, "start_time": start, "end_time": end, "words": text}
                         for start, end, text in words(path)]
    write_dataset(out, recordings, segments)


def words(path: Path) -> list[tuple]:
    out, last = [], 0.0
    for w in ET.parse(path).getroot().iter("w"):
        text = (w.text or "").strip()
        if w.get("punc") == "true" or w.get("c") in PUNCTUATION or not text:
            if text in (".", "?", "!") and out:
                out[-1] = (out[-1][0], out[-1][1], out[-1][2] + text)
            continue
        start = float(w.get("starttime") or last)
        end = max(start, float(w.get("endtime") or start))
        last = end
        if w.get("c") == "APOSS" and out:
            out[-1] = (out[-1][0], end, out[-1][2] + w.text.strip())
        else:
            out.append((start, end, w.text.strip()))
    return out
