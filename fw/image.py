"""Pictures: what kind a file is and how big, from its first bytes. Pure: bytes in, values out."""

from __future__ import annotations

import struct

KINDS = {b"\x89PNG\r\n\x1a\n": "png", b"\xff\xd8": "jpg", b"GIF87a": "gif", b"GIF89a": "gif"}


def kind(head: bytes) -> str | None:
    """The picture format of a file starting with `head`, else None."""
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    return next((k for magic, k in KINDS.items() if head.startswith(magic)), None)


def size(data: bytes) -> tuple[int, int] | None:
    """(width, height) in pixels of a picture's bytes, else None."""
    match kind(data):
        case "png" if len(data) >= 24:
            return struct.unpack(">II", data[16:24])
        case "gif" if len(data) >= 10:
            return struct.unpack("<HH", data[6:10])
        case "jpg":
            return jpeg_size(data)
        case "webp":
            return webp_size(data)
    return None


def jpeg_size(data: bytes) -> tuple[int, int] | None:
    """Walk a JPEG's segments to its frame header (SOFn)."""
    i = 2
    while i + 9 < len(data):
        if data[i] != 0xFF:
            return None
        marker = data[i + 1]
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            i += 2
            continue
        length = struct.unpack(">H", data[i + 2:i + 4])[0]
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            h, w = struct.unpack(">HH", data[i + 5:i + 9])
            return w, h
        i += 2 + length
    return None


def webp_size(data: bytes) -> tuple[int, int] | None:
    chunk = data[12:16]
    if chunk == b"VP8 " and len(data) >= 30:
        w, h = struct.unpack("<HH", data[26:30])
        return w & 0x3FFF, h & 0x3FFF
    if chunk == b"VP8L" and len(data) >= 25:
        b = data[21:25]
        return 1 + (((b[1] & 0x3F) << 8) | b[0]), 1 + (((b[3] & 0xF) << 10) | (b[2] << 2) | ((b[1] & 0xC0) >> 6))
    if chunk == b"VP8X" and len(data) >= 30:
        return 1 + int.from_bytes(data[24:27], "little"), 1 + int.from_bytes(data[27:30], "little")
    return None
