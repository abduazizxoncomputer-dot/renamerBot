import bisect
from typing import List, Optional, Tuple

from aiogram.types import MessageEntity


def _utf16_unit_len(ch: str) -> int:
    return 2 if ord(ch) > 0xFFFF else 1


def _build_utf16_offset_map(text: str) -> List[int]:
    """offsets[i] = UTF-16 offset of python char index i; offsets[len(text)] = total UTF-16 length."""
    offsets = [0] * (len(text) + 1)
    cur = 0
    for i, ch in enumerate(text):
        offsets[i] = cur
        cur += _utf16_unit_len(ch)
    offsets[len(text)] = cur
    return offsets


def _utf16_offset_to_py_index(offsets: List[int], u16_offset: int) -> int:
    return bisect.bisect_left(offsets, u16_offset)


def _find_all(text: str, sub: str) -> List[int]:
    if not sub:
        return []
    positions = []
    start = 0
    while True:
        idx = text.find(sub, start)
        if idx == -1:
            break
        positions.append(idx)
        start = idx + len(sub)
    return positions


def replace_preserving_entities(
    text: Optional[str],
    entities: Optional[List[MessageEntity]],
    old: str,
    new: str,
) -> Tuple[Optional[str], Optional[List[MessageEntity]]]:
    """Replace every occurrence of `old` with `new` inside `text`, remapping `entities`
    (bold/italic/text_link/etc.) so formatting keeps covering the same logical spans.
    For text_link/text_mention entities the URL/user is untouched -- only the
    offset/length of the displayed text is recalculated.
    """
    if text is None:
        return None, None
    if not old:
        return text, entities

    positions = _find_all(text, old)
    if not positions:
        return text, entities

    old_len = len(old)
    mapping = [0] * (len(text) + 1)
    new_chars: List[str] = []
    cur_new_len = 0
    occ_idx = 0
    i = 0
    while i <= len(text):
        if occ_idx < len(positions) and positions[occ_idx] == i:
            occ_start = i
            occ_end = i + old_len
            mapping[occ_start] = cur_new_len
            new_chars.append(new)
            cur_new_len += len(new)
            for k in range(occ_start + 1, occ_end):
                mapping[k] = mapping[occ_start]
            mapping[occ_end] = cur_new_len
            i = occ_end
            occ_idx += 1
            continue
        mapping[i] = cur_new_len
        if i < len(text):
            new_chars.append(text[i])
            cur_new_len += 1
        i += 1

    new_text = "".join(new_chars)

    if not entities:
        return new_text, entities

    orig_offsets = _build_utf16_offset_map(text)
    new_offsets = _build_utf16_offset_map(new_text)

    new_entities: List[MessageEntity] = []
    for e in entities:
        orig_start_py = _utf16_offset_to_py_index(orig_offsets, e.offset)
        orig_end_py = _utf16_offset_to_py_index(orig_offsets, e.offset + e.length)
        new_start_py = mapping[orig_start_py]
        new_end_py = mapping[orig_end_py]
        if new_end_py <= new_start_py:
            continue
        new_start_u16 = new_offsets[new_start_py]
        new_end_u16 = new_offsets[new_end_py]
        new_entities.append(
            e.model_copy(update={"offset": new_start_u16, "length": new_end_u16 - new_start_u16})
        )

    new_entities.sort(key=lambda ent: ent.offset)
    return new_text, new_entities
