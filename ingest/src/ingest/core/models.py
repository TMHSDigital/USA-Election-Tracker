"""Pydantic schemas shared by all adapters.

Every row that ends up on the site carries `source_ids`, and every id must
resolve to a SourceRecord emitted by the same adapter or listed in
sources/registry.yaml. The schemas are versioned by SCHEMA_VERSION; v1 work
(certified results, state legislative races, ballot measures) adds new Office
values and new tables rather than changing these shapes.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

SCHEMA_VERSION = 1

SOURCE_ID_PATTERN = r"^[a-z0-9][a-z0-9_.:-]*$"
STATE_PO_PATTERN = r"^[A-Z]{2}$"


class Row(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SourceRecord(Row):
    source_id: str = Field(pattern=SOURCE_ID_PATTERN)
    name: str = Field(min_length=1)
    publisher: str = Field(min_length=1)
    url: str = Field(pattern=r"^https?://")
    license: str = Field(min_length=1)
    retrieved_at: datetime | None = None
    source_published_at: datetime | None = None
    notes: str = ""


class Office(StrEnum):
    HOUSE = "house"
    SENATE = "senate"
    GOVERNOR = "governor"
    # Reserved for v1. Adding a value here must not change existing race ids.
    STATE_UPPER = "state_upper"
    STATE_LOWER = "state_lower"
    BALLOT_MEASURE = "ballot_measure"


class CandidateListStatus(StrEnum):
    OFFICIAL = "official"
    FEC_REGISTRANTS = "fec_registrants"
    UNAVAILABLE = "unavailable"


class Race(Row):
    race_id: str = Field(pattern=r"^[0-9]{4}-[a-z_]+-[a-z]{2}(-[0-9]{2})?(-special)?$")
    election_date: date
    office: Office
    state_po: str = Field(pattern=STATE_PO_PATTERN)
    district: int | None = None
    special: bool = False
    candidate_list_status: CandidateListStatus
    candidate_list_url: str | None = None
    boundary_set_id: str | None = None
    source_ids: list[str] = Field(min_length=1)


class Candidate(Row):
    candidate_id: str
    race_id: str
    name: str = Field(min_length=1)
    ballot_name: str = Field(min_length=1)
    party_label: str
    incumbent: bool
    ballot_order: int | None = None
    write_in: bool = False
    running_mate: str | None = None
    fec_candidate_id: str | None = Field(default=None, pattern=r"^[HSP][0-9A-Z]{8}$")
    fec_match_method: Literal["seed", "legislators", "name", "override"] | None = None
    list_status: CandidateListStatus
    source_ids: list[str] = Field(min_length=1)


class SeedCandidate(Row):
    """A candidate row from a curated official list (data/seeds), before FEC matching."""

    race_id: str
    state_po: str = Field(pattern=STATE_PO_PATTERN)
    office: Office
    district: int | None = None
    special: bool = False
    name: str = Field(min_length=1)
    ballot_name: str = Field(min_length=1)
    party_label: str
    incumbent: bool
    ballot_order: int | None = None
    write_in: bool = False
    running_mate: str | None = None
    fec_candidate_id: str | None = Field(default=None, pattern=r"^[HSP][0-9A-Z]{8}$")
    notes: str = ""
    source_ids: list[str] = Field(min_length=1)


class SeedCoverage(Row):
    """Whether an official candidate list was found for a state and office."""

    state_po: str = Field(pattern=STATE_PO_PATTERN)
    office: Office
    status: Literal["official", "not_found"]
    list_url: str | None = None
    notes: str = ""
    source_ids: list[str] = Field(min_length=1)


class FinanceSummary(Row):
    fec_candidate_id: str = Field(pattern=r"^[HSP][0-9A-Z]{8}$")
    candidate_name: str
    state_po: str = Field(pattern=STATE_PO_PATTERN)
    office: Office
    district: int | None = None
    party_code: str | None = None
    incumbent_challenge: Literal["I", "C", "O"] | None = None
    election_year: int | None = None
    candidate_status: str | None = None
    receipts: float | None = None
    disbursements: float | None = None
    cash_on_hand: float | None = None
    coverage_end_date: date | None = None
    source_ids: list[str] = Field(min_length=1)


class Incumbent(Row):
    bioguide_id: str
    name: str
    office: Office
    state_po: str = Field(pattern=STATE_PO_PATTERN)
    district: int | None = None
    senate_class: int | None = None
    term_end: date | None = None
    party: str
    fec_candidate_ids: list[str] = []
    source_ids: list[str] = Field(min_length=1)


class HistoricalResult(Row):
    year: int
    office: Office
    state_po: str = Field(pattern=STATE_PO_PATTERN)
    district: int | None = None
    special: bool = False
    stage: str
    candidate_name: str
    party_label: str
    votes: int | None = None
    total_votes: int | None = None
    writein: bool = False
    source_ids: list[str] = Field(min_length=1)


class StateOffice(Row):
    state_po: str = Field(pattern=STATE_PO_PATTERN)
    state_name: str
    state_fips: str = Field(pattern=r"^[0-9]{2}$")
    office_name: str
    homepage_url: str | None = None
    voter_info_url: str | None = None
    results_url: str | None = None
    results_platform: str | None = None
    general_election_date: date
    notes: str = ""
    source_ids: list[str] = Field(min_length=1)


class BoundarySet(Row):
    boundary_set_id: str = Field(pattern=r"^cd-[0-9]{4}-[a-z]{2}$")
    election_year: int
    state_po: str = Field(pattern=STATE_PO_PATTERN)
    district_count: int
    origin: Literal["census_tiger", "state_official"]
    enacting_instrument: str
    enacting_instrument_url: str | None = None
    display_path: str
    lookup_path: str
    source_ids: list[str] = Field(min_length=1)


class DistrictDemographics(Row):
    state_po: str = Field(pattern=STATE_PO_PATTERN)
    district: int
    boundary_vintage: str
    variable: str
    label: str
    estimate: float | None = None
    margin_of_error: float | None = None
    source_ids: list[str] = Field(min_length=1)


class LiveResultRow(Row):
    """Unofficial results exactly as an official source reports them."""

    race_id: str
    state_po: str = Field(pattern=STATE_PO_PATTERN)
    source_contest_name: str
    candidate_name: str
    party_label: str | None = None
    votes: int
    reporting_text: str | None = None
    precincts_reporting: int | None = None
    precincts_total: int | None = None
    source_updated_at: datetime | None = None
    fetched_at: datetime
    source_ids: list[str] = Field(min_length=1)

    @field_validator("votes")
    @classmethod
    def votes_non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("votes must be non-negative")
        return v
