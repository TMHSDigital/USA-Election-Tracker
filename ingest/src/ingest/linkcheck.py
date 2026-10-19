"""Weekly check of the official URLs we link to.

Many state sites sit behind bot protection and answer automated clients with
403, 429 or a challenge redirect even though the page works in a browser.
Those are reported as "needs manual check", not as broken. Only 404, 410,
5xx and connection failures count as broken.
"""

from __future__ import annotations

import csv
from pathlib import Path

import httpx
import yaml

BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/141.0 Safari/537.36"
)
BLOCKED = {401, 403, 405, 406, 429, 503}


def _urls(repo: Path) -> list[tuple[str, str]]:
    seeds = repo / "data" / "seeds"
    out: list[tuple[str, str]] = []
    offices = yaml.safe_load((seeds / "state-election-offices.yaml").read_text(encoding="utf-8"))
    for s in offices["states"]:
        for key in ("homepage_url", "voter_info_url", "results_url"):
            if s.get(key):
                out.append((f"{s['state_po']} {key}", s[key]))
    files = [
        seeds / "governors-2026.csv",
        *sorted((seeds / "federal-candidates-2026").glob("*.csv")),
    ]
    seen: set[str] = set()
    for f in files:
        if not f.exists():
            continue
        with f.open(encoding="utf-8-sig", newline="") as fh:
            for r in csv.DictReader(fh):
                u = (r.get("source_url") or "").strip()
                if u and u not in seen:
                    seen.add(u)
                    out.append((f"{f.name} source", u))
    return out


def run_link_check(repo: Path, report: Path) -> int:
    rows = []
    broken = 0
    with httpx.Client(follow_redirects=True, timeout=30, headers={"User-Agent": BROWSER_UA}) as c:
        for label, url in _urls(repo):
            try:
                status = c.get(url).status_code
                verdict = (
                    "ok"
                    if status < 400
                    else ("needs manual check" if status in BLOCKED else "BROKEN")
                )
            except httpx.HTTPError as e:
                status, verdict = 0, f"BROKEN ({type(e).__name__})"
            if verdict.startswith("BROKEN"):
                broken += 1
            rows.append((verdict, label, url, status))
    rows.sort(key=lambda r: (r[0] == "ok", r[0], r[1]))
    report.parent.mkdir(parents=True, exist_ok=True)
    lines = ["| Result | Item | Status | URL |", "|---|---|---|---|"]
    lines += [f"| {v} | {lab} | {st} | {u} |" for v, lab, u, st in rows if v != "ok"]
    ok = sum(1 for r in rows if r[0] == "ok")
    report.write_text(
        f"Checked {len(rows)} URLs: {ok} ok, {broken} broken.\n\n" + "\n".join(lines) + "\n",
        encoding="utf-8",
    )
    return broken
