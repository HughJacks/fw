"""The rich clipboard: what was last copied in fw, kept beside the store for a paste in any session."""

from __future__ import annotations

import json
import os

from fw.store.paths import CLIP_PATH


def save_clip(clip: dict | None) -> None:
    """Keep `clip` ({"text", and "blocks" (with "cut") or "links"}); None forgets it."""
    try:
        if clip is None:
            return CLIP_PATH.unlink(missing_ok=True)
        tmp = CLIP_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(clip, ensure_ascii=False), encoding="utf-8")
        os.chmod(tmp, 0o600)
        os.replace(tmp, CLIP_PATH)
    except OSError:
        pass


def load_clip() -> dict | None:
    try:
        return json.loads(CLIP_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def clip_holds() -> list:
    """The blocks cut onto the clipboard: kept (not erased) until it holds something else."""
    clip = load_clip()
    return [u["id"] for u in clip.get("blocks", []) if u.get("id")] if clip and clip.get("cut") else []
