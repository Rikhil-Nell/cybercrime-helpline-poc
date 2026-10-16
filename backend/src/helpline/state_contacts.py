"""State/UT allowlist for lookup_state_contact — prevents arbitrary lookups."""

from __future__ import annotations

STATE_NAMES: frozenset[str] = frozenset(
    {
        "ANDAMAN & NICOBAR",
        "ANDHRA PRADESH",
        "ARUNACHAL PRADESH",
        "ASSAM",
        "BIHAR",
        "CHANDIGARH",
        "CHHATTISGARH",
        "DADRA & NAGAR HAVELI AND DAMAN & DIU",
        "DELHI",
        "GOA",
        "GUJARAT",
        "HARYANA",
        "HIMACHAL PRADESH",
        "JAMMU & KASHMIR",
        "JHARKHAND",
        "KARNATAKA",
        "KERALA",
        "LADAKH",
        "LAKSHADWEEP",
        "MADHYA PRADESH",
        "MAHARASHTRA",
        "MANIPUR",
        "MEGHALAYA",
        "MIZORAM",
        "NAGALAND",
        "ODISHA",
        "PUDUCHERRY",
        "PUNJAB",
        "RAJASTHAN",
        "SIKKIM",
        "TAMIL NADU",
        "TELANGANA",
        "TRIPURA",
        "UTTARAKHAND",
        "UTTAR PRADESH",
        "WEST BENGAL",
    }
)

_ALIASES: dict[str, str] = {
    "AP": "ANDHRA PRADESH",
    "UP": "UTTAR PRADESH",
    "MP": "MADHYA PRADESH",
    "MH": "MAHARASHTRA",
    "TN": "TAMIL NADU",
    "TS": "TELANGANA",
    "WB": "WEST BENGAL",
    "JK": "JAMMU & KASHMIR",
    "J&K": "JAMMU & KASHMIR",
    "PONDICHERRY": "PUDUCHERRY",
    "ORISSA": "ODISHA",
    "BENGALURU": "KARNATAKA",
    "BANGALORE": "KARNATAKA",
    "MUMBAI": "MAHARASHTRA",
    "HYDERABAD": "TELANGANA",
    "CHENNAI": "TAMIL NADU",
    "KOLKATA": "WEST BENGAL",
    "DELHI NCR": "DELHI",
    "NCR": "DELHI",
}


def normalize_state(value: str) -> str | None:
    cleaned = " ".join(value.strip().upper().split())
    if not cleaned:
        return None
    if cleaned in STATE_NAMES:
        return cleaned
    if cleaned in _ALIASES:
        return _ALIASES[cleaned]
    for name in STATE_NAMES:
        if cleaned in name or name in cleaned:
            return name
    return None
