"""Text helpers: word counts, narration duration estimates, chunking, hashing."""

from __future__ import annotations

import hashlib
import re

DEFAULT_WPM = 150  # average narration pace for documentary / educational content
WPM_BY_TONE = {
    "calm": 130,
    "documentary": 140,
    "educational": 145,
    "engaging": 150,
    "conversational": 155,
    "energetic": 170,
    "commentary": 165,
    "storytelling": 140,
    "dramatic": 135,
}

_WORD_RE = re.compile(r"[A-Za-z0-9À-ÿ'’\-]+")
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'“(])")


def word_count(text: str) -> int:
    return len(_WORD_RE.findall(text or ""))


def wpm_for_tone(tone: str | None) -> int:
    return WPM_BY_TONE.get((tone or "").lower(), DEFAULT_WPM)


def estimate_duration_seconds(text: str, wpm: int = DEFAULT_WPM) -> float:
    words = word_count(text)
    if words == 0:
        return 0.0
    # Add a small pause budget for punctuation
    pauses = len(re.findall(r"[.!?]", text or "")) * 0.35 + len(re.findall(r"[,;:]", text or "")) * 0.15
    return round(words / max(wpm, 60) * 60.0 + pauses, 2)


def words_for_duration(minutes: float, wpm: int = DEFAULT_WPM) -> int:
    return int(minutes * wpm)


def split_sentences(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", (text or "").strip())
    if not text:
        return []
    return [s.strip() for s in _SENTENCE_RE.split(text) if s.strip()]


def chunk_text(text: str, max_chars: int) -> list[str]:
    """Split text into chunks on sentence boundaries, never exceeding max_chars if avoidable."""
    chunks: list[str] = []
    current = ""
    for sentence in split_sentences(text):
        if len(sentence) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            words = sentence.split(" ")
            piece = ""
            for w in words:
                if len(piece) + len(w) + 1 > max_chars and piece:
                    chunks.append(piece)
                    piece = w
                else:
                    piece = f"{piece} {w}".strip()
            if piece:
                current = piece
            continue
        if len(current) + len(sentence) + 1 > max_chars and current:
            chunks.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        chunks.append(current)
    return chunks


def sha256_text(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def slugify(value: str, max_len: int = 60) -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "-", (value or "").lower()).strip("-")
    return value[:max_len] or "untitled"


def truncate(text: str, n: int) -> str:
    text = text or ""
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"
