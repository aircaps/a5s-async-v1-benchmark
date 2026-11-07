"""Mandarin meeting corpora: channel 0 of the 8-channel far-field array, references from the official TextGrid
files (one tier per speaker). CC BY-SA 4.0.

aishell4    AISHELL-4 test set (20 sessions). https://www.openslr.org/resources/111/test.tar.gz, extracted:
            test/wav/<session>.flac and test/TextGrid/<session>.TextGrid.
alimeeting  AliMeeting Eval (8 sessions) and Test (20 sessions), far-field. Eval_Ali.tar.gz and Test_Ali.tar.gz from
            https://www.openslr.org/119/, extracted: <split>_Ali_far/audio_dir/<meeting>_<array>.wav and
            <split>_Ali_far/textgrid_dir/<meeting>.TextGrid.
"""
from pathlib import Path

import textgrid

from .common import to_wav, write_dataset


def prepare(name: str, source: Path, out: Path) -> None:
    if name == "aishell4":
        pairs = [(wav, wav.parent.parent / "TextGrid" / f"{wav.stem}.TextGrid")
                 for wav in sorted(source.rglob("test/wav/*.flac"))]
    else:
        pairs = [(wav, wav.parent.parent / "textgrid_dir" / f"{wav.stem.rsplit('_', 1)[0]}.TextGrid")
                 for wav in sorted(source.rglob("*_Ali_far/audio_dir/*.wav"))]
    recordings, segments = [], []
    for wav, grid in pairs:
        to_wav(wav, out / "audio" / f"{wav.stem}.wav", channel=0)
        recordings.append({"id": wav.stem, "language": "zh", "source": f"{wav.parent.parent.name}/{wav.name} channel 0"})
        for tier in textgrid.TextGrid.fromFile(str(grid)):
            segments += [{"session_id": wav.stem, "speaker": tier.name, "start_time": round(iv.minTime, 3),
                          "end_time": round(iv.maxTime, 3), "words": iv.mark.strip()} for iv in tier if iv.mark.strip()]
    write_dataset(out, recordings, segments)
