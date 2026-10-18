"""Static state reference table.

House seat counts are the 2020 Census apportionment (source id
`census_apportionment_2020` in sources/registry.yaml). DC elects one
non-voting delegate, modeled as at-large district 0.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class State:
    po: str
    name: str
    fips: str
    house_seats: int


STATES: tuple[State, ...] = (
    State("AL", "Alabama", "01", 7),
    State("AK", "Alaska", "02", 1),
    State("AZ", "Arizona", "04", 9),
    State("AR", "Arkansas", "05", 4),
    State("CA", "California", "06", 52),
    State("CO", "Colorado", "08", 8),
    State("CT", "Connecticut", "09", 5),
    State("DE", "Delaware", "10", 1),
    State("DC", "District of Columbia", "11", 1),
    State("FL", "Florida", "12", 28),
    State("GA", "Georgia", "13", 14),
    State("HI", "Hawaii", "15", 2),
    State("ID", "Idaho", "16", 2),
    State("IL", "Illinois", "17", 17),
    State("IN", "Indiana", "18", 9),
    State("IA", "Iowa", "19", 4),
    State("KS", "Kansas", "20", 4),
    State("KY", "Kentucky", "21", 6),
    State("LA", "Louisiana", "22", 6),
    State("ME", "Maine", "23", 2),
    State("MD", "Maryland", "24", 8),
    State("MA", "Massachusetts", "25", 9),
    State("MI", "Michigan", "26", 13),
    State("MN", "Minnesota", "27", 8),
    State("MS", "Mississippi", "28", 4),
    State("MO", "Missouri", "29", 8),
    State("MT", "Montana", "30", 2),
    State("NE", "Nebraska", "31", 3),
    State("NV", "Nevada", "32", 4),
    State("NH", "New Hampshire", "33", 2),
    State("NJ", "New Jersey", "34", 12),
    State("NM", "New Mexico", "35", 3),
    State("NY", "New York", "36", 26),
    State("NC", "North Carolina", "37", 14),
    State("ND", "North Dakota", "38", 1),
    State("OH", "Ohio", "39", 15),
    State("OK", "Oklahoma", "40", 5),
    State("OR", "Oregon", "41", 6),
    State("PA", "Pennsylvania", "42", 17),
    State("RI", "Rhode Island", "44", 2),
    State("SC", "South Carolina", "45", 7),
    State("SD", "South Dakota", "46", 1),
    State("TN", "Tennessee", "47", 9),
    State("TX", "Texas", "48", 38),
    State("UT", "Utah", "49", 4),
    State("VT", "Vermont", "50", 1),
    State("VA", "Virginia", "51", 11),
    State("WA", "Washington", "53", 10),
    State("WV", "West Virginia", "54", 2),
    State("WI", "Wisconsin", "55", 8),
    State("WY", "Wyoming", "56", 1),
)

BY_PO = {s.po: s for s in STATES}
BY_FIPS = {s.fips: s for s in STATES}
BY_NAME = {s.name.lower(): s for s in STATES}


def is_at_large(po: str) -> bool:
    return BY_PO[po].house_seats == 1
