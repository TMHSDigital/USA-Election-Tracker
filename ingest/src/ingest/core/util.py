"""Small helpers: slugs, name normalization, deterministic source ids."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import UTC, date, datetime

from .models import Office

_SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text or "x"


def race_id(
    year: int, office: Office, state_po: str, district: int | None = None, special: bool = False
) -> str:
    parts = [str(year), office.value, state_po.lower()]
    if office == Office.HOUSE:
        if district is None:
            raise ValueError("house race needs a district")
        parts.append(f"{district:02d}")
    if special:
        parts.append("special")
    return "-".join(parts)


def url_source_id(prefix: str, url: str) -> str:
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:10]
    return f"{prefix}:{digest}"


def name_tokens(name: str) -> list[str]:
    """Lowercase ASCII tokens with punctuation and suffixes removed.

    Handles both "Last, First M." and "First M. Last" orders by returning
    tokens; callers compare sets or last tokens.
    """
    text = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"\([^)]*\)|\"[^\"]*\"", " ", text)  # drop nicknames in quotes/parens
    tokens = [t for t in re.split(r"[^a-zA-Z']+", text.lower()) if t]
    tokens = [t.replace("'", "") for t in tokens]
    return [t for t in tokens if t not in _SUFFIXES and t not in {"mr", "mrs", "ms", "dr"}]


def last_name(name: str) -> str:
    """Best-effort surname. "LAST, FIRST" -> LAST; otherwise final token."""
    if "," in name:
        head = name.split(",", 1)[0]
        toks = name_tokens(head)
        return toks[-1] if toks else ""
    toks = name_tokens(name)
    return toks[-1] if toks else ""


def first_name(name: str) -> str:
    if "," in name:
        tail = name.split(",", 1)[1]
        toks = name_tokens(tail)
        return toks[0] if toks else ""
    toks = name_tokens(name)
    return toks[0] if toks else ""


def sort_key_last_name(name: str) -> tuple[str, str]:
    return (last_name(name), first_name(name))


def parse_bool(v: str | bool | None) -> bool:
    if isinstance(v, bool):
        return v
    return str(v or "").strip().lower() in {"true", "yes", "y", "1", "x"}


def parse_date(v: str | date | None) -> date | None:
    if v is None or v == "":
        return None
    if isinstance(v, date):
        return v
    v = v.strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(v, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"unrecognized date {v!r}")


def to_datetime(d: date | datetime | str) -> datetime:
    if isinstance(d, datetime):
        return d if d.tzinfo else d.replace(tzinfo=UTC)
    if isinstance(d, str):
        d = parse_date(d)  # type: ignore[assignment]
    assert isinstance(d, date)
    return datetime(d.year, d.month, d.day, tzinfo=UTC)
