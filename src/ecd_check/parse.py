"""Section table parsing (CSV or tab separated). Mirrors parseSectionsText in web/app.html."""

from __future__ import annotations

import math
import re
from typing import Dict, List, Optional

from .core import InputError

MAX_ROWS = 50000
_NUM_RE = re.compile(r"^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$")

_HEADER_KEYS = {
    "name": ("name", "section", "label", "description"),
    "hole_id_in": ("hole", "casing", "id", "d2"),
    "pipe_od_in": ("pipe", "od", "d1", "string"),
    "length_ft": ("length", "len", "md", "ft"),
}


def _to_float(cell: str) -> Optional[float]:
    t = cell.strip()
    if t == "" or not _NUM_RE.match(t):
        return None
    try:
        x = float(t)
    except ValueError:
        return None
    return x if math.isfinite(x) else None


def _split(line: str) -> List[str]:
    sep = "\t" if "\t" in line else ","
    return [c.strip().strip('"').strip() for c in line.split(sep)]


def _match_header(cells: List[str]) -> Optional[Dict[str, int]]:
    low = [c.lower() for c in cells]
    mapping: Dict[str, int] = {}
    # Order matters: match the most specific names first.
    for key in ("length_ft", "pipe_od_in", "hole_id_in", "name"):
        for i, c in enumerate(low):
            if i in mapping.values():
                continue
            if any(tok in c for tok in _HEADER_KEYS[key]):
                mapping[key] = i
                break
    if all(k in mapping for k in ("hole_id_in", "pipe_od_in", "length_ft")):
        return mapping
    return None


def parse_sections_text(text: str) -> List[Dict[str, object]]:
    """Parse a section table. Columns: name, hole_id_in, pipe_od_in, length_ft.

    A header row is detected when its numeric columns are not numbers. Without a header,
    four or more columns are read as name, hole ID, pipe OD, length (extra columns ignored);
    exactly three columns are read as hole ID, pipe OD, length.
    """
    if not isinstance(text, str):
        raise InputError("Section file must be text.")
    text = text.lstrip("\ufeff")
    lines = [(i + 1, ln) for i, ln in enumerate(text.replace("\r\n", "\n").replace("\r", "\n").split("\n"))]
    lines = [(no, ln) for no, ln in lines if ln.strip() != "" and not ln.lstrip().startswith("#")]
    if not lines:
        raise InputError("Section file is empty.")
    if len(lines) > MAX_ROWS + 1:
        raise InputError(f"Section file has more than {MAX_ROWS} rows.")
    first = _split(lines[0][1])
    mapping = None
    numeric_first = [c for c in first if _to_float(c) is not None]
    if len(numeric_first) < 3:
        mapping = _match_header(first)
        if mapping is None:
            no, raw = lines[0]
            raise InputError(
                f"Line {no} is neither a header row (name, hole_id_in, pipe_od_in, length_ft) nor a data row "
                f'with numbers for hole ID, pipe OD and length: "{raw.strip()[:60]}".'
            )
        body = lines[1:]
    else:
        body = lines
    out: List[Dict[str, object]] = []
    for no, ln in body:
        cells = _split(ln)
        if mapping is not None:
            if max(mapping.values()) >= len(cells):
                raise InputError(f"Line {no}: expected at least {max(mapping.values()) + 1} columns.")
            name = cells[mapping["name"]] if "name" in mapping else ""
            raw = [cells[mapping["hole_id_in"]], cells[mapping["pipe_od_in"]], cells[mapping["length_ft"]]]
        elif len(cells) >= 4:
            name, raw = cells[0], cells[1:4]
        elif len(cells) == 3:
            name, raw = "", cells
        else:
            raise InputError(f"Line {no}: expected name, hole ID, pipe OD, length.")
        vals = [_to_float(c) for c in raw]
        labels = ("hole/casing ID", "pipe OD", "length")
        for v, c, lab in zip(vals, raw, labels):
            if v is None:
                raise InputError(f"Line {no}: {lab} {c!r} is not a number.")
        out.append({"name": name[:80] or f"Section {len(out) + 1}", "hole_id_in": vals[0], "pipe_od_in": vals[1], "length_ft": vals[2]})
    if not out:
        raise InputError("Section file has a header but no data rows.")
    return out
