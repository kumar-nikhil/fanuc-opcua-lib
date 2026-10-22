"""
Conversion between Python values and the signed 16-bit holding register words.

32-bit values use two words, lower 16 bits first (manual 55.3.1). Strings pack two
characters per word, first character in the lower byte ($MULTIPLY = 1).
"""
from __future__ import annotations

import struct
from typing import List, Sequence

from .types import Config, Position

POSITION_WORDS = 50
STRING_REGISTER_WORDS = 40
PROGRAM_STATUS_WORDS = 18


def tidy(value: float) -> float:
    """Drop float32 noise: 538.0999755859375 -> 538.1."""
    return float(f"{value:.7g}")


def to_int16(value: int) -> int:
    """Map 0..65535 or -32768..32767 to the signed int16 the server expects."""
    if not -32768 <= value <= 65535:
        raise ValueError(f"{value} does not fit in 16 bits")
    return value - 65536 if value > 32767 else value


def words_to_float(lo: int, hi: int) -> float:
    return tidy(struct.unpack("<f", struct.pack("<hh", lo, hi))[0])


def float_to_words(value: float) -> List[int]:
    return list(struct.unpack("<hh", struct.pack("<f", float(value))))


def words_to_int32(lo: int, hi: int) -> int:
    return struct.unpack("<i", struct.pack("<hh", lo, hi))[0]


def int32_to_words(value: int) -> List[int]:
    return list(struct.unpack("<hh", struct.pack("<i", int(value))))


def words_to_floats(words: Sequence[int]) -> List[float]:
    return [words_to_float(words[i], words[i + 1]) for i in range(0, len(words) - 1, 2)]


def words_to_str(words: Sequence[int]) -> str:
    raw = struct.pack(f"<{len(words)}h", *words)
    return raw.split(b"\x00", 1)[0].decode("latin-1")


def str_to_words(text: str, n_words: int) -> List[int]:
    """Encode `text` NUL-terminated into exactly `n_words` words."""
    raw = text.encode("latin-1")
    if len(raw) > n_words * 2 - 1:
        raise ValueError(f"String is too long: {len(raw)} characters, maximum is {n_words * 2 - 1}")
    raw = raw.ljust(n_words * 2, b"\x00")
    return list(struct.unpack(f"<{n_words}h", raw))


def decode_position(words: Sequence[int]) -> Position:
    """Decode the 50-word position structure assigned with $MULTIPLY = 0."""
    if len(words) < POSITION_WORDS:
        raise ValueError(f"A position needs {POSITION_WORDS} words, got {len(words)}")
    cart = words_to_floats(words[0:18])
    joints = words_to_floats(words[26:44])
    if not any(joints[6:]):
        joints = joints[:6]
    return Position(
        x=cart[0], y=cart[1], z=cart[2], w=cart[3], p=cart[4], r=cart[5],
        ext=(cart[6], cart[7], cart[8]),
        config=Config(
            flip=bool(words[18]), left=bool(words[19]), up=bool(words[20]), front=bool(words[21]),
            turn4=words[22], turn5=words[23], turn6=words[24],
        ),
        joints=tuple(joints),
        valid_cartesian=bool(words[25]),
        valid_joint=bool(words[44]),
        uf=words[45],
        ut=words[46],
        representation="cartesian" if words[25] else "joint",
    )


def encode_cartesian(pos: Position) -> List[int]:
    """Words 1-25 of the position structure: x..r, e1..e3 and configuration."""
    words: List[int] = []
    for value in (*pos.xyzwpr, *pos.ext):
        words += float_to_words(value)
    c = pos.config
    words += [int(c.flip), int(c.left), int(c.up), int(c.front), c.turn4, c.turn5, c.turn6]
    return words


def encode_joints(pos: Position) -> List[int]:
    """Words 27.. of the position structure: one float per given joint."""
    if not pos.joints:
        raise ValueError("Position has no joint values")
    words: List[int] = []
    for j in pos.joints:
        words += float_to_words(j)
    return words
