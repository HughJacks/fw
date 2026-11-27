"""Masks on disk: per block, like links ({block id: [[start, end], …]} of its own text; a quote inside, [[0, 1]];
a block not listed shows nothing). In memory a mask is anchors into the target's draft, for the lens."""

from __future__ import annotations

from fw.block.case import quoted
from fw.block.view import block_draft, regions
from fw.lens import normalize, spans_of


def per_block(regs: list, mask: list | None) -> dict | None:
    """Anchors -> what shows of each block."""
    if mask is None:
        return None
    spans, out = spans_of(mask), {}
    for bid, s, e, quote in regs:
        if quote:
            got = [[0, 1]] if any(a < e and b > s for a, b in spans) else []
        else:
            got = [[max(a, s) - s, min(b, e) - s] for a, b in spans
                   if a < b and (max(a, s) < min(b, e) or s == e and a <= s and e <= b)
                   or a == b and s <= a <= e]  # (an empty place)
        if got:
            out[bid] = got
    return out


def flat_mask(regs: list, draft: str, mask: dict | None) -> list | None:
    """What shows of each block -> anchors into the draft (a quote shown spans from the text before it to the text
    after)."""
    if mask is None:
        return None
    spans = []
    for n, (bid, s, e, quote) in enumerate(regs):
        if bid not in mask:
            continue
        if quote:
            spans.append([regs[n - 1][2] if n else 0, regs[n + 1][1] if n + 1 < len(regs) else len(draft)])
        else:
            spans += [[s + a, s + min(b, e - s)] for a, b in mask[bid] if 0 <= a <= b]
    merged = []
    for a, b in sorted(spans):
        if merged and a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    return normalize(draft, [x for span in merged for x in span], keep_empty=True)


def convert_masks(blocks_list: list, to_disk: bool) -> list:
    """Every Quote's mask and inner masks per block (to disk) or as anchors (from it); other blocks as they are."""
    blocks, drafts = {b.get("id"): b for b in blocks_list}, {}
    def turn(target: str, mask):
        if target not in blocks or mask is None:
            return mask
        if target not in drafts:
            draft = block_draft(blocks, target)
            drafts[target] = (draft, regions(blocks, target, draft))
        draft, regs = drafts[target]
        return per_block(regs, mask) if to_disk else flat_mask(regs, draft, mask)
    out = []
    for b in blocks_list:
        c = b.get("content")
        if not (isinstance(c, dict) and ("mask" in c or "inner" in c)):
            out.append(b)
            continue
        c = dict(c)
        if "mask" in c:
            c["mask"] = turn(c["quote"], c["mask"])
        if "inner" in c:   # (one for a quote that's gone goes with it)
            c["inner"] = {k: turn(quoted(blocks[k])[0], m) for k, m in c["inner"].items() if quoted(blocks.get(k))}
        out.append({**b, "content": c})
    return out


def masks_out(blocks_list: list) -> list:
    """The blocks as written to disk: masks per block."""
    return convert_masks(blocks_list, True)


def masks_in(blocks_list: list) -> list:
    """The blocks as read from disk: masks as anchors."""
    return convert_masks(blocks_list, False)
