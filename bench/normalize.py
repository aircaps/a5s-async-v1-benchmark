"""Text normalisation, applied identically to references and hypotheses before scoring.

English uses the Hugging Face Open ASR Leaderboard's normaliser (bench/open_asr, copied unchanged): lower case, no
punctuation, spelled-out numbers to digits, US spellings, contractions expanded, filler words removed, spelled-out
letters joined. As on the leaderboard, which normalises one utterance at a time, text is first split into
sentences at . ? ! and each sentence is normalised on its own; otherwise numbers merge across sentences
("I have two. Three people came." would become "i have 23 people came").
Mandarin is scored per character after the leaderboard's basic normaliser removes punctuation.

Two rules come first, for formatting the normaliser does not reconcile:
- the ellipsis "…" marks a pause, like a dash, and is removed as one (the normaliser would leave a stray ".");
- numerals separated only by spaces are joined ("20 21" -> "2021", "5 5 5" -> "555"), and so are clock times
  ("7:30" -> "730"; whole hours are left to the normaliser, "3:00" -> "3"), so digits written apart are grouped
  the way spoken digits are ("twenty twenty one" -> "2021", "seven thirty" -> "730"); Artificial Analysis's
  speech-to-text benchmark likewise treats grouped and ungrouped digits as equal.
Any token still left with no letter or digit is dropped.
"""
import re

from .open_asr.normalizer import BasicTextNormalizer, EnglishTextNormalizer

_english = EnglishTextNormalizer()
_basic = BasicTextNormalizer()
# whole numerals separated by spaces, not part of a decimal, a time or a grouped number ("1.5 2", "7:30 8", "1,000 2")
_spaced_digits = re.compile(r"(?<![\d.,:])\d+(?:[ \t]+\d+)+(?![.,:]\d)")
_clock_time = re.compile(r"\b(\d{1,2}):((?!00)[0-5]\d)\b")
_sentence_end = re.compile(r"(?<=[.?!])\s+")


def normalize(text: str, language: str) -> str:
    text = _clock_time.sub(r"\1\2", text.replace("…", "—"))
    text = _spaced_digits.sub(lambda m: "".join(m.group(0).split()), text)
    if language == "en":
        text = " ".join(_english(sentence) for sentence in _sentence_end.split(text))
    elif language == "zh":
        text = " ".join(_basic(text).replace(" ", ""))
    else:
        text = _basic(text)
    return " ".join(t for t in text.split() if any(c.isalnum() for c in t))
