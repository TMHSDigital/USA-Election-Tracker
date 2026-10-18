"""Experimental: unofficial live results from Clarity ENR statewide sites.

Only contests explicitly mapped in data/seeds/live-sources-2026.yaml are
emitted, exactly as the source reports them: candidate names, party codes,
vote counts, precincts reporting, and the source's own update time. The
source's winner flags are never read. Candidates keep the source's order.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import yaml

from ..core.adapter import Adapter, Dataset, ValidationFailed
from ..core.models import LiveResultRow, SourceRecord

CLARITY = "https://results.enr.clarityelections.com"
CONFIG = "live-sources-2026.yaml"
TZ = {
    "EST": "America/New_York",
    "EDT": "America/New_York",
    "CST": "America/Chicago",
    "CDT": "America/Chicago",
    "MST": "America/Denver",
    "MDT": "America/Denver",
    "PST": "America/Los_Angeles",
    "PDT": "America/Los_Angeles",
}


@dataclass
class Fetched:
    config: dict[str, Any]
    version: str
    summary: list[dict[str, Any]]
    settings: dict[str, Any]
    summary_url: str


def parse_updated(value: str | None) -> datetime | None:
    """Parse Clarity's 'websiteupdatedat', e.g. '12/18/2024 8:58:00 AM EST'."""
    if not value:
        return None
    try:
        stamp, tz = value.rsplit(" ", 1)
        dt = datetime.strptime(stamp, "%m/%d/%Y %I:%M:%S %p")
        return dt.replace(tzinfo=ZoneInfo(TZ[tz]))
    except (ValueError, KeyError):
        return None


class ClarityAdapter(Adapter):
    id = "live_clarity"
    description = "Unofficial results from Clarity ENR (experimental)"
    experimental = True
    max_age = timedelta(minutes=30)

    def fetch(self) -> list[Fetched]:
        cfg = yaml.safe_load(
            (self.ctx.repo_root / "data" / "seeds" / CONFIG).read_text(encoding="utf-8")
        )
        out = []
        for j in cfg.get("jurisdictions", []):
            if j.get("platform") != "clarity" or not j.get("election_id") or not j.get("contests"):
                continue
            base = f"{CLARITY}/{j['state_po']}/{j['election_id']}"
            version = self.ctx.http.get(f"{base}/current_ver.txt").text.strip()
            if not version.isdigit():
                raise ValidationFailed(f"{j['state_po']}: bad version {version!r}")
            summary_url = f"{base}/{version}/json/en/summary.json"
            summary = json.loads(self.ctx.http.get(summary_url).content)
            settings = json.loads(
                self.ctx.http.get(f"{base}/{version}/json/en/electionsettings.json").content
            )
            out.append(Fetched(j, version, summary, settings, summary_url))
        return out

    def validate(self, raw: list[Fetched]) -> list[Fetched]:
        for f in raw:
            if not isinstance(f.summary, list):
                raise ValidationFailed(f"{f.config['state_po']}: summary is not a list")
            names = {c.get("C") for c in f.summary}
            missing = [c for c in f.config["contests"] if c not in names]
            if missing:
                raise ValidationFailed(f"{f.config['state_po']}: mapped contests missing {missing}")
            for c in f.summary:
                if c.get("C") in f.config["contests"]:
                    n = len(c.get("CH") or [])
                    if not n or len(c.get("V") or []) != n:
                        raise ValidationFailed(f"{c.get('C')}: choices and votes misaligned")
                    if any((v or 0) < 0 for v in c["V"]):
                        raise ValidationFailed(f"{c.get('C')}: negative votes")
        return raw

    def normalize(self, raw: list[Fetched]) -> Dataset:
        now = self.ctx.now
        rows: list[LiveResultRow] = []
        sources: list[SourceRecord] = []
        contests_out: list[dict[str, Any]] = []
        for f in raw:
            po = f.config["state_po"]
            sid = f"clarity:{po.lower()}:{f.config['election_id']}"
            updated = parse_updated(f.settings.get("websiteupdatedat"))
            web = (f.settings.get("pagesettings") or {}).get("web") or {}
            unit_label = web.get("reporting") or "Reporting"
            public = f"{CLARITY}/{po}/{f.config['election_id']}/"
            sources.append(
                SourceRecord(
                    source_id=sid,
                    name=f"{po} official election night results (Clarity ENR), version {f.version}",
                    publisher=f"{po} state election officials via Clarity ENR",
                    url=public,
                    license="Official public election results; unofficial until certified",
                    retrieved_at=now,
                    source_published_at=updated,
                    notes="Unofficial. Copied on a schedule; the source is more current.",
                )
            )
            for c in f.summary:
                race = f.config["contests"].get(c.get("C"))
                if not race:
                    continue
                pr, tp = c.get("PR"), c.get("TP")
                # PR/TP count the site's reporting units (counties on statewide sites),
                # so use the source's own label for them rather than assuming precincts.
                reporting = f"{unit_label}: {pr} of {tp}" if pr is not None and tp else None
                cands = []
                for i, name in enumerate(c["CH"]):
                    party = (c.get("P") or [None] * len(c["CH"]))[i] or None
                    votes = int(c["V"][i] or 0)
                    rows.append(
                        LiveResultRow(
                            race_id=race,
                            state_po=po,
                            source_contest_name=c["C"],
                            candidate_name=name,
                            party_label=party,
                            votes=votes,
                            reporting_text=reporting,
                            precincts_reporting=pr,
                            precincts_total=tp,
                            source_updated_at=updated,
                            fetched_at=now,
                            source_ids=[sid],
                        )
                    )
                    cands.append({"candidate_name": name, "party_label": party, "votes": votes})
                contests_out.append(
                    {
                        "race_id": race,
                        "state_po": po,
                        "source_contest_name": c["C"],
                        "reporting_text": reporting,
                        "source_updated_at": updated.isoformat() if updated else None,
                        "fetched_at": now.isoformat(),
                        "source_url": public,
                        "source_ids": [sid],
                        "candidates": cands,
                    }
                )
        extra = {"contests.json": json.dumps(contests_out, separators=(",", ":")).encode()}
        return Dataset(
            tables={"live_results": rows}, sources=sources, retrieved_at=now, extra_files=extra
        )
