"""Regenerate saved fixtures from live sources (trimmed to stay small).

    uv run python tests/make_fixtures.py

Fixtures are committed so tests never touch the network. Re-run only when a
source format changes, and review the diff.
"""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

from ingest.adapters.fec import CN_HEADER_URL, CN_URL, WEBALL_URL
from ingest.adapters.history import MEDSL_SENATE_URL, SNYDER_URL
from ingest.adapters.legislators import URL as LEGISLATORS_URL
from ingest.core.http import LiveHttp

OUT = Path(__file__).parent / "fixtures"


def rezip(content: bytes, keep_states: set[str], state_col: int) -> bytes:
    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        name = next(n for n in zf.namelist() if n.endswith(".txt"))
        lines = zf.read(name).decode("latin-1").splitlines()
    kept = [ln for ln in lines if ln.split("|")[state_col] in keep_states]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(name, "\n".join(kept) + "\n")
    return buf.getvalue()


def main() -> None:
    http = LiveHttp()
    OUT.mkdir(exist_ok=True)
    states = {"AK", "DE", "WY", "GA"}
    (OUT / "fec").mkdir(exist_ok=True)
    (OUT / "fec" / "cn26.zip").write_bytes(rezip(http.get(CN_URL).content, states, 4))
    (OUT / "fec" / "weball26.zip").write_bytes(rezip(http.get(WEBALL_URL).content, states, 18))
    (OUT / "fec" / "cn_header_file.csv").write_bytes(http.get(CN_HEADER_URL).content)

    leg = json.loads(http.get(LEGISLATORS_URL).content)
    senators = [p for p in leg if p["terms"][-1]["type"] == "sen"]
    reps = [p for p in leg if p["terms"][-1]["type"] == "rep" and p["terms"][-1]["state"] in states]
    # Pad to the adapter's plausibility floor with additional representatives.
    others = [p for p in leg if p["terms"][-1]["type"] == "rep" and p not in reps]
    trimmed = [
        {"id": {k: p["id"][k] for k in ("bioguide", "fec") if k in p["id"]},
         "name": p["name"], "terms": [p["terms"][-1]]}
        for p in senators + reps + others[: max(0, 500 - len(senators) - len(reps))]
    ]
    (OUT / "legislators-current.json").write_text(json.dumps(trimmed), encoding="utf-8")

    (OUT / "history").mkdir(exist_ok=True)
    sen = http.get(MEDSL_SENATE_URL).text.splitlines()
    (OUT / "history" / "senate.csv").write_text(
        "\n".join([sen[0]] + [ln for ln in sen[1:] if ",AK," in ln or ",GA," in ln]) + "\n",
        encoding="utf-8")
    sny = http.get(SNYDER_URL).text.splitlines()
    (OUT / "history" / "snyder.tab").write_text(
        "\n".join([sny[0]] + [ln for ln in sny[1:] if '\t"AK"\t' in ln or '\t"GA"\t' in ln]) + "\n",
        encoding="utf-8")
    print("fixtures written to", OUT)


if __name__ == "__main__":
    main()
